"""Rig Doctor: scan a scene for rig problems and report them (no automatic fixing).

Each check returns :class:`Finding` objects: a short text and the nodes to
select. The checks come from real rigs: dead controls, joints that roll around
the bone compared with their parent, unskinned joints and meshes, leftover
utility nodes, "dead" driver chains (utility nodes with no real input still
pinning an attribute), name clashes, rotate values on bind joints at rest, and
broken or parked wires.

The checks work on whole lists of nodes (one ``ls`` / ``listConnections`` per
list), so a scan stays fast on a production scene.
"""

import collections
import math
import re

from maya import cmds

#: math / matrix / utility nodes: a chain made only of these has no real input
UTILITY_TYPES = (
    "multiplyDivide", "plusMinusAverage", "condition", "clamp", "remapValue", "setRange", "reverse", "blendColors",
    "blendTwoAttr", "blendWeighted", "multDoubleLinear", "addDoubleLinear", "multDL", "addDL", "floatMath",
    "multiply", "divide", "sum", "subtract", "negate", "absolute", "clampRange", "floor", "ceil", "round", "power",
    "min", "max", "average", "crossProduct", "dotProduct", "normalize", "length", "distanceBetween", "angleBetween",
    "vectorProduct", "multMatrix", "decomposeMatrix", "composeMatrix", "inverseMatrix", "blendMatrix",
    "pickMatrix", "aimMatrix", "wtAddMatrix", "holdMatrix", "fourByFourMatrix", "pointMatrixMult",
    "pointMatrixMultDL", "quatToEuler", "eulerToQuat", "unitConversion", "choice",
)
#: destinations that don't count as "using" a node (bookkeeping only)
BOOKKEEPING_TYPES = ("nodeGraphEditorInfo", "hyperLayout", "hyperView", "container", "dagContainer", "objectSet",
                     "network")
MAX_CHAIN = 400

Finding = collections.namedtuple("Finding", "check text nodes severity")  # severity: "problem" | "look"

_TYPES = {}


def utility_types():
    """The utility node types this Maya version knows."""
    if "utility" not in _TYPES:
        known = set(cmds.allNodeTypes() or [])
        _TYPES["utility"] = tuple(t for t in UTILITY_TYPES if t in known)
    return _TYPES["utility"]


def is_utility(node):
    return cmds.objExists(node) and cmds.nodeType(node) in utility_types()


def dead_chain(node):
    """The nodes of ``node``'s upstream chain when it is made only of utility nodes (no real input), else ``[]``.

    The Murakami trap: ``multiplyDivide2`` had nothing plugged into it, but its
    output still drove a blendShape weight, pinning it to 0. A chain that
    reaches something real (a control, a joint, an animation curve, time...)
    is alive.
    """
    if not is_utility(node):
        return []
    seen, queue = [node], [node]
    while queue and len(seen) < MAX_CHAIN:
        current = queue.pop()
        for source in cmds.listConnections(current, source=True, destination=False, skipConversionNodes=False) or []:
            if source in seen:
                continue
            if not is_utility(source):
                return []  # something real feeds the chain
            seen.append(source)
            queue.append(source)
    return seen


def driver_text(plug):
    """``None`` when ``plug`` is free, else a sentence naming what drives it (and whether it is a leftover)."""
    sources = cmds.listConnections(plug, source=True, destination=False, plugs=True, skipConversionNodes=True) or []
    if not sources:
        return None
    source = sources[0]
    text = "%s is already driven by %s" % (plug, source)
    dead = dead_chain(source.split(".", 1)[0])
    if dead:
        names = ", ".join(dead[:4]) + ("..." if len(dead) > 4 else "")
        text += ", which has no input of its own (a leftover: %s): delete %s first" % (
            names, "it" if len(dead) == 1 else "them")
    else:
        text += ": disconnect it first"
    return text


# ---------------------------------------------------------------------------
# Pure helpers (unit tested)
# ---------------------------------------------------------------------------
NUMBERED = re.compile(r"_(CTL|JNT|GRP|ZRO|OFF|OUT|GEO|LOC)\d+$")


def numbered_suffix(name):
    """``L_leaf2Bend_CTL1`` -> True: Maya added a number because the name was taken."""
    return bool(NUMBERED.search(name.rsplit("|", 1)[-1]))


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a):
    length = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / length, a[1] / length, a[2] / length)


