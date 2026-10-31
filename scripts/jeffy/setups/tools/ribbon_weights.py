"""Weights to Ribbon: move a chain's skin weights onto its Ribbon joints, evenly along each bone.

The Ribbon puts its joints at fractions of each bone (0, 1/5 ... 4/5), so
the chain becomes a row of **stations**::

    Ribbon01 (0.0) ... Ribbon05 (0.8) | Ribbon06 (1.0) ... Ribbon10 (1.8) | end joint (2.0)

For every vertex, each chain bone's weight is split linearly between the two
stations around the vertex's position **along that bone** (projected on the
bone, so a wide mesh splits by length, not by distance to a joint):

* bone 1's weight only reaches Ribbon01-06, bone 2's only Ribbon06-10 and the
  end joint (the tip fades into it): the blend painted at the elbow is kept,
* every other influence is untouched and the totals stay the same, so the
  mesh doesn't move at rest,
* the chain bones stay in the skin with 0 weight (paint back if needed).

Rest positions come from the skin (Orig shape, ``bindPreMatrix``), so it
works while the rig is posed, once the ribbon joints are in the skin.
"""

from maya import cmds
from maya.api import OpenMaya as om

from jeffy.core import dag, mathlib, naming
from jeffy.deformers import skin as skin_tools
from jeffy.setups.core import controls, scene
from jeffy.setups.core.schema import SetupError
from jeffy.setups.tools import common

EPSILON = 1e-6
REST_TOLERANCE = 1e-3


def find_ribbon(setup):
    """The Ribbon of ``setup``: the setup itself, or the Ribbon layer on a limb / chain."""
    if setup is None:
        return None
    if setup.TYPE == "ribbon":
        return setup
    for layer in setup.layers():
        if layer.TYPE == "ribbon":
            return layer
    return None


def split(value, values):
    """``[(index, share)]``: ``value`` between the two neighbours in the sorted ``values`` (linear)."""
    if value <= values[0]:
        return [(0, 1.0)]
    if value >= values[-1]:
        return [(len(values) - 1, 1.0)]
    for index in range(len(values) - 1):
        low, high = values[index], values[index + 1]
        if low <= value <= high:
            span = high - low
            share = (value - low) / span if span > EPSILON else 0.0
            if share <= EPSILON:
                return [(index, 1.0)]
            if share >= 1.0 - EPSILON:
                return [(index + 1, 1.0)]
            return [(index, 1.0 - share), (index + 1, share)]
    return [(len(values) - 1, 1.0)]


def stations(ribbon):
    """``(chain joints, [(station, joint)])``: the ribbon joints at bone fractions, then the chain's end joint."""
    if ribbon.base is None:
        raise SetupError("%s has no limb or chain under it" % ribbon.describe())
    chain = [joint for joint, _output in common.chain_outputs(ribbon.base)]
    if len(chain) < 2:
        raise SetupError("%s: its chain has fewer than two joints" % ribbon.describe())
    found = {}
    for output in ribbon.outputs.values():
        key = controls.key_of(output) or ""
        if not key.startswith("s") or "_" not in key:
            continue
        segment, index = (int(part) for part in key[1:].split("_", 1))
        joints = cmds.listConnections("%s.%s" % (output, scene.OUTPUT_JOINT_ATTR), source=True,
                                      destination=False) or []
        if joints:
            found.setdefault(segment, {})[index] = joints[0]
    result = []
    for segment in sorted(found):
        count = max(found[segment]) + 1
        for index in sorted(found[segment]):
            result.append((segment + float(index) / count, found[segment][index]))
    if not result:
        raise SetupError("%s has no ribbon joints" % ribbon.describe())
    result.append((float(len(chain) - 1), chain[-1]))
    return chain, result


def _rest_points(skin):
    """World positions of the skinned mesh before the skin (its input geometry at bind)."""
    selection = om.MSelectionList()
    selection.add(skin + ".input[0].inputGeometry")
    data = selection.getPlug(0).asMObject()
    if not data.hasFn(om.MFn.kMesh):
        raise SetupError("%s: Weights to ribbon works on meshes only" % skin)
    geometry = om.MMatrix(cmds.getAttr(skin + ".geomMatrix"))
    return [list(point * geometry)[:3] for point in om.MFnMesh(data).getPoints(om.MSpace.kObject)]


def _bind_matrix(skin, logical, joint):
    """World matrix of ``joint`` when the skin was bound (inverse ``bindPreMatrix``), else where it is now."""
    index = logical.get(dag.long_name(joint))
    if index is None:
        return cmds.xform(joint, query=True, worldSpace=True, matrix=True)
    return mathlib.inverse(cmds.getAttr("%s.bindPreMatrix[%d]" % (skin, index)))


def _check_at_rest(skin, logical, chain):
    """New influences are bound where they are now: the chain must be at its bind pose for that."""
    for joint in chain:
        if dag.long_name(joint) not in logical:
            continue
        now = cmds.xform(joint, query=True, worldSpace=True, matrix=True)
        bound = _bind_matrix(skin, logical, joint)
        if any(abs(a - b) > REST_TOLERANCE for a, b in zip(now, bound)):
            raise SetupError("%s is posed: the ribbon joints are added to %s where they are now, so put the rig "
                             "at rest first (Reset Pose), then transfer" % (naming.short_name(joint), skin))


