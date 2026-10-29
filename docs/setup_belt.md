# Jeff Inventory: the Setup Belt

Status: **all three stages built**. BUILD: Rig Base, FK Chain, IK/FK Limb
(with auto-snap), Spline IK/FK (spine, neck, chain), Aim, Hand / Fingers,
Jaw / Hinge. LAYERS: Ribbon, Twist, Reverse Foot, Fleshy Lids, Spaces.

## Quick start

1. Build your bind skeleton (joints only, named like `L_upperArm_JNT`). Bend
   elbows and knees slightly so the IK knows which way they bend.
2. Open it: Jeff Inventory menu > *Open Jeff Inventory*, the **JEFF** shelf
   button, or `import jeffy; jeffy.show()`.
3. **Rig Base**: load your root joint, build. (Other tools offer to create it
   when it is missing.)
4. Pick a tool, select the joints, press `[<]` on the first slot (selecting
   several joints in order fills the next slots too), set the options, then
   **Build**. *Preview* first if you want to move the guides (pole, settings
   control).
5. **SCENE > Setups** lists everything. Double click a setup to edit it and
   **Rebuild**, delete it, snap IK/FK or switch spaces without popping.

Python:

```python
from jeffy.setups.tools.rig_base import RigBase
from jeffy.setups.tools.fk_chain import FkChain
from jeffy.setups.tools.ikfk_limb import IkFkLimb, toggle
from jeffy.setups.tools.spaces import Spaces

RigBase.build(root_joint="C_root_JNT", name="hero")
FkChain.build(start="L_clavicle_JNT")                     # builds R_ too (mirror=True)
arm = IkFkLimb.build(start="L_shoulder_JNT", mid="L_elbow_JNT", end="L_wrist_JNT", name="arm")
leg = IkFkLimb.build(start="L_hip_JNT", mid="L_knee_JNT", end="L_ankle_JNT", name="leg", knee="no-flip")
Spaces.build(control="L_armIK_CTL", targets=["C_root_CTL", "C_global_CTL"], mode="parent")
arm = arm.rebuild(options={"game_safe": True})            # layers on top are rebuilt too
toggle("L_armIK_CTL", key=True)                            # IK/FK snap + switch

from jeffy.setups.tools.ribbon import Ribbon
from jeffy.setups.tools.twist import Twist
from jeffy.setups.tools.foot import ReverseFoot

Ribbon.build(base="L_armIK_CTL", joints=5)                 # or Twist.build(base="L_armIK_CTL", count=3)
ReverseFoot.build(base="L_legIK_CTL", ball="L_ball_JNT", toe="L_toe_JNT")

from jeffy.setups.tools.spline import SplineIkFk
from jeffy.setups.tools.aim import Aim
from jeffy.setups.tools.lids import FleshyLids
from jeffy.setups.tools.jaw import Jaw
from jeffy.setups.tools.hand import Hand

SplineIkFk.build(start="C_spine01_JNT", end="C_chest_JNT", pelvis="C_pelvis_JNT")             # spine
SplineIkFk.build(start="C_neck01_JNT", end="C_neck03_JNT", head="C_head_JNT", mode="neck")
SplineIkFk.build(start="C_tail01_JNT", end="C_tail06_JNT", mode="chain", name="tail")
Aim.build(joints=["L_eye_JNT", "R_eye_JNT"])
FleshyLids.build(base="L_eyeFK_CTL", eye="L_eye_JNT", upper=["L_upperLid_JNT"], lower=["L_lowerLid_JNT"])
Jaw.build(jaw="C_jaw_JNT")
Hand.build(wrist="L_wrist_JNT", fingers=["L_thumb01_JNT", "L_indexMeta_JNT", "L_middleMeta_JNT"], ik=True)
arm.delete()                                               # joints back to their rest pose
```

Tests in real Maya: `mayapy tests/in_maya/run.py` (headless, builds every tool
on a test skeleton).

## Decisions made while building stage 3

- **Spline**: the joints take their position from a hidden chain on a spline
  IK along the ribbon (exact bone lengths when `stretch` is 0) and their
  orientation / twist from the ribbon (`uvPin`).
- **Head** orientation follows the neck by default (`space`: neck, chest,
  COG, root, world). The tail **wave** animates with time (FK controls).
