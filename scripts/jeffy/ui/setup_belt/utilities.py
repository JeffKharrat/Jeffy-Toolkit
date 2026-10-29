"""SCENE > Utilities: control shape tools and skin weights export / import."""

from jeffy.ui import actions
from jeffy.ui import widgets as w
from jeffy.ui.qt import QtWidgets

AXES = ["x", "-x", "y", "-y", "z", "-z"]


class UtilitiesPanel(QtWidgets.QScrollArea):
    def __init__(self):
        super(UtilitiesPanel, self).__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        container = QtWidgets.QWidget()
        self.setWidget(container)
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(QtWidgets.QLabel("<span style='font-size:15px'><b>UTILITIES</b></span>"))
        hint = w.label("Control shapes and skin weights. Every button works on the selection.")
        hint.setStyleSheet("color: #9a9a9a;")
        layout.addWidget(hint)

        shapes = w.Section("Control shapes")
        self.gallery = w.ShapeGallery()
        shapes.add(self.gallery)
        self.shape_axis = w.combo(AXES, "y", "Axis the shape faces")
        shapes.add(w.row(("Axis", self.shape_axis), w.button(
            "Replace Shape", lambda: actions.replace_shapes(self.gallery.current_shape() or "circle", None,
                                                            self.shape_axis.currentText()),
            "Replace the selected controls' shapes (size and colour kept)")))
        shapes.add(w.grid([
            w.button("Mirror L <> R", actions.mirror_shapes, "Copy the selected controls' shapes to the other side"),
            w.button("Copy First > Rest", actions.copy_shape, "Select the source control, then the targets"),
            w.button("Scale Up", lambda: actions.scale_shapes(1.25)),
            w.button("Scale Down", lambda: actions.scale_shapes(0.8)),
            w.button("Rotate X 90", lambda: actions.rotate_shapes((90, 0, 0))),
            w.button("Rotate Y 90", lambda: actions.rotate_shapes((0, 90, 0))),
            w.button("Rotate Z 90", lambda: actions.rotate_shapes((0, 0, 90))),
            w.button("Save To Library", actions.save_shape_to_library, "Add the selected curve to your shapes"),
            w.button("Export Shapes", actions.export_shapes),
            w.button("Import Shapes", actions.import_shapes),
            w.button("Remember Shapes", actions.remember_shapes,
                     "Keep the selected belt controls' shapes through every rebuild (edited shapes are kept "
                     "automatically)"),
            w.button("Forget Shapes", actions.forget_shapes,
                     "The next rebuild gives the selected belt controls their default shape again"),
        ], 2))
        self.line_width = w.spin(2.0, -1.0, 20.0, 1, 0.5, "-1 = Maya default")
        shapes.add(w.row(("Line width", self.line_width), w.button(
            "Set", lambda: actions.set_line_width(self.line_width.value()))))
        palette = w.ColorPalette()
        palette.colorPicked.connect(actions.color_selected)
        shapes.add(palette)
        shapes.add(w.button("Reset Color", actions.reset_color_selected))
        layout.addWidget(shapes)

        skin = w.Section("Skin weights")
        self.method = w.combo(["auto", "index", "position"], "auto",
                              "auto: by vertex index when the topology matches, else by position")
        skin.add(w.row(w.button("Export Weights", actions.export_skin_weights,
                                "One mesh: a file. Several meshes: a folder (one file per mesh)"),
                       ("Import by", self.method),
                       w.button("Import Weights", lambda: actions.import_skin_weights(self.method.currentText()))))
        layout.addWidget(skin)
        layout.addStretch(1)
