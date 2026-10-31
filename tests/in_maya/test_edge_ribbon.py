"""Edge Ribbon in real Maya: blendShape follow, no double transformation, jaw follow, master, rebuild, game safe."""

import skeleton
from maya import cmds
from test_setups_stage1 import assert_close, assert_no_constraints, assert_no_pop, pos

from jeffy.setups.core import scene
from jeffy.setups.tools.edge_ribbon import EdgeRibbon
from jeffy.setups.tools.jaw import Jaw
from jeffy.setups.tools.rig_base import RigBase

MOUTH = (0.0, 158.0, 11.0)
LIFT = 0.5


def rig():
    skeleton.build_biped(mirror=False, face=True)
    before = skeleton.world_matrices()
    RigBase.build(root_joint="C_root_JNT", name="hero")
    Jaw.build(jaw="C_jaw_JNT", chin="C_chin_JNT")
    return before


def mouth_mesh(name="face_GEO", blend=True, skin=True):
    """A tube facing forward: its middle edge ring is a round 'lip' loop (radius 3)."""
    mesh = cmds.polyCylinder(name=name, radius=3, height=1, subdivisionsAxis=16, subdivisionsHeight=2,
                             axis=(0, 0, 1), constructionHistory=False)[0]
    cmds.xform(mesh, translation=MOUTH)
    loop = ring_edges(mesh, MOUTH[2])
    if blend:
        target = cmds.duplicate(mesh, name=name + "Smile")[0]
        for vertex in ring_vertices(target, MOUTH[2]):
            if cmds.pointPosition(vertex, world=True)[1] > MOUTH[1] + 0.1:
                cmds.move(0, LIFT, 0, vertex, relative=True, worldSpace=True)
        cmds.blendShape(target, mesh, name=name + "_BS")
        cmds.delete(target)
    if skin:
        cmds.skinCluster("C_head_JNT", "C_jaw_JNT", mesh, toSelectedBones=True, name=name + "_SKN")
        cmds.skinPercent(name + "_SKN", mesh + ".vtx[*]", transformValue=[("C_head_JNT", 1.0)])
    return mesh, loop


def ring_vertices(mesh, z):
    return [v for v in cmds.ls(mesh + ".vtx[*]", flatten=True) if abs(cmds.pointPosition(v, world=True)[2] - z) < 1e-3]


def ring_edges(mesh, z):
    result = []
    for edge in cmds.ls(mesh + ".e[*]", flatten=True):
        vertices = cmds.ls(cmds.polyListComponentConversion(edge, toVertex=True), flatten=True)
        if all(abs(cmds.pointPosition(v, world=True)[2] - z) < 1e-3 for v in vertices):
            result.append(edge)
    return result


def top_vertex(mesh):
    return max(ring_vertices(mesh, MOUTH[2]), key=lambda v: cmds.pointPosition(v, world=True)[1])


def skin_ring_to(setup, mesh):
    """Add the bind joints to the mesh's skin, each ring vertex fully on its nearest bind joint."""
    skin = mesh + "_SKN"
    joints = setup.bind_joints()
    for joint in joints:
        cmds.skinCluster(skin, edit=True, addInfluence=joint, weight=0.0)
    for vertex in ring_vertices(mesh, MOUTH[2]):
        point = cmds.pointPosition(vertex, world=True)
        nearest = min(joints, key=lambda j: sum((a - b) ** 2 for a, b in zip(pos(j), point)))
        cmds.skinPercent(skin, vertex, transformValue=[(nearest, 1.0)], zeroRemainingInfluences=True)
    return skin