- **Hand** is a build tool on the wrist joint (it follows whatever drives the
  wrist). Metacarpals: *auto* (chains of 5 joints or more), all, all but the
  thumb, or none. The poses and master controls rotate the controls' `ZRO`
  through its `offsetParentMatrix` instead of an extra `POSE` group, so
  `ZRO > OFF > CTL` stays the only hierarchy and `OFF` stays yours.
- **Jaw** is driven by a **chin control you translate** (down opens, X
  swings, Z slides), with clamps on the control.
- **Fleshy Lids** take one or many joints per lid and add a control per lid.

## Decisions made while building stage 2

- **Auto-snap** (*FK follows IK / IK follows FK*): changing `ikFk` (on the
  settings control or any control's proxy) snaps the side you switch to onto
  the other one, so the bend is kept. It is a callback installed by the
  toolkit, and a script node (`jeffySetupBelt_autoSnap_SN`) reinstalls it when
  the scene opens. `autoSnap` on the settings control turns it off. Keyed
  switches during playback are not snapped.
- **Reverse Foot** uses a dedicated **roll control** (rotateX roll, rotateZ
  bank, rotateY ball twist) plus grabbable ground pivots, instead of
  attributes on the IK control. The other attributes are on the roll control.
- **Twist** and **Ribbon** are exclusive on a setup (the ribbon twists already).

## Decisions made while building stage 1

- The **skeleton group follows the Global control**. Global scale reaches
  every joint, driven or not, and the bind joints keep a scale of 1. Keep
  *Put skeleton in rig* on.
- The **Global and Root controls** sit directly under `{name}_RIG`, next to
  the four groups, so *controlsVis* hides the setups' controls but never the
  Global control.
- The **hidden IK chain has its own planar orientation** (X down the bone, Z
  on the bend axis). Fixed offsets map it back to your joints, so pin, pole
  and snapping are exact whatever the orientation of your skeleton.
- The **Spaces** tool can also rename the enum (*Attribute* option). Deleting
  the layer brings the default `space` enum back.
- The belt sizes controls from your joint lengths (the *Control size* option
  multiplies that).

## What it is

A dockable **Jeff Inventory** window: a belt of setup tools for
rigging by hand. You build the bind skeleton yourself (no controls, no
setups). Then each tool turns the joints you give it into one clean, complete
setup. Tools **stack**: a layer tool (ribbon, reverse foot, hand poses...)
builds on top of a setup that already exists.

It is not an auto-rigger and has no body-part templates or recipes. Next to
the tools, SCENE > **Utilities** keeps the control shape tools and skin
weights export / import. (The old Jeffy Toolkit tabs were removed in 2.0.0.)

## Decisions

| Topic | Decision |
|---|---|
| Window | Separate dockable window. Tool list on the left, the selected tool's panel on the right |
| Giving joints | Named slots filled by hand: select a joint, press `[<]`. Nothing is guessed |
| Placement | **Preview** shows guide locators at their default positions; you move them; **Build** uses them |
| Wiring | Matrix-based: `offsetParentMatrix`, `blendMatrix`, `aimMatrix`, `pickMatrix`, `multMatrix`, `uvPin`. **No constraint nodes** (IK handles are the only solver nodes) |
| Bind skeleton | Hidden IK and FK chains blend into it. Its translate/rotate/scale channels are driven; nothing is parented under it or re-parented, and joint orients are never changed |
| Per-build toggles | **Game safe**, **Bendy**, **Squash & stretch** (on the tools where they apply) |
| Naming | `L_upperArm_JNT` style. Side and name come from the first joint and can be edited. Created nodes: `{side}_{name}{Part}_{TYPE}` |
| Controls | `ZRO` + `OFF` group above every control. `ZRO` takes attach/space matrices, `OFF` is free for your own SDKs. Side colours from the toolkit (L blue, R red, C yellow) |
| Twist | The tools create twist joints (Twist layer). The Ribbon layer has its own deform joints |
| Linking | Auto-attach to the setup above in the joint hierarchy, plus default spaces |
| Mirror | A **Mirror** checkbox builds the other side from `L_`/`R_` names |
| Management | **Setup list**, plus **Rebuild with new options** |
| Clavicle | Plain FK (no auto clavicle) |
| Delivery | Three stages. Each one is tested headless in Maya 2027 before you test it in Maya |

## How stacking works

### Setup tag
Every build creates one hidden `network` node, `{side}_{name}_SETUP`, holding:

- type, version, side, name, and options (JSON)
- **slots**: the joints you gave it
- **outputs**: one transform per joint whose world matrix is that joint's final
  pose. Bind joints follow outputs; other setups and layers read outputs.
- **controls**, **settings control**, top groups, and guide positions
- **parent setup** and **layers** (setups stacked on it)

A layer's panel has one **Base setup** slot. Pick *any* control of a setup and
the tool reads everything else from the tag: joints, side, name, outputs, and
where its attributes go.

### Rig layout
```
{name}_RIG
  C_global_ZRO > OFF > C_global_CTL      global scale, visibility / display switches
    C_root_ZRO > OFF > C_root_CTL
  {name}_controls_GRP     one group per setup (controls only)
  {name}_systems_GRP      hidden: IK chains, outputs, systems
  {name}_skeleton_GRP     your skeleton (joint values untouched), follows the Global control
  {name}_geometry_GRP
```
The **Rig Base** tool makes this. If you build another tool first, the
window offers to create a Rig Base.

### Auto-attach and default spaces
- When a setup is built, its top `ZRO` follows the output of the setup that
  drives the parent joint (arm -> clavicle output, clavicle -> chest...). If
  no setup drives it, the `ZRO` follows the Rig Base root control.
- **Order between base setups doesn't matter.** Building the spine after the
  arms re-attaches the arms to it and refreshes their spaces.
- Controls carry a **space role** (`world`, `root`, `cog`, `hips`, `chest`,
  `head`...). Default spaces are found by walking up the setup tree:

| Control | Default spaces |
|---|---|
| Limb IK control (hand/foot) | world, root, COG, chest/hips, parent setup |
| Pole vector | world, root, IK control, limb root |
| Limb FK top control | orient: parent, chest/hips, root, world |
| Head | orient: neck, chest, COG, world |
| Eye target | head, world |

The **Spaces** tool edits them later, on any control.

### Order rules, delete and rebuild
- A layer refuses to build on the wrong base, with a clear message (for example
  "Reverse Foot needs an IK/FK Limb setup").
- **Delete**: removes every node of the setup and puts the bind joints back to
  the rest pose stored at build. If layers are stacked on it, a dialog lists
  them; confirming deletes them too.
- **Rebuild with new options**: load a setup from the setup list, change
  options or guides, press **Rebuild**. Layers on top rebuild after it with
  their own stored options.
- **Control shapes are remembered.** Edit a belt control's shape by hand (CVs,
  Replace Shape, colour, line width, always on top) and Delete or Rebuild the
  setup: the next build of a setup with the same type, name and side gives the
  shape back (a Rebuild under a new name keeps it too). Only edited controls
  are stored, so untouched ones still follow the joints and the size option.
  A remembered shape scales with the setup's *Control size* when that option
  changes. The memory is one scene node, `jeffyShapeMemory`, which belongs to
  no setup. SCENE > Utilities > **Remember Shapes** stores the selected
  controls now, **Forget Shapes** makes the next rebuild use the default shape
  again. The Edge Ribbon master outline (its CVs follow the lips) is never
  stored.
