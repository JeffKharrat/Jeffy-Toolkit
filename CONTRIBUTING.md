# Contributing / maintaining Jeff Inventory

Jeff Inventory is meant to grow over time. This page explains where things go
and how to ship an update safely.

## Setup

```bash
git clone https://github.com/CrapyShit/Jeffy-Toolkit.git
cd Jeffy-Toolkit
pip install pytest ruff maya-stubs "PySide6-Essentials<6.12"
```

Inside Maya, install once with `install/drag_and_drop_install.py`. After
editing code, use Jeff Inventory menu > **Reload** (or run `jeffy.reload_toolkit()`).

## Checks to run before every commit

```bash
ruff check .                                   # style + common bugs
python tools/check_maya_api.py scripts install # every cmds flag exists
QT_QPA_PLATFORM=offscreen python -m pytest     # tests (no Maya needed)
```

CI runs the same three steps on every push.

Scene behaviour (every tool's build) is tested in real Maya, headless:

```bash
"C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe" tests/in_maya/run.py   # -k name to filter
```

## Conventions

- **Python 3.7 compatible** (Maya 2022). No walrus operator, no `match`, no
  `list[str]` annotations at runtime, no `str.removeprefix`.
- **Long flag names only** in `maya.cmds` calls (`maintainOffset=True`, not
  `mo=True`). `tools/check_maya_api.py` only knows long names, and they read better.
- `cmds` calls that may return `None` are guarded: `cmds.listRelatives(...) or []`.
- **Never depend on the selection** inside library functions. Pass nodes as
  arguments. Selection handling belongs in `jeffy/ui/actions.py`.
- Joints are created with `jeffy.joints.tools.create_joint` (never
  `cmds.joint`, which parents to the current selection).
- Names go through `jeffy.core.naming` (`naming.compose(name, side, type)`).
- Pure math lives in `jeffy.core.mathlib` / `jeffy.deformers.weights` /
  `jeffy.geometry.spatial` so it can be unit tested.
- Belt tools wire everything with matrix / utility nodes: **no constraint
  nodes** (the Maya tests check it).
- Every user-facing entry point is a function in `jeffy/ui/actions.py`
  decorated with `@tool("Label")`, which gives one undo chunk and friendly errors.

## Where to add things

| You want to add... | Put it in |
|---|---|
| a belt tool | a `Setup` subclass with `@scene.register` in `setups/tools/` (declare `SLOTS`, `OPTIONS`, `GUIDES`, write `build_setup`), imported in `setups/tools/__init__.py`. Its panel is generated; add a test in `tests/in_maya/` |
| a control shape | `controls/library.py` (`SHAPES` + `CATEGORIES`). Tests validate it automatically |
| a utility button | an action in `ui/actions.py` and a button in `ui/setup_belt/utilities.py` |
| a menu entry | `ui/menu.py` (`MENU`) |
| a shelf button | `ui/shelf.py` (`BUTTONS`) |

`tests/test_ui.py` fails if the menu, the shelf or the Utilities panel
references an action that doesn't exist.

### Writing a belt tool

```python
from jeffy.setups.core import scene
from jeffy.setups.core.base import Setup
from jeffy.setups.core.schema import SIZE_OPTION, Option, Slot
from jeffy.setups.tools import common


@scene.register
class Antenna(Setup):
    TYPE = "antenna"
    LABEL = "Antenna"
    CATEGORY = "build"          # or "layer" (first slot: a control of the base setup)
    ORDER = 60
    DESCRIPTION = "One control per joint that wobbles."
    SLOTS = (Slot("start", "Start"), Slot("end", "End"))
    OPTIONS = (Option("wobble", "Wobble", True), SIZE_OPTION)

    def build_setup(self):
        joints = common.chain(self.slot_node("start"), self.slot_node("end"))
        controls = []
        for index, joint in enumerate(joints):
            parent = controls[-1].node if controls else None
            ctl = self.control("fk%d" % index, common.label(joint) + "FK", parent=parent, match=joint)
            self.add_output("j%d" % index, ctl.node + ".worldMatrix[0]", joint=joint)
            controls.append(ctl)
        self.add_anchor(controls[0].zero)  # the chain follows the setup above it
```

The base class handles the rest: slot checks, the rig base, the setup tag,
driving the bind joints from the outputs, mirroring, delete and rebuild.

## Releasing a new version

1. Update `scripts/jeffy/version.py` (semantic versioning: MAJOR for breaking
   API changes, MINOR for new tools, PATCH for fixes).
2. Move the `[Unreleased]` notes in `CHANGELOG.md` under a new version heading
   (`tests/test_imports.py` checks that the current version is in the changelog).
3. Commit, tag (`git tag v2.1.0`) and push with tags.
4. Users update with `git pull`. The module file points at the repository, so
   there's nothing to reinstall.
