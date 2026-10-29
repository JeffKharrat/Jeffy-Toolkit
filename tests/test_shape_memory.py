"""Shape memory pure helpers (no Maya)."""

from jeffy.setups.core import shape_memory as sm

CURVE = {"points": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]], "degree": 1, "periodic": False}


def test_entry_key():
    assert sm.entry_key("spline", "spine", "C", "hips") == "spline|spine|C|hips"
    assert sm.entry_key("rig_base", "hero", None, "global") == "rig_base|hero||global"


def test_signature_ignores_noise_and_size():
    entry = {"curves": [CURVE], "color": 17, "line_width": 2.0, "on_top": False}
    noisy = {"curves": [dict(CURVE, points=[[1.00000001, -0.0, 0.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])],
             "color": 17, "line_width": 2.0, "on_top": False, "size": 3.0}
    assert sm.signature(entry) == sm.signature(noisy)
    assert sm.signature(entry) != sm.signature(dict(entry, color=13))
    moved = dict(entry, curves=[dict(CURVE, points=[[2.0, 0.0, 0.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])])
    assert sm.signature(entry) != sm.signature(moved)


def test_scaled_and_size_factor():
    assert sm.scaled([CURVE], 1.0) == [CURVE]
    doubled = sm.scaled([CURVE], 2.0)
    assert doubled[0]["points"][0] == [2.0, 0.0, 0.0]
    assert CURVE["points"][0] == [1.0, 0.0, 0.0], "the input is not modified"
    assert sm.size_factor(1.0, 1.5) == 1.5
    assert sm.size_factor(None, 2.0) == 1.0 and sm.size_factor(0, 2.0) == 1.0 and sm.size_factor("x", 1) == 1.0


def test_rename_entries():
    data = {"ribbon|leg|L|bend1": 1, "ribbon|leg|L|bend2": 2, "ribbon|legs|L|bend1": 3, "ribbon|arm|L|bend1": 4}
    result = sm.rename_entries(data, "ribbon", "leg", "L", "arm", "L")
    assert result == {"ribbon|arm|L|bend1": 4, "ribbon|arm|L|bend2": 2, "ribbon|legs|L|bend1": 3}, \
        "existing entries win, 'legs' is another setup"
    assert sm.rename_entries(data, "ribbon", "leg", "L", "leg", "L") == data
