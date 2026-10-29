# Jeff Inventory

**Stackable setup tools for Autodesk Maya that rig the skeleton you built
yourself.** Build the bind skeleton first (joints only). Then pick a tool, load
its joints into named slots and build: each tool makes one clean setup, and
layer tools stack on setups that already exist (a ribbon on an IK/FK arm, a
reverse foot on a leg...).

Everything is matrix based: no constraint nodes, and your joints keep their
hierarchy and joint orients. Setups attach to each other automatically (in any
build order), get default spaces, mirror L to R, and can be deleted (the
skeleton goes back to its rest pose) or rebuilt with new options.

| | |
|---|---|
| Maya | 2022 – 2027 (Python 3.7+, PySide2 or PySide6) |
| Status | `2.0.0` (formerly the Jeffy Toolkit). See the [CHANGELOG](CHANGELOG.md) |
| Docs | [docs/setup_belt.md](docs/setup_belt.md): every tool, its options and how stacking works |
| License | [MIT](LICENSE) |

---

## Installation

1. Clone or download this repository somewhere permanent:
   `git clone https://github.com/CrapyShit/Jeffy-Toolkit.git`
2. Drag `install/drag_and_drop_install.py` into a Maya viewport.

The installer writes a Maya module file (`jeffy_toolkit.mod`) pointing at the
repository, creates the **Jeff Inventory** menu and opens the window. From then
on it loads in every Maya session. To update, `git pull`; no reinstall needed.

Manual install: create `<maya app dir>/modules/jeffy_toolkit.mod` with

```
+ JeffyToolkit 2.0.0 /path/to/Jeffy-Toolkit
PYTHONPATH +:= scripts
```

To uninstall, delete that file (or run `drag_and_drop_install.uninstall()`).

---

## The window

```python
import jeffy
jeffy.show()      # or the Jeff Inventory menu, or the JEFF shelf button
```

| | Tools |
|---|---|
| **BUILD** | **Rig Base** (rig groups, Global / Root controls, visibility switches), **FK Chain**, **IK/FK Limb** (stretch, soft IK, pin, pole or no-flip knee, IK/FK auto-snap), **Spline IK/FK** (spine with COG and independent hips, neck with head spaces, tails with an automatic wave), **Aim** (eyes), **Hand / Fingers** (poses, masters, metacarpals, IK fingers), **Jaw / Hinge** (chin control) |
| **LAYERS** | **Ribbon** (bendy limbs with their own deform joints), **Twist**, **Reverse Foot** (roll control + ground pivots), **Fleshy Lids**, **Spaces** (custom spaces on any top control) |
| **SCENE** | **Setups** (every setup: edit, rebuild, delete, IK/FK snap, seamless space switch), **Utilities** (control shapes, skin weights export / import) |

Each panel is generated from the tool's slots and options: select joints,
press `[<]` (several selected joints fill the next slots), set the options,
*Preview* the guides if you want to place them, then **Build**. Editing a setup
from the Setups list turns Build into **Rebuild**.

## Python

```python
from jeffy.setups.tools.rig_base import RigBase
from jeffy.setups.tools.ikfk_limb import IkFkLimb
from jeffy.setups.tools.foot import ReverseFoot
from jeffy.setups.tools.ribbon import Ribbon

RigBase.build(root_joint="C_root_JNT", name="hero")
arm = IkFkLimb.build(start="L_shoulder_JNT", mid="L_elbow_JNT", end="L_wrist_JNT", name="arm")
leg = IkFkLimb.build(start="L_hip_JNT", mid="L_knee_JNT", end="L_ankle_JNT", name="leg", knee="no-flip")
ReverseFoot.build(base="L_legIK_CTL", ball="L_ball_JNT", toe="L_toe_JNT")
Ribbon.build(base="L_armIK_CTL")
arm = arm.rebuild(options={"game_safe": True})   # the ribbon is rebuilt with it
```

More in [docs/setup_belt.md](docs/setup_belt.md).

---

## Repository layout

```
install/drag_and_drop_install.py   Maya installer (module file)
scripts/userSetup.py               builds the menu at Maya startup
scripts/jeffy/
    setups/      the belt: framework (core/) and tools (tools/)
    core/        naming, attributes, transforms, matrices, math, nodes, undo
    controls/    control shape library and shape tools
    joints/      joint helpers used by the tools
    geometry/    curves, meshes, spatial queries
    deformers/   skin weights export / import
    ui/          the window (setup_belt/), menu, shelf, actions
tests/           pytest suite (runs without Maya)
tests/in_maya/   headless tests in real Maya: mayapy tests/in_maya/run.py
tools/           check_maya_api.py (validates every cmds flag against maya-stubs)
```

## Development

```bash
pip install pytest ruff maya-stubs "PySide6-Essentials<6.12"
ruff check .
python tools/check_maya_api.py scripts install
QT_QPA_PLATFORM=offscreen python -m pytest
"C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe" tests/in_maya/run.py   # builds every tool in Maya
```

Inside Maya, Jeff Inventory menu > *Reload* (or `jeffy.reload_toolkit()`)
reloads every module while you develop. See [CONTRIBUTING.md](CONTRIBUTING.md).

The old Jeffy Toolkit (tabs, rig builders, auto-rigger, face tools...) was
removed in 2.0.0; the git history keeps it (commit `35f5fec`).

## License

Released under the [MIT License](LICENSE).
