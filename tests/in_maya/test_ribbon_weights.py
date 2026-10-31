"""Weights to Ribbon in real Maya: a chain's skin weights spread evenly onto its Ribbon joints."""

import skeleton
from maya import cmds
from test_setups_stage1 import pos

from jeffy.core import decorators, mathlib
from jeffy.deformers import skin
from jeffy.setups.core.schema import SetupError
from jeffy.setups.tools import ribbon_weights
from jeffy.setups.tools.ikfk_limb import IkFkLimb
from jeffy.setups.tools.ribbon import Ribbon
from jeffy.setups.tools.rig_base import RigBase

RIBBON = ["L_armRibbon%02d_JNT" % i for i in range(1, 11)]
CHAIN = ["L_shoulder_JNT", "L_elbow_JNT", "L_wrist_JNT"]
TOL = 1e-4


def _weight_for(x):
    """Painted weights by x: clavicle blend at the shoulder, a 50/50 elbow band, the hand on the wrist."""
    if x < 18:
        return {"L_clavicle_JNT": 0.4, "L_shoulder_JNT": 0.6}
    if 38 <= x <= 42:
        return {"L_shoulder_JNT": 0.5, "L_elbow_JNT": 0.5}
    if x < 40:
        return {"L_shoulder_JNT": 1.0}
    if x < 66:
        return {"L_elbow_JNT": 1.0}
    return {"L_wrist_JNT": 1.0}


def _leaf():
    """An IK/FK arm with a Ribbon, and a mesh much wider than the bone skinned to the chain + clavicle."""
    skeleton.build_biped(mirror=False)
    RigBase.build(root_joint="C_root_JNT", name="hero")
    IkFkLimb.build(name="arm", start="L_shoulder_JNT", mid="L_elbow_JNT", end="L_wrist_JNT", mirror=False)
    ribbon = Ribbon.build(base="L_armIK_CTL", mirror=False)
    mesh = cmds.polyCube(name="L_leaf_GEO", width=60, height=24, depth=30, subdivisionsX=60, subdivisionsY=2,
                         subdivisionsZ=2, constructionHistory=False)[0]
    cmds.xform(mesh, worldSpace=True, translation=(44, 145, -2))
    cmds.makeIdentity(mesh, apply=True, translate=True)
    cluster = skin.bind(mesh, ["L_clavicle_JNT"] + CHAIN, max_influences=4)[0]
    for vertex in range(cmds.polyEvaluate(mesh, vertex=True)):
        x = cmds.pointPosition("%s.vtx[%d]" % (mesh, vertex), world=True)[0]
        cmds.skinPercent(cluster, "%s.vtx[%d]" % (mesh, vertex), transformValue=list(_weight_for(x).items()))
    return ribbon, mesh, cluster


def _weights(cluster, mesh, vertex):
    names = skin.get_influences(cluster)
    values = cmds.skinPercent(cluster, "%s.vtx[%d]" % (mesh, vertex), query=True, value=True)
    return dict((name, value) for name, value in zip(names, values) if value > TOL)


def _points(mesh):
    return [cmds.pointPosition("%s.vtx[%d]" % (mesh, v), world=True) for v in range(cmds.polyEvaluate(mesh,
                                                                                                    vertex=True))]


def _along(point, start, end):
    direction = mathlib.sub(pos(end), pos(start))
    return mathlib.dot(mathlib.sub(point, pos(start)), direction) / mathlib.dot(direction, direction)


def test_split_math():
    values = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0]
    assert ribbon_weights.split(-1, values) == [(0, 1.0)]
    assert ribbon_weights.split(3, values) == [(10, 1.0)]
    (low, a), (high, b) = ribbon_weights.split(0.3, values)
    assert (low, high) == (1, 2) and abs(a - 0.5) < 1e-9 and abs(b - 0.5) < 1e-9
    assert ribbon_weights.split(1.0, values) == [(5, 1.0)]