def _carry(vector, start, end):
    """Rotate ``vector`` by the smallest rotation taking direction ``start`` onto ``end`` (Rodrigues)."""
    start, end = _unit(start), _unit(end)
    axis = _cross(start, end)
    sin = math.sqrt(_dot(axis, axis))
    cos = _dot(start, end)
    if sin < 1e-9:
        return tuple(vector) if cos > 0 else tuple(-v for v in vector)
    axis = (axis[0] / sin, axis[1] / sin, axis[2] / sin)
    cross = _cross(axis, vector)
    along = _dot(axis, vector) * (1 - cos)
    return tuple(vector[i] * cos + cross[i] * sin + axis[i] * along for i in range(3))


def roll_degrees(parent_axes, child_axes, parent_bone, child_bone):
    """How much a joint's frame rolls around its bone compared with its parent's, in degrees (-180..180).

    ``parent_axes`` / ``child_axes``: each joint's X, Y, Z axes in world space;
    ``parent_bone`` / ``child_bone``: the direction of each bone. The parent's
    frame is carried along the bend between the two bones (the smallest
    rotation); what is left, around the child's bone, is the roll. A blend
    between the two frames (a ribbon's middle control) turns by half of it:
    a 90 degree roll makes a 45 degree control.
    """
    child_bone = _unit(child_bone)
    # the parent axis least aligned with its bone is a stable reference
    index = min(range(3), key=lambda i: abs(_dot(_unit(parent_axes[i]), _unit(parent_bone))))
    carried = _carry(_unit(parent_axes[index]), parent_bone, child_bone)
    own = _unit(child_axes[index])

    def flat(vector):
        d = _dot(vector, child_bone)
        return _unit((vector[0] - d * child_bone[0], vector[1] - d * child_bone[1], vector[2] - d * child_bone[2]))

    a, b = flat(carried), flat(own)
    return math.degrees(math.atan2(_dot(_cross(a, b), child_bone), _dot(a, b)))


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
def _short(node):
    return node.rsplit("|", 1)[-1] if node else node


def _setups():
    from jeffy.setups.core import scene

    return [s for s in scene.all_setups() if s is not None]


def _outgoing_uses(nodes, ignore=None):
    """The nodes of ``nodes`` (long names) with at least one real outgoing connection.

    Connections into ``ignore`` nodes (short names) don't count.
    """
    if not nodes:
        return set()
    pairs = cmds.listConnections(nodes, source=False, destination=True, connections=True, plugs=True,
                                 skipConversionNodes=False) or []
    used = set()
    for source, destination in zip(pairs[::2], pairs[1::2]):
        attr = source.split(".", 1)[1] if "." in source else ""
        if attr.startswith("message") or attr.startswith("jeffy"):
            continue
        target = destination.split(".", 1)[0]
        if cmds.nodeType(target) in BOOKKEEPING_TYPES or (ignore and target in ignore):
            continue
        used.add(source.split(".", 1)[0])
    return set(cmds.ls(list(used), long=True) or []) if used else set()


def check_dead_controls(setups):
    """Belt controls that drive nothing: no real outgoing connection, on them or below them.

    Being offered as a space to other controls doesn't count as driving: the
    Hips control of a spine built without a pelvis is only a space option.
    """
    from jeffy.setups.core import controls
    from jeffy.setups.core import tag as tag_module

    spaces = set()
    for setup in setups:
        spaces.update(tag_module.get_nodes(setup.tag, "attach"))
    findings = []
    for setup in setups:
        for ctl in setup.controls.values():
            if not cmds.objExists(ctl):
                continue
            below = cmds.listRelatives(ctl, allDescendents=True, type="transform", fullPath=True) or []
            if any(controls.key_of(node) for node in below):
                continue  # child controls hang from it
            nodes = cmds.ls([ctl] + below, long=True)
            if _outgoing_uses(nodes, ignore=spaces):
                continue
            text = "%s drives nothing (%s)" % (_short(ctl), setup.describe())
            if _outgoing_uses(nodes):
                text += ": it is only offered as a space to other controls"
            findings.append(Finding("dead_controls", text, [ctl], "problem"))
    return findings


def _skeleton_joints(setups):
    """Bind skeleton joints: the rig roots' hierarchies, the joints setups drive, the skin influences."""
    joints = set()
    for setup in setups:
        if setup.TYPE == "rig_base":
            root = setup.slot_node("root_joint")
            if root and cmds.objExists(root):
                joints.update(cmds.ls(root, long=True) or [])
                joints.update(cmds.listRelatives(root, allDescendents=True, type="joint", fullPath=True) or [])
        driven = [joint for joint in setup.driven if joint]
        if driven:
            joints.update(cmds.ls(driven, long=True) or [])
    for skin in cmds.ls(type="skinCluster") or []:
        influences = cmds.skinCluster(skin, query=True, influence=True) or []
        if influences:
            joints.update(cmds.ls(influences, type="joint", long=True) or [])
    return sorted(joints)


