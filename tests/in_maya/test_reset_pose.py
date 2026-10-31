"""Reset pose: every control back to zero, attributes to their defaults, driven channels untouched."""

import skeleton
from maya import cmds
from test_setups_stage1 import ARM, assert_no_pop

from jeffy.setups.core import pose
from jeffy.setups.tools.hand import Hand
from jeffy.setups.tools.ikfk_limb import IkFkLimb
from jeffy.setups.tools.rig_base import RigBase
from jeffy.setups.tools.spline import SplineIkFk

FINGERS = ["L_thumb01_JNT", "L_indexMeta_JNT", "L_middleMeta_JNT", "L_ringMeta_JNT", "L_pinkyMeta_JNT"]


def _rig():
    skeleton.build_biped(fingers=True)
    before = skeleton.world_matrices()
    RigBase.build(root_joint="C_root_JNT", name="hero")
    SplineIkFk.build(start="C_spine01_JNT", end="C_chest_JNT", pelvis="C_pelvis_JNT", mode="spine")
    IkFkLimb.build(name="arm", **ARM)
    Hand.build(wrist="L_wrist_JNT", fingers=FINGERS)
    return before


def _pose():
    cmds.setAttr("C_spineCog_CTL.translateY", -5)
    cmds.setAttr("C_spineChestIk_CTL.rotateX", 20)
    cmds.setAttr("L_armIK_CTL.translate", 3, -4, 2)
    cmds.setAttr("R_armIK_CTL.rotateZ", 30)
    cmds.setAttr("L_hand_CTL.fist", 6)
    cmds.setAttr("C_root_CTL.translateX", 7)


def test_reset_pose_puts_the_whole_rig_back():
    before = _rig()
    _pose()
    settings = [n for n in cmds.ls("*Settings_CTL") if cmds.attributeQuery("ikFk", node=n, exists=True)]
    for node in settings:
        cmds.setAttr(node + ".ikFk", 1 - cmds.getAttr(node + ".ikFk"))
    assert pose.reset() > 0
    assert_no_pop(before)
    assert cmds.getAttr("L_hand_CTL.fist") == 0
    for node in settings:
        default = cmds.attributeQuery("ikFk", node=node, listDefault=True)[0]
        assert cmds.getAttr(node + ".ikFk") == default, node
    assert pose.reset() == 0, "nothing left to reset"


def test_reset_pose_transforms_only_and_selected_controls():
    before = _rig()
    _pose()
    pose.reset(controls=["L_armIK_CTL"])
    assert cmds.getAttr("L_armIK_CTL.translate")[0] == (0.0, 0.0, 0.0)
    assert abs(cmds.getAttr("R_armIK_CTL.rotateZ") - 30) < 1e-4, "only the given controls"
    pose.reset(attributes=False)
    assert cmds.getAttr("L_hand_CTL.fist") == 6, "attributes kept"
    cmds.setAttr("L_hand_CTL.fist", 0)
    assert_no_pop(before)
