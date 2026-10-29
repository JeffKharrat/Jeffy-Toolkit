"""Shape memory in real Maya: edited control shapes survive Rebuild / Delete + Build.

Run with ``mayapy tests/in_maya/run.py -k shape``.
"""

import skeleton
from maya import cmds

from jeffy.controls import shapes
from jeffy.core import color
from jeffy.setups.core import scene, shape_memory
from jeffy.setups.tools.ikfk_limb import IkFkLimb
from jeffy.setups.tools.rig_base import RigBase

ARM = {"start": "L_shoulder_JNT", "mid": "L_elbow_JNT", "end": "L_wrist_JNT"}
TOL = 1e-3


def points(node):
    result = []
    for curve in shapes.get_shape_data(node):
        result.extend(curve["points"])
    return result


def assert_points(node, expected, factor=1.0):
    current = points(node)
    assert len(current) == len(expected), "%s: %d CVs, expected %d" % (node, len(current), len(expected))
    for a, b in zip(current, expected):
        assert all(abs(x - y * factor) <= TOL for x, y in zip(a, b)), "%s: %s != %s" % (node, a, b)


def build():
    skeleton.build_biped()
    RigBase.build(root_joint="C_root_JNT", name="hero")
    return IkFkLimb.build(name="arm", **ARM)


def test_edited_shapes_survive_rebuild():
    limb = build()
    default_ik = points("L_armIK_CTL")
    default_pole = points("L_armPole_CTL")
    shapes.scale_shapes("L_armIK_CTL", 2.0)
    shapes.rotate_shapes("L_armIK_CTL", (0, 45, 0))
    color.set_color("L_armIK_CTL", 13)
    edited = points("L_armIK_CTL")

    limb = limb.rebuild(options={"stretch": False})
    assert_points("L_armIK_CTL", edited)
    assert color.get_color("L_armIK_CTL") == 13
    assert_points("L_armPole_CTL", default_pole)  # untouched: the build's shape
    assert shape_memory.stored_keys() == ["ikfk_limb|arm|L|ik"], shape_memory.stored_keys()

    # a second rebuild keeps it too (the restored shape counts as edited)
    limb = limb.rebuild(options={"stretch": True})
    assert_points("L_armIK_CTL", edited)

    # size option doubled: the remembered shape scales with it
    limb = limb.rebuild(options={"size": 2.0})
    assert_points("L_armIK_CTL", edited, factor=2.0)

    # forget: the next rebuild gives the default shape back
    shape_memory.forget(limb, ["L_armIK_CTL"])
    limb = limb.rebuild(options={"size": 1.0})
    assert_points("L_armIK_CTL", default_ik)
    assert not shape_memory.stored_keys()


def test_shapes_come_back_after_delete_and_build():
    limb = build()
    shapes.scale_shapes("L_armIK_CTL", 3.0)
    shapes.scale_shapes("R_armIK_CTL", 0.5)  # the mirrored side has its own memory
    left, right = points("L_armIK_CTL"), points("R_armIK_CTL")
    limb.delete(mirror=True)
    assert cmds.objExists(shape_memory.NODE)
    assert not [s for s in scene.all_setups() if s.TYPE == "ikfk_limb"]
    IkFkLimb.build(name="arm", **ARM)
    assert_points("L_armIK_CTL", left)
    assert_points("R_armIK_CTL", right)


def test_topology_change_keeps_shape_connections():
    build()
    shape = shapes.curve_shapes("L_armIK_CTL")[0]
    driver = cmds.createNode("transform", name="visDriver", skipSelect=True)
    cmds.connectAttr(driver + ".visibility", shape + ".visibility")
    entry = shape_memory.read("L_armIK_CTL")
    entry["curves"] = [{"points": [[0, 0, 0], [1, 0, 0], [1, 1, 0]], "degree": 1, "periodic": False}]
    shape_memory.apply("L_armIK_CTL", entry)
    new_shapes = shapes.curve_shapes("L_armIK_CTL")
    assert len(new_shapes) == 1 and len(points("L_armIK_CTL")) == 3
    assert cmds.listConnections(new_shapes[0] + ".visibility", source=True) == ["visDriver"]


def test_unedited_controls_leave_no_memory():
    limb = build()
    limb.rebuild(options={"stretch": False})
    assert not cmds.objExists(shape_memory.NODE), "nothing was edited, nothing is stored"