def test_edge_ribbon_follows_blendshape_without_double_transform():
    before = rig()
    mesh, loop = mouth_mesh()
    lips = EdgeRibbon.build(base="C_jawChin_CTL", edges=loop)
    assert lips.name == "lips" and lips.side == "C", (lips.name, lips.side)
    assert_no_constraints()
    assert_no_pop(before)
    names = sorted(scene.short(c) for c in lips.controls.values())
    for expected in ("C_lipsUpper_CTL", "C_lipsLower_CTL", "L_lipsCorner_CTL", "R_lipsCorner_CTL",
                     "L_lipsUpper_CTL", "C_lipsMaster_CTL"):
        assert expected in names, (expected, names)
    assert len(lips.bind_joints()) == 20
    # the controls and joints sit on the loop, even though the mesh is moved away from the origin
    assert_close(pos("C_lipsUpper_CTL"), (0.0, MOUTH[1] + 3.0, MOUTH[2]), "the upper lip control is on the lip")
    assert_close(pos("L_lipsCorner_CTL"), (3.0, MOUTH[1], MOUTH[2]), "the corner control is on the corner")
    assert_close(pos("C_lipsUpper_JNT"), (0.0, MOUTH[1] + 3.0, MOUTH[2]), "the bind joint is on the lip", 0.01)
    spheres = len(cmds.listRelatives("C_lipsUpper_CTL", shapes=True))
    assert spheres > 1, "sphere controls by default (several curves)"

    # the controls follow the blendShape, their channels stay at 0
    upper = "C_lipsUpper_CTL"
    rest = pos(upper)
    cmds.setAttr(mesh + "_BS.w[0]", 1)
    assert_close(pos(upper), (rest[0], rest[1] + LIFT, rest[2]), "the upper lip control follows the blendShape", 0.05)
    assert cmds.getAttr(upper + ".translateY") == 0
    cmds.setAttr(mesh + "_BS.w[0]", 0)

    # skin, connect, then the blendShape moves the lips once
    skin_ring_to(lips, mesh)
    assert lips.connect_skin() == 20
    top = top_vertex(mesh)
    top_rest = cmds.pointPosition(top, world=True)
    cmds.setAttr(mesh + "_BS.w[0]", 1)
    assert_close(cmds.pointPosition(top, world=True), (top_rest[0], top_rest[1] + LIFT, top_rest[2]),
                 "no double transformation", 0.02)
    # and the control still moves the lip on top
    cmds.setAttr(upper + ".translateY", 1)
    moved = cmds.pointPosition(top, world=True)[1]
    assert moved > top_rest[1] + LIFT + 0.7, ("the control moves the lip on top", moved - top_rest[1])
    cmds.setAttr(upper + ".translateY", 0)
    # the whole rig moves: the lips come along, still moved once by the blendShape
    root = lips.rig.controls["root"]
    cmds.setAttr(root + ".translateX", 10)
    assert_close(cmds.pointPosition(top, world=True), (top_rest[0] + 10, top_rest[1] + LIFT, top_rest[2]),
                 "the lips follow the rig", 0.02)
    cmds.setAttr(root + ".translateX", 0)


def test_edge_ribbon_jaw_follow_and_master():
    rig()
    _mesh, loop = mouth_mesh()
    lips = EdgeRibbon.build(base="C_jawChin_CTL", edges=loop)
    upper, lower, corner = "C_lipsUpper_CTL", "C_lipsLower_CTL", "L_lipsCorner_CTL"
    master = "C_lipsMaster_CTL"
    assert [cmds.getAttr(master + "." + a) for a in ("upperJawFollow", "cornerJawFollow", "lowerJawFollow")] == \
        [0.0, 0.5, 1.0]
    joints = lips.bind_joints()
    nodes = [upper, lower, corner] + joints
    rests = dict((node, pos(node)) for node in nodes)
    cmds.setAttr("C_jawChin_CTL.translateY", -2)
    drop = dict((node, rests[node][1] - pos(node)[1]) for node in nodes)
    assert_close(pos(upper), rests[upper], "upperJawFollow 0: the upper lip control stays")
    assert drop[lower] > 0.3, ("the lower lip follows the jaw", drop[lower])
    assert 0.0 < drop[corner] < drop[lower], ("corners follow half way", drop[corner], drop[lower])
    # every bind joint: upper lip ones stay unless they are close to a corner, lower lip ones follow fully
    uppers = [j for j in joints if "Upper" in j]
    lowers = [j for j in joints if "Lower" in j]
    corners = [j for j in joints if "Corner" in j]
    far_uppers = [j for j in uppers if abs(rests[j][0]) < 1.5]  # the middle of the upper lip (radius 3)
    assert far_uppers and all(abs(drop[j]) < 1e-3 for j in far_uppers), \
        ("the middle of the upper lip never follows the jaw", [(j, round(drop[j], 3)) for j in far_uppers])
    far_lowers = [j for j in lowers if abs(rests[j][0]) < 1.5]
    assert all(abs(drop[j] - drop[lower]) < 0.05 for j in far_lowers), "the lower lip follows the jaw fully"
    assert all(0.0 < drop[j] < max(drop[k] for k in far_lowers) for j in corners), "corners blend"
    # live: the corner falloff region follows the attribute
    cmds.setAttr(master + ".upperJawFollow", 0.3)
    assert all(drop[j] < rests[j][1] - pos(j)[1] for j in far_uppers), "upperJawFollow is live"
    cmds.setAttr(master + ".upperJawFollow", 0)
    cmds.setAttr("C_jawChin_CTL.translateY", 0)
    for node in nodes:
        assert_close(pos(node), rests[node], "back at rest: " + node)

    # the master moves every control
    cmds.setAttr("C_lipsMaster_CTL.translateX", 1)
    for node in (upper, lower, corner):
        assert_close(pos(node), (rests[node][0] + 1, rests[node][1], rests[node][2]), "master moves " + node)
    cmds.setAttr("C_lipsMaster_CTL.translateX", 0)
    # its outline follows the blendShape
    shape = cmds.listRelatives("C_lipsMaster_CTL", shapes=True)[0]
    tops = lambda: max(p[1] for p in cmds.getAttr(shape + ".cv[*]"))  # noqa: E731
    before = tops()
    cmds.setAttr("face_GEO_BS.w[0]", 1)
    assert tops() > before + LIFT * 0.5, ("the outline follows the lips", tops() - before)
    assert lips.TYPE == "edge_ribbon"


