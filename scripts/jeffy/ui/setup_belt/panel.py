"""One panel per belt tool, generated from the tool's slots and options.

::

    IK/FK LIMB                                   description
    Name [arm      ]  Side [auto v]
    -- Joints -------------------------------------------
    Start [L_shoulder_JNT ] [<]
    Mid   [L_elbow_JNT    ] [<]
    End   [L_wrist_JNT    ] [<]
    -- Options ------------------------------------------
    [x] Stretch  [x] Soft IK  ...
    [Preview]  [Build]                 (editing: [Rebuild] [Delete] [New])
"""

from maya import cmds

from jeffy.core import naming, settings
from jeffy.setups.core import edges as edge_tools
from jeffy.setups.core import scene
from jeffy.ui import widgets as w
from jeffy.ui.qt import QtCore, QtWidgets
from jeffy.ui.setup_belt import common

SIDES = ("auto", "L", "R", "C")
SETTINGS_PREFIX = "belt_options_"


class SlotField(QtWidgets.QWidget):
    """A slot: text field + [<] (load selection), plus [+] and [x] for lists."""

    def __init__(self, slot, panel):
        super(SlotField, self).__init__()
        self.slot = slot
        self.panel = panel
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self.edit = QtWidgets.QLineEdit()
        placeholder = "optional" if slot.optional else (
            "select the edges, then <" if slot.components else
            "select, highlight in the Channel Box, then <" if slot.plugs else
            "select in order, then <" if slot.multi else "select, then <")
        self.edit.setPlaceholderText(placeholder)
        self.edit.setToolTip(slot.tip)
        layout.addWidget(self.edit, 1)
        load = QtWidgets.QToolButton()
        load.setText("<")
        load.setToolTip("Load the selection" + (" (several selected joints fill the next slots too)"
                                                 if not slot.multi else " (replaces the list)"))
        load.clicked.connect(self.load_selection)
        layout.addWidget(load)
        if slot.multi:
            add = QtWidgets.QToolButton()
            add.setText("+")
            add.setToolTip("Add the selection to the list")
            add.clicked.connect(self.add_selection)
            layout.addWidget(add)
        clear = QtWidgets.QToolButton()
        clear.setText("x")
        clear.setToolTip("Clear")
        clear.clicked.connect(lambda: self.set_value(None))
        layout.addWidget(clear)

    # ------------------------------------------------------------------
    def value(self):
        text = self.edit.text().strip()
        if self.slot.multi:
            return [part.strip() for part in text.split(",") if part.strip()]
        return text or None

    def set_value(self, value):
        if isinstance(value, (list, tuple)):
            value = ", ".join(value)
        self.edit.setText(value or "")

    def _selected(self):
        if self.slot.components:  # keep the edges (``mesh.e[3:9]``), not their mesh
            return edge_tools.compact(cmds.ls(selection=True, flatten=True) or [])
        if self.slot.plugs:  # node.attr from the Channel Box
            return common.channel_box_plugs()
        return common.selection()

    def load_selection(self):
        nodes = self._selected()
        if not nodes:
            cmds.warning("[Jeffy] select something first")
            return
        if self.slot.multi:
            self.set_value(nodes)
        else:
            self.panel.fill_from(self, nodes)

    def add_selection(self):
        current = self.value()
        if self.slot.components:
            self.set_value(edge_tools.compact(current + self._selected()))
            return
        self.set_value(current + [node for node in self._selected() if node not in current])


