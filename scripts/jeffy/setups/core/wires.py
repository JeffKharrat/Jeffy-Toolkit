"""Wires and the setups they depend on: rebuilt together, parked when a setup is deleted.

* **Rebuild** a setup: the wires using it (or its layers, or its mirror) are
  deleted first (they put back what they drove), then rebuilt after the setup
  and its layers, from their own settings (:func:`take_dependents`,
  :func:`rebuild_specs`).
* **Delete** a setup: the wires using it are *parked*. Their settings go into
  one scene node, ``jeffyWireMemory`` (a hidden ``network`` that belongs to no
  setup, like shape memory), then they are deleted cleanly. After any build,
  a parked wire whose setups all exist again is rebuilt automatically
  (:func:`restore_parked`). Deleting a wire yourself never parks it.
"""

import json

from maya import cmds

from jeffy.core import attributes
from jeffy.setups.core import scene
from jeffy.setups.core import tag as tag_module
from jeffy.setups.core.schema import SetupError

NODE = "jeffyWireMemory"
DATA_ATTR = "jeffy_wires"
_BUSY = {"restoring": False}


# ---------------------------------------------------------------------------
# Memory (pure helpers are unit tested)
# ---------------------------------------------------------------------------
def entry_name(spec):
    """``L_armFollow`` style key of a parked wire."""
    return "%s|%s|%s" % (spec.get("type", ""), spec.get("name", ""), spec.get("side") or "")


def add_entry(entries, spec, depends_keys):
    """``entries`` with ``spec`` parked (replacing an older entry of the same wire)."""
    key = entry_name(spec)
    result = [entry for entry in entries if entry_name(entry["spec"]) != key]
    result.append({"spec": spec, "depends": list(depends_keys)})
    return result


def _load():
    if not cmds.objExists(NODE):
        return []
    text = attributes.get_string(NODE, DATA_ATTR, "")
    try:
        return json.loads(text) if text else []
    except ValueError:
        return []


def _save(entries):
    if not cmds.objExists(NODE):
        if not entries:
            return
        cmds.createNode("network", name=NODE, skipSelect=True)
    attributes.set_string(NODE, DATA_ATTR, json.dumps(entries, sort_keys=True))


def parked():
    """``[{"spec": ..., "depends": ["type|name|side", ...]}]`` of the wires waiting for their setups."""
    return _load()


def forget(name=None):
    """Drop parked wires (all, or the one whose ``type|name|side`` key is ``name``)."""
    entries = [] if name is None else [entry for entry in _load() if entry_name(entry["spec"]) != name]
    _save(entries)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
def dependents(tags):
    """The wires using any setup of ``tags``."""
    tags = set(tags)
    result = []
    for setup in scene.all_setups():
        if setup.CATEGORY != "wire":
            continue
        if tags & set(tag_module.get_nodes(setup.tag, "depends")):
            result.append(setup)
    return result


def _specs(wires):
    """Specs of ``wires``; a mirrored pair gives one spec (its primary side builds the other)."""
    tags = set(wire.tag for wire in wires)
    result = []
    for wire in wires:
        partner = wire.mirror
        spec = wire.spec()
        if partner is not None and partner.tag in tags:
            if wire.is_mirror_secondary():
                continue
        else:
            spec["options"]["mirror"] = False
        result.append((spec, tag_module.get_data(wire.tag, "depends_keys", []) or []))
    return result


def take_dependents(tags):
    """Delete the wires using ``tags`` (what they drove is put back) and return their specs to rebuild."""
    wires = dependents(tags)
    specs = _specs(wires)
    for wire in wires:
        if cmds.objExists(wire.tag):
            wire.delete(mirror=False)
    return specs


def park_dependents(tags):
    """Park the wires using ``tags``: remember them, then delete them. Returns how many."""
    wires = dependents(tags)
    names = [wire.describe() for wire in wires]
    entries = _load()
    for spec, keys in _specs(wires):
        spec["options"]["mirror"] = False  # each side comes back on its own, with its own setups
        entries = add_entry(entries, spec, keys)
    for wire in wires:
        if cmds.objExists(wire.tag):
            wire.delete(mirror=False)
    if wires:
        _save(entries)
        cmds.warning("[Jeffy] parked %d wire(s) (%s): they come back when their setups are built again"
                     % (len(wires), ", ".join(names)))
    return len(wires)


def _create(spec):
    cls = scene.tool_class(spec["type"])
    if cls is None:
        raise SetupError("unknown wire type %s" % spec["type"])
    return cls.create(spec["slots"], spec["options"], name=spec["name"], side=spec["side"],
                      guides=spec.get("guides") or {})


def rebuild_specs(specs):
    """Rebuild wires after their setups; one that fails is parked (with a warning)."""
    entries, failed = _load(), []
    for spec, keys in specs:
        try:
            _create(spec)
        except SetupError as error:
            spec["options"]["mirror"] = False
            entries = add_entry(entries, spec, keys)
            failed.append("%s_%s: %s" % (spec.get("side"), spec.get("name"), error))
    if failed:
        _save(entries)
        cmds.warning("[Jeffy] wire(s) parked, they could not be rebuilt: %s" % "; ".join(failed))


def _present(key):
    setup_type, name, side = (key.split("|") + ["", "", ""])[:3]
    for setup in scene.all_setups(setup_type=setup_type):
        if setup.name == name and (setup.side or "") == side:
            return True
    return False


def restore_parked():
    """Rebuild the parked wires whose setups all exist again. Returns the wires built."""
    if _BUSY["restoring"]:
        return []
    entries = _load()
    if not entries:
        return []
    _BUSY["restoring"] = True
    built, keep = [], []
    try:
        for entry in entries:
            if not all(_present(key) for key in entry["depends"]):
                keep.append(entry)
                continue
            try:
                built.append(_create(entry["spec"]))
            except SetupError as error:
                keep.append(entry)
                cmds.warning("[Jeffy] parked wire %s not rebuilt yet: %s" % (entry_name(entry["spec"]), error))
    finally:
        _BUSY["restoring"] = False
    if len(keep) != len(entries):
        _save(keep)
    return built
