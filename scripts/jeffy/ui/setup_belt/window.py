"""The Jeff Inventory window (the Setup Belt): tool list on the left, the selected tool's panel on the right."""

from jeffy import TOOLKIT_NAME, __version__
from jeffy.core import logger, settings
from jeffy.setups.core import scene
from jeffy.ui import theme
from jeffy.ui.qt import QtCore, QtWidgets, delete_workspace_control, dockable_base, maya_main_window
from jeffy.ui.setup_belt.doctor_panel import DoctorPanel
from jeffy.ui.setup_belt.panel import ToolPanel
from jeffy.ui.setup_belt.setup_list import SetupsPanel
from jeffy.ui.setup_belt.utilities import UtilitiesPanel

LOG = logger.get_logger("setup_belt")
OBJECT_NAME = "jeffySetupBeltWindow"
CATEGORIES = (("base", "BUILD"), ("build", None), ("layer", "LAYERS"), ("wire", "WIRES"))
SETUPS_KEY = "__setups__"
UTILITIES_KEY = "__utilities__"
DOCTOR_KEY = "__doctor__"

_MIXIN = dockable_base()
_BASES = (QtWidgets.QWidget,) if _MIXIN is object else (_MIXIN, QtWidgets.QWidget)
_STATE = {"window": None}


class SetupBeltWindow(*_BASES):
    def __init__(self, parent=None):
        super(SetupBeltWindow, self).__init__(parent=parent or maya_main_window())
        self.setObjectName(OBJECT_NAME)
        self.setWindowTitle("%s %s" % (TOOLKIT_NAME, __version__))
        self.setWindowFlags(QtCore.Qt.Window)
        self.setMinimumSize(520, 480)
        self.resize(700, 680)

        theme.apply(self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.banner = theme.EyeBanner("%s %s" % (TOOLKIT_NAME, __version__))
        layout.addWidget(self.banner)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        layout.addWidget(splitter)

        self.tool_list = QtWidgets.QListWidget()
        self.tool_list.setMaximumWidth(170)
        self.tool_list.setMinimumWidth(120)
        self.stack = QtWidgets.QStackedWidget()
        splitter.addWidget(self.tool_list)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([150, 600])

        self.panels = {}
        tools = sorted(scene.load_tools().items(), key=lambda item: (item[1].ORDER, item[1].LABEL))
        for category, header in CATEGORIES:
            if header:
                self._header(header)
            for setup_type, cls in tools:
                if cls.CATEGORY != category:
                    continue
                try:
                    panel = ToolPanel(cls, window=self)
                except Exception as error:  # a broken panel must not break the window
                    LOG.exception("Could not build the %s panel: %s", cls.LABEL, error)
                    panel = QtWidgets.QLabel("Panel failed to load:\n%s" % error)
                self._add(cls.LABEL, setup_type, panel, cls.DESCRIPTION)
        self._header("SCENE")
        self.setups_panel = SetupsPanel(window=self)
        self._add("Setups", SETUPS_KEY, self.setups_panel, "Every setup in the scene")
        try:
            utilities = UtilitiesPanel()
        except Exception as error:  # a broken panel must not break the window
            LOG.exception("Could not build the Utilities panel: %s", error)
            utilities = QtWidgets.QLabel("Panel failed to load: %s" % error)
        self._add("Utilities", UTILITIES_KEY, utilities, "Control shapes and skin weights")
        try:
            doctor = DoctorPanel()
        except Exception as error:  # a broken panel must not break the window
            LOG.exception("Could not build the Rig Doctor panel: %s", error)
            doctor = QtWidgets.QLabel("Panel failed to load: %s" % error)
        self._add("Rig Doctor", DOCTOR_KEY, doctor, "Scan the scene for rig problems (report only)")

        self.tool_list.currentItemChanged.connect(self._on_tool)
        last = settings.get("belt_last_tool") or "ikfk_limb"
        self.select_tool(last if last in self.panels else next(iter(self.panels)))

    # ------------------------------------------------------------------
    def _header(self, text):
        item = QtWidgets.QListWidgetItem(text)
        item.setFlags(QtCore.Qt.NoItemFlags)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        self.tool_list.addItem(item)

    def _add(self, label, key, panel, tooltip=""):
        item = QtWidgets.QListWidgetItem("   " + label)
        item.setData(QtCore.Qt.UserRole, key)
        item.setToolTip(tooltip)
        self.tool_list.addItem(item)
        self.stack.addWidget(panel)
        self.panels[key] = panel

    def _on_tool(self, current, _previous=None):
        if current is None:
            return
        key = current.data(QtCore.Qt.UserRole)
        panel = self.panels.get(key)
        if panel is None:
            return
        self.stack.setCurrentWidget(panel)
        if key == SETUPS_KEY:
            self.setups_panel.refresh()
        try:
            settings.set("belt_last_tool", key)
        except Exception:
            pass

    def select_tool(self, key):
        for row in range(self.tool_list.count()):
            item = self.tool_list.item(row)
            if item.data(QtCore.Qt.UserRole) == key:
                self.tool_list.setCurrentItem(item)
                return self.panels[key]
        return None

    def edit_setup(self, setup):
        """Open a setup in its tool panel (editing mode)."""
        panel = self.select_tool(setup.TYPE)
        if isinstance(panel, ToolPanel):
            panel.load(setup)
        return panel

    def refresh_setups(self):
        self.setups_panel.refresh()


def close():
    window = _STATE.get("window")
    if window is not None:
        try:
            window.close()
            window.deleteLater()
        except RuntimeError:
            pass
    _STATE["window"] = None
    delete_workspace_control(OBJECT_NAME)


def show(dockable=True):
    """Open the Setup Belt (a single instance)."""
    close()
    window = SetupBeltWindow()
    _STATE["window"] = window
    if _MIXIN is not object:
        window.show(dockable=dockable, floating=True)
    else:
        window.show()
    return window
