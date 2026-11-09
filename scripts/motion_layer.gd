class_name MotionLayer
extends SkeletonModifier3D
## Runs after the pose animations each frame and adds what isn't baked into them:
## hip height from the pose (bob/crouch), walking leg swing and hip sway, breathing.
## Your keyframed bone edits stay intact underneath.

var hips_offset := 0.0      ## meters, from the pose (negative = crouch)
var walk := 0.0             ## 0..1 walking blend
var phase := 0.0            ## walk cycle phase (radians)
var t := 0.0
var heavy := false
var run := 0.0  # FRG06 - locomotion and procedural footwork
var strafe := 0.0
var airborne := false
var burst := 0.0          ## male fighters: quieter idle
var bone_map: Dictionary = {}  # FRG04 - dynamic humanoid lookups
# FRG16A - interactive animation lab
var lab_profile: Dictionary = {}  # per-fighter, persisted locomotion settings
var _hips := -1
var _legs := [-1, -1]
var _knees := [-1, -1]
var _feet := [-1, -1]
var _arms := [-1, -1]
var _chest := -1
var _hip_rest := Vector3.ZERO
var _scale := 1.0

func _bone_name(sk: Skeleton3D, wanted: String) -> int:
	var resolved: String = str(bone_map.get(wanted, wanted))
	return sk.find_bone(resolved)

func _ready() -> void:
	var sk := get_skeleton()
	if sk == null:
		return
	_hips = _bone_name(sk, "Hips")
	_legs = [_bone_name(sk, "LeftUpperLeg"), _bone_name(sk, "RightUpperLeg")]
	_knees = [_bone_name(sk, "LeftLowerLeg"), _bone_name(sk, "RightLowerLeg")]
	_feet = [_bone_name(sk, "LeftFoot"), _bone_name(sk, "RightFoot")]
	_arms = [_bone_name(sk, "LeftUpperArm"), _bone_name(sk, "RightUpperArm")]
	_chest = _bone_name(sk, "UpperChest")
	if _chest < 0:
		_chest = _bone_name(sk, "Chest")
	if _hips >= 0:
		_hip_rest = sk.get_bone_rest(_hips).origin
		_scale = maxf(absf(sk.get_bone_global_rest(_hips).origin.y) / 0.84, 0.15)

func _rotate_local(sk: Skeleton3D, bone: int, axis: Vector3, amount: float) -> void:
	if bone < 0 or absf(amount) < 0.00001:
		return
	var q := Quaternion(axis, amount)
	sk.set_bone_pose_rotation(bone, (sk.get_bone_pose_rotation(bone) * q).normalized())

func _lab_offsets(table: Dictionary, role: String) -> Vector3:
	var raw: Variant = table.get(role, [0.0, 0.0, 0.0])
	if not (raw is Array) or raw.size() != 3:
		return Vector3.ZERO
	return Vector3(float(raw[0]), float(raw[1]), float(raw[2]))

func _process_modification() -> void:
	var sk := get_skeleton()
	if sk == null or _hips < 0:
		return
	var idle := 1.0 - clampf(walk, 0.0, 1.0)
	var sprint := clampf(run, 0.0, 1.0)
	var grounded := 0.0 if airborne else 1.0
	var gait := clampf(walk, 0.0, 1.0) * grounded * (1.0 - clampf(burst, 0.0, 1.0) * 0.75)
	var s := sin(phase)
	var breath := sin(t * TAU / (3.6 if not heavy else 4.2))
	var gait_settings: Dictionary = lab_profile.get("gait", {})
	var stride := (0.48 + 0.22 * sprint) * gait * clampf(float(gait_settings.get("stride", 1.0)), 0.0, 2.0)

	# Keep authored crouch/pose height; add light heel-to-toe bob only while moving.
	var bob := absf(s) * (0.025 + 0.018 * sprint) * gait * clampf(float(gait_settings.get("bob", 1.0)), 0.0, 2.0)
	var shift := 0.016 * strafe * gait
	var pos := _hip_rest + Vector3(shift, hips_offset * _scale + bob + breath * 0.004 * idle, 0.0)
	sk.set_bone_pose_position(_hips, pos)
	# Thighs, knees, and ankles are animated as a unit, rather than stiff scissor legs.
	for i in 2:
		var sign := 1.0 if i == 0 else -1.0
		var stepping := s * sign
		_rotate_local(sk, _legs[i], Vector3.RIGHT, stepping * stride)
		_rotate_local(sk, _knees[i], Vector3.RIGHT, maxf(0.0, -stepping) * 0.42 * gait * clampf(float(gait_settings.get("knee", 1.0)), 0.0, 2.0) + (0.16 if airborne else 0.0))
		_rotate_local(sk, _feet[i], Vector3.RIGHT, -stepping * (0.16 + 0.06 * sprint) * gait)
		# Opposing arm counter-swing; reduced to preserve the kit's guard stance.
		_rotate_local(sk, _arms[i], Vector3.RIGHT, -stepping * 0.10 * gait * (0.7 if heavy else 1.0) * clampf(float(gait_settings.get("arms", 1.0)), 0.0, 2.0))
	# Dodge / dash reads as a brief forward lean, not running in place.
	_rotate_local(sk, _chest, Vector3.RIGHT, -0.13 * clampf(burst, 0.0, 1.0))
	_rotate_local(sk, _chest, Vector3.FORWARD, -0.045 * strafe * gait)
	# Minimal idle breathing to keep heavy knights grounded.
	_rotate_local(sk, _chest, Vector3.RIGHT, -breath * deg_to_rad(1.6 if not heavy else 0.8) * idle)

	# FRG16A: user-authored joint offsets blend into the existing procedural gait.
	# No changes to humanoid rest poses, skin weights, or combat animation tracks.
	var pose_states: Dictionary = lab_profile.get("poses", {})
	var idle_offsets: Dictionary = pose_states.get("idle", {})
	var walk_offsets: Dictionary = pose_states.get("walk", {})
	var run_offsets: Dictionary = pose_states.get("run", {})
	var blend_walk: float = clampf(walk, 0.0, 1.0)
	var blend_run: float = clampf(run, 0.0, 1.0) * blend_walk
	for key in bone_map.keys():
		var role: String = String(key)
		var bone_id: int = _bone_name(sk, role)
		if bone_id < 0:
			continue
		var euler: Vector3 = _lab_offsets(idle_offsets, role).lerp(_lab_offsets(walk_offsets, role), blend_walk)
		euler = euler.lerp(_lab_offsets(run_offsets, role), blend_run)
		if euler.length_squared() < 0.000001:
			continue
		var radians := Vector3(deg_to_rad(euler.x), deg_to_rad(euler.y), deg_to_rad(euler.z))
		var adjustment := Quaternion.from_euler(radians)
		sk.set_bone_pose_rotation(bone_id, (sk.get_bone_pose_rotation(bone_id) * adjustment).normalized())
