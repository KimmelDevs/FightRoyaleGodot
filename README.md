# FightRoyaleGodot

Godot 4.7 version of Fight Royale (anime cel-shaded arena fighter). This becomes the main
game; the web version keeps deploying from the `Fight-Royale` repo.

## Setup

1. Open this folder in Godot 4.7 (Import -> `project.godot`).
2. Godot imports the VRoid fighters in `models/` with the **godot-vrm** importer
   (`addons/vrm`, MIT, by V-Sekai) and the MToon shader (`addons/Godot-MToon-Shader`).

Each fighter is a scene with a humanoid `Skeleton3D` (`GeneralSkeleton`, Godot's standard
humanoid bone names: Hips, Spine, Chest, UpperChest, Neck, Head, LeftUpperArm, LeftLowerArm,
LeftHand, finger bones, LeftUpperLeg, LeftLowerLeg, LeftFoot, ... plus VRoid hair/skirt bones).

## Credits

- 3D characters made with VRoid Studio by Fruit.
- VRM importer: godot-vrm (MIT) by V-Sekai.

## Editing movements (bones)

Every combat pose is a keyframed bone animation in `animations/<kit>.tres`
(knight, greatsword, katana, mage, bow, assassin, knuckles, kicks). To adjust one:

1. Open any fighter scene, select its `AnimationPlayer`, pick a pose (e.g. `l1_s`, `block`).
2. Select the `GeneralSkeleton`, rotate bones in the viewport, and key them.
3. Save. The game plays poses by name, so your edit shows up in every fighter on that kit.

Pose names: `idle`, `jump`, `block`, `hit`, `stagger`, `down`, `win`, attack wind-ups `*_w`
and strikes `*_s` (see `data/attacks.json` for which attack uses which pose).

Regenerating (overwrites edits!): `godot --headless --path . -s tools/bake_poses.gd`
rebuilds the libraries from `data/poses.json`. `tools/render_poses.gd` saves a preview PNG.

## Data

`data/*.json` holds the roster, kit stats, every attack/skill, poses and economy, exported
from the web game by `tools/export_web_data.ts` (tune numbers here from now on).
