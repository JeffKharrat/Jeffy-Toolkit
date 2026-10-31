"""SCENE > Rig Doctor: scan the scene for rig problems, then select what it found (it fixes nothing)."""

from maya import cmds

from jeffy.setups.core import doctor
from jeffy.ui import widgets as w
from jeffy.ui.qt import QtCore, QtGui, QtWidgets
from jeffy.ui.setup_belt import common

PROBLEM_COLOR = "#e07a5f"
LOOK_COLOR = "#d6b25e"


class DoctorPanel(QtWidgets.QWidget):
    def __init__(self):
        super(DoctorPanel, self).__init__()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(QtWidgets.QLabel("<span style='font-size:15px'><b>RIG DOCTOR</b></span>"))
        hint = w.label("Scans the scene and lists what looks wrong. Nothing is changed: select a row (or a whole "
                       "check) to go and look. Red: a problem. Yellow: worth a look.")
        hint.setStyleSheet("color: #9a9a9a;")
        layout.addWidget(hint)

        self.checks = {}
        boxes = []
        for key, label, func in doctor.CHECKS:
            box = w.check(label, True, (func.__doc__ or "").strip().splitlines()[0])
            self.checks[key] = box
            boxes.append(box)
        layout.addWidget(w.grid(boxes, columns=2))
        layout.addWidget(w.row(w.button("Scan", self.scan, "Run the ticked checks", height=30)))

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Finding"])
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree.itemDoubleClicked.connect(lambda *_args: self.select())
        layout.addWidget(self.tree, 1)
        layout.addWidget(w.row(w.button("Select", self.select, "Select the nodes of the highlighted rows (a check's "
                                                               "header selects all of its nodes)")))
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def scan(self):
        keys = [key for key, box in self.checks.items() if box.isChecked()]
        done, results = common.run("Rig Doctor", lambda: doctor.scan(keys), self.status)
        if not done:
            return
        self.tree.clear()
        total = 0
        for _key, label, findings in results:
            group = QtWidgets.QTreeWidgetItem(["%s (%d)" % (label, len(findings))])
            group.setData(0, QtCore.Qt.UserRole, [n for f in findings for n in f.nodes])
            font = group.font(0)
            font.setBold(True)
            group.setFont(0, font)
            for finding in findings:
                row = QtWidgets.QTreeWidgetItem([finding.text])
                row.setData(0, QtCore.Qt.UserRole, list(finding.nodes))
                color = PROBLEM_COLOR if finding.severity == "problem" else LOOK_COLOR
                row.setForeground(0, QtGui.QColor(color))
                row.setToolTip(0, finding.text)
                group.addChild(row)
            self.tree.addTopLevelItem(group)
            group.setExpanded(bool(findings) and len(findings) <= 30)
            total += len(findings)
        common.ok(self.status, "%d finding(s)." % total if total else "Nothing found: the scene looks clean.")

    def select(self):
        nodes = []
        for item in self.tree.selectedItems():
            for node in item.data(0, QtCore.Qt.UserRole) or []:
                if node and node not in nodes and cmds.objExists(node):
                    nodes.append(node)
        if nodes:
            cmds.select(nodes, replace=True)
        else:
            cmds.select(clear=True)
