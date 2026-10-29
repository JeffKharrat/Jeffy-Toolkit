"""Shape memory: belt controls keep the shapes you edited by hand.

When a setup is deleted (Delete, Rebuild, deleting its Rig Base), the shape of
every control you changed since the build is saved in one scene node
(``jeffyShapeMemory``, a hidden ``network`` that belongs to no setup). The next
build of a setup with the same type, name and side gives those controls their
shape back: CVs, colour, line width and *always on top*.

* Only edited controls are remembered. At the end of a build each control
  stores a signature of its shape (``jeffyShapeBuilt``); a control whose shape
  still matches it is left alone, so untouched controls keep following the
  joint lengths and the size option.
* The remembered CVs are in control (object) space. When the setup's ``size``
  option changed between the two builds they are scaled by the ratio.
* Controls whose CVs the build drives (the Edge Ribbon master outline) are
  never remembered.
* When the curve topology is the same, only the CVs move, so connections on
  the shape nodes (visibility of foot pivots...) are kept. Otherwise the shapes
  are replaced and their incoming connections moved onto the new shapes.
* **Remember Shapes** / **Forget Shapes** (SCENE > Utilities) do it by hand on
  the selected controls.

The pure helpers (:func:`signature`, :func:`scaled`, :func:`entry_key`) don't
need Maya and are unit tested.
"""

import hashlib
import json

from maya import cmds

from jeffy.core import attributes

NODE = "jeffyShapeMemory"
DATA_ATTR = "jeffy_shapes"
BUILT_ATTR = "jeffyShapeBuilt"
PRECISION = 4


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def entry_key(setup_type, name, side, control_key):
    """Memory key of one control: ``type|name|side|key``."""
    return "|".join((setup_type or "", name or "", side or "", control_key or ""))


def _rounded(value):
    if isinstance(value, dict):
        return dict((k, _rounded(v)) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return [_rounded(v) for v in value]
    if isinstance(value, float):
        result = round(value, PRECISION)
        return 0.0 if result == 0 else result  # no "-0.0"
    return value


def signature(entry):
    """Short hash of a shape entry (curves, colour, line width, on top). Size is ignored."""
    data = dict((k, v) for k, v in entry.items() if k != "size")
    text = json.dumps(_rounded(data), sort_keys=True)
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]


def scaled(curves, factor):
    """Curves with every point multiplied by ``factor`` (object space, around the control)."""
    if not factor or abs(factor - 1.0) < 1e-9:
        return curves
    result = []
    for curve in curves:
        copy = dict(curve)
        copy["points"] = [[c * factor for c in point] for point in curve["points"]]
        result.append(copy)
    return result


def size_factor(stored_size, current_size):
    try:
        stored, current = float(stored_size), float(current_size)
    except (TypeError, ValueError):
        return 1.0
    if stored <= 0 or current <= 0:
        return 1.0
    return current / stored


def rename_entries(data, setup_type, old_name, old_side, new_name, new_side):
    """``data`` with the entries of one setup moved to a new name / side (existing ones win)."""
    old_prefix = entry_key(setup_type, old_name, old_side, "")
    new_prefix = entry_key(setup_type, new_name, new_side, "")
    if old_prefix == new_prefix:
        return dict(data)
    result = dict(data)
    for key, value in data.items():
        if key.startswith(old_prefix):
            target = new_prefix + key[len(old_prefix):]
            result.setdefault(target, value)
            del result[key]
    return result


# ---------------------------------------------------------------------------
# Scene storage
# ---------------------------------------------------------------------------
def _load():
    if not cmds.objExists(NODE):
        return {}
    text = attributes.get_string(NODE, DATA_ATTR)
    if not text:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        cmds.warning("[Jeffy] %s.%s is not valid JSON, shape memory reset" % (NODE, DATA_ATTR))
        return {}
    return data if isinstance(data, dict) else {}


def _save(data):
    if not data and not cmds.objExists(NODE):
        return
    if not cmds.objExists(NODE):
        cmds.createNode("network", name=NODE, skipSelect=True)
    attributes.set_string(NODE, DATA_ATTR, json.dumps(data, sort_keys=True))


def stored_keys():
    """Every remembered ``type|name|side|key`` (for the UI and tests)."""
    return sorted(_load())


# ---------------------------------------------------------------------------
# Reading / writing controls
# ---------------------------------------------------------------------------
def _shapes(node):
    from jeffy.controls import shapes

    return shapes.curve_shapes(node)


def read(node):
    """Shape entry of a control: curves (object space), colour, line width, always on top."""
    from jeffy.controls import shapes
    from jeffy.core import color

    entry = {"curves": shapes.get_shape_data(node)}
    value = color.get_color(node)
    entry["color"] = list(value) if isinstance(value, tuple) else value
    curve_shapes = _shapes(node)
    if curve_shapes:
        first = curve_shapes[0]
        if cmds.attributeQuery("lineWidth", node=first, exists=True):
            entry["line_width"] = cmds.getAttr(first + ".lineWidth")
        entry["on_top"] = bool(cmds.getAttr(first + ".alwaysDrawOnTop"))
    return entry


def is_procedural(node):
    """True when the build drives the control's CVs (Edge Ribbon master outline): never remembered."""
    for shape in _shapes(node):
        pairs = cmds.listConnections(shape, source=True, destination=False, plugs=True, connections=True) or []
        for plug in pairs[0::2]:
            attr = plug.split(".", 1)[1].split("[")[0].split(".")[0]
            if attr in ("controlPoints", "cp", "create", "cr"):
                return True
    return False