def test_edge_ribbon_rebuild_keeps_weights_and_delete_restores():
    rig()
    mesh, loop = mouth_mesh()
    rest_points = [cmds.pointPosition(v, world=True) for v in cmds.ls(mesh + ".vtx[*]", flatten=True)]
    lips = EdgeRibbon.build(base="C_jawChin_CTL", edges=loop)
    skin = skin_ring_to(lips, mesh)
    lips.connect_skin()
    top = top_vertex(mesh)
    weights_before = cmds.skinPercent(skin, top, query=True, value=True, ignoreBelow=1e-6)
    joint_ids = sorted(cmds.ls(lips.bind_joints(), uuid=True))
    top_rest = cmds.pointPosition(top, world=True)

    def check(label):
        """Same joints, same weights, live bindPreMatrix, and the blendShape still moves the lips once."""
        assert sorted(cmds.ls(lips.bind_joints(), uuid=True)) == joint_ids, label + ": the skinned joints are reused"
        assert cmds.skinPercent(skin, top, query=True, value=True, ignoreBelow=1e-6) == weights_before, label
        connected = cmds.listConnections(skin + ".bindPreMatrix", source=True, destination=False) or []
        assert len(connected) == 20, label + ": bindPreMatrix wired again"
        cmds.setAttr(mesh + "_BS.w[0]", 1)
        assert_close(cmds.pointPosition(top, world=True), (top_rest[0], top_rest[1] + LIFT, top_rest[2]),
                     label + ": no double transform", 0.02)
        cmds.setAttr(mesh + "_BS.w[0]", 0)

    lips = lips.rebuild(options={"width": 0.4})
    check("rebuild")

    # delete: the skinned joints stay at rest in the skin, the mesh is back as it was (never re-weighted)
    lips.delete()
    assert len([j for j in cmds.skinCluster(skin, query=True, influence=True) if "lips" in j]) == 20
    after = [cmds.pointPosition(v, world=True) for v in cmds.ls(mesh + ".vtx[*]", flatten=True)]
    for a, b in zip(rest_points, after):
        assert_close(a, b, "the mesh is back as it was")
    assert cmds.objExists(mesh + "_BS"), "the user's blendShape stays"
    assert not cmds.listConnections(skin + ".bindPreMatrix", source=True, destination=False)
    cmds.setAttr(mesh + "_BS.w[0]", 1)
    assert_close(cmds.pointPosition(top, world=True), (top_rest[0], top_rest[1] + LIFT, top_rest[2]),
                 "kept joints at rest: the blendShape alone moves the mesh", 0.02)
    cmds.setAttr(mesh + "_BS.w[0]", 0)

    # a new build (same name) picks the kept joints up again
    lips = EdgeRibbon.build(base="C_jawChin_CTL", edges=loop)
    check("new build")


