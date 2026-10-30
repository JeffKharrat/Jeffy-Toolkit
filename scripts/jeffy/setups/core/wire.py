"""The :class:`Wire` base class: a tiny, tracked node network with one job.

A wire connects things that already exist (controls, joints, attributes,
blendShape weights). It is a setup like the others (tag, owned nodes, panel,
mirror, Node Editor tab, Setups list) with three extras:

* :meth:`Wire.drive_plug` connects a target attribute and remembers its value:
  deleting the wire disconnects it and puts the value back. It refuses a
  target that something else already drives, naming the driver (and saying
  when it is a leftover with no real input).
* :meth:`Wire.note` writes a one-line explanation in each node's Notes.
* The setups its nodes belong to are its *dependencies*: rebuilding one of
  them rebuilds the wire after it; deleting one parks the wire until that
  setup is built again (:mod:`jeffy.setups.core.wires`).

A wire doesn't need a Rig Base: it can connect plain nodes too.
"""

from maya import cmds

from jeffy.core import attributes, naming
from jeffy.setups.core import doctor, notes, scene
from jeffy.setups.core import tag as tag_module
from jeffy.setups.core.base import Setup
from jeffy.setups.core.schema import SetupError


def node_of(name):
    """``node.attr`` -> ``node`` (a node stays a node)."""
    return name.split(".", 1)[0] if name else name


def setup_key(setup):
    return "|".join((setup.TYPE, setup.name or "", setup.side or ""))


class Wire(Setup):
    CATEGORY = "wire"
    HAS_GROUPS = False
    MIRRORABLE = True

    @classmethod
    def rig_lookup_node(cls, slots):
        for slot in cls.SLOTS:
            value = slots.get(slot.key)
            if value:
                return node_of(value[0] if isinstance(value, list) else value)
        return None

    @classmethod
    def side_of(cls, node):
        """``L`` / ``R`` / ``C`` from a node's name."""
        parsed = naming.parse(node_of(node)) if node else {"side": None}
        return parsed.get("side") or naming.side_from_name(node_of(node)) or naming.SIDE_CENTER

    @staticmethod
    def label_of(node):
        """``L_upperArm_CTL`` -> ``upperArm`` (a short name part for the wire's name)."""
        parsed = naming.parse(node_of(node))
        return naming.legalize(parsed.get("name") or naming.strip_namespace(node_of(node))).strip("_")

    @classmethod
    def check_free(cls, plug, label):
        """Raise when ``plug`` is locked or already driven."""
        text = doctor.driver_text(plug)
        if text:
            raise SetupError("%s: %s" % (label, text))
        if cmds.getAttr(plug, lock=True):
            raise SetupError("%s: %s is locked" % (label, plug))

    # ------------------------------------------------------------------
    def _start(self, slots, options, guides, rig):
        super(Wire, self)._start(slots, options, guides, rig)
        owners, keys = [], []
        for slot in self.SLOTS:
            value = slots.get(slot.key)
            for name in (value if isinstance(value, list) else ([value] if value else [])):
                owner = scene.find_setup(node_of(name))
                if owner is None or owner.CATEGORY == "wire" or owner.tag in owners:
                    continue
                owners.append(owner.tag)
                keys.append(setup_key(owner))
        tag_module.set_nodes(self.tag, "depends", owners)
        tag_module.set_data(self.tag, "depends_keys", keys)

    def depends(self):
        """The setups this wire uses (rebuilt with them, parked when one is deleted)."""
        return [scene.wrap(tag) for tag in tag_module.get_nodes(self.tag, "depends") if tag_module.is_tag(tag)]

    def note(self, node, text):
        """Explain ``node`` in its Notes (Attribute Editor > Notes). Returns ``node``."""
        return notes.write(node, text)

    def make(self, node_type, label, text):
        """A utility node named after the wire, with its note."""
        return self.note(self.node(node_type, label), text)

    def drive_plug(self, source, target):
        """Connect ``source`` -> ``target``, remembering ``target``'s value so delete can put it back."""
        self.check_free(target, self.LABEL)
        value = cmds.getAttr(target)
        kind = cmds.getAttr(target, type=True)
        if isinstance(value, list) and value and isinstance(value[0], tuple):
            value = list(value[0])
        records = tag_module.get_data(self.tag, "driven_plugs", []) or []
        records.append({"attr": target.split(".", 1)[1], "value": value, "type": kind})
        tag_module.set_data(self.tag, "driven_plugs", records)
        tag_module.add_nodes(self.tag, "driven_plug_nodes", [node_of(target)])
        cmds.connectAttr(source, target)

    def add_attr(self, node, name, attr_type="float", **kwargs):
        """Add an attribute the wire owns (removed on delete). Returns its plug."""
        existed = cmds.attributeQuery(name, node=node, exists=True)
        plug = attributes.add_attr(node, name, attr_type, **kwargs)
        if not existed:
            added = tag_module.get_data(self.tag, "added_attrs", []) or []
            added.append(name)
            tag_module.set_data(self.tag, "added_attrs", added)
            tag_module.add_nodes(self.tag, "added_attr_nodes", [node])
        return plug

    def driven_targets(self):
        """``node.attr`` of every target this wire drives."""
        records = tag_module.get_data(self.tag, "driven_plugs", []) or []
        nodes = tag_module.get_nodes(self.tag, "driven_plug_nodes", keep_empty=True)
        return ["%s.%s" % (node, record["attr"]) for node, record in zip(nodes, records) if node]

    def graph_nodes(self):
        """``[(node, role)]`` for the Node Editor tab: what it reads, then what it drives."""
        result = []
        for slot in self.SLOTS:
            for name in self.slot_nodes(slot.key):
                result.append((node_of(name), "input"))
        for target in self.driven_targets():
            result.append((node_of(target), "output"))
        return result

    # ------------------------------------------------------------------
    def after_release(self):
        """Disconnect what the wire drove and put the values back, then remove the attributes it added."""
        records = tag_module.get_data(self.tag, "driven_plugs", []) or []
        nodes = tag_module.get_nodes(self.tag, "driven_plug_nodes", keep_empty=True)
        for node, record in zip(nodes, records):
            if not node or not cmds.objExists(node):
                continue
            plug = "%s.%s" % (node, record["attr"])
            if not cmds.objExists(plug):
                continue
            for source in cmds.listConnections(plug, source=True, destination=False, plugs=True) or []:
                cmds.disconnectAttr(source, plug)
            locked = cmds.getAttr(plug, lock=True)
            if locked:
                cmds.setAttr(plug, lock=False)
            try:
                if record.get("type") == "matrix":
                    cmds.setAttr(plug, record["value"], type="matrix")
                elif isinstance(record["value"], list):
                    cmds.setAttr(plug, *record["value"])
                else:
                    cmds.setAttr(plug, record["value"])
            except (RuntimeError, TypeError) as error:
                cmds.warning("[Jeffy] %s: could not restore %s (%s)" % (self.describe(), plug, error))
            if locked:
                cmds.setAttr(plug, lock=True)
        names = tag_module.get_data(self.tag, "added_attrs", []) or []
        for node, name in zip(tag_module.get_nodes(self.tag, "added_attr_nodes", keep_empty=True), names):
            if node and cmds.objExists(node) and cmds.attributeQuery(name, node=node, exists=True):
                cmds.setAttr("%s.%s" % (node, name), lock=False)
                cmds.deleteAttr(node, attribute=name)
