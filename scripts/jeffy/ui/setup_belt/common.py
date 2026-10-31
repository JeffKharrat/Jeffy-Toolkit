"""Helpers shared by the belt panels: running commands safely, selection."""

import traceback

from maya import cmds

from jeffy.core import decorators, logger
from jeffy.setups.core.schema import SetupError
from jeffy.ui import theme
from jeffy.ui.qt import QtWidgets

LOG = logger.get_logger("setup_belt")


def run(label, func, status=None, parent=None):
    """Run ``func`` in one undo step and report the result.

    User errors (:class:`SetupError`, bad values) are shown as a warning;
    unexpected errors are logged with a traceback and the partial work is
    undone. Returns ``(ok, result)``.
    """
    theme.set_state(theme.LOADING)
    try:
        with decorators.undo_chunk(label):
            result = func()
    except (SetupError, decorators.ToolError) as error:
        theme.set_state(theme.FAULTED)
        cmds.warning("[Jeffy] %s: %s" % (label, error))
        _status(status, "%s: %s" % (label, error), error=True)
        return False, None
    except Exception as error:  # pragma: no cover - interactive only
        theme.set_state(theme.FAULTED)
        LOG.error("%s failed: %s\n%s", label, error, traceback.format_exc())
        rolled_back = decorators._rollback(label)
        note = " (the partial build was undone)" if rolled_back else ""
        cmds.warning("[Jeffy] %s failed: %s%s - see the Script Editor" % (label, error, note))
        _status(status, "%s failed: %s%s. See the Script Editor." % (label, error, note), error=True)
        return False, None
    theme.set_state(theme.IDLE)
    return True, result


def _status(widget, text, error=False):
    if widget is None:
        return
    widget.setText(text)
    widget.setStyleSheet("color: %s;" % theme.status_color(error))


def ok(widget, text):
    _status(widget, text, error=False)


def channel_box_plugs():
    """``node.attr`` of the attributes highlighted in the Channel Box (object, shape, inputs and outputs)."""
    box = "mainChannelBox"
    result = []
    if not cmds.channelBox(box, exists=True):
        return result
    for objects_flag, attrs_flag in (("mainObjectList", "selectedMainAttributes"),
                                     ("shapeObjectList", "selectedShapeAttributes"),
                                     ("historyObjectList", "selectedHistoryAttributes"),
                                     ("outputObjectList", "selectedOutputAttributes")):
        objects = cmds.channelBox(box, query=True, **{objects_flag: True}) or []
        attrs = cmds.channelBox(box, query=True, **{attrs_flag: True}) or []
        for node in objects:
            for attr in attrs:
                if not cmds.attributeQuery(attr, node=node, exists=True):
                    continue
                name = attr
                aliases = cmds.aliasAttr(node, query=True) or []  # [alias, real, alias, real...]
                if attr not in aliases[::2]:  # ty -> translateY; a blendShape target name (an alias) stays
                    try:
                        long_name = cmds.attributeQuery(attr, node=node, longName=True)
                        if long_name and long_name[0].isalpha() and "[" not in long_name:
                            name = long_name
                    except RuntimeError:
                        pass
                plug = "%s.%s" % (node, name)
                if plug not in result:
                    result.append(plug)
    return result


def selection(transforms_only=True):
    """Selected nodes in selection order (shapes -> transforms, components -> objects).

    Without Maya's *Track selection order* preference, joints come parent
    first (the right order for a chain).
    """
    nodes = cmds.ls(orderedSelection=True, long=False) or []
    if not nodes:
        nodes = cmds.ls(selection=True, long=False) or []
        if len(nodes) > 1:
            depth = dict((node, (cmds.ls(node, long=True) or [""])[0].count("|")) for node in nodes)
            nodes = sorted(nodes, key=lambda node: depth[node])
    result = []
    for node in nodes:
        node = node.split(".")[0]
        if transforms_only and cmds.objExists(node) and cmds.objectType(node, isAType="shape"):
            node = (cmds.listRelatives(node, parent=True) or [node])[0]
        if node not in result:
            result.append(node)
    return result


def confirm(parent, title, text):
    answer = QtWidgets.QMessageBox.question(parent, title, text,
                                            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                            QtWidgets.QMessageBox.No)
    return answer == QtWidgets.QMessageBox.Yes