def _skins(movers, meshes):
    if meshes:
        result = []
        for mesh in meshes:
            skin = skin_tools.find_skin_cluster(mesh)
            if not skin:
                raise SetupError("%s has no skinCluster" % mesh)
            result.append(skin)
        return result
    wanted = set(dag.long_name(joint) for joint in movers)
    return [skin for skin in cmds.ls(type="skinCluster") or []
            if wanted.intersection(dag.long_name(i) for i in skin_tools.get_influences(skin))]


def _write(skin, logical_of, changes):
    """``changes``: ``{vertex: {influence position: weight}}``, written with setAttr (undoable)."""
    normalize = cmds.getAttr(skin + ".normalizeWeights")
    cmds.setAttr(skin + ".normalizeWeights", 0)
    try:
        for vertex, row in changes.items():
            for position, weight in row.items():
                cmds.setAttr("%s.weightList[%d].weights[%d]" % (skin, vertex, logical_of[position]), weight)
    finally:
        cmds.setAttr(skin + ".normalizeWeights", normalize)


def transfer(ribbon, meshes=None, components=None):
    """Move the chain's weights onto the ribbon joints. Returns ``[(mesh, vertices changed)]``.

    :param meshes: the skinned meshes (default: every skin the chain bones are in)
    :param components: selected vertices: only those change
    """
    chain, station_list = stations(ribbon)
    movers = chain[:-1]
    values = [value for value, _joint in station_list]
    station_joints = [joint for _value, joint in station_list]
    limits = None
    if components:
        limits = dict((dag.long_name(mesh), set(indices)) for mesh, indices in skin_tools._vertex_selection(components))
    report = []
    for skin in _skins(movers, meshes):
        geometry = cmds.skinCluster(skin, query=True, geometry=True)[0]
        mesh = cmds.listRelatives(geometry, parent=True, fullPath=True)[0]
        if limits is not None and dag.long_name(mesh) not in limits:
            continue
        logical = skin_tools._logical_indices(skin)
        missing = [joint for joint in station_joints if dag.long_name(joint) not in logical]
        if missing:
            _check_at_rest(skin, logical, chain)
            skin_tools.add_influences(mesh, missing)
            logical = skin_tools._logical_indices(skin)
        flat, names, count = skin_tools.get_weights(skin)
        width = len(names)
        position_of = dict((dag.long_name(name), position) for position, name in enumerate(names))
        logical_of = [logical[dag.long_name(name)] for name in names]
        mover_positions = [position_of.get(dag.long_name(joint)) for joint in movers]
        station_positions = [position_of[dag.long_name(joint)] for joint in station_joints]
        bones = []
        for index, joint in enumerate(movers):
            start = mathlib.get_translation(_bind_matrix(skin, logical, joint))
            end = mathlib.get_translation(_bind_matrix(skin, logical, chain[index + 1]))
            bones.append((start, mathlib.sub(end, start)))
        candidates = range(count) if limits is None else sorted(limits[dag.long_name(mesh)])
        points = None
        changes = {}
        for vertex in candidates:
            row = flat[vertex * width:(vertex + 1) * width]
            if not any(p is not None and row[p] > EPSILON for p in mover_positions):
                continue
            if points is None:
                points = _rest_points(skin)
            new = {}
            for index, position in enumerate(mover_positions):
                if position is None or row[position] <= EPSILON:
                    continue
                weight = row[position]
                start, direction = bones[index]
                length = mathlib.dot(direction, direction)
                along = mathlib.dot(mathlib.sub(points[vertex], start), direction) / length if length else 0.0
                along = min(max(along, 0.0), 1.0)
                for station, share in split(index + along, values):
                    target = station_positions[station]
                    new[target] = new.get(target, row[target]) + weight * share
                new[position] = 0.0
            changes[vertex] = new
        if changes:
            _write(skin, logical_of, changes)
        report.append((naming.short_name(mesh), len(changes)))
        print("[Jeffy] Weights to ribbon: %s, %d vertices moved onto %d ribbon joints"
              % (naming.short_name(mesh), len(changes), len(station_joints) - 1))
        limit = cmds.getAttr(skin + ".maxInfluences")
        if changes and cmds.getAttr(skin + ".maintainMaxInfluences"):
            over = sum(1 for vertex in changes
                       if sum(1 for w in _row_after(flat, width, vertex, changes[vertex]) if w > EPSILON) > limit)
            if over:
                cmds.warning("[Jeffy] %s: %d vertices now have more than %d influences (the ribbon split adds one "
                             "per bone). Skin > Prune or raise Max Influences if your engine needs it"
                             % (naming.short_name(mesh), over, limit))
    if not report:
        raise SetupError("No skinned mesh has weights on %s" % ", ".join(naming.short_name(j) for j in movers))
    return report


def _row_after(flat, width, vertex, new):
    row = list(flat[vertex * width:(vertex + 1) * width])
    for position, weight in new.items():
        row[position] = weight
    return row
