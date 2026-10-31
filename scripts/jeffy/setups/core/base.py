"""The :class:`Setup` base class: build, delete, rebuild and mirror.

Every belt tool is a subclass registered with :func:`scene.register`::

    @scene.register
    class FkChain(Setup):
        TYPE = "fk_chain"
        LABEL = "FK Chain"
        SLOTS = (Slot("start", "Start"), Slot("end", "End", optional=True))
        OPTIONS = (Option("stretch", "Stretch", True), SIZE_OPTION)

        def build_setup(self):
            ctl = self.control("fk1", "shoulderFK", shape="circle", match=joint)
            out = self.add_output("start", ctl.node + ".worldMatrix[0]", joint=joint)
            self.add_anchor(ctl.zero, ctl.node, kind="orient", spaces=("parent", "root", "world"))

The base class does everything around ``build_setup``: checks the slots and
options, finds the rig, creates the setup groups and tag, reads the guides,
drives the bind joints from the outputs, records every created node,
attaches the setup to its parent and builds the mirrored side.
"""

from maya import cmds

from jeffy.core import attributes, matrix, naming, plugins, transform
from jeffy.setups.core import attach, controls, drive, scene, schema, shape_memory
from jeffy.setups.core import edges as edge_tools
from jeffy.setups.core import guides as guides_module
from jeffy.setups.core import tag as tag_module
from jeffy.setups.core.schema import SetupError

#: scene-wide nodes Maya creates on first use and shares between every setup (never owned, never deleted):
#: deleting an IK solver deletes every IK handle using it
SHARED_TYPES = ("ikRPsolver", "ikSCsolver", "ikSplineSolver", "ikSpringSolver", "ikSystem", "hikSolver")
NO_RIG_MESSAGE = "No Rig Base found for these joints. Build a Rig Base first (BUILD > Rig Base)."


def _notify(hook, setup):
    """Tell the Node Editor tabs a setup was built / is being deleted (never breaks a build)."""
    try:
        from jeffy.ui.setup_belt import node_tabs
    except ImportError:  # no Qt (batch tools): nothing to show
        return
    try:
        getattr(node_tabs, hook)(setup)
    except Exception as error:  # a UI problem must not stop building or deleting
        cmds.warning("[Jeffy] Node Editor tab for %s: %s" % (setup.describe(), error))


def _shared(node):
    return cmds.objExists(node) and cmds.nodeType(node) in SHARED_TYPES