- Every Build, Rebuild or Delete is one undo step.

### Game safe
- **On**: stretch moves child joints along the bone (translate). Bind joints
  never get scale. Ribbon deform joints are parented inside the bind
  hierarchy so they export.
- **Off**: scale-based stretch and squash are allowed on bind joints. Ribbon
  joints live in their own group.

## The window

```
+------------+------------------------------------+
| BUILD      | IK/FK LIMB                         |
|  Rig Base  |  Name [arm     ]  Side [L v]       |
|  FK Chain  |  -- Joints ----------------------  |
| >IK/FK     |  Start [L_shoulder_JNT  ] [<]      |
|  Spline    |  Mid   [L_elbow_JNT     ] [<]      |
|  Aim       |  End   [L_wrist_JNT     ] [<]      |
|  Jaw/Hinge |  -- Options ---------------------  |
| LAYERS     |  [x] Stretch  [x] Soft IK  [x] Pin |
|  Ribbon    |  Knee (o) Pole  ( ) No-flip        |
|  Twist     |  [ ] Game safe   [x] Mirror        |
|  Foot      |  -- Controls --------------------  |
|  Hand      |  Size [1.0]  Colour [side]         |
|  Lids      |                                    |
|  Spaces    |  [Preview]  [Build]  [Delete]      |
| SCENE      |                                    |
|  Setups    |                                    |
+------------+------------------------------------+
```

