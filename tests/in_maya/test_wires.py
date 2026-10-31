"""Wires in real Maya: Follow, Attribute Driver, and how wires rebuild / park with their setups."""

import skeleton
from maya import cmds
from test_setups_stage1 import ARM, assert_close, assert_no_constraints, pos, wm

from jeffy.core import mathlib
from jeffy.setups.core import notes, scene, wires
from jeffy.setups.core.schema import SetupError
from jeffy.setups.tools.ikfk_limb import IkFkLimb
from jeffy.setups.tools.rig_base import RigBase
from jeffy.setups.tools.wire_attribute import AttributeDriver
from jeffy.setups.tools.wire_follow import Follow


def _transform(name, position, rotation=(0, 0, 0), parent=None):
    node = cmds.createNode("transform", name=name, skipSelect=True)
    if parent:
        node = cmds.parent(node, parent)[0]
    cmds.xform(node, worldSpace=True, translation=position, rotation=rotation)
    return node


def _raises(func, text):
    try:
        func()
    except SetupError as error:
        assert text in str(error), str(error)
        return str(error)
    raise AssertionError("expected an error containing %r" % text)


# ---------------------------------------------------------------------------
# Follow
# ---------------------------------------------------------------------------
def test_follow_keeps_the_offset_and_restores_on_delete():
    driver = _transform("C_driverA_GRP", (2, 3, 4), (10, 20, 30))
    group = _transform("C_prop_GRP", (0, 5, 0))
    prop = _transform("C_prop_GEO", (5, 6, 1), (0, 45, 0), parent=group)
    rest = wm(prop)
    wire = Follow.build(driver=driver, driven=prop)
    assert wire.name == "propFollow" and wire.side == "C"
    assert_close(wm(prop), rest, "no pop at build", 1e-4)
    driver_rest = wm(driver)
    cmds.setAttr(driver + ".translate", 4, 1, -2)
    cmds.setAttr(driver + ".rotate", 50, -30, 15)
    cmds.setAttr(group + ".translateX", 3)  # the driven node's parent moves too: the follow stays in world
    expected = mathlib.mult_all(rest, mathlib.inverse(driver_rest), wm(driver))
    assert_close(wm(prop), expected, "follows with its offset", 1e-3)
    assert_no_constraints()
    for node in cmds.listConnections(prop + ".offsetParentMatrix", source=True) or []:
        assert notes.read(node), "every wire node explains itself (%s)" % node
    cmds.setAttr(group + ".translateX", 0)
    wire.delete()
    assert not cmds.listConnections(prop + ".offsetParentMatrix", source=True)
    assert_close(cmds.getAttr(prop + ".offsetParentMatrix"), mathlib.identity(), "offsetParentMatrix put back")
    assert_close(wm(prop), rest, "back at rest")


def test_follow_translate_only_and_two_drivers():
    a = _transform("C_driverA_GRP", (0, 0, 0))
    b = _transform("C_driverB_GRP", (10, 0, 0))
    prop = _transform("C_prop_GRP", (0, 5, 0))
    Follow.build(driver=a, driven=prop, driver2=b, rotate=False)
    assert cmds.getAttr(prop + ".follow") == 0.0, "the blend attribute is on the driven node"
    rest = pos(prop)
    cmds.setAttr(a + ".rotateZ", 90)
    assert_close(pos(prop), rest, "translate only: the driver's rotation doesn't swing it", 1e-4)
    assert_close(cmds.xform(prop, query=True, worldSpace=True, rotation=True), (0, 0, 0), "nor turn it", 1e-4)
    cmds.setAttr(a + ".translateY", 2)
    assert_close(pos(prop), (rest[0], rest[1] + 2, rest[2]), "follows driver 1", 1e-4)
    cmds.setAttr(prop + ".follow", 1)
    assert_close(pos(prop), rest, "blend 1: driver 2 (which did not move)", 1e-4)
    cmds.setAttr(b + ".translateZ", -3)
    assert_close(pos(prop), (rest[0], rest[1], rest[2] - 3), "follows driver 2", 1e-4)


def test_follow_on_a_belt_control_drives_its_off_group():
    skeleton.build_biped(mirror=False)
    RigBase.build(root_joint="C_root_JNT", name="hero")
    IkFkLimb.build(name="arm", mirror=False, **ARM)
    prop = _transform("C_shield_GRP", (60, 140, 10))
    rest = wm("L_armIK_CTL")
    Follow.build(driver=prop, driven="L_armIK_CTL")
    assert cmds.listConnections("L_armIK_ZRO.offsetParentMatrix", source=True), "the ZRO keeps its spaces"
    assert cmds.listConnections("L_armIK_OFF.offsetParentMatrix", source=True), "the OFF group follows"
    assert_close(wm("L_armIK_CTL"), rest, "no pop", 1e-3)
    cmds.move(0, -5, 0, prop, relative=True)
    assert_close(pos("L_armIK_CTL"), (rest[12], rest[13] - 5, rest[14]), "the control follows", 1e-3)
    assert cmds.getAttr("L_armIK_CTL.translateY") == 0, "the animator's channels stay clean"
    # a second follow on the same control is refused, naming the driver
    _raises(lambda: Follow.build(driver="C_root_CTL", driven="L_armIK_CTL"), "already driven by")


