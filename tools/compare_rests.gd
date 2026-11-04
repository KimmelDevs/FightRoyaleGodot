extends SceneTree
# Checks that every model's humanoid bones share the same rest orientation.
const BONES := ["Hips", "Spine", "Chest", "UpperChest", "Neck", "Head", "LeftUpperArm", "LeftLowerArm", "LeftHand", "RightUpperArm", "RightLowerArm", "RightHand", "LeftUpperLeg", "LeftLowerLeg", "LeftFoot", "RightUpperLeg", "LeftIndexProximal"]
func _init() -> void:
	var ref := {}
	for f in ["aster", "ember", "garrick", "kaede", "raven", "rook", "vesper"]:
		var sc: Node = load("res://models/%s.vrm" % f).instantiate()
		var sk: Skeleton3D = sc.find_children("*", "Skeleton3D", true, false)[0]
		var worst := 0.0
		var worst_b := ""
		for b in BONES:
			var i := sk.find_bone(b)
			if i < 0: print(f, " missing ", b); continue
			var q := sk.get_bone_rest(i).basis.get_rotation_quaternion()
			if not ref.has(b): ref[b] = q
			var a := rad_to_deg(q.angle_to(ref[b]))
			if a > worst: worst = a; worst_b = b
		print(f, ": worst local-rest difference vs aster = %.1f deg (%s), hips y=%.2f" % [worst, worst_b, sk.get_bone_global_rest(sk.find_bone("Hips")).origin.y])
		sc.free()
	quit()