- Panels are generated from each tool's slot and option list, so every tool
  looks and behaves the same.
- **Setups** (scene list): a tree of setups and their layers. Click one to load
  it back into its panel. It also has Select controls, Rebuild, Delete,
  IK/FK match and seamless space switch.
- Opens from the Jeff Inventory menu, the **JEFF** shelf button (the green
  eye), or `jeffy.show()`.
- The window keeps Maya's grey style. Its header is a soft dot-matrix strip
  where the eye shows the state. A light eye with a square of light means
  idle. A green eye with the sigil means a command is running. A red eye split
  in two means the last command failed; the panel's message says why. The eye
  lives in `jeffy/ui/theme.py`, and `tools/make_icons.py` renders the shelf
  icons from the same drawing code.
- Every tool is also a Python class, for example
  `IkFkLimb.build(start=..., mid=..., end=..., stretch=True)`.

### Node Editor tabs

Each time a setup is built or rebuilt, the Node Editor gets a tab named after
it (`L_arm_IkFkLimb`, `C_hero_RigBase`...). The tab shows only that setup's
main nodes, laid out left to right by dependency:

1. **inputs**: its controls, what its anchors follow, and for layers the base
   controls they use,
2. **systems**: the matrix nodes it created (multMatrix, blendMatrix,
   aimMatrix, decompose/compose, pickMatrix, choice, uvPin...) and its hidden
   joints, IK handles, ribbons and curves,
3. **outputs**: its output transforms,
4. **joints**: the bind joints it drives.

Scalar math nodes, shapes, unit conversions, controller tags and plain groups
are hidden, but dependencies are traced through them so the order stays right.
The node list comes from the setup's tag.