class Setup(object):
    TYPE = "setup"
    LABEL = "Setup"
    #: ``base`` (rig base), ``build`` (builds on joints) or ``layer`` (builds on a setup)
    CATEGORY = "build"
    #: position in the belt (inside its category)
    ORDER = 100
    DESCRIPTION = ""
    SLOTS = ()
    OPTIONS = ()
    #: option keys of earlier versions: dropped (not an error) when a stored setup is rebuilt
    RETIRED_OPTIONS = ()
    #: guide keys shown by Preview
    GUIDES = ()
    MIRRORABLE = True
    #: the bind joints may scale along the bone when ``game_safe`` is off
    SCALE_STRETCH = False
    VERSION = 1
    #: layers: setup types they can be stacked on (empty = any)
    BASE_TYPES = ()
    HAS_GROUPS = True

    def __init__(self, tag):
        if not tag_module.is_tag(tag):
            raise SetupError("%s is not a setup" % tag)
        self.tag = tag
        self._drives = []
        self._options = None
        self._guides = None
        self._slots = None
        self._keep = []

    def __repr__(self):
        return "%s(%r)" % (type(self).__name__, self.tag)

    def __eq__(self, other):
        return isinstance(other, Setup) and other.tag == self.tag

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.tag)

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    @classmethod
    def option_schema(cls):
        options = list(cls.OPTIONS)
        if cls.MIRRORABLE:
            options.append(schema.MIRROR_OPTION)
        return options

    @classmethod
    def slot_schema(cls, key):
        for slot in cls.SLOTS:
            if slot.key == key:
                return slot
        return None

    @classmethod
    def split_values(cls, values):
        slot_keys = set(slot.key for slot in cls.SLOTS)
        slots = dict((k, v) for k, v in values.items() if k in slot_keys)
        options = dict((k, v) for k, v in values.items() if k not in slot_keys)
        return slots, options

    @classmethod
    def resolve_slots(cls, values):
        values = dict(values or {})
        known = set(slot.key for slot in cls.SLOTS)
        unknown = sorted(k for k in values if k not in known)
        if unknown:
            raise SetupError("Unknown slot(s): %s" % ", ".join(unknown))
        result = {}
        for slot in cls.SLOTS:
            value = slot.normalize(values.get(slot.key))
            if slot.components:
                result[slot.key] = cls._resolve_edges(slot, value)
                continue
            if slot.plugs:
                plugs = cls._resolve_plugs(slot, value)
                result[slot.key] = plugs if slot.multi else (plugs[0] if plugs else None)
                continue
            names = value if slot.multi else ([value] if value else [])
            resolved = []
            for name in names:
                matches = cmds.ls(name) or []
                if not matches:
                    raise SetupError("%s: '%s' does not exist" % (slot.label, name))
                if len(matches) > 1:
                    raise SetupError("%s: several nodes are named '%s', give them unique names" % (slot.label, name))
                if slot.joints_only and cmds.nodeType(matches[0]) != "joint":
                    raise SetupError("%s: '%s' is not a joint" % (slot.label, name))
                resolved.append(matches[0])
            if not resolved and not slot.optional:
                raise SetupError("Fill the '%s' slot" % slot.label)
            result[slot.key] = resolved if slot.multi else (resolved[0] if resolved else None)
        return result

    @staticmethod
    def _resolve_edges(slot, value):
        if not value:
            if not slot.optional:
                raise SetupError("Fill the '%s' slot (select the edges, then <)" % slot.label)
            return []
        if not edge_tools.is_edges(value):
            raise SetupError("%s: give mesh edges (%s)" % (slot.label, ", ".join(value)))
        edge_tools.mesh_of(value)  # one mesh only
        return edge_tools.compact(value)

    @staticmethod
    def _resolve_plugs(slot, value):
        names = value if isinstance(value, list) else ([value] if value else [])
        if not names:
            if not slot.optional:
                raise SetupError("Fill the '%s' slot (select the node, highlight the attribute in the Channel Box, "
                                 "then <)" % slot.label)
            return []
        result = []
        for name in names:
            node, _, attr = name.partition(".")
            if not attr:
                raise SetupError("%s: give an attribute as node.attribute (%s)" % (slot.label, name))
            matches = cmds.ls(node) or []
            if not matches:
                raise SetupError("%s: '%s' does not exist" % (slot.label, node))
            if len(matches) > 1:
                raise SetupError("%s: several nodes are named '%s', give them unique names" % (slot.label, node))
            plug = "%s.%s" % (matches[0], attr)
            if not cmds.objExists(plug):
                raise SetupError("%s: %s has no attribute '%s'" % (slot.label, matches[0], attr))
            result.append(plug)
        return result

    @classmethod
    def first_joint(cls, slots):
        for slot in cls.SLOTS:
            value = slots.get(slot.key)
            if slot.joints_only and value:
                return value[0] if slot.multi else value
        return None

    @classmethod
    def resolve_name_side(cls, slots, options, name=None, side=None):
        first = cls.first_joint(slots)
        parsed = naming.parse(first) if first else {"side": None, "name": None}
        if not side or side == "auto":
            side = parsed["side"] or (naming.side_from_name(first) if first else None) or "C"
        if not name:
            name = cls.default_name(slots, options) or parsed["name"] or cls.TYPE
        name = naming.legalize(str(name).strip()).strip("_")
        if not name:
            raise SetupError("Give the setup a name")
        return name, side

    @classmethod
    def default_name(cls, slots, options):
        return None

    # ------------------------------------------------------------------
    # Hooks for tools
    # ------------------------------------------------------------------
    @classmethod
    def validate(cls, slots, options):
        """Extra checks on the slots (chain relationships...). Raise SetupError."""

    @classmethod
    def driven_joints(cls, slots):
        """Bind joints the tool will drive (checked to be free before building)."""
        return []

    @classmethod
    def default_guides(cls, slots, options, side):
        """``{guide key: world matrix or position}`` used by Preview and Build."""
        return {}

    @classmethod
    def rig_lookup_node(cls, slots):
        """Node used to find the rig base (the first joint by default)."""
        return cls.first_joint(slots)

    def build_setup(self):
        raise NotImplementedError

    def before_delete(self):
        """Called before the setup's nodes are deleted."""

    def after_release(self):
        """Called once the bind joints are back to their rest pose, before the nodes are deleted."""

    def attach_joint(self):
        """Joint whose parents decide what the setup follows (``parent`` space)."""
        first = self.first_slot_joint()
        if not first or not cmds.objExists(first):
            return None
        return (cmds.listRelatives(first, parent=True, fullPath=True) or [None])[0]

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------
    @classmethod
    def build(cls, name=None, side=None, guides=None, rig=None, **values):
        """Python API: slots and options as keyword arguments.

        ``ikfk_limb.IkFkLimb.build(start="L_shoulder_JNT", mid=..., end=..., stretch=True)``
        """
        slots, options = cls.split_values(values)
        return cls.create(slots, options, name=name, side=side, guides=guides, rig=rig)

    @classmethod
    def create(cls, slots=None, options=None, name=None, side=None, guides=None, rig=None, _mirror_of=None):
        plugins.ensure_matrix_plugins()
        slots = cls.resolve_slots(slots)
        options = schema.resolve_options(cls.option_schema(), options, cls.RETIRED_OPTIONS)
        name, side = cls.resolve_name_side(slots, options, name, side)
        cls.validate(slots, options)
        cls._check_joints_free(slots)
        cls._check_name_free(name, side)

        rig_setup = rig
        if cls.CATEGORY != "base" and rig_setup is None:
            rig_setup = scene.find_rig(cls.rig_lookup_node(slots))
            if rig_setup is None and cls.CATEGORY != "wire":  # wires also connect plain nodes, outside any rig
                raise SetupError(NO_RIG_MESSAGE)

        guide_values = cls.collect_guides(slots, options, name, side, guides)
        before = set(cmds.ls(uuid=True) or [])
        setup_tag = tag_module.create(cls.TYPE, name, side, cls.VERSION)
        setup = cls(setup_tag)
        try:
            setup._start(slots, options, guide_values, rig_setup)
            setup.build_setup()
            setup._finish(before)
        except Exception:
            setup._abort(before)
            raise
        guides_module.delete(cls.TYPE, name, side)
        attach.refresh_rig(rig_setup if rig_setup is not None else setup)

        if _mirror_of is not None:
            tag_module.set_node(setup.tag, "mirror", _mirror_of.tag)
            tag_module.set_node(_mirror_of.tag, "mirror", setup.tag)
        elif cls.MIRRORABLE and options.get("mirror") and side in (naming.SIDE_LEFT, naming.SIDE_RIGHT):
            setup._build_mirror(rig_setup)
        # last: the Node Editor adds nodes created while a tab is active to that tab
        _notify("on_built", setup)
        if _mirror_of is None and cls.CATEGORY != "wire":  # parked wires whose setups are all back
            from jeffy.setups.core import wires

            wires.restore_parked()
        return setup

    @classmethod
    def collect_guides(cls, slots, options, name, side, guides=None):
        if not cls.GUIDES:
            return {}
        values = dict(cls.default_guides(slots, options, side))
        values.update(guides_module.read(cls.TYPE, name, side))
        if guides:
            values.update(guides)
        return values

    @classmethod
    def preview(cls, slots=None, options=None, name=None, side=None, guides=None):
        """Create the guide locators (Preview button). Returns ``{key: locator}``."""
        if not cls.GUIDES:
            raise SetupError("%s has no guides to preview" % cls.LABEL)
        slots = cls.resolve_slots(slots)
        options = schema.resolve_options(cls.option_schema(), options, cls.RETIRED_OPTIONS)
        name, side = cls.resolve_name_side(slots, options, name, side)
        cls.validate(slots, options)
        values = cls.collect_guides(slots, options, name, side, guides)
        return guides_module.create(cls.TYPE, name, side, values, size=cls.guide_size(slots, options))

    @classmethod
    def guide_size(cls, slots, options):
        return 1.0

    @classmethod
    def _check_joints_free(cls, slots):
        for joint in cls.driven_joints(slots):
            owner = scene.setup_driving(joint)
            if owner is not None:
                raise SetupError("%s is already driven by %s. Delete or rebuild that setup first."
                                 % (naming.short_name(joint), owner.describe()))
            plugs = drive.incoming(joint)
            if plugs:
                raise SetupError("%s is already driven by %s. Disconnect it first (keys, constraints or "
                                 "another rig)." % (naming.short_name(joint), plugs[0]))

    @classmethod
    def _check_name_free(cls, name, side):
        for other in scene.all_setups():
            if other.name == name and other.side == side:
                raise SetupError("A setup named %s already exists (%s). Choose another name or rebuild it."
                                 % (naming.compose(name, side), other.LABEL))

    def _start(self, slots, options, guides, rig):
        self._slots = slots
        self._options = options
        self._guides = dict((key, list(value)) for key, value in guides.items())
        tag = self.tag
        tag_module.set_data(tag, "options", options)
        tag_module.set_data(tag, "guides", self._guides)
        names = {}
        for slot in self.SLOTS:
            value = slots.get(slot.key)
            nodes = value if slot.multi else ([value] if value else [])
            if slot.components:  # the mesh (rename proof), the edge names go in "slots"
                nodes = [edge_tools.mesh_of(value)[0]] if value else []
            elif slot.plugs:  # their nodes (rename proof), the "node.attr" names go in "slots"
                nodes = [plug.split(".", 1)[0] for plug in nodes]
            tag_module.set_nodes(tag, "slot_" + slot.key, nodes)
            names[slot.key] = value
        tag_module.set_data(tag, "slots", names)
        if rig is not None and self.CATEGORY != "base":
            tag_module.set_node(tag, "rig", rig.tag)
        if self.CATEGORY == "layer":
            base = self.find_base(slots)
            tag_module.set_node(tag, "base", base.tag)
            tag_module.add_nodes(base.tag, "layers", [tag])
        if self.HAS_GROUPS and self.CATEGORY != "base":
            ctl_group = self._make_group("Controls", rig.rig_group("controls"))
            sys_group = self._make_group("Systems", rig.rig_group("systems"))
            tag_module.set_node(tag, "controls_group", ctl_group)
            tag_module.set_node(tag, "systems_group", sys_group)

    def _make_group(self, label, parent):
        group = cmds.createNode("transform", name=naming.unique_name(naming.compose(self.name + label, self.side,
                                                                                    "group")), skipSelect=True)
        if parent:
            group = cmds.parent(group, parent, relative=True)[0]
        tag_module.link(self.tag, group)
        return group

    def keep(self, nodes):
        """Nodes created by the build that must survive its delete (deformers on the user's meshes...).

        The tool removes what it should in :meth:`before_delete`.
        """
        self._keep.extend(node for node in nodes if node)

    def on_abort(self):
        """Called when the build fails, before its new nodes are deleted (undo what :meth:`keep` protects)."""

    def _finish(self, before):
        # first: replaced curve shapes are new nodes the setup must own
        shape_memory.restore(self)
        outputs = self.outputs
        driven, rest = [], []
        scale = self.scale_stretch()
        for joint, output, child_key in self._drives:
            child = outputs.get(child_key) if child_key else None
            _created, joint_rest = drive.drive(joint, output, child_output=child,
                                               scale_stretch=bool(scale and child))
            driven.append(joint)
            rest.append(joint_rest)
        tag_module.set_nodes(self.tag, "driven", driven)
        tag_module.set_data(self.tag, "rest", rest)
        kept = set(cmds.ls(self._keep, long=True) or []) if self._keep else set()
        owned = [node for node in self._new_nodes(before) if (cmds.ls(node, long=True) or [node])[0] not in kept]
        tag_module.set_nodes(self.tag, "owned", owned)
        tag_module.set_nodes(self.tag, "kept", self._keep)

    def _new_nodes(self, before):
        new = [uuid for uuid in (cmds.ls(uuid=True) or []) if uuid not in before]
        if not new:  # cmds.ls([]) would list the whole scene
            return []
        return [node for node in (cmds.ls(new) or []) if node != self.tag and not _shared(node)]

    def _abort(self, before):
        """Undo a failed build: release joints and delete what was created."""
        try:
            self.on_abort()
        except Exception as error:  # keep cleaning up
            cmds.warning("[Jeffy] %s: %s" % (self.LABEL, error))
        kept = set(cmds.ls(self._keep, long=True) or []) if self._keep else set()
        for joint, _output, _child in self._drives:
            if cmds.objExists(joint) and drive.incoming(joint):
                drive.release(joint, None)
        for node in self._new_nodes(before):
            if (cmds.ls(node, long=True) or [node])[0] in kept:
                continue
            if cmds.objExists(node) and not cmds.lockNode(node, query=True, lock=True)[0]:
                try:
                    cmds.delete(node)
                except (RuntimeError, ValueError):
                    pass
        if cmds.objExists(self.tag):
            cmds.delete(self.tag)

    def _build_mirror(self, rig):
        slots = {}
        for slot in self.SLOTS:
            value = self._slots.get(slot.key)
            names = value if slot.multi else ([value] if value else [])
            if slot.components:
                try:
                    slots[slot.key] = edge_tools.mirror(names) if names else []
                except SetupError as error:
                    cmds.warning("[Jeffy] %s: %s, the other side was not built" % (self.LABEL, error))
                    return None
                continue
            attrs = None
            if slot.plugs:  # mirror the node, keep the attribute
                attrs = [name.split(".", 1)[1] for name in names]
                names = [name.split(".", 1)[0] for name in names]
            mirrored = []
            for node in names:
                short = naming.strip_namespace(node)
                # centre nodes (no L / R token) stay the same on both sides
                other = naming.find_mirror_node(node) if naming.mirror_name(short) != short else node
                if not other:
                    cmds.warning("[Jeffy] %s: no mirror found for %s (expected %s), the other side was not built"
                                 % (self.LABEL, node, naming.mirror_name(naming.strip_namespace(node))))
                    return None
                mirrored.append(other)
            if attrs is not None:
                mirrored = ["%s.%s" % (node, attr) for node, attr in zip(mirrored, attrs)]
            slots[slot.key] = mirrored if slot.multi else (mirrored[0] if mirrored else None)
        options = dict(self._options)
        options["mirror"] = False
        guides = dict((key, guides_module.mirror(value)) for key, value in self._guides.items())
        return type(self).create(slots, self.mirror_options(options), name=self.name,
                                 side=naming.mirror_side(self.side), guides=guides, rig=rig, _mirror_of=self)

    def mirror_options(self, options):
        """Options of the mirrored side (tools can flip side dependent values)."""
        return options

    # ------------------------------------------------------------------
    # Build helpers (call them from build_setup)
    # ------------------------------------------------------------------
    def control(self, key, label, shape="circle", size=1.0, axis="x", parent=None, match=None, world_matrix=None,
                position=None, lock=("v",), secondary=False, color=None, role=None, side=None):
        return controls.create(self, key, label, shape=shape, size=size, axis=axis, parent=parent, match=match,
                               world_matrix=world_matrix, position=position, lock=lock, secondary=secondary,
                               color=color, role=role, side=side)

    def register_control(self, key, node):
        tag_module.add_nodes(self.tag, "controls", [node])

    def group(self, label, parent=None, match=None, world_matrix=None, visible=True):
        """A transform in the setup's systems group (or under ``parent``)."""
        node = cmds.createNode("transform", name=naming.unique_name(naming.compose(self.name + label, self.side,
                                                                                   "group")), skipSelect=True)
        parent = parent or self.systems_group
        if parent:
            node = cmds.parent(node, parent, relative=True)[0]
        if match:
            cmds.matchTransform(node, match, position=True, rotation=True)
        elif world_matrix is not None:
            matrix.set_world_matrix(node, world_matrix, scale=False)
        if not visible:
            cmds.setAttr(node + ".visibility", 0)
        return node

    def node(self, node_type, label, suffix="UTL"):
        """A utility node named after the setup."""
        from jeffy.core import nodes as node_tools

        return cmds.createNode(node_tools.node_type(node_type),
                               name=naming.unique_name(naming.compose(self.name + label, self.side, suffix)),
                               skipSelect=True)

    @property
    def outputs_group(self):
        group = tag_module.get_node(self.tag, "outputs_group")
        if not group:
            group = self.group("Outputs", visible=True)
            tag_module.set_node(self.tag, "outputs_group", group)
        return group

    def add_output(self, key, matrix_plug, joint=None, stretch_child=None, label=None):
        """Output transform whose world matrix is ``matrix_plug``.

        :param joint: bind joint driven by this output
        :param stretch_child: key of the next output in the chain (bone length
            for scale stretch)
        :param label: name of the output (default: setup name + key)
        """
        label = label or (self.name + key[0].upper() + key[1:])
        output = cmds.createNode("transform", name=naming.unique_name(naming.compose(label, self.side, "OUT")),
                                 skipSelect=True)
        output = cmds.parent(output, self.outputs_group, relative=True)[0]
        mm = cmds.createNode("multMatrix", name=naming.unique_name(output + "_MM"), skipSelect=True)
        cmds.connectAttr(matrix_plug, mm + ".matrixIn[0]")
        cmds.connectAttr(self.outputs_group + ".worldInverseMatrix[0]", mm + ".matrixIn[1]")
        cmds.connectAttr(mm + ".matrixSum", output + ".offsetParentMatrix")
        attributes.set_string(output, controls.KEY_ATTR, key)
        tag_module.link(self.tag, output)
        controls.store_rest(output)
        tag_module.add_nodes(self.tag, "outputs", [output])
        if joint:
            attributes.add_attr(output, scene.OUTPUT_JOINT_ATTR, "message")
            cmds.connectAttr(joint + ".message", "%s.%s" % (output, scene.OUTPUT_JOINT_ATTR), force=True)
            self._drives.append((joint, output, stretch_child))
        return output

    def add_anchor(self, zero, control=None, kind="parent", spaces=("parent",), default=None, attr="space"):
        """Make ``zero`` follow spaces resolved by :mod:`attach` (see there)."""
        if kind not in attach.KINDS:
            raise ValueError("Unknown anchor kind %r" % kind)
        definitions = tag_module.get_data(self.tag, "anchors", [])
        definitions.append({"kind": kind, "spaces": list(spaces), "default": default or spaces[0],
                            "attr": attr if control else None, "rest": matrix.get_world_matrix(zero)})
        tag_module.set_data(self.tag, "anchors", definitions)
        tag_module.add_nodes(self.tag, "anchor_zero", [zero])
        tag_module.add_nodes(self.tag, "anchor_control", [control or zero])

    def follow(self, zero, target, label="follow"):
        """``zero`` follows ``target`` with its current offset (internal, not refreshed)."""
        offset = matrix.offset_matrix(zero, target)
        transform.reset(zero)
        mm = cmds.createNode("multMatrix", name=naming.unique_name("%s_%s_MM" % (naming.strip_namespace(zero),
                                                                                 label)), skipSelect=True)
        matrix.set_matrix_attr(mm + ".matrixIn[0]", offset)
        cmds.connectAttr(target + ".worldMatrix[0]", mm + ".matrixIn[1]")
        parent_inverse = matrix.parent_inverse_plug(zero)
        if parent_inverse:
            cmds.connectAttr(parent_inverse, mm + ".matrixIn[2]")
        cmds.connectAttr(mm + ".matrixSum", zero + ".offsetParentMatrix", force=True)
        return mm

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------
    @property
    def name(self):
        return tag_module.name_of(self.tag)

    @property
    def side(self):
        return tag_module.side_of(self.tag)

    @property
    def options(self):
        if self._options is not None:
            return self._options
        stored = tag_module.get_data(self.tag, "options", {}) or {}
        defaults = dict((option.key, option.default) for option in self.option_schema())
        defaults.update(stored)
        return defaults

    @property
    def guides(self):
        if self._guides is not None:
            return self._guides
        return tag_module.get_data(self.tag, "guides", {}) or {}

    def option(self, key):
        return self.options.get(key)

    def slot_nodes(self, key):
        slot = self.slot_schema(key)
        if slot is not None and slot.named:
            return self._slot_names(key)
        if self._slots is not None:
            value = self._slots.get(key)
            if value is None:
                return []
            return list(value) if isinstance(value, list) else [value]
        nodes = tag_module.get_nodes(self.tag, "slot_" + key)
        if nodes:
            return nodes
        stored = (tag_module.get_data(self.tag, "slots", {}) or {}).get(key)
        names = stored if isinstance(stored, list) else ([stored] if stored else [])
        return [name for name in names if cmds.objExists(name)]

    def _slot_names(self, key):
        """Names of an edges / attributes slot (``node.part``), following a rename of their nodes."""
        if self._slots is not None:
            value = self._slots.get(key)
            return list(value) if isinstance(value, list) else ([value] if value else [])
        stored = (tag_module.get_data(self.tag, "slots", {}) or {}).get(key) or []
        stored = stored if isinstance(stored, list) else [stored]
        nodes = tag_module.get_nodes(self.tag, "slot_" + key, keep_empty=True)
        result = []
        for index, name in enumerate(stored):
            if "." not in name:
                continue
            node = nodes[index] if index < len(nodes) else (nodes[0] if len(nodes) == 1 else None)
            if node:  # renamed nodes keep working
                name = "%s.%s" % (naming.short_name(node), name.split(".", 1)[1])
            result.append(name)
        return result

    def slot_node(self, key):
        nodes = self.slot_nodes(key)
        return nodes[0] if nodes else None

    def first_slot_joint(self):
        for slot in self.SLOTS:
            if slot.joints_only:
                nodes = self.slot_nodes(slot.key)
                if nodes:
                    return nodes[0]
        return None

    @property
    def controls_group(self):
        return tag_module.get_node(self.tag, "controls_group")

    @property
    def systems_group(self):
        return tag_module.get_node(self.tag, "systems_group")

    @property
    def rig(self):
        if self.CATEGORY == "base":
            return self
        node = tag_module.get_node(self.tag, "rig")
        return scene.wrap(node) if node else None

    @property
    def controls(self):
        """``{key: control}``."""
        return dict((controls.key_of(node) or node, node) for node in tag_module.get_nodes(self.tag, "controls"))

    @property
    def outputs(self):
        """``{key: output transform}``."""
        return dict((controls.key_of(node) or node, node) for node in tag_module.get_nodes(self.tag, "outputs"))

    @property
    def driven(self):
        return tag_module.get_nodes(self.tag, "driven")

    @property
    def base(self):
        node = tag_module.get_node(self.tag, "base")
        return scene.wrap(node) if node else None

    def layers(self):
        return [scene.wrap(node) for node in tag_module.get_nodes(self.tag, "layers") if tag_module.is_tag(node)]

    def all_layers(self):
        """Layers stacked on this setup, recursively, in build order."""
        result = []
        for layer in self.layers():
            result.append(layer)
            result.extend(layer.all_layers())
        return result

    def family_tags(self):
        return [self.tag] + [layer.tag for layer in self.all_layers()]

    @property
    def mirror(self):
        node = tag_module.get_node(self.tag, "mirror")
        return scene.wrap(node) if node else None

    def is_mirror_secondary(self):
        partner = self.mirror
        return bool(partner) and not self.options.get("mirror") and bool(partner.options.get("mirror"))

    def mirror_primary(self):
        return self.mirror if self.is_mirror_secondary() else self

    def anchors(self):
        """``[(definition, zero, control)]``."""
        definitions = tag_module.get_data(self.tag, "anchors", []) or []
        zeros = tag_module.get_nodes(self.tag, "anchor_zero", keep_empty=True)
        ctls = tag_module.get_nodes(self.tag, "anchor_control", keep_empty=True)
        result = []
        for index, definition in enumerate(definitions):
            zero = zeros[index] if index < len(zeros) else None
            ctl = ctls[index] if (definition.get("attr") and index < len(ctls)) else None
            result.append((definition, zero, ctl))
        return result

    def set_anchor_custom(self, index, custom):
        definitions = tag_module.get_data(self.tag, "anchors", []) or []
        definitions[index]["custom"] = custom
        tag_module.set_data(self.tag, "anchors", definitions)

    def anchor_index(self, control):
        for index, (_definition, zero, ctl) in enumerate(self.anchors()):
            if control in (ctl, zero) and ctl:
                return index
        return None

    def scale_stretch(self):
        return self.SCALE_STRETCH and not self.options.get("game_safe", True)

    def describe(self):
        return "%s (%s)" % (naming.compose(self.name, self.side), self.LABEL)

    def spec(self):
        """Everything needed to build this setup again."""
        slots = {}
        for slot in self.SLOTS:
            nodes = self.slot_nodes(slot.key)
            if not slot.named:
                nodes = [naming.short_name(node) for node in nodes]
            slots[slot.key] = nodes if slot.multi else (nodes[0] if nodes else None)
        return {"type": self.TYPE, "name": self.name, "side": self.side, "slots": slots,
                "options": dict(self.options), "guides": dict(self.guides)}

    @classmethod
    def find_base(cls, slots):
        """Base setup of a layer (from its first node slot)."""
        node = None
        for slot in cls.SLOTS:
            value = slots.get(slot.key)
            if value:
                node = value[0] if slot.multi else value
                break
        base = scene.find_setup(node) if node else None
        if base is None:
            raise SetupError("%s is not part of a setup" % (node or "The base slot"))
        if cls.BASE_TYPES and base.TYPE not in cls.BASE_TYPES:
            allowed = ", ".join(scene.tool_class(t).LABEL for t in cls.BASE_TYPES if scene.tool_class(t))
            raise SetupError("%s builds on: %s. %s is a %s." % (cls.LABEL, allowed, base.describe(), base.LABEL))
        return base

    # ------------------------------------------------------------------
    # Delete / rebuild
    # ------------------------------------------------------------------
    def delete(self, layers=True, mirror=False):
        """Delete the setup (and the layers stacked on it). The skeleton goes back to its rest pose."""
        if not cmds.objExists(self.tag):
            return
        partner = self.mirror if mirror else None
        rig = None if self.CATEGORY == "base" else self.rig
        if self.CATEGORY != "wire":  # wires using this setup are remembered, and come back with it
            from jeffy.setups.core import wires

            family = self.family_tags() + (partner.family_tags() if partner is not None else [])
            wires.park_dependents(family)
        if self.CATEGORY == "base":
            for member in reversed(scene.all_setups(rig=self)):
                if member.tag != self.tag and cmds.objExists(member.tag):
                    member.delete(layers=True)
        if layers:
            for layer in reversed(self.all_layers()):
                if cmds.objExists(layer.tag):
                    layer._delete_self()
        self._delete_self()
        if rig is not None and cmds.objExists(rig.tag):
            attach.refresh_rig(rig)
        if partner is not None and cmds.objExists(partner.tag):
            partner.delete(layers=layers, mirror=False)

    def _delete_self(self):
        _notify("on_deleted", self)
        try:  # the hand edited control shapes come back at the next build
            shape_memory.capture(self)
        except Exception as error:  # never stops a delete
            cmds.warning("[Jeffy] %s: control shapes not remembered (%s)" % (self.describe(), error))
        self.before_delete()
        attach.clear(self)
        driven = tag_module.get_nodes(self.tag, "driven", keep_empty=True)
        rest = tag_module.get_data(self.tag, "rest", []) or []
        for joint, joint_rest in zip(driven, rest):
            if joint:
                drive.release(joint, joint_rest)
        self.after_release()
        owned = tag_module.get_nodes(self.tag, "owned")
        self._rescue_children(owned)
        # utility (DG) nodes first: nothing is left to re-evaluate when the surfaces / curves go
        owned = [node for node in owned if cmds.objExists(node) and not cmds.objectType(node, isAType="dagNode")] + \
            [node for node in owned if cmds.objExists(node) and cmds.objectType(node, isAType="dagNode")]
        for node in owned:
            if cmds.objExists(node) and not _shared(node):  # older scenes may list shared solvers
                try:
                    cmds.delete(node)
                except (RuntimeError, ValueError):
                    pass
        if cmds.objExists(self.tag):
            cmds.delete(self.tag)

    @staticmethod
    def _rescue_children(owned):
        """Move nodes the user parented under the setup's groups out of them."""
        owned_long = set(cmds.ls(owned, long=True) or [])
        rescued = []
        for node in owned_long:
            if not cmds.objExists(node) or not cmds.objectType(node, isAType="transform"):
                continue
            for child in cmds.listRelatives(node, children=True, type="transform", fullPath=True) or []:
                if child not in owned_long:
                    rescued.append(cmds.parent(child, world=True)[0])
        if rescued:
            cmds.warning("[Jeffy] moved to the world (they were inside the deleted setup): %s"
                         % ", ".join(naming.short_name(n) for n in rescued))
        return rescued

    def rebuild(self, options=None, slots=None, guides=None, name=None, side=None):
        """Delete and build again with new values. Layers on top are rebuilt too."""
        primary = self.mirror_primary()
        spec = primary.spec()
        if options:
            spec["options"].update(options)
            if primary is not self:
                spec["options"]["mirror"] = True
        if primary is self:
            if slots:
                spec["slots"].update(slots)
            if guides:
                spec["guides"].update(guides)
            spec["name"] = name or spec["name"]
            spec["side"] = side or spec["side"]
        spec["guides"].update(guides_module.read(primary.TYPE, primary.name, primary.side))

        layer_specs = []
        owners = [primary] + ([primary.mirror] if primary.mirror else [])
        for owner in owners:
            for layer in owner.all_layers():
                if not layer.is_mirror_secondary():
                    layer_specs.append(layer.spec())
        wire_specs = []
        if primary.CATEGORY != "wire":  # wires using the family are rebuilt after it (deleted first: they restore)
            from jeffy.setups.core import wires

            family = [tag for owner in owners for tag in owner.family_tags()]
            wire_specs = wires.take_dependents(family)
        was_secondary = primary is not self
        old_name, old_side, had_mirror = primary.name, primary.side, primary.mirror is not None
        primary.delete(layers=True, mirror=True)
        if (spec["name"], spec["side"]) != (old_name, old_side):  # the remembered shapes follow the new name
            shape_memory.rename(primary.TYPE, old_name, old_side, spec["name"], spec["side"])
            if had_mirror:
                shape_memory.rename(primary.TYPE, old_name, naming.mirror_side(old_side), spec["name"],
                                    naming.mirror_side(spec["side"]))
        cls = type(primary)
        new = cls.create(spec["slots"], spec["options"], name=spec["name"], side=spec["side"], guides=spec["guides"])
        errors = []
        for layer_spec in layer_specs:
            layer_cls = scene.tool_class(layer_spec["type"])
            try:
                layer_cls.create(layer_spec["slots"], layer_spec["options"], name=layer_spec["name"],
                                 side=layer_spec["side"], guides=layer_spec["guides"])
            except SetupError as error:
                errors.append("%s: %s" % (layer_spec["name"], error))
        if errors:
            cmds.warning("[Jeffy] some layers could not be rebuilt: %s" % "; ".join(errors))
        if wire_specs:
            wires.rebuild_specs(wire_specs)
        if was_secondary and new.mirror is not None:
            return new.mirror
        return new
