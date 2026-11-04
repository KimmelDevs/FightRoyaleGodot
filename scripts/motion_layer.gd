class_name MotionLayer
extends SkeletonModifier3D
## Runs after the pose animations each frame and adds what isn't baked into them:
## hip height from the pose (bob/crouch), walking leg swing and hip sway, breathing.
## Your keyframed bone edits stay intact underneath.

var hips_offset := 0.0      ## meters, from the pose (negative = crouch)
var walk := 0.0             ## 0..1 walking blend
var phase := 0.0            ## walk cycle phase (radians)
var t := 0.0
var heavy := false          ## male fighters: quieter idle
var _hips := -1
var _legs := [-1, -1]
var _chest := -1
var _hip_rest := Vector3.ZERO
var _scale := 1.0

func _ready() -> void:
	var sk := get_skeleton()
	if sk == null:
		return
	_hips = sk.find_bone("Hips")
	_legs = [sk.find_bone("LeftUpperLeg"), sk.find_bone("RightUpperLeg")]
	_chest = sk.find_bone("UpperChest")
	if _hips >= 0:
		_hip_rest = sk.get_bone_rest(_hips).origin
		_scale = sk.get_bone_global_rest(_hips).origin.y / 0.84  # web rig hip height was 0.84

func _process_modification() -> void:
	var sk := get_skeleton()
	if sk == null or _hips < 0:
		return
	var s := sin(phase)
	var idle := 1.0 - walk
	var breath := sin(t * TAU / (3.6 if not heavy else 4.2))
	# Hips: pose crouch + walk bob + idle breathing rise.
	var pos := _hip_rest + Vector3(0, hips_offset * _scale + absf(s) * 0.03 * walk + breath * 0.004 * idle, 0)
	sk.set_bone_pose_position(_hips, pos)
	# Walk: legs swing opposite each other (global X rotation added on top of the pose).
	if walk > 0.001:
		for i in 2:
			var b: int = _legs[i]
			if b < 0: continue
			var swing := (1.0 if i == 0 else -1.0) * s * 0.55 * walk
			var parent_g := sk.get_bone_global_pose(sk.get_bone_parent(b)).basis.get_rotation_quaternion()
			var cur_g := parent_g * sk.get_bone_pose_rotation(b)
			var want := Quaternion(Vector3.RIGHT, swing) * cur_g
			sk.set_bone_pose_rotation(b, (parent_g.inverse() * want).normalized())
	# Breathing on the upper chest.
	if _chest >= 0:
		var r := sk.get_bone_pose_rotation(_chest)
		sk.set_bone_pose_rotation(_chest, (r * Quaternion(Vector3.RIGHT, -breath * deg_to_rad(1.6 if not heavy else 0.8) * idle)).normalized())
