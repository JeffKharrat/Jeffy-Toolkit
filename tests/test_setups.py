"""Setup Belt tests that run without Maya (schema, registry, window).

The scene behaviour (builds, snapping, spaces, delete, rebuild) is tested in
real Maya by ``tests/in_maya`` (``mayapy tests/in_maya/run.py``).
"""

import pytest

from jeffy.setups.core import scene, schema
from jeffy.setups.core.base import Setup
from jeffy.setups.core.schema import Option, SetupError, Slot


def test_option_coercion():
    flag = Option("stretch", "Stretch", True)
    assert flag.kind == "bool"
    assert flag.coerce("off") is False and flag.coerce(1) is True and flag.coerce(None) is True
    count = Option("count", "Count", 3, minimum=1, maximum=10)
    assert count.kind == "int" and count.coerce("4") == 4
    with pytest.raises(SetupError):
        count.coerce(0)
    with pytest.raises(SetupError):
        count.coerce("many")
    mode = Option("mode", "Mode", "pole", choices=("pole", "no-flip"))
    assert mode.kind == "choice" and mode.coerce("no-flip") == "no-flip"
    with pytest.raises(SetupError):
        mode.coerce("auto")
    with pytest.raises(ValueError):
        Option("bad", "Bad", "x", choices=("a", "b"))


def test_resolve_options_rejects_typos():
    options = (Option("stretch", "Stretch", True), Option("size", "Size", 1.0))
    assert schema.resolve_options(options, {"size": "2"}) == {"stretch": True, "size": 2.0}
    with pytest.raises(SetupError):
        schema.resolve_options(options, {"strech": False})


def test_slot_normalize():
    single = Slot("start", "Start")
    many = Slot("targets", "Targets", kind=schema.NODES)
    assert single.normalize(["a", "b"]) == "a" and single.normalize("") is None
    assert many.normalize("a, b;c") == ["a", "b", "c"] and many.normalize(None) == []
    with pytest.raises(ValueError):
        Slot("x", "X", kind="bone")


def test_registry():
    tools = scene.load_tools()
    assert set(tools) >= {"rig_base", "fk_chain", "ikfk_limb", "spaces", "ribbon", "twist", "reverse_foot", "spline",
                          "aim", "lids", "jaw", "hand", "wire_follow", "wire_attribute"}
    for setup_type, cls in tools.items():
        assert issubclass(cls, Setup) and cls.TYPE == setup_type
        assert cls.LABEL and cls.DESCRIPTION
        assert cls.CATEGORY in ("base", "build", "layer", "wire")
        keys = [slot.key for slot in cls.SLOTS]
        assert len(keys) == len(set(keys)), "%s has duplicate slots" % setup_type
        options = cls.option_schema()
        option_keys = [option.key for option in options]
        assert len(option_keys) == len(set(option_keys)), "%s has duplicate options" % setup_type
        assert not set(keys) & set(option_keys), "%s: slot and option names overlap" % setup_type
        defaults = schema.resolve_options(options, {})
        assert set(defaults) == set(option_keys)
        if cls.CATEGORY == "layer":
            assert cls.SLOTS and not cls.SLOTS[0].joints_only, "layers start with the base node slot"


def test_split_values():
    from jeffy.setups.tools.ikfk_limb import IkFkLimb

    slots, options = IkFkLimb.split_values({"start": "a", "mid": "b", "end": "c", "stretch": False})
    assert slots == {"start": "a", "mid": "b", "end": "c"} and options == {"stretch": False}


def test_belt_window_builds_offscreen():
    qt = pytest.importorskip("jeffy.ui.qt")
    app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
    from jeffy.ui.setup_belt import panel, window

    belt = window.SetupBeltWindow()
    labels = [belt.tool_list.item(i).text().strip() for i in range(belt.tool_list.count())]
    assert labels[:4] == ["BUILD", "Rig Base", "FK Chain", "IK/FK Limb"]
    build = labels[:labels.index("LAYERS")]
    layers = labels[labels.index("LAYERS"):labels.index("WIRES")]
    wire_labels = labels[labels.index("WIRES"):labels.index("SCENE")]
    assert set(wire_labels) >= {"Follow", "Attribute Driver"}
    assert set(build) >= {"Spline IK/FK", "Aim", "Hand / Fingers", "Jaw / Hinge"}
    assert set(layers) >= {"Ribbon", "Twist", "Reverse Foot", "Fleshy Lids", "Spaces"}
    assert labels[-4:] == ["SCENE", "Setups", "Utilities", "Rig Doctor"]
    assert belt.windowTitle().startswith("Jeff Inventory")
    for setup_type, cls in scene.load_tools().items():
        tool_panel = belt.panels[setup_type]
        assert isinstance(tool_panel, panel.ToolPanel), "%s panel failed" % setup_type
        assert set(tool_panel.slot_fields) == set(slot.key for slot in cls.SLOTS)
        assert set(tool_panel.option_values()) == set(option.key for option in cls.option_schema())
        assert tool_panel.preview_button.isHidden() == (not cls.GUIDES)
    limb = belt.panels["ikfk_limb"]
    limb.fill_from(limb.slot_fields["start"], ["L_shoulder_JNT", "L_elbow_JNT", "L_wrist_JNT", "L_hand_JNT"])
    assert limb.slot_values() == {"start": "L_shoulder_JNT", "mid": "L_elbow_JNT", "end": "L_wrist_JNT"}
    limb.set_options({"knee": "no-flip", "stretch": False, "pole_distance": 2.5})
    values = limb.option_values()
    assert values["knee"] == "no-flip" and values["stretch"] is False and values["pole_distance"] == 2.5
    belt.close()
    del app


def test_attribute_slots():
    one = Slot("source", "Source", kind=schema.ATTRIBUTE)
    many = Slot("targets", "Targets", kind=schema.ATTRIBUTES)
    assert one.plugs and one.named and not one.multi and not one.components
    assert many.plugs and many.multi
    assert one.normalize(["L_mouth_CTL.translateY"]) == "L_mouth_CTL.translateY"
    assert many.normalize("face_BS.smile, face_BS.frown") == ["face_BS.smile", "face_BS.frown"]


def test_parked_wire_entries_replace_older_ones():
    from jeffy.setups.core import wires

    spec = {"type": "wire_follow", "name": "swordFollow", "side": "C", "options": {}, "slots": {}}
    entries = wires.add_entry([], spec, ["ikfk_limb|arm|L"])
    entries = wires.add_entry(entries, dict(spec, options={"rotate": False}), ["ikfk_limb|arm|L"])
    assert len(entries) == 1 and entries[0]["spec"]["options"] == {"rotate": False}
    assert wires.entry_name(spec) == "wire_follow|swordFollow|C"


def test_doctor_roll_and_names():
    from jeffy.setups.core import doctor

    world = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
    rolled = [(1, 0, 0), (0, 0, 1), (0, -1, 0)]          # 90 degrees around the bone (X)
    bent = [(0, 1, 0), (-1, 0, 0), (0, 0, 1)]            # a plain 90 degree bend: no roll
    assert round(doctor.roll_degrees(world, rolled, (1, 0, 0), (1, 0, 0))) == 90
    assert round(doctor.roll_degrees(world, bent, (1, 0, 0), (0, 1, 0))) == 0
    assert doctor.numbered_suffix("L_LegLeaf2Bend_CTL1") and not doctor.numbered_suffix("L_arm_CTL")
