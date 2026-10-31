"""Slot and option definitions shared by every setup tool.

A tool declares what it needs as :class:`Slot` objects (joints or nodes the
user picks) and :class:`Option` objects (checkboxes, choices, numbers). The
belt window builds each tool's panel from these lists, and the Python API
validates its arguments with them, so both always agree.

This module is pure Python (no Maya calls) so it can be unit tested.
"""

from jeffy.core.decorators import ToolError

#: slot kinds
JOINT = "joint"
JOINTS = "joints"
NODE = "node"
NODES = "nodes"
EDGES = "edges"  # mesh edges (components), kept as names: ``face_GEO.e[120:131]``
ATTRIBUTE = "attribute"  # a node's attribute (plug), kept as a name: ``L_mouth_CTL.translateY``
ATTRIBUTES = "attributes"
SLOT_KINDS = (JOINT, JOINTS, NODE, NODES, EDGES, ATTRIBUTE, ATTRIBUTES)


class SetupError(ToolError):
    """A user error while building, editing or deleting a setup.

    Shown as a short warning (no traceback) by the belt and the menu actions.
    """


class Slot(object):
    """A joint (or node) the user gives to a tool.

    :param key: argument name in the Python API (``start``, ``end``...)
    :param label: text shown in the panel (``Start``, ``Mid``...)
    :param kind: ``joint``, ``joints`` (ordered list), ``node``, ``nodes``, ``edges``, ``attribute`` or
        ``attributes``
    :param optional: the tool can build without it
    :param tip: tooltip in the panel
    """

    def __init__(self, key, label, kind=JOINT, optional=False, tip=""):
        if kind not in SLOT_KINDS:
            raise ValueError("Unknown slot kind %r" % kind)
        self.key = key
        self.label = label
        self.kind = kind
        self.optional = optional
        self.tip = tip

    @property
    def multi(self):
        return self.kind in (JOINTS, NODES, EDGES, ATTRIBUTES)

    @property
    def components(self):
        """Mesh components (edges), not nodes."""
        return self.kind == EDGES

    @property
    def plugs(self):
        """Attributes (``node.attr``), not nodes."""
        return self.kind in (ATTRIBUTE, ATTRIBUTES)

    @property
    def named(self):
        """Kept by name (edges, attributes): the tag stores their node for renames, the names as data."""
        return self.components or self.plugs

    @property
    def joints_only(self):
        return self.kind in (JOINT, JOINTS)

    def normalize(self, value):
        """``value`` as a list of names (multi slots) or a name / ``None``."""
        if self.multi:
            if value is None or value == "":
                return []
            if isinstance(value, str):
                value = [part.strip() for part in value.replace(";", ",").split(",")]
            return [str(item) for item in value if item]
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        return str(value) if value else None

    def is_empty(self, value):
        return not value

    def __repr__(self):
        return "Slot(%r, %r)" % (self.key, self.kind)


class Option(object):
    """A setting of a tool.

    The type comes from ``default``: ``bool`` (checkbox), ``int`` / ``float``
    (spin box), ``str`` (text field). With ``choices`` it is a combo box.
    """

    def __init__(self, key, label, default, choices=None, minimum=None, maximum=None, decimals=2, step=None,
                 tip=""):
        self.key = key
        self.label = label
        self.default = default
        self.choices = tuple(choices) if choices else None
        self.minimum = minimum
        self.maximum = maximum
        self.decimals = decimals
        self.step = step
        self.tip = tip
        if self.choices and default not in self.choices:
            raise ValueError("Default %r of option %s is not one of %s" % (default, key, self.choices))

    @property
    def kind(self):
        if self.choices:
            return "choice"
        if isinstance(self.default, bool):
            return "bool"
        if isinstance(self.default, int):
            return "int"
        if isinstance(self.default, float):
            return "float"
        return "string"

    def coerce(self, value):
        """Convert ``value`` to this option's type and check its range.

        Raises :class:`SetupError` with a readable message for bad values.
        """
        if value is None:
            return self.default
        kind = self.kind
        try:
            if kind == "bool":
                if isinstance(value, str):
                    value = value.strip().lower() in ("1", "true", "yes", "on")
                value = bool(value)
            elif kind == "int":
                value = int(value)
            elif kind == "float":
                value = float(value)
            elif kind == "choice":
                value = str(value)
                if value not in self.choices:
                    raise SetupError("%s must be one of: %s" % (self.label, ", ".join(self.choices)))
            else:
                value = str(value)
        except (TypeError, ValueError):
            raise SetupError("%s: %r is not a valid %s" % (self.label, value, kind)) from None
        if kind in ("int", "float"):
            if self.minimum is not None and value < self.minimum:
                raise SetupError("%s must be at least %s" % (self.label, self.minimum))
            if self.maximum is not None and value > self.maximum:
                raise SetupError("%s must be at most %s" % (self.label, self.maximum))
        return value

    def __repr__(self):
        return "Option(%r, %r)" % (self.key, self.default)


#: options every mirrorable tool gets (shown in the panel's header / footer)
MIRROR_OPTION = Option("mirror", "Mirror", True, tip="Also build the other side (L_ <-> R_ joint names)")
SIZE_OPTION = Option("size", "Control size", 1.0, minimum=0.01, maximum=1000.0, step=0.1,
                     tip="Multiplier on the control sizes (they are sized from the joint lengths)")
GAME_SAFE_OPTION = Option("game_safe", "Game safe", False,
                          tip="On: stretch moves the child joints (translate) and the bind joints never get "
                              "stretch scale - safe for Unreal / Unity.\n"
                              "Off: the bind joints also scale along the bone when they stretch.")


def resolve_options(options_schema, values, retired=()):
    """Merge ``values`` over the defaults of ``options_schema`` (coerced).

    Unknown keys raise :class:`SetupError` so typos in scripts are caught;
    ``retired`` keys (options a tool no longer has) are dropped quietly.
    """
    values = dict((key, value) for key, value in (values or {}).items() if key not in retired)
    known = dict((option.key, option) for option in options_schema)
    unknown = sorted(key for key in values if key not in known)
    if unknown:
        raise SetupError("Unknown option(s): %s" % ", ".join(unknown))
    return dict((key, option.coerce(values.get(key))) for key, option in known.items())