def _world_axes(node):
    m = cmds.xform(node, query=True, worldSpace=True, matrix=True)
    return [m[0:3], m[4:7], m[8:11]], m[12:15]


def check_joint_rolls(setups, threshold=60.0):
    """Joints whose frame rolls a lot around the bone compared with the parent (``L_LegLeaf3``: about 90)."""
    findings = []
    for joint in _skeleton_joints(setups):
        parent = (cmds.listRelatives(joint, parent=True, fullPath=True, type="joint") or [None])[0]
        children = cmds.listRelatives(joint, children=True, fullPath=True, type="joint") or []
        if not parent or len(children) != 1:
            continue  # needs one bone on each side to compare
        if len(cmds.listRelatives(parent, children=True, type="joint") or []) != 1:
            continue  # the parent is a hub (pelvis, chest, head): it has no single bone to compare with
        p_axes, p_pos = _world_axes(parent)
        c_axes, c_pos = _world_axes(joint)
        _axes, end = _world_axes(children[0])
        parent_bone = [c_pos[i] - p_pos[i] for i in range(3)]
        child_bone = [end[i] - c_pos[i] for i in range(3)]
        if _dot(parent_bone, parent_bone) < 1e-10 or _dot(child_bone, child_bone) < 1e-10:
            continue
        roll = roll_degrees(p_axes, c_axes, parent_bone, child_bone)
        if abs(roll) >= threshold:
            findings.append(Finding("joint_rolls", "%s rolls %d degrees around its bone compared with %s "
                                    "(a blend between them twists by half)"
                                    % (_short(joint), round(roll), _short(parent)), [joint], "look"))
    return findings


def check_unskinned(setups):
    """Joints setups drive that no skin uses, and meshes under the rig's geometry group with no skin."""
    findings = []
    influences = set()
    for skin in cmds.ls(type="skinCluster") or []:
        names = cmds.skinCluster(skin, query=True, influence=True) or []
        if names:
            influences.update(cmds.ls(names, long=True) or [])
    for setup in setups:
        for joint in setup.driven:
            if joint and cmds.objExists(joint) and cmds.ls(joint, long=True)[0] not in influences:
                findings.append(Finding("unskinned", "%s is driven by %s but no skin uses it"
                                        % (_short(joint), setup.describe()), [joint], "look"))
        if setup.TYPE != "rig_base":
            continue
        group = setup.rig_group("geometry")
        if not group or not cmds.objExists(group):
            continue
        for shape in cmds.listRelatives(group, allDescendents=True, type="mesh", fullPath=True) or []:
            if cmds.getAttr(shape + ".intermediateObject"):
                continue
            if not cmds.ls(cmds.listHistory(shape, pruneDagObjects=True) or [], type="skinCluster"):
                mesh = cmds.listRelatives(shape, parent=True, fullPath=True)[0]
                findings.append(Finding("unskinned", "%s (in the rig's geometry) has no skin" % _short(mesh),
                                        [mesh], "look"))
    return findings


def check_leftovers(setups):
    """Utility nodes connected to nothing downstream, and intermediate shapes nothing uses."""
    findings = []
    nodes = cmds.ls(type=list(utility_types()), long=True) or []
    used = _outgoing_uses(nodes)
    for node in nodes:
        if node not in used:
            findings.append(Finding("leftovers", "%s (%s) is connected to nothing downstream"
                                    % (_short(node), cmds.nodeType(node)), [node], "look"))
    shapes = cmds.ls(intermediateObjects=True, shapes=True, long=True) or []
    used = _outgoing_uses(shapes)
    for shape in shapes:
        if shape not in used:
            findings.append(Finding("leftovers", "%s is an intermediate shape nothing uses" % _short(shape),
                                    [shape], "look"))
    return findings


