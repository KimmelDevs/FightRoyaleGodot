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
