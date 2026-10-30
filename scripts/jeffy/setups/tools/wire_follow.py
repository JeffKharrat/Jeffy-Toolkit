"""Follow (wire): A drives B through ``offsetParentMatrix``, keeping the current offset.

It replaces parent / point / orient constraints, with matrix nodes only:

* pick what follows: translate, rotate and / or scale,
* an optional second driver adds a blend attribute (0: driver 1, 1: driver 2)
  on a control you choose,
* on a belt control it drives the control's **OFF** group: the ZRO above keeps
  its anchors and spaces, the CTL below stays clean for the animator.

Nothing pops at build: the offset between B and A is measured and kept.
"""

from maya import cmds

from jeffy.core import mathlib, matrix, naming
from jeffy.setups.core import controls, scene
from jeffy.setups.core.schema import NODE, Option, SetupError, Slot
from jeffy.setups.core.wire import Wire


def belt_control(node):
    """The belt control (CTL) ``node`` is, or the one under it when ``node`` is its ZRO / OFF group."""
    if controls.key_of(node):
        return node
    level = [node]
    for _depth in range(2):  # ZRO > OFF > CTL
        level = [child for parent in level for child in (cmds.listRelatives(parent, children=True, type="transform")
                                                          or [])]
        for child in level:
            if controls.key_of(child):
                return child
    return None


def follow_target(node):
    """The node whose ``offsetParentMatrix`` Follow drives: a belt control's OFF group, else ``node`` itself."""
    ctl = belt_control(node)
    if ctl is None:
        return node
    parent = cmds.listRelatives(ctl, parent=True)
    return parent[0] if parent else ctl


