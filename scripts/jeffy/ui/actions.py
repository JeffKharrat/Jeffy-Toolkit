"""Selection based entry points used by the belt's Utilities panel, the menu and the shelf.

Every function is wrapped with :func:`jeffy.core.decorators.tool`: one undo
step, friendly warnings for bad selections and no exception leaking into Qt::

    from jeffy.ui import actions
    actions.replace_shapes("cube")
"""

import os

from maya import cmds

from jeffy.core import decorators
from jeffy.core.decorators import ToolError, tool


def _selection(minimum=1):
    nodes = cmds.ls(selection=True) or []
    if len(nodes) < minimum:
        raise ToolError("Select at least %d object(s)" % minimum)
    return nodes


def _file_dialog(mode="save", caption="File", file_filter="JSON (*.json)"):
    from jeffy.core import fileio, settings

    start = settings.get("last_export_dir") or fileio.scene_dir()
    result = cmds.fileDialog2(fileMode=0 if mode == "save" else 1, caption=caption, fileFilter=file_filter,
                              startingDirectory=start, dialogStyle=2)
    if not result:
        return None
    settings.set("last_export_dir", os.path.dirname(result[0]))
    return result[0]


def _folder_dialog(caption="Folder"):
    from jeffy.core import fileio

    result = cmds.fileDialog2(fileMode=3, caption=caption, startingDirectory=fileio.scene_dir(), dialogStyle=2)
    return result[0] if result else None


# ===========================================================================
# Window
# ===========================================================================
@tool("Open Jeff Inventory", undo=False)
def show_setup_belt():
    import jeffy

    return jeffy.show()


# ===========================================================================
# Control shapes
# ===========================================================================
@tool("Replace Shape")
def replace_shapes(shape="circle", size=None, axis="y"):
    from jeffy.controls import shapes

    shapes.replace_shape(_selection(), shape, size=size, axis=axis)


@tool("Set Color")
def color_selected(color_value):
    from jeffy.core import color

    color.set_color(_selection(), color_value)


@tool("Reset Color")
def reset_color_selected():
    from jeffy.core import color

    color.reset_color(_selection())


@tool("Mirror Shapes")
def mirror_shapes(axis="x"):
    from jeffy.controls import shapes

    done = shapes.mirror_shapes(_selection(), axis)
    if not done:
        raise ToolError("No L_/R_ counterpart found for the selection")
    decorators.message("Mirrored %d shape(s)" % len(done))


@tool("Copy Shape")
def copy_shape(world=False):
    from jeffy.controls import shapes

    selection = _selection(2)
    shapes.copy_shape(selection[0], selection[1:], world=world)


@tool("Scale Shapes")
def scale_shapes(factor=1.25):
    from jeffy.controls import shapes

    shapes.scale_shapes(_selection(), factor)


@tool("Rotate Shapes")
def rotate_shapes(rotation=(90, 0, 0)):
    from jeffy.controls import shapes

    shapes.rotate_shapes(_selection(), rotation)


@tool("Line Width")
def set_line_width(width=2.0):
    from jeffy.controls import shapes

    shapes.set_line_width(_selection(), width)


@tool("Save Shape")
def save_shape_to_library(name=None):
    from jeffy.controls import shapes

    path = shapes.save_to_library(_selection(1)[0], name)
    decorators.message("Saved shape to %s" % path)
    return path


def _belt_controls():
    """``[(setup, [controls])]`` of the selected belt controls."""
    from jeffy.setups.core import scene

    groups = []
    for node in _selection():
        setup = scene.find_setup(node)
        if setup is None:
            continue
        long_node = (cmds.ls(node, long=True) or [node])[0]
        controls = [c for c in setup.controls.values() if (cmds.ls(c, long=True) or [c])[0] == long_node]
        if not controls:
            continue
        for existing, members in groups:
            if existing == setup:
                members.extend(controls)
                break
        else:
            groups.append((setup, controls))
    if not groups:
        raise ToolError("Select controls made by the belt")
    return groups


@tool("Remember Shapes")
def remember_shapes():
    """Remember the selected belt controls' shapes now (they come back at every rebuild)."""
    from jeffy.setups.core import shape_memory

    count = sum(len(shape_memory.capture(setup, nodes, force=True)) for setup, nodes in _belt_controls())
    decorators.message("Remembered %d control shape(s)" % count)


@tool("Forget Shapes")
def forget_shapes():
    """Forget the selected belt controls' shapes: the next rebuild gives them the default shape."""
    from jeffy.setups.core import shape_memory

    count = sum(len(shape_memory.forget(setup, nodes)) for setup, nodes in _belt_controls())
    decorators.message("Forgot %d control shape(s)" % count)


@tool("Export Shapes")
def export_shapes():
    from jeffy.controls import shapes

    path = _file_dialog("save", "Export control shapes")
    if path:
        shapes.export_shapes(path, _selection())


@tool("Import Shapes")
def import_shapes():
    from jeffy.controls import shapes

    path = _file_dialog("open", "Import control shapes")
    if path:
        shapes.import_shapes(path, cmds.ls(selection=True) or None)


# ===========================================================================
# Skin weights
# ===========================================================================
def _meshes():
    selection = cmds.ls(selection=True, transforms=True) or []
    meshes = [s for s in selection if cmds.listRelatives(s, shapes=True, type=["mesh", "nurbsCurve",
                                                                                "nurbsSurface"])]
    if not meshes:
        raise ToolError("Select skinned geometry")
    return meshes


@tool("Export Skin Weights")
def export_skin_weights():
    from jeffy.deformers import skin

    meshes = _meshes()
    if len(meshes) == 1:
        path = _file_dialog("save", "Export skin weights")
        if path:
            skin.export_weights(meshes[0], path)
    else:
        folder = _folder_dialog("Export skin weights to folder")
        if folder:
            skin.export_selected(folder)


@tool("Import Skin Weights")
def import_skin_weights(method="auto"):
    from jeffy.deformers import skin

    meshes = _meshes()
    if len(meshes) == 1:
        path = _file_dialog("open", "Import skin weights")
        if path:
            skin.import_weights(meshes[0], path, method=method)
    else:
        folder = _folder_dialog("Import skin weights from folder")
        if folder:
            skin.import_selected(folder, method=method)
