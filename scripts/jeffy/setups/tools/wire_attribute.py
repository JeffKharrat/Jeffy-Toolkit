"""Attribute Driver (wire): one attribute drives others through a range, like a set driven key made of nodes.

``L_mouth_CTL.translateY`` 0..1 -> ``face_BS.smile`` 0..1, for example:

* **input range -> output range**, clamped (the output stays inside its range)
  or not (it keeps going past it, linear only),
* a **curve**: linear, smooth, ease in (slow start) or ease out (slow end),
* one or more **targets**. A target something else already drives is refused,
  naming the driver, and saying when that driver is a leftover with no real
  input (a ``multiplyDivide`` nothing feeds, still pinning the weight to 0).

Deleting the wire puts each target's value back.
"""

from maya import cmds

from jeffy.core import naming, nodes
from jeffy.setups.core import scene
from jeffy.setups.core.schema import ATTRIBUTE, ATTRIBUTES, Option, SetupError, Slot
from jeffy.setups.core.wire import Wire, node_of

CURVES = ("linear", "smooth", "ease in", "ease out")
#: remapValue curve points: (position, value, interpolation 1 linear / 2 smooth / 3 spline)
CURVE_POINTS = {
    "linear": ((0.0, 0.0, 1), (1.0, 1.0, 1)),
    "smooth": ((0.0, 0.0, 2), (1.0, 1.0, 2)),
    "ease in": ((0.0, 0.0, 3), (0.5, 0.2, 3), (1.0, 1.0, 3)),
    "ease out": ((0.0, 0.0, 3), (0.5, 0.8, 3), (1.0, 1.0, 3)),
}


@scene.register
class AttributeDriver(Wire):
    TYPE = "wire_attribute"
    LABEL = "Attribute Driver"
    ORDER = 20
    DESCRIPTION = ("One attribute drives others through a range: a control's translateY -> a blendShape weight, "
                   "for example. Input range -> output range, clamped or not, with a curve. Targets that "
                   "something else already drives are refused (and leftovers are named).")
    SLOTS = (
        Slot("source", "Source", kind=ATTRIBUTE,
             tip="Select the node, highlight one attribute in the Channel Box, then <"),
        Slot("targets", "Targets", kind=ATTRIBUTES,
             tip="Select the node(s), highlight the attribute(s) in the Channel Box, then < (or + to add)"),
    )
    OPTIONS = (
        Option("in_min", "Input min", 0.0, minimum=-100000.0, maximum=100000.0),
        Option("in_max", "Input max", 1.0, minimum=-100000.0, maximum=100000.0),
        Option("out_min", "Output min", 0.0, minimum=-100000.0, maximum=100000.0),
        Option("out_max", "Output max", 1.0, minimum=-100000.0, maximum=100000.0),
        Option("clamp", "Clamp", True, tip="On: the output stays inside its range. Off: it keeps going (linear only)"),
        Option("curve", "Curve", "linear", choices=CURVES),
    )

    @classmethod
    def resolve_name_side(cls, slots, options, name=None, side=None):
        source = slots.get("source") or ""
        attr = source.split(".", 1)[1] if "." in source else "attr"
        default = cls.label_of(source) + attr[:1].upper() + attr[1:] + "Driver"
        name = naming.legalize(str(name or default).strip()).strip("_")
        if not name:
            raise SetupError("Give the wire a name")
        if not side or side == "auto":
            side = cls.side_of(source)
        return name, side

    @classmethod
    def validate(cls, slots, options):
        source = slots["source"]
        value = cmds.getAttr(source)
        if not isinstance(value, (int, float, bool)):
            raise SetupError("Source %s is not a single number (pick one channel, like translateY)" % source)
        if abs(options["in_max"] - options["in_min"]) < 1e-9:
            raise SetupError("Input min and max must differ")
        if not options["clamp"] and options["curve"] != "linear":
            raise SetupError("A curve needs Clamp on (unclamped is linear only)")
        targets = slots["targets"]
        for target in targets:
            if target == source:
                raise SetupError("%s can't drive itself" % source)
            if not isinstance(cmds.getAttr(target), (int, float, bool)):
                raise SetupError("Target %s is not a single number" % target)
            cls.check_free(target, "Attribute Driver")
        if len(set(targets)) != len(targets):
            raise SetupError("A target is listed twice")

    def build_setup(self):
        options = self.options
        source = self.slot_node("source")
        span = "%s..%s -> %s..%s" % (_num(options["in_min"]), _num(options["in_max"]), _num(options["out_min"]),
                                     _num(options["out_max"]))
        if options["clamp"]:
            remap = self.make("remapValue", "Remap",
                              "remapValue: maps %s from %s along a %s curve, and stays inside the output range"
                              % (source, span, options["curve"]))
            cmds.connectAttr(source, remap + ".inputValue")
            for attr, key in (("inputMin", "in_min"), ("inputMax", "in_max"), ("outputMin", "out_min"),
                              ("outputMax", "out_max")):
                cmds.setAttr("%s.%s" % (remap, attr), options[key])
            for index, (position, value, interp) in enumerate(CURVE_POINTS[options["curve"]]):
                cmds.setAttr("%s.value[%d].value_Position" % (remap, index), position)
                cmds.setAttr("%s.value[%d].value_FloatValue" % (remap, index), value)
                cmds.setAttr("%s.value[%d].value_Interp" % (remap, index), interp)
            output = remap + ".outValue"
        else:  # (input - in_min) * scale + out_min, linear past the range
            scale = (options["out_max"] - options["out_min"]) / (options["in_max"] - options["in_min"])
            shifted = nodes.add(source, -options["in_min"], name=self._n(self.name + "Shift", "ADL"))
            scaled = nodes.multiply(shifted, scale, name=self._n(self.name + "Scale", "MDL"))
            output = nodes.add(scaled, options["out_min"], name=self._n(self.name + "Offset", "ADL"))
            self.note(node_of(shifted), "addDL: the source minus the input min (%s)" % _num(options["in_min"]))
            self.note(node_of(scaled), "multDL: x %s, so the input range becomes the output range's size"
                      % _num(scale))
            self.note(node_of(output), "addDL: + the output min (%s); it keeps going past the range (no clamp)"
                      % _num(options["out_min"]))
        for target in self.slot_nodes("targets"):
            self.drive_plug(output, target)

    def _n(self, label, suffix):
        return naming.compose(label, self.side, suffix)


def _num(value):
    return ("%.3f" % value).rstrip("0").rstrip(".") or "0"
