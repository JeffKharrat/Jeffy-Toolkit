"""Rig Doctor in real Maya: each planted problem is found, and a scan stays fast."""

import time

import skeleton
from maya import cmds
from test_setups_stage1 import ARM

from jeffy.joints import tools as joint_tools
from jeffy.setups.core import doctor
from jeffy.setups.tools.ikfk_limb import IkFkLimb
from jeffy.setups.tools.rig_base import RigBase
from jeffy.setups.tools.spline import SplineIkFk
from jeffy.setups.tools.wire_follow import Follow


def _found(results, key, text):
    findings = dict((k, f) for k, _label, f in results)[key]
    hits = [f for f in findings if text in f.text]
    assert hits, "%s should report %r, got: %s" % (key, text, [f.text for f in findings][:10])
    return hits[0]


def _plant():
    skeleton.build_biped(mirror=False)
    RigBase.build(root_joint="C_root_JNT", name="hero")
    # the Murakami case: no pelvis slot, so the Hips control drives nothing
    SplineIkFk.build(start="C_spine01_JNT", end="C_chest_JNT", mode="spine")
    arm = IkFkLimb.build(name="arm", mirror=False, **ARM)
    # a chain whose middle joint rolls 90 degrees around the bone
    a = joint_tools.create_joint("C_leaf1_JNT", parent="C_root_JNT", position=(0, 10, 30))
    b = joint_tools.create_joint("C_leaf2_JNT", parent=a, position=(10, 10, 30))
    joint_tools.create_joint("C_leaf3_JNT", parent=b, position=(20, 10, 30))
    cmds.setAttr(b + ".jointOrientX", 90)
    # rotate left on a bind joint at rest
    cmds.setAttr("C_headEnd_JNT.rotateZ", 12)
    # leftovers: an unconnected utility node and an orphan intermediate shape
    cmds.createNode("plusMinusAverage", name="lonely_PMA", skipSelect=True)
    cube = cmds.polyCube(name="C_body_GEO", constructionHistory=False)[0]
    orphan = cmds.createNode("mesh", name="orphanShapeOrig", parent=cube, skipSelect=True)
    cmds.setAttr(orphan + ".intermediateObject", 1)
    # a dead driver: multiplyDivide with no input pins a blendShape weight
    target = cmds.duplicate(cube, name="smile")[0]
    cmds.blendShape(target, cube, name="C_body_BS")
    cmds.delete(target)
    leftover = cmds.createNode("multiplyDivide", name="multiplyDivide2", skipSelect=True)
    cmds.connectAttr(leftover + ".outputX", "C_body_BS.smile")
    # name clashes
    for group in ("A_GRP", "B_GRP"):
        cmds.createNode("transform", name="twin_GRP", parent=cmds.createNode("transform", name=group))
    cmds.createNode("transform", name="L_leafBend_CTL1", skipSelect=True)
    # a parked wire: its arm is deleted
    sword = cmds.createNode("transform", name="C_sword_GRP", skipSelect=True)
    Follow.build(driver="L_armIK_CTL", driven=sword)
    arm.delete()
    IkFkLimb.build(name="arm2", mirror=False, **ARM)


def test_doctor_finds_each_planted_problem():
    _plant()
    results = doctor.scan()
    _found(results, "dead_controls", "C_spineHips_CTL drives nothing")
    roll = _found(results, "joint_rolls", "C_leaf2_JNT rolls")
    assert "90" in roll.text
    _found(results, "unskinned", "is driven by")
    _found(results, "leftovers", "lonely_PMA")
    _found(results, "leftovers", "orphanShapeOrig")
    dead = _found(results, "dead_drivers", "C_body_BS")
    assert "multiplyDivide2" in dead.text
    _found(results, "names", "twin_GRP")
    _found(results, "names", "L_leafBend_CTL1")
    _found(results, "rest_rotate", "C_headEnd_JNT")
    _found(results, "extras", "parked wire C_swordFollow")
    # healthy things are not reported
    texts = [f.text for _k, _l, findings in results for f in findings]
    assert not [t for t in texts if "L_elbow_JNT rolls" in t], "a plain bend is not a roll"
    assert not [t for t in texts if t.startswith("L_armIK_CTL drives nothing")]


def test_doctor_scan_is_fast():
    skeleton.build_biped(mirror=True, fingers=True)
    RigBase.build(root_joint="C_root_JNT", name="hero")
    IkFkLimb.build(name="arm", **ARM)
    previous = cmds.createNode("transform", name="driver_GRP", skipSelect=True)
    for index in range(1500):  # a few thousand utility nodes, like a production rig
        node = cmds.createNode("multiplyDivide", skipSelect=True)
        cmds.connectAttr(previous + ".translateX" if index == 0 else previous + ".outputX", node + ".input1X")
        previous = node
        cmds.createNode("plusMinusAverage", skipSelect=True)
    start = time.time()
    doctor.scan()
    elapsed = time.time() - start
    assert elapsed < 15.0, "scan took %.1fs" % elapsed
    print("scan of %d nodes: %.2fs" % (len(cmds.ls()), elapsed))