def check_dead_drivers(setups):
    """Attributes driven by utility chains with no real input (``multiplyDivide2`` pinning a weight to 0)."""
    findings = []
    nodes = cmds.ls(type=list(utility_types())) or []
    if not nodes:
        return findings
    has_input = set()
    pairs = cmds.listConnections(nodes, source=True, destination=False, connections=True, plugs=True) or []
    for destination in pairs[::2]:
        has_input.add(destination.split(".", 1)[0])
    seen_targets = set()
    for root in [node for node in nodes if node not in has_input]:
        queue, visited = [root], {root}
        while queue:
            current = queue.pop()
            out = cmds.listConnections(current, source=False, destination=True, connections=True, plugs=True,
                                       skipConversionNodes=False) or []
            for source, destination in zip(out[::2], out[1::2]):
                node = destination.split(".", 1)[0]
                if cmds.nodeType(node) in BOOKKEEPING_TYPES or source.split(".", 1)[1].startswith("message"):
                    continue
                if is_utility(node):
                    if node not in visited:
                        visited.add(node)
                        queue.append(node)
                    continue
                if destination in seen_targets or not dead_chain(current):
                    continue
                seen_targets.add(destination)
                findings.append(Finding("dead_drivers", "%s is pinned by %s, a chain with no real input "
                                        "(a leftover)" % (destination, current), [current, node], "problem"))
    return findings


def check_names(setups):
    """Duplicate short names, and names Maya numbered because they were taken (``_CTL1``)."""
    findings = []
    for node in cmds.ls(dagObjects=True, transforms=True) or []:
        if "|" in node:
            findings.append(Finding("names", "%s: another node has the same short name" % node, [node],
                                    "problem"))
        elif numbered_suffix(node):
            findings.append(Finding("names", "%s: numbered by Maya (the name was taken)" % node, [node], "look"))
    return findings


def check_rest_rotate(setups, tolerance=0.01):
    """Bind joints with rotate values at rest (the rest pose belongs in jointOrient)."""
    from jeffy.setups.core import tag as tag_module

    findings = []
    driven = {}
    for setup in setups:
        rests = tag_module.get_data(setup.tag, "rest", []) or []
        for joint, rest in zip(tag_module.get_nodes(setup.tag, "driven", keep_empty=True), rests):
            if joint and cmds.objExists(joint):
                driven[cmds.ls(joint, long=True)[0]] = rest
    for joint in _skeleton_joints(setups):
        if joint in driven:
            rotate = (driven[joint] or {}).get("rotate") or [0, 0, 0]
        else:
            rotate = cmds.getAttr(joint + ".rotate")[0]
        if any(abs(v) > tolerance for v in rotate):
            findings.append(Finding("rest_rotate", "%s has rotate %s at rest (keep the rest pose in jointOrient)"
                                    % (_short(joint), ", ".join("%.1f" % v for v in rotate)), [joint], "look"))
    return findings


def check_extras(setups):
    """Setups or wires whose nodes are gone, parked wires, constraint nodes, keys on bind joints."""
    from jeffy.setups.core import tag as tag_module
    from jeffy.setups.core import wires

    findings = []
    for setup in setups:
        stored = tag_module.get_data(setup.tag, "slots", {}) or {}
        for slot in setup.SLOTS:
            names = stored.get(slot.key)
            names = names if isinstance(names, list) else ([names] if names else [])
            if names and not setup.slot_nodes(slot.key):
                findings.append(Finding("extras", "%s: its %s (%s) is gone"
                                        % (setup.describe(), slot.label, ", ".join(names)), [setup.tag], "problem"))
    for entry in wires.parked():
        spec = entry["spec"]
        findings.append(Finding("extras", "parked wire %s_%s waits for: %s"
                                % (spec.get("side"), spec.get("name"), ", ".join(entry["depends"])), [], "look"))
    constraints = cmds.ls(type="constraint") or []
    if constraints:
        findings.append(Finding("extras", "%d constraint node(s) in the scene" % len(constraints), constraints,
                                "look"))
    joints = _skeleton_joints(setups)
    keyed = (cmds.listConnections(joints, source=True, destination=False, type="animCurve") or []) if joints else []
    if keyed:
        targets = sorted(set(cmds.listConnections(keyed, source=False, destination=True) or []))
        findings.append(Finding("extras", "keys on bind joints: %s" % ", ".join(_short(t) for t in targets[:8]),
                                targets, "look"))
    return findings


#: (key, label, function), in report order
CHECKS = (
    ("dead_controls", "Dead controls", check_dead_controls),
    ("joint_rolls", "Joint rolls", check_joint_rolls),
    ("unskinned", "Unskinned joints / meshes", check_unskinned),
    ("leftovers", "Leftover nodes", check_leftovers),
    ("dead_drivers", "Dead drivers", check_dead_drivers),
    ("names", "Name clashes", check_names),
    ("rest_rotate", "Rotate at rest", check_rest_rotate),
    ("extras", "Broken links and extras", check_extras),
)


def scan(keys=None):
    """Run the checks (all, or ``keys``). Returns ``[(key, label, findings)]``."""
    setups = _setups()
    return [(key, label, func(setups)) for key, label, func in CHECKS if keys is None or key in keys]
