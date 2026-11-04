extends SceneTree
# Prints a VRM scene's skeleton: bone count, humanoid bone names, arm rest directions.
func _init() -> void:
	var path := "res://models/aster.vrm"
	var scene: Node = load(path).instantiate()
	var sk: Skeleton3D = scene.find_children("*", "Skeleton3D", true, false)[0]
	print("skeleton: ", sk.name, " bones=", sk.get_bone_count())
	var names := []
	for i in sk.get_bone_count():
		names.append(sk.get_bone_name(i))
	print(", ".join(names.slice(0, 60)))
	for b in ["Hips", "LeftUpperArm", "LeftLowerArm", "LeftHand", "RightUpperArm", "LeftUpperLeg", "LeftLowerLeg", "Head"]:
		var i := sk.find_bone(b)
		if i < 0:
			print(b, " MISSING"); continue
		var g := sk.get_bone_global_rest(i)
		var kids := sk.get_bone_children(i)
		var dir := Vector3.ZERO
		if kids.size() > 0:
			dir = (sk.get_bone_global_rest(kids[0]).origin - g.origin).normalized()
		print(b, " pos=", g.origin.snapped(Vector3.ONE * 0.001), " dir_to_child=", dir.snapped(Vector3.ONE * 0.01), " rest_basis=", g.basis.get_euler().snapped(Vector3.ONE * 0.01))
	print("scene root type=", scene.get_class(), " children=", scene.get_children().map(func(c): return c.name))
	quit()