class ToolPanel(QtWidgets.QScrollArea):
    """The panel of one belt tool."""

    def __init__(self, tool_cls, window=None):
        super(ToolPanel, self).__init__()
        self.tool = tool_cls
        self.window_ref = window
        self.loaded = None  # setup being edited
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        container = QtWidgets.QWidget()
        self.setWidget(container)
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)

        title = QtWidgets.QLabel("<span style='font-size:15px'><b>%s</b></span>" % tool_cls.LABEL.upper())
        layout.addWidget(title)
        description = w.label(tool_cls.DESCRIPTION)
        description.setStyleSheet("color: #9a9a9a;")
        layout.addWidget(description)

        self.banner = QtWidgets.QLabel()
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet("background-color: rgba(129, 178, 154, 40); padding: 4px; border-radius: 3px;")
        self.banner.setVisible(False)
        layout.addWidget(self.banner)

        # name / side
        self.name_edit = w.line_edit("", "auto (from the first joint)" if tool_cls.TYPE != "rig_base" else "character",
                                     "Setup name: used in every node name ({side}_{name}...)")
        self.side_combo = w.combo(SIDES, "auto", "auto: from the first joint's name (L_, R_, C_)")
        if tool_cls.TYPE == "rig_base":
            layout.addWidget(w.row(("Name", self.name_edit)))
        else:
            layout.addWidget(w.row(("Name", self.name_edit), ("Side", self.side_combo)))

        # slots
        self.slot_fields = {}
        if tool_cls.SLOTS:
            section = w.Section("Joints" if any(s.joints_only for s in tool_cls.SLOTS) else "Nodes")
            grid_widget = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(grid_widget)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(4)
            for row_index, slot in enumerate(tool_cls.SLOTS):
                label = QtWidgets.QLabel(slot.label + ("" if not slot.optional else " (opt.)"))
                label.setToolTip(slot.tip)
                field = SlotField(slot, self)
                grid.addWidget(label, row_index, 0)
                grid.addWidget(field, row_index, 1)
                self.slot_fields[slot.key] = field
            grid.setColumnStretch(1, 1)
            section.add(grid_widget)
            if tool_cls.TYPE == "spaces":
                section.add(w.button("Load current spaces of the control", self._load_current_spaces,
                                     "Fill the targets with the spaces the control has now"))
            layout.addWidget(section)

        # options
        self.option_widgets = {}
        options = tool_cls.option_schema()
        if options:
            section = w.Section("Options")
            form_widget = QtWidgets.QWidget()
            form = QtWidgets.QFormLayout(form_widget)
            form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
            form.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
            form.setContentsMargins(0, 0, 0, 0)
            form.setSpacing(4)
            checks = []
            for option in options:
                widget = _option_widget(option)
                self.option_widgets[option.key] = widget
                if option.kind == "bool":
                    checks.append(widget)
                else:
                    label = QtWidgets.QLabel(option.label)
                    label.setToolTip(option.tip)
                    form.addRow(label, widget)
            section.add(form_widget)
            for start in range(0, len(checks), 2):
                section.add(w.row(*checks[start:start + 2]))
            layout.addWidget(section)
        self._restore_options()

        # buttons
        self.preview_button = w.button("Preview", self.preview, "Show the guides (pole, pivots...) at their default "
                                                                "places. Move them, then Build.")
        self.preview_button.setVisible(bool(tool_cls.GUIDES))
        self.build_button = w.button("Build", self.build, "Build the setup (one undo step)", height=32)
        self.build_button.setStyleSheet("QPushButton { font-weight: bold; }")
        self.delete_button = w.button("Delete", self.delete, "Delete the setup being edited (and its layers)")
        self.new_button = w.button("New", self.unload, "Stop editing: the next Build creates a new setup")
        self.select_button = w.button("Select controls", self.select_controls)
        for button in (self.delete_button, self.new_button, self.select_button):
            button.setVisible(False)
        layout.addWidget(w.row(self.preview_button, self.build_button))
        layout.addWidget(w.row(self.select_button, self.delete_button, self.new_button))
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch(1)

    # ------------------------------------------------------------------
    # Values
    # ------------------------------------------------------------------
    def fill_from(self, field, nodes):
        """Single slots: the first node goes in ``field``, the next ones in the following single slots."""
        keys = [slot.key for slot in self.tool.SLOTS]
        start = keys.index(field.slot.key)
        remaining = list(nodes)
        for key in keys[start:]:
            target = self.slot_fields[key]
            if target.slot.multi or not remaining:
                break
            target.set_value(remaining.pop(0))

    def slot_values(self):
        return dict((key, field.value()) for key, field in self.slot_fields.items())

    def option_values(self):
        return dict((key, w.value_of(widget)) for key, widget in self.option_widgets.items())

    def name_side(self):
        side = self.side_combo.currentText()
        return (self.name_edit.text().strip() or None), (None if side == "auto" else side)

    def _store_options(self):
        try:
            settings.set(SETTINGS_PREFIX + self.tool.TYPE, self.option_values())
        except Exception:  # settings are a convenience only
            pass

    def _restore_options(self):
        stored = settings.get(SETTINGS_PREFIX + self.tool.TYPE) or {}
        self.set_options(stored)

    def set_options(self, values):
        for key, value in (values or {}).items():
            widget = self.option_widgets.get(key)
            if widget is not None:
                _set_widget(widget, value)

    # ------------------------------------------------------------------
    # Editing an existing setup
    # ------------------------------------------------------------------
    def load(self, setup):
        spec = setup.spec()
        self.loaded = setup
        self.name_edit.setText(spec["name"] or "")
        index = self.side_combo.findText(spec["side"] or "auto")
        self.side_combo.setCurrentIndex(max(index, 0))
        for key, field in self.slot_fields.items():
            field.set_value(spec["slots"].get(key))
        self.set_options(spec["options"])
        self._update_mode()

    def unload(self):
        self.loaded = None
        self._update_mode()

    def _update_mode(self):
        editing = self.loaded is not None and cmds.objExists(self.loaded.tag)
        if not editing:
            self.loaded = None
        self.banner.setVisible(editing)
        if editing:
            text = "Editing <b>%s</b>. <i>Rebuild</i> applies your changes" % self.loaded.describe()
            if self.loaded.mirror is not None:
                text += " to both sides"
            layers = self.loaded.all_layers()
            if layers:
                text += " and rebuilds its layers (%s)" % ", ".join(layer.describe() for layer in layers)
            self.banner.setText(text + ".")
        self.build_button.setText("Rebuild" if editing else "Build")
        for button in (self.delete_button, self.new_button, self.select_button):
            button.setVisible(editing)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def preview(self):
        name, side = self.name_side()
        guides = self.loaded.guides if self.loaded is not None else None
        done, result = common.run("Preview " + self.tool.LABEL, lambda: self.tool.preview(
            self.slot_values(), self.option_values(), name=name, side=side, guides=guides), self.status)
        if done:
            cmds.select(list(result.values()))
            common.ok(self.status, "Move the guides, then press %s." % self.build_button.text())

    def build(self):
        self._store_options()
        if self.loaded is not None and cmds.objExists(self.loaded.tag):
            return self._rebuild()
        if not self._ensure_rig():
            return
        name, side = self.name_side()
        done, setup = common.run("Build " + self.tool.LABEL, lambda: self.tool.create(
            self.slot_values(), self.option_values(), name=name, side=side), self.status)
        if done:
            built = [setup.describe()] + ([setup.mirror.describe()] if setup.mirror is not None else [])
            common.ok(self.status, "Built %s." % " and ".join(built))
            self._refresh_window()

    def _rebuild(self):
        name, side = self.name_side()
        setup = self.loaded
        done, new = common.run("Rebuild " + self.tool.LABEL, lambda: setup.rebuild(
            options=self.option_values(), slots=self.slot_values(), name=name, side=side), self.status)
        if done:
            self.loaded = new
            self._update_mode()
            common.ok(self.status, "Rebuilt %s." % new.describe())
            self._refresh_window()

    def delete(self):
        setup = self.loaded
        if setup is None or not cmds.objExists(setup.tag):
            return self.unload()
        delete_mirror = False
        layers = setup.all_layers()
        text = "Delete %s?" % setup.describe()
        if layers:
            text += "\n\nLayers stacked on it are deleted too:\n%s" % "\n".join(layer.describe() for layer in layers)
        if not common.confirm(self, "Delete setup", text):
            return
        if setup.mirror is not None:
            delete_mirror = common.confirm(self, "Delete setup", "Also delete the other side (%s)?"
                                           % setup.mirror.describe())
        described = setup.describe()
        done, _result = common.run("Delete " + self.tool.LABEL, lambda: setup.delete(mirror=delete_mirror),
                                   self.status)
        if done:
            common.ok(self.status, "Deleted %s." % described)
            self.unload()
            self._refresh_window()

    def select_controls(self):
        if self.loaded is not None and cmds.objExists(self.loaded.tag):
            cmds.select(list(self.loaded.controls.values()) or self.loaded.tag)

    def _load_current_spaces(self):
        from jeffy.setups.tools import spaces

        control = self.slot_fields["control"].value()
        if not control:
            cmds.warning("[Jeffy] load the control first")
            return
        done, targets = common.run("Load spaces", lambda: spaces.current_targets(control), self.status)
        if done:
            self.slot_fields["targets"].set_value([naming.short_name(t) for t in targets])

    def _ensure_rig(self):
        """Offer to create the Rig Base when the scene has none."""
        if self.tool.CATEGORY in ("base", "wire") or scene.rigs():  # wires also work outside a rig
            return True
        values = self.slot_values()
        first = None
        for slot in self.tool.SLOTS:
            value = values.get(slot.key)
            if slot.joints_only and value:
                first = value[0] if slot.multi else value
                break
        root = None
        if first and cmds.objExists(first):
            ancestors = [first] + scene.ancestors(first)
            joints = [node for node in ancestors if cmds.nodeType(node) == "joint"]
            root = naming.short_name(joints[-1]) if joints else None
        text = "There is no Rig Base yet. Create one now"
        text += (" with %s as the root joint?" % root) if root else "?"
        if not common.confirm(self, "Rig Base", text):
            common._status(self.status, "Build a Rig Base first (BUILD > Rig Base).", error=True)
            return False
        from jeffy.setups.tools.rig_base import RigBase

        done, _rig = common.run("Build Rig Base", lambda: RigBase.create({"root_joint": root}, {}), self.status)
        return done

    def _refresh_window(self):
        if self.window_ref is not None:
            self.window_ref.refresh_setups()


