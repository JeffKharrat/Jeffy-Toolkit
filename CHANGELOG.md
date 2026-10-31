# Changelog

All notable changes to Jeff Inventory (formerly the Jeffy Toolkit) are
documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Weights to ribbon** (Setups list): moves a limb's skin weights onto its
  Ribbon joints, split evenly along each bone, with the tip fading into the
  end joint. Other influences are untouched, the mesh doesn't move at rest,
  and it can work on selected vertices only. One undo.
- **Wires**, a third kind of belt tool (WIRES, next to BUILD and LAYERS): tiny
  tracked node networks that connect things that already exist. Each wire owns
  its nodes, shows in the Setups list, mirrors, gets its Node Editor tab, and
  deleting it puts back what it drove. Every node it creates explains itself in
  its Notes. Wires rebuild with the setups they use; deleting such a setup
  parks the wire, and building it again brings the wire back.
  - **Follow**: A drives B keeping their offset (translate / rotate / scale,
    optional second driver with a blend attribute). On a belt control it
    drives the OFF group, so spaces keep working.
  - **Attribute Driver**: one attribute drives others through a range
    (clamp, curves). Refuses targets something else drives, and names
    leftover drivers with no real input.
- **Rig Doctor** (SCENE): a scan that reports dead controls, joints rolling
  around their bone, unskinned joints and meshes, leftover nodes, dead driver
  chains, name clashes, rotate at rest, broken setups and parked wires, with
  Select buttons. It changes nothing.
- Setup slots can hold attributes (`node.attr`), loaded from the Channel Box.
- **Shape memory.** Control shapes edited by hand (CVs, colour, line width,
  always on top) are saved when a setup is deleted or rebuilt and given back
  at its next build. Untouched controls are not stored. Remembered shapes
  scale with the *Control size* option. SCENE > Utilities has **Remember
  Shapes** and **Forget Shapes** buttons.
- **Edge Ribbon** layer tool: a ribbon on a mesh edge loop or chain (lips,
  brows, cheeks). Its controls follow the mesh's blendShape and can still be
  animated on top with no double transformation, using a hidden base ribbon
  and live `bindPreMatrix` (or offset joints in game safe mode). It also has
  `jawFollow` on a Jaw setup, a master control whose outline follows the lips,
  its own bind joints, rebuilds that keep the skin weights, and mirroring for
  one-sided chains.
- Setup slots can hold mesh edges.
- **The eye** at the top of the window (Proto Yeff logo) shows the state live,
  in soft colours on Maya's own grey style: light with a square of light
  (idle), green with the sigil (a command is running), red and split (the
  last command failed).
- The shelf's JEFF button is now the green eye (`icons/jeffy_eye.png`, made by
  `tools/make_icons.py`).
- **Node Editor tab per setup.** Building or rebuilding a setup opens a Node
  Editor tab named after it (for example `L_arm_IkFkLimb`). The tab shows only
  that setup's main nodes, laid out left to right: inputs, then matrix nodes,
  then outputs and bind joints. Deleting the setup removes the tab. This can be
  turned off in the Setups list.

### Fixed
- **Rebuilding or deleting a setup could delete other setups' IK handles.** The
  first setup with IK recorded Maya's shared IK solvers as its own nodes;
  rebuilding it deleted them, and every IK handle in the scene with them (a
  spine stuck when the COG moved, dead IK arms and fingers). Setups now never
  own or delete shared solvers, even in older scenes. To repair a scene, reload
  the tool and rebuild the setups whose IK stopped working.
- **The thumb curls toward the palm** instead of sideways: it curls in its own
  bend plane, or toward the palm's centre when it is straight, whatever its
  joint orientation.
- The IK/FK Limb's auto-snap script node is created before the build, so it no
  longer lands in the setup's node list.

## [2.0.0] - 2026-10-23

### Changed
- The project is now **Jeff Inventory**: the Setup Belt is the whole product.
  `jeffy.show()` opens it, the menu is *Jeff Inventory* and the shelf *Jeff*.
  The Python package is still `jeffy`, so the Maya module file keeps working.

### Added
- **Setup Belt** (`jeffy.show()`, menu *Jeff Inventory*, **JEFF** shelf
  button): stackable setup tools that rig your own skeleton.
  Stage 1:
  - Framework (`jeffy.setups`): every setup keeps a hidden tag (slots,
    options, guides, controls, outputs, created nodes), drives the bind joints
    with matrix nodes only (joint orient aware, no constraint nodes),
    auto-attaches to the setup above it in any build order, gets default
    spaces, mirrors L to R, and can be deleted (skeleton back to rest) or
    rebuilt with new options (layers on top are rebuilt too). Preview guides,
    one undo step per build.
  - **Rig Base**: `{name}_RIG` with controls / systems / skeleton / geometry
    groups, Global (global scale, visibility and display switches) and Root
    controls. The skeleton group follows the Global control.
  - **FK Chain**: orient / parent spaces on the top control, master control,
    FK stretch (`length`), optional control on the last joint.
  - **IK/FK Limb**: planar hidden IK chain (works with any joint
    orientation), soft IK, stretch, pin to the pole, upper / lower length,
    pole or no-flip knee (`kneeTwist`), game safe (translate) or scale stretch,
    `ikFk` on a settings control with proxies, seamless snap both ways
    (`jeffy.setups.tools.ikfk_limb.toggle`).
  - **Spaces**: custom spaces (parent / orient / point) on any top control,
    seamless space switch.
  - Window: tool list + generated panels (slots with `[<]` load buttons,
    options, Preview / Build / Rebuild / Delete) and a Setups list with IK/FK
    snap and space switching.
  - `tests/in_maya`: headless tests in real Maya (`mayapy tests/in_maya/run.py`).
