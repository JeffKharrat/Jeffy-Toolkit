"""The "Jeff Inventory" menu in Maya's main menu bar."""

from maya import cmds

from jeffy import TOOLKIT_NAME, __version__

MENU_NAME = "jeffyToolkitMenu"


def _act(name, *args, **kwargs):
    """Menu command calling ``jeffy.ui.actions.<name>`` (imported lazily)."""

    def command(*_unused):
        from jeffy.ui import actions

        getattr(actions, name)(*args, **kwargs)

    return command


def _reload(*_unused):
    import jeffy

    jeffy.reload_toolkit()


def _about(*_unused):
    cmds.confirmDialog(title=TOOLKIT_NAME, message="%s %s\nStackable setup tools for your own skeleton.\n\n"
                       "import jeffy; jeffy.show()" % (TOOLKIT_NAME, __version__), button=["OK"])


MENU = [
    ("Control Shapes", [
        ("Mirror Shapes L <> R", _act("mirror_shapes")),
        ("Copy Shape First > Rest", _act("copy_shape")),
        ("Scale Shapes Up", _act("scale_shapes", 1.25)),
        ("Scale Shapes Down", _act("scale_shapes", 0.8)),
        ("Reset Color", _act("reset_color_selected")),
        (None, None),
        ("Export Shapes", _act("export_shapes")),
        ("Import Shapes", _act("import_shapes")),
    ]),
    ("Skin Weights", [
        ("Export Skin Weights", _act("export_skin_weights")),
        ("Import Skin Weights", _act("import_skin_weights")),
    ]),
]


def _reset_pose(*_unused):
    from jeffy.core import decorators
    from jeffy.setups.core import pose

    with decorators.undo_chunk("Reset pose"):
        count = pose.reset()
    print("[Jeffy] reset the rig's pose (%d channels)" % count)


def install():
    """(Re)create the menu. Does nothing in batch mode."""
    if cmds.about(batch=True):
        return None
    uninstall()
    menu = cmds.menu(MENU_NAME, label=TOOLKIT_NAME, parent="MayaWindow", tearOff=True)
    cmds.menuItem(label="Open %s" % TOOLKIT_NAME, command=_act("show_setup_belt"), parent=menu)
    cmds.menuItem(label="Reset Pose (whole rig)", command=_reset_pose, parent=menu,
                  annotation="Every control back to zero, attributes to their defaults (one undo)")
    cmds.menuItem(divider=True, parent=menu)
    for title, entries in MENU:
        sub = cmds.menuItem(label=title, subMenu=True, tearOff=True, parent=menu)
        for label_text, command in entries:
            if label_text is None:
                cmds.menuItem(divider=True, parent=sub)
            else:
                cmds.menuItem(label=label_text, command=command, parent=sub)
    cmds.menuItem(divider=True, parent=menu)
    cmds.menuItem(label="Create Shelf", command=lambda *_: __import__("jeffy").install_shelf(), parent=menu)
    cmds.menuItem(label="Reload", command=_reload, parent=menu)
    cmds.menuItem(label="About", command=_about, parent=menu)
    return menu


def uninstall():
    if cmds.menu(MENU_NAME, exists=True):
        cmds.deleteUI(MENU_NAME, menu=True)
