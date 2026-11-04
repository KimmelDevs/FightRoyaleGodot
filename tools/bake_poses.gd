extends SceneTree
## Bakes every combat pose (data/poses.json, exported from the web game) into keyframed bone
## animations, one AnimationLibrary per kit: res://animations/<kit>.tres.
##
## The web game posed a simple joint rig (torso, head, arm, hand, legs, as Euler angles). Here
## each pose becomes rotations on the VRoid humanoid skeleton (same math as the web VRM layer):
## torso bend spread over Spine/Chest/UpperChest, neck takes 40% of head turns, T-pose arms
## calibrated to hang down, soft elbows (fists-up guard for brawlers), soft knees with matching
## hip flexion, level feet and finger curls (grip on weapon hands).
##
## Open a library in the editor (AnimationPlayer -> Animation -> Manage Animations) to adjust
## any bone of any pose. Re-running this tool overwrites the files.
##
## Run: godot --headless --path . -s tools/bake_poses.gd

const REF_MODEL := "res://models/aster.vrm"
const SK := "GeneralSkeleton"

## Kits whose left hand holds something (fingers curl into a grip).
const LEFT_GRIP := ["knight", "greatsword", "katana", "bow", "assassin", "knuckles"]
const RIGHT_GRIP := ["knight", "greatsword", "katana", "bow", "assassin", "knuckles", "mage"]
const FINGERS := ["Index", "Middle", "Ring", "Little"]
const SEGS := ["Proximal", "Intermediate", "Distal"]

var sk: Skeleton3D
var rest_g := {}  # bone name -> global rest Quaternion

func _init() -> void:
	var scene: Node = load(REF_MODEL).instantiate()
	sk = scene.find_children("*", "Skeleton3D", true, false)[0]
	for i in sk.get_bone_count():
		rest_g[sk.get_bone_name(i)] = sk.get_bone_global_rest(i).basis.get_rotation_quaternion()
	var poses: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/poses.json"))
	DirAccess.make_dir_recursive_absolute("res://animations")
	for kit in poses:
		var lib := AnimationLibrary.new()
		for pose_name in poses[kit]:
			lib.add_animation(pose_name, bake(kit, poses[kit][pose_name]))
		var err := ResourceSaver.save(lib, "res://animations/%s.tres" % kit)
		print("%s: %d poses -> res://animations/%s.tres (%s)" % [kit, poses[kit].size(), kit, error_string(err)])
	scene.free()
	quit()

# --- helpers -------------------------------------------------------------------------

## Euler (YXZ order, like the web rig) to quaternion.
static func eq(v: Array) -> Quaternion:
	return Quaternion.from_euler(Vector3(v[0], v[1], v[2]))  # Godot's default order is YXZ

static func axis(a: Vector3, ang: float) -> Quaternion:
	return Quaternion(a.normalized(), ang)