def test_edge_ribbon_creates_blendshape_and_removes_it():
    rig()
    mesh, loop = mouth_mesh(blend=False, skin=False)
    lips = EdgeRibbon.build(base="C_jawChin_CTL", edges=loop, master=False)
    created = cmds.ls(cmds.listHistory(mesh), type="blendShape")
    assert created, "an empty blendShape was added"
    assert "C_lipsMaster_CTL" not in [scene.short(c) for c in lips.controls.values()]
    lips.delete()
    assert not cmds.ls(cmds.listHistory(mesh), type="blendShape"), "the empty blendShape is removed again"
    assert not cmds.ls("*lips*", type="transform")


def test_edge_ribbon_game_safe_offsets():
    rig()
    mesh, loop = mouth_mesh()
    lips = EdgeRibbon.build(base="C_jawChin_CTL", edges=loop, game_safe=True, master=False)
    for joint in lips.bind_joints():
        assert cmds.listRelatives(joint, parent=True)[0] == "C_head_JNT", joint
    skin_ring_to(lips, mesh)
    assert lips.connect_skin() == 0
    assert not cmds.listConnections(mesh + "_SKN.bindPreMatrix", source=True, destination=False)
    top = top_vertex(mesh)
    top_rest = cmds.pointPosition(top, world=True)
    joint_rest = dict((j, pos(j)) for j in lips.bind_joints())
    cmds.setAttr(mesh + "_BS.w[0]", 1)
    assert_close(cmds.pointPosition(top, world=True), (top_rest[0], top_rest[1] + LIFT, top_rest[2]),
                 "game safe: no double transform", 0.02)
    for joint, value in joint_rest.items():
        assert_close(pos(joint), value, "game safe joints stay at rest without control motion", 0.01)
    cmds.setAttr("C_lipsUpper_CTL.translateY", 1)
    assert cmds.pointPosition(top, world=True)[1] > top_rest[1] + LIFT + 0.7


def test_edge_ribbon_open_chain_mirrors():
    rig()
    plane = cmds.polyPlane(name="brow_GEO", width=12, height=4, subdivisionsX=12, subdivisionsY=4, axis=(0, 0, 1),
                           constructionHistory=False)[0]
    cmds.xform(plane, translation=(0, 170, 10))
    chain = []
    for edge in cmds.ls(plane + ".e[*]", flatten=True):
        points = [cmds.pointPosition(v, world=True) for v in
                  cmds.ls(cmds.polyListComponentConversion(edge, toVertex=True), flatten=True)]
        if all(abs(p[1] - 170) < 1e-3 and 1.5 < p[0] < 5.5 for p in points):
            chain.append(edge)
    brow = EdgeRibbon.build(base="C_jawChin_CTL", edges=chain, name="brow", control_count=3, joint_count=5,
                            control_shape="cube")
    assert brow.side == "L"
    other = brow.mirror
    assert other is not None and other.side == "R"
    assert cmds.objExists("R_brow01_CTL") and cmds.objExists("L_brow01_CTL")
    assert_close(pos("R_brow01_CTL"), (-pos("L_brow01_CTL")[0],) + tuple(pos("L_brow01_CTL")[1:]),
                 "mirrored control")
    assert all(name.startswith("R_") for name in (scene.short(j) for j in other.bind_joints()))