def mark_built(node):
    """Store the signature of the control's current shape (the shape the build made)."""
    attributes.set_string(node, BUILT_ATTR, signature(read(node)))


def is_edited(node):
    """True when the shape differs from the one made by the build (or the build stored none)."""
    built = attributes.get_string(node, BUILT_ATTR)
    if not built:
        return True  # built before shape memory existed: keep what is there
    return signature(read(node)) != built


def _same_topology(node, curves):
    shapes = _shapes(node)
    if len(shapes) != len(curves):
        return False
    for shape, curve in zip(shapes, curves):
        degree = cmds.getAttr(shape + ".degree")
        spans = cmds.getAttr(shape + ".spans")
        periodic = cmds.getAttr(shape + ".form") == 2
        count = spans if periodic else spans + degree
        if degree != curve.get("degree", 1) or periodic != bool(curve.get("periodic")) or \
                count != len(curve["points"]):
            return False
    return True


def _incoming(shapes):
    """``[(source plug, attribute name)]`` connected into the shape nodes (first one per attribute)."""
    result, seen = [], set()
    for shape in shapes:
        pairs = cmds.listConnections(shape, source=True, destination=False, plugs=True, connections=True) or []
        for index in range(0, len(pairs), 2):
            attr = pairs[index].split(".", 1)[1]
            if attr not in seen:
                seen.add(attr)
                result.append((pairs[index + 1], attr))
    return result


def apply(node, entry, factor=1.0):
    """Give ``node`` the remembered shape ``entry``."""
    from jeffy.controls import shapes
    from jeffy.core import color

    curves = scaled(entry["curves"], factor)
    if _same_topology(node, curves):
        for shape, curve in zip(_shapes(node), curves):
            for index, point in enumerate(curve["points"]):
                cmds.xform("%s.cv[%d]" % (shape, index), objectSpace=True, translation=point)
    else:
        connections = _incoming(_shapes(node))
        shapes.set_shape_data(node, curves, keep_color=False, keep_line_width=False)
        for source, attr in connections:
            for shape in _shapes(node):
                if cmds.attributeQuery(attr.split("[")[0].split(".")[0], node=shape, exists=True):
                    try:
                        cmds.connectAttr(source, "%s.%s" % (shape, attr), force=True)
                    except RuntimeError:
                        pass
    value = entry.get("color")
    if value is None:
        color.reset_color(node)
    else:
        color.set_color(node, tuple(value) if isinstance(value, list) else value)
    if entry.get("line_width") is not None:
        shapes.set_line_width(node, entry["line_width"])
    if "on_top" in entry:
        shapes.set_always_on_top(node, bool(entry["on_top"]))


# ---------------------------------------------------------------------------
# Setup level (called by Setup)
# ---------------------------------------------------------------------------
def _key(setup, control_key):
    return entry_key(setup.TYPE, setup.name, setup.side, control_key)


def _size(setup):
    return setup.options.get("size")


def _long(node):
    return (cmds.ls(node, long=True) or [node])[0]


def _wanted(nodes):
    return None if nodes is None else set(cmds.ls(nodes, long=True) or [])


def capture(setup, nodes=None, force=False):
    """Remember the edited control shapes of ``setup`` (all of its controls, or ``nodes``).

    :param force: remember them even when they were not edited
    :returns: the controls remembered
    """
    data = _load()
    wanted = _wanted(nodes)
    done = []
    for control_key, node in setup.controls.items():
        if wanted is not None and _long(node) not in wanted:
            continue
        if not cmds.objExists(node) or not _shapes(node) or is_procedural(node):
            continue
        if not force and not is_edited(node):
            continue
        entry = read(node)
        entry["size"] = _size(setup)
        data[_key(setup, control_key)] = entry
        done.append(node)
    if done:
        _save(data)
    return done


def restore(setup):
    """End of a build: mark every control as built, then give back the remembered shapes."""
    data = _load()
    restored = []
    for control_key, node in setup.controls.items():
        if not cmds.objExists(node):
            continue
        mark_built(node)
        entry = data.get(_key(setup, control_key))
        if not entry or is_procedural(node):
            continue
        try:
            apply(node, entry, size_factor(entry.get("size"), _size(setup)))
            restored.append(node)
        except Exception as error:  # a bad entry must never stop a build
            cmds.warning("[Jeffy] could not restore the shape of %s: %s" % (node, error))
    return restored


def forget(setup, nodes=None):
    """Forget the shapes of ``setup``'s controls (all, or ``nodes``). Their current shape becomes the default."""
    data = _load()
    wanted = _wanted(nodes)
    forgotten = []
    for control_key, node in setup.controls.items():
        if wanted is not None and _long(node) not in wanted:
            continue
        key = _key(setup, control_key)
        if key in data:
            del data[key]
        if cmds.objExists(node):
            mark_built(node)
        forgotten.append(node)
    _save(data)
    return forgotten


def rename(setup_type, old_name, old_side, new_name, new_side):
    """A setup is rebuilt under a new name / side: its memory follows."""
    data = _load()
    if data:
        _save(rename_entries(data, setup_type, old_name, old_side, new_name, new_side))
