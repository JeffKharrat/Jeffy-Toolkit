"""SCENE > Setups: every setup of the scene, with its layers.

Edit (load into its tool panel), select its controls, rebuild, delete, and
the animation helpers: IK/FK snap and seamless space switch.
"""

from maya import cmds

from jeffy.core import naming
from jeffy.setups.core import attach, scene
from jeffy.ui import widgets as w
from jeffy.ui.qt import QtCore, QtWidgets
from jeffy.ui.setup_belt import common

TAG_ROLE = QtCore.Qt.UserRole


class SetupsPanel(QtWidgets.QWidget):
    def __init__(self, window=None):
        super(SetupsPanel, self).__init__()
        self.window_ref = window
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(QtWidgets.QLabel("<span style='font-size:15px'><b>SETUPS</b></span>"))
        hint = w.label("Every setup in the scene. Double click one to edit it in its panel.")
        hint.setStyleSheet("color: #9a9a9a;")
        layout.addWidget(hint)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Setup", "Tool", "Joints"])
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.tree.itemDoubleClicked.connect(lambda *_args: self.edit())
        self.tree.setColumnWidth(0, 170)
        self.tree.setColumnWidth(1, 90)
        layout.addWidget(self.tree, 1)

        layout.addWidget(w.row(
            w.button("Refresh", self.refresh),
            w.button("Edit", self.edit, "Load the setup into its panel to change it and rebuild"),
            w.button("Select controls", self.select_controls),
        ))
        layout.addWidget(w.row(
            w.button("Rebuild", self.rebuild, "Delete and build again with the same options (layers included)"),
            w.button("Delete", self.delete, "Delete the setup and its layers; the joints go back to rest"),
            w.button("Connect skin", self.connect_skin, "Edge Ribbon: after skinning the mesh to its joints, wire "
                                                        "bindPreMatrix so the blendShape moves the mesh only once"),
            w.button("Weights to ribbon", self.weights_to_ribbon,
                     "Ribbon (or its limb): move the chain bones' skin weights onto the ribbon joints, split evenly "
                     "along each bone. Selected vertices only, if you selected some"),
        ))
        from jeffy.ui.setup_belt import node_tabs

        self.node_tabs = w.check("Node Editor tab per setup", node_tabs.enabled(),
                                 "Every build opens a Node Editor tab named after the setup with only its nodes, "
                                 "laid out left to right (inputs > matrix nodes > outputs / joints)")
        self.node_tabs.toggled.connect(node_tabs.set_enabled)
        layout.addWidget(w.row(self.node_tabs, w.button("Show in Node Editor", self.show_graph,
                                                        "Open / refresh the selected setup's Node Editor tab")))

        animate = w.Section("Animate")
        self.key = w.check("Key", False, "Set keys after snapping / switching")
        animate.add(w.row(w.button("IK/FK snap + switch", self.snap,
                                   "Select any control of an IK/FK Limb: it snaps to the other mode and "
                                   "switches"), self.key))
        self.space_combo = QtWidgets.QComboBox()
        animate.add(w.row(w.button("Spaces of selected", self.load_spaces, "List the spaces of the selected control"),
                          self.space_combo, w.button("Switch (keep pose)", self.switch_space)))
        layout.addWidget(animate)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        self.tree.clear()
        setups = [s for s in scene.all_setups() if s is not None]
        items = {}
        roots = []
        rigs = [s for s in setups if s.CATEGORY == "base"]
        for rig in rigs:
            item = self._item(rig)
            items[rig.tag] = item
            roots.append(item)
        builds = [s for s in setups if s.CATEGORY == "build"]
        layers = [s for s in setups if s.CATEGORY == "layer"]
        wires = [s for s in setups if s.CATEGORY == "wire"]
        for setup in builds:
            item = self._item(setup)
            items[setup.tag] = item
            rig = setup.rig
            parent = items.get(rig.tag) if rig is not None else None
            if parent is not None:
                parent.addChild(item)
            else:
                roots.append(item)
        pending = list(layers)
        while pending:  # layers can stack on layers: add a layer once its base is in the tree
            progressed = False
            for setup in list(pending):
                base = setup.base
                if base is not None and base.CATEGORY == "layer" and base.tag not in items:
                    continue
                item = self._item(setup)
                items[setup.tag] = item
                parent = items.get(base.tag) if base is not None else None
                if parent is not None:
                    parent.addChild(item)
                else:
                    roots.append(item)
                pending.remove(setup)
                progressed = True
            if not progressed:
                for setup in pending:
                    roots.append(self._item(setup))
                break
        for setup in wires:  # under the setup they drive, else their rig, else at the top
            item = self._item(setup)
            parent = None
            for target in setup.driven_targets():
                owner = scene.find_setup(target.split(".", 1)[0])
                if owner is not None and owner.tag in items:
                    parent = items[owner.tag]
                    break
            if parent is None and setup.rig is not None:
                parent = items.get(setup.rig.tag)
            if parent is not None:
                parent.addChild(item)
            else:
                roots.append(item)
        self.tree.addTopLevelItems(roots)
        self.tree.expandAll()

    @staticmethod
    def _item(setup):
        joints = ", ".join(naming.short_name(j) for key in [s.key for s in setup.SLOTS]
                           for j in setup.slot_nodes(key)[:3])
        label = naming.compose(setup.name, setup.side) if setup.CATEGORY != "base" else setup.name
        if setup.is_mirror_secondary():
            label += "  (mirror)"
        item = QtWidgets.QTreeWidgetItem([label, setup.LABEL, joints])
        item.setData(0, TAG_ROLE, setup.tag)
        item.setToolTip(0, setup.describe())
        return item

    def selected_setup(self):
        items = self.tree.selectedItems()
        if not items:
            common._status(self.status, "Select a setup in the list", error=True)
            return None
        tag = items[0].data(0, TAG_ROLE)
        setup = scene.wrap(tag) if tag and cmds.objExists(tag) else None
        if setup is None:
            self.refresh()
            common._status(self.status, "That setup does not exist anymore", error=True)
        return setup

    # ------------------------------------------------------------------
    def edit(self):
        setup = self.selected_setup()
        if setup is not None and self.window_ref is not None:
            self.window_ref.edit_setup(setup)

    def show_graph(self):
        from jeffy.ui.setup_belt import node_tabs

        setup = self.selected_setup()
        if setup is None:
            return
        editor = node_tabs.backend()
        if editor is None:
            common._status(self.status, "The Node Editor needs Maya's interface", error=True)
            return
        done, name = common.run("Show in Node Editor", lambda: node_tabs.show(setup, editor), self.status)
        if done:
            common.ok(self.status, "Node Editor tab %s" % name)

    def connect_skin(self):
        setup = self.selected_setup()
        if setup is None:
            return
        if not hasattr(setup, "connect_skin"):
            common._status(self.status, "Connect skin is for Edge Ribbon setups", error=True)
            return
        done, count = common.run("Connect skin", setup.connect_skin, self.status)
        if done:
            common.ok(self.status, "%s: bindPreMatrix wired for %d influence(s)." % (setup.describe(), count))

    def weights_to_ribbon(self):
        from jeffy.deformers import skin
        from jeffy.setups.tools import ribbon_weights

        setup = self.selected_setup()
        if setup is None:
            return
        ribbon = ribbon_weights.find_ribbon(setup)
        if ribbon is None:
            common._status(self.status, "Weights to ribbon: pick a Ribbon (or the limb it's on)", error=True)
            return
        components = [item for item in cmds.ls(selection=True) or [] if "." in item] or None
        if components and not skin._vertex_selection(components):
            components = None
        done, report = common.run("Weights to ribbon", lambda: ribbon_weights.transfer(ribbon, components=components),
                                  self.status)
        if done:
            common.ok(self.status, "%s: %s." % (ribbon.describe(), ", ".join(
                "%s %d vertices" % (mesh, count) for mesh, count in report)))

    def select_controls(self):
        setup = self.selected_setup()
        if setup is not None:
            cmds.select(list(setup.controls.values()) or setup.tag)

    def rebuild(self):
        setup = self.selected_setup()
        if setup is None:
            return
        done, new = common.run("Rebuild " + setup.LABEL, setup.rebuild, self.status)
        if done:
            common.ok(self.status, "Rebuilt %s." % new.describe())
            self.refresh()

    def delete(self):
        setup = self.selected_setup()
        if setup is None:
            return
        layers = setup.all_layers()
        text = "Delete %s?" % setup.describe()
        if setup.CATEGORY == "base":
            members = setup.members()
            if members:
                text += "\n\nEvery setup of the rig is deleted too (%d)." % len(members)
        elif layers:
            text += "\n\nLayers stacked on it are deleted too:\n%s" % "\n".join(layer.describe() for layer in layers)
        if not common.confirm(self, "Delete setup", text):
            return
        mirror = False
        if setup.mirror is not None:
            mirror = common.confirm(self, "Delete setup", "Also delete the other side (%s)?" % setup.mirror.describe())
        described = setup.describe()
        done, _result = common.run("Delete " + setup.LABEL, lambda: setup.delete(mirror=mirror), self.status)
        if done:
            common.ok(self.status, "Deleted %s." % described)
            self.refresh()

    # ------------------------------------------------------------------
    def snap(self):
        from jeffy.setups.tools import ikfk_limb

        nodes = common.selection()
        if not nodes:
            common._status(self.status, "Select a control of an IK/FK Limb", error=True)
            return

        def snap_all():
            done = []
            for node in nodes:
                limb = ikfk_limb.find_limb(node)
                if limb is not None and limb not in done:
                    ikfk_limb.toggle(limb, key=self.key.isChecked())
                    done.append(limb)
            if not done:
                raise common.SetupError("Select a control of an IK/FK Limb")
            return done

        done, limbs = common.run("IK/FK Snap", snap_all, self.status)
        if done:
            common.ok(self.status, "Snapped %s." % ", ".join(limb.describe() for limb in limbs))

    def load_spaces(self):
        nodes = common.selection()
        self.space_combo.clear()
        if not nodes:
            common._status(self.status, "Select a control with spaces", error=True)
            return
        labels = attach.space_labels(nodes[0])
        if not labels:
            common._status(self.status, "%s has no spaces" % nodes[0], error=True)
            return
        self.space_combo.addItems(labels)
        current = cmds.getAttr("%s.%s" % (nodes[0], attach.space_attr(nodes[0])))
        self.space_combo.setCurrentIndex(current)
        self.space_combo.setProperty("control", nodes[0])
        common.ok(self.status, "%s: %s" % (nodes[0], ", ".join(labels)))

    def switch_space(self):
        control = self.space_combo.property("control")
        if not control or not cmds.objExists(control) or self.space_combo.count() == 0:
            common._status(self.status, "Press 'Spaces of selected' first", error=True)
            return
        label = self.space_combo.currentText()
        done, _result = common.run("Switch Space", lambda: attach.switch(control, label, key=self.key.isChecked()),
                                   self.status)
        if done:
            common.ok(self.status, "%s is now in %s space." % (control, label))