@scene.register
class Follow(Wire):
    TYPE = "wire_follow"
    LABEL = "Follow"
    ORDER = 10
    DESCRIPTION = ("A drives B, keeping their current offset: a matrix network instead of a constraint. Choose "
                   "translate, rotate and / or scale. A second driver adds a blend attribute. On a belt control it "
                   "drives the OFF group, so spaces keep working. Each node explains itself in its Notes.")
    SLOTS = (
        Slot("driver", "Driver", kind=NODE, tip="What B follows (select it first, then B, then <)"),
        Slot("driven", "Driven", kind=NODE, tip="What follows: any transform, or a belt control (its OFF group "
                                                "is driven)"),
        Slot("driver2", "Driver 2", kind=NODE, optional=True, tip="A second driver: B blends between the two"),
        Slot("blend_on", "Blend on", kind=NODE, optional=True,
             tip="The node that gets the blend attribute (default: the driven control)"),
    )
    OPTIONS = (
        Option("translate", "Translate", True),
        Option("rotate", "Rotate", True),
        Option("scale", "Scale", False),
        Option("blend_attr", "Blend attribute", "follow", tip="Name of the blend attribute (with Driver 2)"),
        Option("blend_default", "Blend default", 0.0, minimum=0.0, maximum=1.0,
               tip="0: driver 1, 1: driver 2"),
    )

    @classmethod
    def resolve_name_side(cls, slots, options, name=None, side=None):
        driven = slots.get("driven")
        name = naming.legalize(str(name or (cls.label_of(driven) + "Follow")).strip()).strip("_")
        if not name:
            raise SetupError("Give the wire a name")
        if not side or side == "auto":
            side = cls.side_of(driven)
        return name, side

    @classmethod
    def validate(cls, slots, options):
        if not (options["translate"] or options["rotate"] or options["scale"]):
            raise SetupError("Follow at least one of translate, rotate or scale")
        driven = slots["driven"]
        target = follow_target(driven)
        drivers = [slots["driver"]] + ([slots["driver2"]] if slots.get("driver2") else [])
        for driver in drivers:
            if driver in (driven, target) or scene.is_ancestor(target, driver):
                raise SetupError("%s can't follow %s: the driver is %s itself or under it (a cycle)"
                                 % (driven, driver, naming.short_name(target)))
        if not cmds.attributeQuery("offsetParentMatrix", node=target, exists=True):
            raise SetupError("%s has no offsetParentMatrix (Maya 2020+ transforms only)" % target)
        cls.check_free(target + ".offsetParentMatrix", "Follow")
        if slots.get("blend_on") and not slots.get("driver2"):
            raise SetupError("'Blend on' needs a Driver 2")

    # ------------------------------------------------------------------
    def build_setup(self):
        options = self.options
        driven = self.slot_node("driven")
        target = follow_target(driven)
        picks = (options["translate"], options["rotate"], options["scale"])
        partial = not all(picks)
        offset_rest = list(cmds.getAttr(target + ".offsetParentMatrix"))
        parent_rest = list(cmds.getAttr(target + ".parentMatrix[0]"))
        parent_inverse = matrix.parent_inverse_plug(target)

        follows = []
        for key, label in (("driver", ""), ("driver2", "2")):
            driver = self.slot_node(key)
            if not driver:
                continue
            source = driver + ".worldMatrix[0]"
            if partial:  # only the driver's chosen channels move B
                pick = self.make("pickMatrix", "Pick" + label,
                                 "pickMatrix: keeps only the driver's %s, so only those move %s"
                                 % (_channels(picks), naming.short_name(driven)))
                cmds.connectAttr(source, pick + ".inputMatrix")
                for flag, on in zip(("useTranslate", "useRotate", "useScale"), picks):
                    cmds.setAttr("%s.%s" % (pick, flag), on)
                cmds.setAttr(pick + ".useShear", picks[2])
                source = pick + ".outputMatrix"
            driver_rest = list(cmds.getAttr(source))
            offset = mathlib.mult_all(offset_rest, parent_rest, mathlib.inverse(driver_rest))
            follow = self.make("multMatrix", "Offset" + label,
                               "multMatrix: the offset between %s and %s at build x the driver's live world "
                               "matrix x the parent's inverse = where %s goes, with nothing popping"
                               % (naming.short_name(driven), naming.short_name(driver), naming.short_name(target)))
            matrix.set_matrix_attr(follow + ".matrixIn[0]", offset)
            cmds.connectAttr(source, follow + ".matrixIn[1]")
            if parent_inverse:
                cmds.connectAttr(parent_inverse, follow + ".matrixIn[2]")
            follows.append(follow + ".matrixSum")

        result = follows[0]
        if len(follows) == 2:
            holder = self.slot_node("blend_on") or belt_control(driven) or driven
            weight = self.add_attr(holder, options["blend_attr"], "float", default=options["blend_default"],
                                   minimum=0.0, maximum=1.0)
            cmds.setAttr(weight, options["blend_default"])
            mix = self.make("blendMatrix", "Blend",
                            "blendMatrix: mixes the two drivers by %s (0: %s, 1: %s)"
                            % (weight, naming.short_name(self.slot_node("driver")),
                               naming.short_name(self.slot_node("driver2"))))
            cmds.connectAttr(follows[0], mix + ".inputMatrix")
            cmds.connectAttr(follows[1], mix + ".target[0].targetMatrix")
            cmds.connectAttr(weight, mix + ".target[0].weight")
            result = mix + ".outputMatrix"

        if partial:  # the channels that don't follow stay at their rest value (pickMatrix would zero them)
            keep = self.make("blendMatrix", "Channels",
                             "blendMatrix: takes the %s from the follow, keeps the rest as it was at build"
                             % _channels(picks))
            matrix.set_matrix_attr(keep + ".inputMatrix", offset_rest)
            cmds.connectAttr(result, keep + ".target[0].targetMatrix")
            cmds.setAttr(keep + ".target[0].weight", 1.0)
            for attr, on in zip(("translateWeight", "rotateWeight", "scaleWeight"), picks):
                cmds.setAttr("%s.target[0].%s" % (keep, attr), 1.0 if on else 0.0)
            cmds.setAttr(keep + ".target[0].shearWeight", 1.0 if picks[2] else 0.0)
            result = keep + ".outputMatrix"
        self.drive_plug(result, target + ".offsetParentMatrix")
        if target != driven:
            print("[Jeffy] Follow: %s is a belt control, its OFF group %s follows (spaces keep working)"
                  % (naming.short_name(driven), naming.short_name(target)))


def _channels(picks):
    names = [name for name, on in zip(("translate", "rotate", "scale"), picks) if on]
    return " and ".join(names)