- Rebuilding a setup updates its tab in place. Deleting a setup removes its tab
  (and its layers' tabs).
- Turn it off with **Node Editor tab per setup** in the Setups list. **Show in
  Node Editor** opens the tab for the selected setup on demand.
- Placement uses `nodeEditor -dotFormat` with a Graphviz "plain" file (no
  Graphviz install needed). If Maya refuses it, the editor's own automatic
  layout is used instead. Moving node items through Qt crashed Maya in
  testing, so that fallback is not used.
- Nothing happens in batch or mayapy, where there is no Node Editor.

## Tools

### Base tools (build on joints)

**1. Rig Base**
- Slots: root joint (optional).
- Creates: the rig layout above, **Global** control (global scale) and **Root**
  control. Global holds visibility (controls, joints, geo) and geo display
  (normal / template / reference).

**2. FK Chain**: clavicle, simple chains, props, the base for fingers and toes
- Slots: Start, End (any number of joints between; End empty = one joint).
- Options:
  - orient isolation (follow parent / world)
  - master control that bends the whole chain
  - FK stretch (length attributes)
  - control on the last joint on/off
  - lock translate

**3. IK/FK Limb**: arms, legs
- Slots: Start (shoulder/hip), Mid (elbow/knee), End (wrist/ankle).
- Guides: pole position, settings control position.
- Options:
  - stretch, soft IK, pin to pole
  - knee/elbow mode: **pole vector** or **no-flip** (`kneeTwist` attribute)
  - IK control orientation (world / joint)
  - upper/lower length multipliers
  - game safe, mirror
- Creates:
  - FK controls, IK control, pole and connector line
  - settings control with `ikFk` (also a proxy attribute on every limb control)
  - hidden IK and FK chains blended by `blendMatrix`
- Animation: seamless IK->FK / FK->IK snap, with an option to key it.

**4. Spline IK/FK** (built): spine, neck, tail, tentacle
- Slots: Start, End (3 joints or more), Pelvis (spine, optional), Head (neck,
  optional). Option *Mode*: spine / neck / chain.
- Inside: a hidden NURBS ribbon shaped by the IK controls (each control holds
  its tangents, so rotating it bends the chain) with `uvPin` (stable twist),
  and a hidden spline IK chain for the lengths.
- Spine: **COG** (role `cog`) moves everything; **hips** (role `hips`) rotate
  the pelvis on their own; IK controls hips / mid / chest (role `chest`) under
  an FK layer.
- Neck: FK layer, IK base / mid, and a **head** control: the neck's top, with
  orient spaces (neck by default, chest, COG, root, world).
- Chain: FK on every joint and IK controls, `ikFk` on a settings control, and
  the **wave** (`waveAmplitude`, `waveLength`, `waveSpeed`, `waveOffset`,
  `waveFalloff`) on the FK controls, animated by time with native `sin` nodes.
- All modes: `stretch` (0 keeps the length) and `volume` (film).

**5. Aim** (built): eyes, also pistons and look-at parts
- Slots: the eye joints (2 or more). They follow the setup driving their
  parent (the head).
- Guide: the target. Options: look direction, default target distance.
- Creates: a master target (spaces: parent / world / root), one target per
  eye, and an FK control per eye on top of the aim (`aim` 0..1).

**6. Jaw / Hinge** (built): jaw, also prop lids and doors
- Slots: Jaw joint, Chin joint (optional: the jaw's child).
- A **chin control** you translate: down (-Y) opens, X swings, Z slides
  forward / back; clamps `openMax`, `closeMax`, `sideMax`, `forwardMax`,
  `backMax` and an `open` attribute (degrees) on the control.

**7. Hand / Fingers** (built, also toes)
- Slots: Wrist (the hand's root joint), Fingers (first joint of each finger,
  thumb first).
- Options: metacarpals (auto / all / all but thumb / none), IK fingers,
  controls on the tips, flip curl direction.
- Creates: FK controls per joint, metacarpal controls, a **master** control
  per finger, a **hand** control with `curl`, `spread`, `fist`, `relax`,
  `cup` and `<finger>Curl` / `<finger>Ik`.
- IK fingers: a planar IK on the first three phalanges, an IK tip control
  (spaces: hand / world / root) to keep a fingertip on a surface.

### Layer tools (build on a setup)

**8. Ribbon** (bendy, built)
- Base: an IK/FK Limb or a FK Chain with 2+ segments.
- Options: deform joints per segment (default 5), bend controls, first segment
  twist (from parent / follow joint), volume, game safe.
- Creates: one NURBS ribbon per segment (its CVs ride on the outputs and bend
  controls) with `uvPin`, its **own deform joints**, a bend control in the
  middle of each segment and at each inner joint (elbow / knee). `bendyVis`
  and `volume` go on the limb's settings control.
- Game safe: the ribbon joints are parented under the bind joints (they
  export) and get no volume scale. Otherwise they live in their own group.
- You skin to the ribbon joints instead of the limb joints.

**9. Twist** (built)
- Base: an IK/FK Limb or FK Chain.
- Options: joints per segment (3); first segment `counter` (the shoulder / hip
  roll fades in along the bone), other segments `forward` (the end joint's
  roll spreads along the bone), or `off`.
- Creates: twist joints parented under each segment's first joint, driven by
  `aimMatrix` frames blended along the bone.
- Refuses a setup that already has a Ribbon (the ribbon handles twist there).

**10. Reverse Foot** (built)
- Base: an IK/FK Limb. Slots: Ball, Toe tip (the ankle comes from the limb).
- Guides: heel, toe tip, inner, outer and the roll control, placed on the
  ground automatically. Move them, then Build.
- A **roll control** behind the heel: rotateX roll (heel below 0, ball up to
  `rollBreak`, toe tip after, the ball straightens by `rollStraight`),
  rotateZ bank (positive: outer edge), rotateY ball twist; attributes
  `heelTwist`, `toeTwist`, `toeTap`, `rollBreak`, `rollStraight`, `pivotsVis`.
- **Ground pivot controls** you can grab (heel, toe, outer, inner, ball, toe
  tap), and an FK toe control under the limb's FK end control.
- The limb's IK end moves under the foot pivots automatically; snapping and
  auto-snap include the foot.

**11. Fleshy Lids** (built)
- Base: an Aim setup. Slots: the eye, upper lid joint(s), lower lid joint(s).
- Every lid joint turns around the eye by the eye's rotation scaled by
  `eyeFollow` (up / down) and `sideFollow`, plus a control per lid (rotate it
  to open / close).

**12. Spaces**
- Slots: control, targets (a list, pre-filled with the default candidates).
- Options: parent / orient / point, attribute name, labels, default space.
- Uses `ZRO` `offsetParentMatrix`. Has a seamless switch button, with an
  option to key it.

**13. Edge Ribbon** (built): lips, also brows, cheeks, nasolabial folds
- Slots: the setup it follows (the **Jaw / Hinge** for lips, the head's setup
  otherwise), the **edges** (a closed loop all around the lips, or an open
  chain), and the blendShape (optional).
- BlendShape: the one you load, else the first one on the mesh, else an empty
  one is added at the front of the mesh's deformers (add targets whenever).
  Delete removes that empty one again; it is kept once it has targets. The
  blendShape must come before the skinCluster.
- Options: controls (8; on a closed loop with an even count both corners get
  one), bind joints (20), control shape (sphere, circle, cube, diamond,
  octahedron, square, locator), ribbon width (auto), master control, jaw follow
  defaults (upper 0, corners 0.5, lower 1), size, game safe.
- Creates:
  - controls along the loop that **follow the blendShape** (their channels
    stay at 0, you animate on top), named from the centre out:
    `C_lipsUpper`, `L_lipsUpper01`, `L_lipsCorner`, `C_lipsLower`...;
  - `jawFollow` on each control when the base is a Jaw setup;
  - a **master** control: moving, rotating or scaling it moves every control.
    Its outline follows the lips' blendShape and jaw pose live;
  - its own **bind joints** riding a ribbon driven by the controls.
- **No double transformation**: a hidden base ribbon follows only the
  blendShape. Skin the mesh to the bind joints yourself, then press
  **Connect skin** in the Setups list (or `setup.connect_skin()`): each joint's
  `bindPreMatrix` becomes the inverse of its base point, so the skin only adds
  what the controls, the jaw and the head did.
- **Rebuild keeps your skin**: the joints' weights are saved before the delete
  and put back on the new joints (same names), and bindPreMatrix is wired
  again.
- **Game safe**: engines don't read live bindPreMatrix, so each joint carries
  only the offset (`rest * inverse(base) * driven`) under the head bind joint.
  A normal bind then gives the same result. In that mode the joints sit at
  their rest spot plus the controls' offset, not on the deformed lip.
- Mirror: an open chain on one side (a brow) builds the other side too (the
  mesh must be symmetrical).

## Code layout

```
scripts/jeffy/setups/
    core/      schema.py (slots, options), tag.py (setup tag), base.py (Setup class: build/delete/rebuild/mirror),
               scene.py (registry, queries), controls.py (ZRO/OFF controls), drive.py (joint-orient-aware
               matrix driving of bind joints), attach.py (auto-attach + spaces), guides.py,
               edges.py (edge loop slots: order, mirror)
    tools/     rig_base, fk_chain, ikfk_limb, spline, aim, hand, jaw, ribbon, twist, foot, lids, spaces,
               edge_ribbon
scripts/jeffy/ui/setup_belt/
               window.py, panel.py (built from each tool's schema), setup_list.py, common.py,
               node_tabs.py (a Node Editor tab per setup; layout from core/graph.py)
tests/test_setups.py   pure-Python tests (schema, registry, window offscreen), run in CI
tests/in_maya/         headless builds in mayapy on a generated test skeleton: mayapy tests/in_maya/run.py
```

## Testing (before each stage reaches you)

Each tool is built headless in Maya 2027 on a generated test biped. The tests
check that:

- there are **no constraint nodes**
- bind joints don't move at build (no pop)
- IK/FK snap matches both ways
- stretch, soft IK and pin values are right
- mirror gives matching sides
- delete leaves the skeleton exactly as it was
- rebuild with new options keeps the stacked layers

## Stages

1. **Foundation** (built): setup tag, Setup class, controls, matrix driving,
   auto-attach and spaces, guides, delete/rebuild; window, panels, setup
   list; **Rig Base, FK Chain, IK/FK Limb, Spaces**.
2. **IK/FK auto-snap, Ribbon, Twist, Reverse Foot** (built).
3. **Spline IK/FK** (spine, neck, tail), **Hand**, **Aim**, **Jaw / Hinge**,
   **Fleshy Lids** (built).

You test each stage in Maya before the next one starts.