## Bake one pose into a short animation: one rotation key per driven bone.
func bake(kit: String, p: Dictionary) -> Animation:
	var g := {}  # bone -> target global rotation
	var T := eq(p.torso)
	var Hd := T * eq(p.head)
	var I := Quaternion.IDENTITY
	g["Spine"] = I.slerp(T, 0.5) * rest_g.Spine
	g["Chest"] = I.slerp(T, 0.8) * rest_g.Chest
	g["UpperChest"] = T * rest_g.UpperChest
	g["Neck"] = T.slerp(Hd, 0.4) * rest_g.Neck
	g["Head"] = Hd * rest_g.Head

	for side in ["Left", "Right"]:
		var s := "l" if side == "Left" else "r"
		var sgn := 1.0 if side == "Left" else -1.0
		var arm := T * eq(p["arm_" + s])
		var hand := arm * eq(p["hand_" + s])
		# T-pose arms point sideways; the web rig's arms rest hanging down.
		var cal := Quaternion(Vector3(sgn, 0, 0), Vector3.DOWN)
		var arm_dir := (arm * cal) * Vector3(sgn, 0, 0)
		var elev := arm_dir.angle_to(Vector3.DOWN)
		var flex: float
		var hand_frame: Quaternion
		if kit == "knuckles":
			# Brawler: the pose's wrist angle drives the elbow (fists up at the cheeks in guard).
			var wrist_x := absf(eq(p["hand_" + s]).get_euler().x)
			flex = clampf(deg_to_rad(12) + wrist_x * 1.75, deg_to_rad(12), deg_to_rad(125))
		else:
			flex = minf(deg_to_rad(16) + elev * 0.3, deg_to_rad(75))
		# Forearm bends toward the front of the arm (rotation about the T-pose's vertical).
		var bend := axis(Vector3.UP, -sgn * flex)
		g[side + "UpperArm"] = arm * cal * rest_g[side + "UpperArm"]
		g[side + "LowerArm"] = arm * cal * bend * rest_g[side + "LowerArm"]
		hand_frame = (arm * cal * bend) if kit == "knuckles" else (hand * cal * bend)
		g[side + "Hand"] = hand_frame * rest_g[side + "Hand"]
		g[side + "Shoulder"] = axis(Vector3.BACK, -sgn * deg_to_rad(5)) * rest_g[side + "Shoulder"]
		# Fingers: grip around a weapon or a soft relaxed curl; curl is toward the palm (-Y in T-pose).
		var grip: bool = kit in (LEFT_GRIP if side == "Left" else RIGHT_GRIP)
		for fi in FINGERS.size():
			var cum := hand_frame
			for si in SEGS.size():
				var c: float = ([72.0, 85.0, 55.0] if grip else [18.0, 30.0, 22.0])[si] + (0.0 if grip else fi * 4.0)
				cum = cum * axis(Vector3.BACK, -sgn * deg_to_rad(c))
				var b: String = side + FINGERS[fi] + SEGS[si]
				if rest_g.has(b): g[b] = cum * rest_g[b]
		var thumb := hand_frame * axis(Vector3.UP, sgn * deg_to_rad(35 if grip else 15)) * axis(Vector3.BACK, -sgn * deg_to_rad(25 if grip else 8))
		for b in [side + "ThumbMetacarpal", side + "ThumbProximal", side + "ThumbDistal"]:
			if rest_g.has(b): g[b] = thumb * rest_g[b]

		# Legs: thigh from the pose plus hip flexion matching a soft knee; feet level.
		var leg := eq(p["leg_" + s])
		var knee := deg_to_rad(6) + clampf(-float(p.hips_y) * 2.6, 0.0, deg_to_rad(55))
		g[side + "UpperLeg"] = leg * axis(Vector3.RIGHT, -knee * 0.5) * rest_g[side + "UpperLeg"]
		g[side + "LowerLeg"] = leg * axis(Vector3.RIGHT, -knee * 0.5) * axis(Vector3.RIGHT, knee) * rest_g[side + "LowerLeg"]
		g[side + "Foot"] = rest_g[side + "Foot"]

	# Global targets -> local bone rotations, parents first.
	var anim := Animation.new()
	anim.length = 0.05
	anim.loop_mode = Animation.LOOP_NONE
	var global := {}  # bone index -> global rotation (bones visited parents-first)
	var order: Array[int] = []
	var stack: Array = Array(sk.get_parentless_bones())
	while not stack.is_empty():
		var b: int = stack.pop_front()
		order.append(b)
		stack.append_array(Array(sk.get_bone_children(b)))
	for i in order:
		var name := String(sk.get_bone_name(i))
		var parent := sk.get_bone_parent(i)
		var pg: Quaternion = global[parent] if parent >= 0 else Quaternion.IDENTITY
		var local: Quaternion
		if g.has(name):
			local = (pg.inverse() * g[name]).normalized()
			global[i] = g[name]
		else:
			local = sk.get_bone_rest(i).basis.get_rotation_quaternion()
			global[i] = pg * local
		if g.has(name):
			var t := anim.add_track(Animation.TYPE_ROTATION_3D)
			anim.track_set_path(t, NodePath("%s:%s" % [SK, name]))
			anim.rotation_track_insert_key(t, 0.0, local)
	# Hip height offset (meters at the web rig's scale) kept as metadata for the runtime layer.
	anim.set_meta("hips_y", float(p.hips_y))
	return anim