def _option_widget(option):
    kind = option.kind
    if kind == "bool":
        widget = w.check(option.label, option.default, option.tip)
    elif kind == "choice":
        widget = w.combo(option.choices, option.default, option.tip)
    elif kind == "int":
        widget = w.spin(option.default, option.minimum if option.minimum is not None else -100000,
                        option.maximum if option.maximum is not None else 100000, 0, option.step or 1, option.tip)
    elif kind == "float":
        widget = w.spin(option.default, option.minimum if option.minimum is not None else -100000.0,
                        option.maximum if option.maximum is not None else 100000.0, option.decimals,
                        option.step or 0.1, option.tip)
    else:
        widget = w.line_edit(str(option.default or ""), "", option.tip)
    return widget


def _set_widget(widget, value):
    try:
        if isinstance(widget, QtWidgets.QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QtWidgets.QComboBox):
            index = widget.findText(str(value))
            if index >= 0:
                widget.setCurrentIndex(index)
        elif isinstance(widget, QtWidgets.QSpinBox):
            widget.setValue(int(value))
        elif isinstance(widget, QtWidgets.QDoubleSpinBox):
            widget.setValue(float(value))
        elif isinstance(widget, QtWidgets.QLineEdit):
            widget.setText("" if value is None else str(value))
    except (TypeError, ValueError):
        pass