def test_edge_ribbon_lower_lip_chain_follows_the_jaw():
    """An open chain along the lower lip only: every joint between its ends follows the jaw fully."""
    rig()
    mesh, loop = mouth_mesh()
    lower = []
    for edge in loop:
        vertices = cmds.ls(cmds.polyListComponentConversion(edge, toVertex=True), flatten=True)
        if all(cmds.pointPosition(v, world=True)[1] < MOUTH[1] + 0.01 for v in vertices):
            lower.append(edge)
    lips = EdgeRibbon.build(base="C_jawChin_CTL", edges=lower, name="lowLip", joint_count=9, control_count=5)
    joints = lips.bind_joints()
    rest = dict((j, pos(j)[1]) for j in joints)
    cmds.setAttr("C_jawChin_CTL.translateY", -2)
    drops = [rest[j] - pos(j)[1] for j in joints]
    middle = drops[len(drops) // 2]
    assert middle > 0.3, ("the lower lip follows the jaw", middle)
    # past the corner falloff, the joints next to the ends follow like the middle (none is taken for upper lip)
    assert all(d > 0.0 for d in drops), [round(d, 3) for d in drops]
    assert min(drops[2:-2]) > middle * 0.8, [round(d, 3) for d in drops]


def _distance_to_loop(point, loop_points):
    """Closest distance from ``point`` to the closed polyline through ``loop_points``."""
    best = None
    for i, a in enumerate(loop_points):
        b = loop_points[(i + 1) % len(loop_points)]
        ab = [y - x for x, y in zip(a, b)]
        ap = [y - x for x, y in zip(a, point)]
        t = max(0.0, min(1.0, sum(x * y for x, y in zip(ap, ab)) / sum(x * x for x in ab)))
        closest = [x + t * y for x, y in zip(a, ab)]
        distance = sum((x - y) ** 2 for x, y in zip(closest, point)) ** 0.5
        best = distance if best is None else min(best, distance)
    return best


def test_edge_ribbon_sits_on_the_edges():
    from jeffy.setups.core import edges as edge_tools
    before = rig()
    mesh, loop = mouth_mesh()
    _ids, loop_points, closed = edge_tools.ordered_loop(loop)
    assert closed
    lips = EdgeRibbon.build(base="C_jawChin_CTL", edges=loop, joint_count=24)
    assert_no_pop(before)
    joints = lips.bind_joints()
    nodes = joints + [c for c in lips.controls.values() if not c.endswith("Master_CTL")]
    off = max(_distance_to_loop(pos(node), loop_points) for node in nodes)
    assert off < 1e-3, ("linear: the controls and joints sit on the edges", off)
    shape = cmds.listRelatives("C_lipsMaster_CTL", shapes=True)[0]
    assert cmds.getAttr(shape + ".degree") == 1, "the master outline is linear too"
    cvs = cmds.getAttr(shape + ".spans") + cmds.getAttr(shape + ".degree")
    assert cvs == 17, ("16 outline points by default (closed: the first one repeated)", cvs)
    rest_top = max(cmds.pointPosition(shape + ".cv[%d]" % i, world=True)[1] for i in range(cvs))
    cmds.setAttr(mesh + "_BS.w[0]", 1)
    lifted = max(cmds.pointPosition(shape + ".cv[%d]" % i, world=True)[1] for i in range(cvs))
    assert lifted > rest_top + LIFT * 0.9, ("the outline follows the blendShape", lifted - rest_top)
    cmds.setAttr(mesh + "_BS.w[0]", 0)

    # still no double transformation
    skin_ring_to(lips, mesh)
    lips.connect_skin()
    top = top_vertex(mesh)
    top_rest = cmds.pointPosition(top, world=True)
    cmds.setAttr(mesh + "_BS.w[0]", 1)
    assert_close(cmds.pointPosition(top, world=True), (top_rest[0], top_rest[1] + LIFT, top_rest[2]),
                 "no double transformation", 0.02)
    cmds.setAttr(mesh + "_BS.w[0]", 0)

    # a setup stored with the retired Curve option still rebuilds, still exactly on the edges
    lips = lips.rebuild(options={"curve": "cubic"})
    off = max(_distance_to_loop(pos(joint), loop_points) for joint in lips.bind_joints())
    assert off < 1e-3, ("still on the edges after a rebuild", off)


def cartoon_face(name="toon_GEO"):
    """A flat face (normal +Z) with a lip loop pointed at the corners, and a blendShape with two targets:
    0 stretches the mouth wide and almost closes it (the lips 0.2 of a row apart), 1 makes it a round O."""
    import math
    mesh = cmds.polyPlane(name=name, width=10, height=10, subdivisionsX=6, subdivisionsY=6, axis=(0, 0, 1),
                          constructionHistory=False)[0]
    cmds.xform(mesh, translation=MOUTH)
    step = 10.0 / 6
    grid = {}
    for vertex in cmds.ls(mesh + ".vtx[*]", flatten=True):
        x, y, _z = cmds.pointPosition(vertex, world=True)
        grid[int(vertex.split("[")[1][:-1])] = (int(round((x - MOUTH[0]) / step)), int(round((y - MOUTH[1]) / step)))
    ring = set(i for i, g in grid.items() if max(abs(c) for c in g) == 1)
    names = set("%s.vtx[%d]" % (mesh, i) for i in ring)
    loop = [e for e in cmds.ls(mesh + ".e[*]", flatten=True)
            if set(cmds.ls(cmds.polyListComponentConversion(e, toVertex=True), flatten=True)) <= names]
    for i in ring:  # pointed corners, like real lips
        gx, gy = grid[i]
        if gy == 0:
            cmds.move(gx * step * 0.6, 0, 0, "%s.vtx[%d]" % (mesh, i), relative=True, worldSpace=True)
    targets = []
    for label in ("Toon", "O"):
        target = cmds.duplicate(mesh, name=name + label)[0]
        for i, (gx, gy) in grid.items():
            if max(abs(gx), abs(gy)) > 1:
                continue
            vertex = "%s.vtx[%d]" % (target, i)
            if label == "Toon":
                dy = -0.9 * step * gy  # top row down, bottom row up: nearly closed
                cmds.move(gx * step * 0.8, dy, 0, vertex, relative=True, worldSpace=True)  # and much wider
            elif (gx, gy) != (0, 0):
                angle = math.atan2(gy, gx)
                cmds.move(MOUTH[0] + math.cos(angle) * step * 1.6, MOUTH[1] + math.sin(angle) * step * 1.6,
                          MOUTH[2], vertex, absolute=True, worldSpace=True)
        targets.append(target)
    cmds.blendShape(targets, mesh, name=name + "_BS")
    cmds.delete(targets)
    cmds.skinCluster("C_head_JNT", "C_jaw_JNT", mesh, toSelectedBones=True, name=name + "_SKN")
    cmds.skinPercent(name + "_SKN", mesh + ".vtx[*]", transformValue=[("C_head_JNT", 1.0)])
    return mesh, loop, ["%s.vtx[%d]" % (mesh, i) for i in sorted(ring)]


def _axis(node, index):
    m = cmds.xform(node, query=True, worldSpace=True, matrix=True)
    v = m[index * 4:index * 4 + 3]
    length = sum(x * x for x in v) ** 0.5
    return [x / length for x in v]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def test_edge_ribbon_cartoony_stretch_follow_modes():
    rig()
    mesh, loop, ring = cartoon_face()
    lips = EdgeRibbon.build(base="C_jawChin_CTL", edges=loop, name="toon", master=False, control_count=8,
                            joint_count=16)
    ctls = sorted(lips.controls.values())
    rest = dict((c, pos(c)) for c in ctls)
    cmds.setAttr(mesh + "_BS.w[0]", 1)

    # along lip (default): every control keeps facing out of the face and aims along the loop
    for ctl in ctls:
        assert _dot(_axis(ctl, 2), (0.0, 0.0, 1.0)) > 0.999 or _dot(_axis(ctl, 2), (0.0, 0.0, -1.0)) > 0.999, \
            (ctl, _axis(ctl, 2))
        assert abs(_axis(ctl, 0)[2]) < 1e-3, (ctl, "X stays in the face's plane")
    upper = "C_toonUpper_CTL"
    if cmds.objExists(upper):
        # the middle of the upper lip runs straight across: its X stays horizontal
        assert abs(_axis(upper, 0)[1]) < 0.02, ("the upper lip control doesn't tilt", _axis(upper, 0))
        assert pos(upper)[1] < rest[upper][1] - 1.0, "it follows the blendShape down"

    # skin every vertex to its nearest bind joint: still no double transformation on a huge stretch
    skin = mesh + "_SKN"
    joints = lips.bind_joints()
    cmds.setAttr(mesh + "_BS.w[0]", 0)
    for joint in joints:
        cmds.skinCluster(skin, edit=True, addInfluence=joint, weight=0.0)
    for vertex in ring:
        point = cmds.pointPosition(vertex, world=True)
        nearest = min(joints, key=lambda j: sum((a - b) ** 2 for a, b in zip(pos(j), point)))
        cmds.skinPercent(skin, vertex, transformValue=[(nearest, 1.0)], zeroRemainingInfluences=True)
    lips.connect_skin()
    cmds.setAttr(skin + ".envelope", 0)
    cmds.setAttr(mesh + "_BS.w[0]", 1)
    shaped = [cmds.pointPosition(v, world=True) for v in ring]
    cmds.setAttr(skin + ".envelope", 1)
    for vertex, expected in zip(ring, shaped):
        assert_close(cmds.pointPosition(vertex, world=True), expected, "no double transformation", 1e-3)

    # mouth nearly closed: moving the upper lip control moves the upper lip, not the lower one
    if cmds.objExists(upper):
        top = [v for v in ring if cmds.pointPosition(v, world=True)[1] > MOUTH[1] + 0.05]
        bottom = [v for v in ring if cmds.pointPosition(v, world=True)[1] < MOUTH[1] - 0.05]
        before = dict((v, cmds.pointPosition(v, world=True)) for v in top + bottom)
        cmds.setAttr(upper + ".translateY", 0.5)
        moved_top = max(cmds.pointPosition(v, world=True)[1] - before[v][1] for v in top)
        moved_bottom = max(abs(cmds.pointPosition(v, world=True)[1] - before[v][1]) for v in bottom)
        assert moved_top > 0.3, moved_top
        assert moved_bottom < 0.05, ("the lower lip stays", moved_bottom)
        cmds.setAttr(upper + ".translateY", 0)

    # position only: the controls keep their rest orientation
    cmds.setAttr(mesh + "_BS.w[0]", 0)
    lips = lips.rebuild(options={"follow": "position only"})
    cmds.setAttr(mesh + "_BS.w[0]", 1)
    for ctl in lips.controls.values():
        for index in range(3):
            assert abs(abs(_dot(_axis(ctl, index), [1.0 if k == index else 0.0 for k in range(3)])) - 1) < 1e-3, \
                (ctl, index, _axis(ctl, index))


def _loop_now(mesh, loop):
    """The loop's current points, in loop order."""
    from jeffy.setups.core import edges as edge_tools
    ids, _points, _closed = edge_tools.ordered_loop(loop)
    return [cmds.pointPosition("%s.vtx[%d]" % (mesh, i), world=True) for i in ids]


def _turn(node, before):
    import math
    now = cmds.xform(node, query=True, worldSpace=True, matrix=True)
    worst = 0.0
    for i in range(3):
        a, b = before[i * 4:i * 4 + 3], now[i * 4:i * 4 + 3]
        d = _dot(a, b) / (_dot(a, a) * _dot(b, b)) ** 0.5
        worst = max(worst, math.degrees(math.acos(max(-1.0, min(1.0, d)))))
    return worst


def test_edge_ribbon_split_lips_follow_the_loop_exactly():
    rig()
    mesh, loop, ring = cartoon_face()
    lips = EdgeRibbon.build(base="C_jawChin_CTL", edges=loop, name="toon", control_count=8, joint_count=16)
    names = [scene.short(c) for c in lips.controls.values()]
    corners = [n for n in names if "Corner" in n]
    assert sorted(corners) == ["L_toonCorner_CTL", "R_toonCorner_CTL"], names  # one control per corner
    ctls = [c for c in lips.controls.values() if not scene.short(c).endswith("Master_CTL")]
    joints = lips.bind_joints()
    rest = dict((n, cmds.xform(n, query=True, worldSpace=True, matrix=True)) for n in joints)

    # every control and bind joint stays exactly on the edge loop: wide + closed, and a round O
    for weights in ((1, 0), (0, 1), (0.5, 0.5)):
        for target, weight in enumerate(weights):
            cmds.setAttr("%s_BS.w[%d]" % (mesh, target), weight)
        now = _loop_now(mesh, loop)
        off = max(_distance_to_loop(pos(node), now) for node in joints + ctls)
        assert off < 1e-3, (weights, "on the edge loop", off)
    cmds.setAttr(mesh + "_BS.w[1]", 0)
    cmds.setAttr(mesh + "_BS.w[0]", 1)
    turned = max(_turn(j, rest[j]) for j in joints)
    assert turned < 100, ("closed mouth: no joint flips", turned)

    # the corner control drives both lips
    upper = [j for j in joints if "Upper" in j]
    lower = [j for j in joints if "Lower" in j]
    corner_side = [j for j in upper + lower if j.startswith("L_")]
    before = dict((j, pos(j)) for j in corner_side)
    cmds.setAttr("L_toonCorner_CTL.translateY", 0.5)
    moved = dict((j, pos(j)[1] - before[j][1]) for j in corner_side)
    assert any(moved[j] > 0.05 for j in corner_side if j in upper), moved
    assert any(moved[j] > 0.05 for j in corner_side if j in lower), moved
    cmds.setAttr("L_toonCorner_CTL.translateY", 0)

    # game safe: the same skin result with plain bindPreMatrix
    cmds.setAttr(mesh + "_BS.w[0]", 0)
    skin = mesh + "_SKN"
    for joint in joints:
        cmds.skinCluster(skin, edit=True, addInfluence=joint, weight=0.0)
    for vertex in ring:
        point = cmds.pointPosition(vertex, world=True)
        nearest = min(joints, key=lambda j: sum((a - b) ** 2 for a, b in zip(pos(j), point)))
        cmds.skinPercent(skin, vertex, transformValue=[(nearest, 1.0)], zeroRemainingInfluences=True)
    lips = lips.rebuild(options={"game_safe": True})
    cmds.setAttr(skin + ".envelope", 0)
    cmds.setAttr(mesh + "_BS.w[1]", 1)
    shaped = [cmds.pointPosition(v, world=True) for v in ring]
    cmds.setAttr(skin + ".envelope", 1)
    for vertex, expected in zip(ring, shaped):
        assert_close(cmds.pointPosition(vertex, world=True), expected, "game safe: no double transformation", 1e-3)


def test_edge_ribbon_built_while_a_shape_is_on():
    rig()
    mesh, loop, _ring = cartoon_face()
    cmds.setAttr(mesh + "_BS.w[1]", 1)  # the O is dialed in while building
    lips = EdgeRibbon.build(base="C_jawChin_CTL", edges=loop, name="toon")
    nodes = lips.bind_joints() + [c for c in lips.controls.values() if not c.endswith("Master_CTL")]
    assert max(_distance_to_loop(pos(n), _loop_now(mesh, loop)) for n in nodes) < 1e-3, "on the O"
    cmds.setAttr(mesh + "_BS.w[1]", 0)
    assert max(_distance_to_loop(pos(n), _loop_now(mesh, loop)) for n in nodes) < 1e-3, "back on the neutral"
    for ctl in lips.controls.values():
        for attr in ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"):
            assert abs(cmds.getAttr(ctl + "." + attr)) < 1e-6, (ctl, attr)


def test_edge_ribbon_centre_control_moves_joints_evenly():
    rig()
    mesh, loop, _ring = cartoon_face()
    lips = EdgeRibbon.build(base="C_jawChin_CTL", edges=loop, name="toon", follow="position only", joint_count=16)
    joints = lips.bind_joints()
    rest = dict((j, pos(j)) for j in joints)
    cmds.setAttr("C_toonUpper_CTL.translateY", 2.0)
    centre = "C_toonUpper_JNT"
    moved = [a - b for a, b in zip(pos(centre), rest[centre])]
    assert abs(moved[0]) < 1e-3 and moved[1] > 1.5, ("the centre joint goes straight up", moved)
    assert abs(cmds.xform(centre, query=True, worldSpace=True, rotation=True)[2]) < 0.5, "and doesn't tilt"
    left = [j for j in joints if j.startswith("L_toonUpper")]
    right = [j.replace("L_", "R_", 1) for j in left]
    for a, b in zip(left, right):  # both sides move alike
        da = [x - y for x, y in zip(pos(a), rest[a])]
        db = [x - y for x, y in zip(pos(b), rest[b])]
        assert abs(da[1] - db[1]) < 1e-3 and abs(da[0] + db[0]) < 1e-3, (a, da, db)