def test_weights_move_evenly_onto_the_ribbon():
    ribbon, mesh, cluster = _leaf()
    count = cmds.polyEvaluate(mesh, vertex=True)
    before = [_weights(cluster, mesh, v) for v in range(count)]
    points = _points(mesh)
    report = ribbon_weights.transfer(ribbon)
    assert report and report[0][1] > 0, report
    assert _points(mesh) == points or all(mathlib.distance(a, b) < TOL for a, b in zip(_points(mesh), points)), \
        "the mesh moved at rest"
    after = [_weights(cluster, mesh, v) for v in range(count)]
    for vertex in range(count):
        old, new = before[vertex], after[vertex]
        assert abs(sum(new.values()) - 1.0) < TOL, (vertex, new)
        assert "L_shoulder_JNT" not in new and "L_elbow_JNT" not in new, (vertex, new)
        assert abs(new.get("L_clavicle_JNT", 0) - old.get("L_clavicle_JNT", 0)) < TOL, "clavicle untouched"
        assert new.get("L_wrist_JNT", 0) >= old.get("L_wrist_JNT", 0) - TOL, "the wrist keeps its weights"

    # a full upper-arm vertex at 0.3 of the bone: 50/50 between Ribbon02 (0.2) and Ribbon03 (0.4)
    upper = [v for v in range(count) if before[v] == {"L_shoulder_JNT": 1.0}]
    vertex = min(upper, key=lambda v: abs(_along(points[v], *CHAIN[:2]) - 0.3))
    t = _along(points[vertex], *CHAIN[:2]) * 5
    low = int(t)
    share = t - low
    assert abs(after[vertex].get(RIBBON[low], 0) - (1 - share)) < 1e-3, (t, after[vertex])
    assert abs(after[vertex].get(RIBBON[low + 1], 0) - share) < 1e-3, (t, after[vertex])

    # the elbow band stays around the elbow: shoulder half -> Ribbon04-06, elbow half -> Ribbon06-07
    band = [v for v in range(count) if before[v] == {"L_shoulder_JNT": 0.5, "L_elbow_JNT": 0.5}]
    assert band
    for vertex in band:
        assert set(after[vertex]) <= set(RIBBON[3:7]), after[vertex]

    # the forearm's end fades into the wrist (no ribbon joint between Ribbon10 and the wrist)
    tip = [v for v in range(count) if before[v] == {"L_elbow_JNT": 1.0} and _along(points[v], *CHAIN[1:]) > 0.92]
    assert tip and all(after[v].get("L_wrist_JNT", 0) > 0.1 for v in tip), [after[v] for v in tip]


def test_selected_vertices_posed_rig_and_undo():
    cmds.undoInfo(state=True, infinity=True)
    ribbon, mesh, cluster = _leaf()
    count = cmds.polyEvaluate(mesh, vertex=True)
    original = [_weights(cluster, mesh, v) for v in range(count)]

    # selected vertices only
    picked = list(range(0, count, 7))
    with decorators.undo_chunk("selected"):
        ribbon_weights.transfer(ribbon, components=["%s.vtx[%d]" % (mesh, v) for v in picked])
    for vertex in range(count):
        now = _weights(cluster, mesh, vertex)
        if vertex in picked:
            assert "L_shoulder_JNT" not in now and "L_elbow_JNT" not in now
        else:
            assert now == original[vertex] or all(abs(now.get(k, 0) - w) < TOL for k, w in original[vertex].items())

    # one undo puts everything back
    cmds.undo()
    with decorators.undo_chunk("transfer"):
        ribbon_weights.transfer(ribbon)
    cmds.undo()
    for vertex in range(count):
        now = _weights(cluster, mesh, vertex)
        assert all(abs(now.get(k, 0) - w) < TOL for k, w in original[vertex].items()), (vertex, now)

    # posed before the ribbon joints are in the skin: refused (they would be bound where they are)
    assert not set(RIBBON) & set(skin.get_influences(cluster)), "undo removes the added influences"
    cmds.setAttr("L_armIK_CTL.translateY", -20)
    try:
        ribbon_weights.transfer(ribbon)
    except SetupError as error:
        assert "Reset Pose" in str(error), error
    else:
        raise AssertionError("a posed rig with new influences should be refused")

    # once they are in the skin (added at rest), posing doesn't change the result
    cmds.setAttr("L_armIK_CTL.translateY", 0)
    with decorators.undo_chunk("rest"):
        ribbon_weights.transfer(ribbon)
    at_rest = [_weights(cluster, mesh, v) for v in range(count)]
    cmds.undo()
    skin.add_influences(mesh, RIBBON)
    cmds.setAttr("L_armIK_CTL.translateY", -20)
    ribbon_weights.transfer(ribbon)
    for vertex in range(count):
        now = _weights(cluster, mesh, vertex)
        assert all(abs(now.get(k, 0) - w) < 1e-3 for k, w in at_rest[vertex].items()), (vertex, now, at_rest[vertex])
    cmds.undoInfo(state=False)
