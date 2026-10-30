"""A setup's node graph: its main nodes and a left to right layout by dependency.

Used by the Node Editor tabs (:mod:`jeffy.ui.setup_belt.node_tabs`). Works
headless (no UI), so it is tested with mayapy.

Main nodes, from the setup's tag:

* **inputs**: its controls, plus what its anchors follow (the parent setup's
  output, root / world controls...) and, for layers, the base controls they use,
* **systems**: the matrix nodes the build created (``multMatrix``,
  ``blendMatrix``, ``aimMatrix``, ``decompose`` / ``composeMatrix``,
  ``pickMatrix``, ``choice``, ``uvPin``...) and its hidden joints, IK handles,
  ribbons and curves, including its attach / space networks,
* **outputs**: its output transforms,
* **joints**: the bind joints it drives.

The scalar math between them (``multDL``, ``plusMinusAverage``, conditions,
clamps...), shapes, controller tags, unit conversions and plain hierarchy
groups are hidden; dependencies are traced *through* the hidden nodes, so the
order stays right. Columns: inputs first, every other node one column right of
the deepest main node it depends on, bind joints last.
"""

import collections

from maya import cmds

from jeffy.core import naming
from jeffy.setups.core import attach
from jeffy.setups.core import tag as tag_module

ROLES = ("input", "system", "output", "joint")
#: system node types shown in the graph (the matrix flow); everything else is traced through
MAIN_TYPES = ("multMatrix", "blendMatrix", "aimMatrix", "decomposeMatrix", "composeMatrix", "pickMatrix",
              "inverseMatrix", "choice", "uvPin", "proximityPin", "wtAddMatrix", "holdMatrix", "parentMatrix",
              "remapValue", "multDL", "addDL", "multDoubleLinear", "addDoubleLinear",
              "joint", "ikHandle", "transform", "nurbsSurface", "nurbsCurve", "curveFromSurfaceIso", "motionPath",
              "pointOnCurveInfo", "closestPointOnSurface")
SKIPPED_TYPES = ("unitConversion", "controller", "network", "nodeGraphEditorInfo", "objectSet", "ikEffector")
#: graphviz "plain" units (inches) between columns / rows
COLUMN_SPACING = 3.0
ROW_SPACING = 0.75
MAX_TRACE = 5000


def tab_name(setup):
    """``L_arm_IkFkLimb``: side, name and tool."""
    return naming.legalize("%s_%s" % (naming.compose(setup.name, setup.side), type(setup).__name__))


def _short(node):
    return (cmds.ls(node) or [node])[0]


def _is_shape(node):
    return cmds.objectType(node, isAType="shape")


def _connected(node):
    """Does ``node`` have DG connections other than message links / hierarchy?"""
    for plug in cmds.listConnections(node, connections=True, plugs=True, skipConversionNodes=True) or []:
        if not plug.endswith(".message") and ".jeffy" not in plug:
            return True
    return False


def _system_type(node):
    """The type deciding whether a created node is shown (a transform's shape type when it has one)."""
    node_type = cmds.nodeType(node)
    if node_type == "transform":
        shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
        if shapes:
            return cmds.nodeType(shapes[0])
    return node_type


def setup_nodes(setup):
    """``{node: role}`` of a setup's main nodes (ordered: inputs first)."""
    result = collections.OrderedDict()
    controls = set(_short(node) for node in setup.controls.values())
    outputs = set(_short(node) for node in setup.outputs.values())
    driven = set(_short(node) for node in setup.driven)

    def add(node, role):
        if not node or not cmds.objExists(node):
            return
        node = _short(node)
        if node in result or cmds.nodeType(node) in SKIPPED_TYPES or _is_shape(node):
            return
        result[node] = role

    extra = getattr(setup, "graph_nodes", None)  # wires: what they read and what they drive
    extra = extra() if extra else []
    for node, role in extra:
        if role == "input":
            add(node, "input")
    for node in setup.controls.values():
        add(node, "input")
    for definition, _zero, _control in setup.anchors():
        for _label, target in attach.targets_of(setup, definition):
            add(target, "input")
    if setup.base is not None:
        for node in setup.slot_nodes(setup.SLOTS[0].key):
            add(node, "input")
    for node in created_nodes(setup):
        if node in controls or node in outputs or node in driven or _is_shape(node):
            continue
        node_type = _system_type(node)
        if node_type not in MAIN_TYPES:
            continue
        if node_type == "transform" and not _connected(node):
            continue  # a plain hierarchy group (ZRO, OFF, setup groups)
        add(node, "system")
    for node in setup.outputs.values():
        add(node, "output")
    for node, role in extra:
        if role == "output":
            add(node, "output")
    for node in setup.driven:
        add(node, "joint")
    return result


