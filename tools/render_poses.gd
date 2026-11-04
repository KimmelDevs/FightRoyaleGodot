extends SceneTree
## Renders a fighter in several baked poses side by side and saves a PNG (visual check).
## Run: godot --path . -s tools/render_poses.gd -- <model> <kit> <pose,pose,...> <out.png>

func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var model: String = args[0] if args.size() > 0 else "aster"
	var kit: String = args[1] if args.size() > 1 else "knight"
	var pose_list: PackedStringArray = (args[2] if args.size() > 2 else "idle,l1_s,block,heavy_s").split(",")
	var out: String = args[3] if args.size() > 3 else "user://poses.png"
	var root := Node3D.new()
	get_root().add_child(root)
	get_root().size = Vector2i(320 * pose_list.size(), 480)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color("#bcd8f0")
	env.environment.ambient_light_color = Color.WHITE
	env.environment.ambient_light_energy = 0.6
	root.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-40, 30, 0)
	root.add_child(sun)
	var lib: AnimationLibrary = load("res://animations/%s.tres" % kit)
	for i in pose_list.size():
		var m: Node3D = load("res://models/%s.vrm" % model).instantiate()
		root.add_child(m)
		m.position.x = (i - (pose_list.size() - 1) / 2.0) * 1.1
		var ap := AnimationPlayer.new()
		m.add_child(ap)
		ap.root_node = NodePath("..")
		ap.add_animation_library("", lib)
		ap.play(pose_list[i])
		ap.seek(0.0, true)
	var cam := Camera3D.new()
	root.add_child(cam)
	cam.position = Vector3(0, 1.0, 1.6 + pose_list.size() * 0.9)
	cam.look_at(Vector3(0, 0.9, 0))
	cam.fov = 40
	for f in 6:
		await process_frame
	var img := get_root().get_texture().get_image()
	img.save_png(out)
	print("saved ", ProjectSettings.globalize_path(out))
	quit()
