"""Reset the rig's pose: every setup control back to zero (its build pose).

Translate / rotate go to 0 and scale to 1 on each control. With
``attributes=True`` every other keyable attribute of the controls goes back
to its default too (curl, fist, ikFk, stretch, spaces...).

Locked, hidden and connected (driven) channels are left alone, so nothing
the rig computes is touched. Keys are not deleted: on a keyed control the
reset value holds until the next frame change (set a key to keep it).
"""

from maya import cmds

from jeffy.setups.core import scene

TRANSFORM_DEFAULTS = {"translate": 0.0, "rotate": 0.0, "scale": 1.0}


def controls_of(setups=None):
    """Every control of ``setups`` (default: every setup in the scene)."""
    result = []
    for setup in setups if setups is not None else scene.all_setups():
        for node in setup.controls.values():
            if cmds.objExists(node) and node not in result:
                result.append(node)
    return result


def _settable(plug):
    if cmds.getAttr(plug, lock=True):
        return False
    return not cmds.listConnections(plug, source=True, destination=False)


def reset(setups=None, attributes=True, controls=None):
    """Put the controls back to their build pose. Returns how many channels changed.

    :param setups: the setups to reset (default: all of the scene)
    :param attributes: also the controls' other keyable attributes, to their defaults
    :param controls: reset only these controls instead
    """
    nodes = controls if controls is not None else controls_of(setups)
    changed = 0
    if attributes:  # first: switches (ikFk...) can snap controls, the transforms are zeroed after
        for node in nodes:
            for attr in cmds.listAttr(node, keyable=True, userDefined=True) or []:
                plug = "%s.%s" % (node, attr)
                try:
                    default = cmds.attributeQuery(attr, node=node, listDefault=True)
                except RuntimeError:
                    continue
                if not default or not _settable(plug):
                    continue
                current = cmds.getAttr(plug)
                if isinstance(current, (list, tuple)) or abs(float(current) - float(default[0])) < 1e-9:
                    continue
                cmds.setAttr(plug, default[0])
                changed += 1
    for node in nodes:
        for channel, value in TRANSFORM_DEFAULTS.items():
            for axis in "XYZ":
                plug = "%s.%s%s" % (node, channel, axis)
                if not _settable(plug) or abs(cmds.getAttr(plug) - value) < 1e-9:
                    continue
                cmds.setAttr(plug, value)
                changed += 1
    return changed