def created_nodes(setup):
    """Every node the setup's build and its anchors created (short names)."""
    nodes = tag_module.get_nodes(setup.tag, "owned") + tag_module.get_nodes(setup.tag, "attach")
    return [_short(node) for node in nodes if cmds.objExists(node)]


def _direct_sources(node):
    pairs = cmds.listConnections(node, source=True, destination=False, connections=True, plugs=True,
                                 skipConversionNodes=True) or []
    result = []
    for source in pairs[1::2]:
        if source.endswith(".message"):
            continue  # bookkeeping links (setup tags, control offsets), not dependencies
        owner = _short(source.split(".")[0])
        if owner not in result:
            result.append(owner)
    return result


def _sources(node, members, hidden):
    """Main nodes feeding ``node``, directly or through hidden (scalar) nodes of the setup."""
    result, seen, queue = [], set([node]), [node]
    while queue and len(seen) < MAX_TRACE:
        current = queue.pop()
        for source in _direct_sources(current):
            if source in seen:
                continue
            seen.add(source)
            if source in members:
                result.append(source)
            elif source in hidden:
                queue.append(source)
    return result


def columns(nodes, hidden=()):
    """``{node: column}``: inputs 0, everything else by its longest path from them, joints last.

    A node goes right of all it depends on: matrix nodes after the controls,
    outputs after their matrix nodes, what follows an output (settings
    control, connector lines...) after the output. Bind joints go in the last
    column; a parent joint feeding its child's driving nodes is the only link
    that points back.
    """
    members = set(nodes)
    hidden = set(hidden) - members
    sources = dict((node, _sources(node, members, hidden)) for node in nodes)
    depth = {}

    def visit(node, stack):
        if node in depth:
            return depth[node]
        if nodes[node] == "input":
            depth[node] = 0
            return 0
        stack.add(node)
        best = 0
        for source in sources[node]:
            if source in stack or nodes.get(source) == "joint":
                continue
            best = max(best, visit(source, stack))
        stack.discard(node)
        depth[node] = best + 1
        return depth[node]

    for node, role in nodes.items():
        if role != "joint":
            visit(node, set())
    last = max(list(depth.values()) + [0])
    for node, role in nodes.items():
        if role == "joint":
            depth[node] = last + 1
    return depth, sources


def layout(setup):
    """``{node: (x, y)}`` in graphviz plain units, columns left to right, rows top down.

    Inside a column, nodes are ordered by the average row of what feeds them,
    so connections stay as straight as possible.
    """
    nodes = setup_nodes(setup)
    if not nodes:
        return collections.OrderedDict()
    depth, sources = columns(nodes, created_nodes(setup))
    by_column = collections.defaultdict(list)
    for node in nodes:
        by_column[depth[node]].append(node)
    rows = {}
    positions = collections.OrderedDict()
    for column in sorted(by_column):
        members = by_column[column]

        def weight(node, members=members):
            fed = [rows[s] for s in sources[node] if s in rows]
            return (sum(fed) / float(len(fed)) if fed else members.index(node), members.index(node))

        for row, node in enumerate(sorted(members, key=weight)):
            rows[node] = row
            positions[node] = (column * COLUMN_SPACING, -row * ROW_SPACING)
    return positions


def edges(setup):
    """``[(source, destination)]`` between a setup's main nodes (traced through hidden ones)."""
    nodes = setup_nodes(setup)
    members = set(nodes)
    hidden = set(created_nodes(setup)) - members
    return [(source, node) for node in nodes for source in _sources(node, members, hidden)]


def plain_format(positions, edge_list=None):
    """Graphviz ``plain`` text placing ``positions`` (what ``nodeEditor -dotFormat`` reads)."""
    if not positions:
        return "graph 1 1 1\nstop\n"
    xs = [x for x, _y in positions.values()]
    ys = [y for _x, y in positions.values()]
    width, height = (max(xs) - min(xs)) + 2.0, (max(ys) - min(ys)) + 1.0
    lines = ["graph 1 %.3f %.3f" % (width, height)]
    bottom = min(ys)
    for node, (x, y) in positions.items():
        lines.append('node "%s" %.3f %.3f 2 0.5 "%s" solid box black lightgrey' % (node, x + 1.0, y - bottom + 0.5,
                                                                                  node))
    for tail, head in edge_list or []:
        if tail in positions and head in positions:
            lines.append('edge "%s" "%s" 0 solid black' % (tail, head))
    lines.append("stop")
    return "\n".join(lines) + "\n"