def test_follow_mirrors():
    for side, x in (("L", 5), ("R", -5)):
        _transform("%s_hand_GRP" % side, (x, 1, 0))
        _transform("%s_cup_GRP" % side, (x * 1.5, 2, 0))
    wire = Follow.build(driver="L_hand_GRP", driven="L_cup_GRP")
    assert wire.mirror is not None and wire.mirror.side == "R"
    cmds.move(0, 3, 0, "R_hand_GRP", relative=True)
    assert abs(pos("R_cup_GRP")[1] - 5) < 1e-4, "the mirrored wire works"


# ---------------------------------------------------------------------------
# Attribute Driver
# ---------------------------------------------------------------------------
def _face():
    cube = cmds.polyCube(name="C_face_GEO", constructionHistory=False)[0]
    targets = []
    for name in ("smile", "frown"):
        target = cmds.duplicate(cube, name=name)[0]
        cmds.move(0, 1, 0, target + ".vtx[0]", relative=True)
        targets.append(target)
    cmds.blendShape(targets, cube, name="C_face_BS")
    cmds.delete(targets)
    slider = _transform("L_mouth_CTL", (2, 0, 0))
    return slider, "C_face_BS"


def test_attribute_driver_ranges_and_curves():
    slider, blend = _face()
    cmds.setAttr(blend + ".smile", 0.3)
    wire = AttributeDriver.build(source=slider + ".translateY", targets=[blend + ".smile", blend + ".frown"],
                                 in_max=2.0)
    assert wire.name == "mouthTranslateYDriver" and wire.side == "L"
    cmds.setAttr(slider + ".translateY", 1)
    assert abs(cmds.getAttr(blend + ".smile") - 0.5) < 1e-4 and abs(cmds.getAttr(blend + ".frown") - 0.5) < 1e-4
    cmds.setAttr(slider + ".translateY", 5)
    assert abs(cmds.getAttr(blend + ".smile") - 1.0) < 1e-4, "clamped"
    wire.delete()
    assert not cmds.listConnections(blend + ".smile", source=True)
    assert abs(cmds.getAttr(blend + ".smile") - 0.3) < 1e-6, "the target's value is put back"
    # unclamped: keeps going past the range
    AttributeDriver.build(source=slider + ".translateY", targets=[blend + ".smile"], in_max=2.0, clamp=False,
                          name="smileLinear")
    cmds.setAttr(slider + ".translateY", 4)
    assert abs(cmds.getAttr(blend + ".smile") - 2.0) < 1e-4
    _raises(lambda: AttributeDriver.build(source=slider + ".translateX", targets=[blend + ".frown"],
                                          clamp=False, curve="smooth", name="bad"), "needs Clamp")
    # ease in starts slower than linear
    AttributeDriver.build(source=slider + ".translateX", targets=[blend + ".frown"], curve="ease in", name="ease")
    cmds.setAttr(slider + ".translateX", 0.5)
    assert cmds.getAttr(blend + ".frown") < 0.4


def test_attribute_driver_refuses_a_leftover_driver():
    slider, blend = _face()
    leftover = cmds.createNode("multiplyDivide", name="multiplyDivide2", skipSelect=True)
    cmds.connectAttr(leftover + ".outputX", blend + ".smile")
    message = _raises(lambda: AttributeDriver.build(source=slider + ".translateY", targets=[blend + ".smile"]),
                      "no input of its own")
    assert "multiplyDivide2" in message
    cmds.delete(leftover)
    AttributeDriver.build(source=slider + ".translateY", targets=[blend + ".smile"])


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
def test_wires_rebuild_with_their_setup_and_park_when_it_is_deleted():
    skeleton.build_biped(mirror=False)
    RigBase.build(root_joint="C_root_JNT", name="hero")
    arm = IkFkLimb.build(name="arm", mirror=False, **ARM)
    prop = _transform("C_sword_GRP", (66, 140, 5))
    wire = Follow.build(driver="L_armIK_CTL", driven=prop)
    assert [s.TYPE for s in wire.depends()] == ["ikfk_limb"]

    arm = arm.rebuild(options={"knee": "no-flip"})
    found = scene.all_setups(setup_type="wire_follow")
    assert len(found) == 1, "the wire was rebuilt after the arm"
    rest = pos(prop)
    cmds.setAttr("L_armIK_CTL.translateY", -4)
    assert abs(pos(prop)[1] - (rest[1] - 4)) < 1e-3, "and follows the new controls"
    cmds.setAttr("L_armIK_CTL.translateY", 0)

    arm.delete()
    assert not scene.all_setups(setup_type="wire_follow"), "deleting the arm parks the wire"
    assert len(wires.parked()) == 1
    assert not cmds.listConnections(prop + ".offsetParentMatrix", source=True), "what it drove is put back"
    IkFkLimb.build(name="arm", mirror=False, **ARM)
    assert len(scene.all_setups(setup_type="wire_follow")) == 1, "building the arm again brings the wire back"
    assert not wires.parked()
    cmds.setAttr("L_armIK_CTL.translateY", -4)
    assert abs(pos(prop)[1] - (rest[1] - 4)) < 1e-3