- **Setup Belt stage 2**:
  - **IK/FK auto-snap**: changing `ikFk` snaps the other side first, so the
    bend is kept (`autoSnap` on the settings control; a script node reinstalls
    the callback when the scene opens). Layers take part in snapping.
  - **Ribbon** layer: one ribbon per segment of an IK/FK Limb or FK Chain
    drives its own deform joints (5 per segment by default), bend controls at
    mid segments and inner joints, counter twist from the parent, `volume`,
    game safe parenting.
  - **Twist** layer: counter (upper arm / thigh) and forward (forearm / shin)
    twist joints under each segment's first joint.
  - **Reverse Foot** layer: roll control (roll / bank / ball twist with break
    and straight angles, toe tap, heel / toe twist), grabbable ground pivots,
    FK toe control, foot guides.
- **Setup Belt stage 3**:
  - **Spline IK/FK**: spine (COG, independent hips, hips / mid / chest IK
    with an FK layer), neck (head control with orient spaces, neck by
    default) and chain (tails: IK/FK switch, automatic wave with time). A
    ribbon gives the twist, a hidden spline IK keeps the lengths (`stretch`),
    `volume` for film.
  - **Aim**: eyes with a master target, per-eye targets and FK overrides.
  - **Fleshy Lids** layer: lid joints (one or many per lid) follow the eye
    by `eyeFollow` / `sideFollow`, plus a control per lid.
  - **Jaw / Hinge**: a chin control you translate (open, side, forward /
    back), clamped.
  - **Hand / Fingers**: FK, metacarpals, master controls, poses (curl,
    spread, fist, relax, cup, per finger curl) on a hand control, IK fingers
    for contact.
- **Utilities** panel in the window (SCENE > Utilities): control shape tools
  (replace from the gallery, mirror L <> R, copy, scale, rotate, line width,
  colour, save / export / import shapes) and skin weights export / import.

### Removed
- The Jeffy Toolkit window and its ten tabs, and everything only they used:
  the rig builders (`jeffy.rig`, flexible rig, face tools), the auto-rigger
  (`jeffy.autorig`), the animation / scene utilities and rig checks
  (`jeffy.utils`), blendshape and deformer tools, the expression compiler,
  proxy geometry and symmetry maps. Their docs (`docs/api.md`,
  `docs/autorig.md`, `docs/ROADMAP.md`) and tests went with them. The git
  history keeps them: commit `35f5fec` (main before this release) has the
  whole toolkit.

## [1.0.0] - 2026-10-01

First release.

### Added
- **Core**: configurable naming convention and renaming tools, attribute
  helpers (add/lock/proxy/reorder/copy/transfer), transform and matrix helpers
  (joint-orient aware world matrix setting, offsetParentMatrix zeroing), a pure
  Python math library, utility node helpers, an expression-to-node-network
  compiler, undo/tool decorators, colours, settings and JSON IO.
- **Controls**: 55 procedural shapes, `Control` class with offset groups and
  metadata, shape tools (replace, copy, mirror, scale, rotate, combine, text,
  user library, export/import).
- **Joints**: creation (selection, curves, insert, duplicate chain), an orient
  tool with world/plane/object/keep up modes, rotate axes, freeze rotations,
  planarize, mirror, labels and display helpers.
- **Geometry**: mesh, curve and surface helpers, spatial hash, symmetry maps,
  proxy geometry from skin weights and capsule proxies.
- **Rig**: structure, FK, IK (stretch, soft IK, pin), IK/FK limbs with
  seamless matching, space switching (constraint or matrix) with seamless
  switching, twist extraction and twist joints, spline IK with volume,
  ribbons, reverse foot, finger poses, eye rigs, rivets (follicle/uvPin),
  matrix constraints, pose readers and nHair dynamic chains.
- **Deformers**: skin weights IO (index/position), copy/mirror, prune, limit,
  smooth, vertex copy/paste/average, move weights, rebind at current pose;
  blendshape extract/mirror/symmetrize/split/transfer and weights IO; generic
  deformer weights IO/mirror, soft-selection clusters, wraps, delta mush.
- **Utils**: pose tools (mirror/flip/save/load/bind pose), baking and FBX
  export skeleton, connections and set driven key tools, selection helpers,
  scene cleanup and a rig validator with 23 checks.
- **Auto-rigger**: guide system, components (root, spine, neck, arm, leg,
  hand, chain, eyes, jaw, control), builder, templates (biped, simple biped,
  biped with tail, prop).
- **UI**: dockable window with nine tabs, Jeffy menu, shelf, drag-and-drop
  installer and startup script.
- MIT license.
- **Development**: pytest suite running without Maya, `tools/check_maya_api.py`
  validating Maya command flags against `maya-stubs`, ruff config and GitHub
  Actions CI.

[Unreleased]: https://github.com/CrapyShit/Jeffy-Toolkit/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/CrapyShit/Jeffy-Toolkit/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/CrapyShit/Jeffy-Toolkit/releases/tag/v1.0.0
