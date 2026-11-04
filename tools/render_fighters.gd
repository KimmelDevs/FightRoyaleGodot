extends SceneTree
## Renders several fighters (FighterModel with weapons) in a pose to a PNG.
## godot --path . -s tools/render_fighters.gd -- <id,id,...> <pose> <out.png>
func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var ids: PackedStringArray = (args[0] if args.size() > 0 else "aster,vesper,garrick,kaede,rook,raven,ember").split(",")
	var pose: String = args[1] if args.size() > 1 else "idle"
	var out: String = args[2] if args.size() > 2 else "user://fighters.png"
	var roster: Array = JSON.parse_string(FileAccess.get_file_as_string("res://data/roster.json"))
	var root := Node3D.new()
	get_root().add_child(root)
	get_root().size = Vector2i(260 * ids.size(), 520)
	var env := WorldEnvironment.new(); env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR; env.environment.background_color = Color("#bcd8f0")
	env.environment.ambient_light_color = Color.WHITE; env.environment.ambient_light_energy = 0.6
	root.add_child(env)
	var sun := DirectionalLight3D.new(); sun.rotation_degrees = Vector3(-40, 30, 0); root.add_child(sun)
	for i in ids.size():
		var look: Dictionary = {}
		for c in roster: if c.id == ids[i]: look = c.look
		var m := FighterModel.new()
		root.add_child(m)
		m.position.x = (i - (ids.size() - 1) / 2.0) * 1.0
		m.setup(look)
		m.play_pose(pose, 1000)
	var cam := Camera3D.new(); root.add_child(cam)
	cam.position = Vector3(0, 1.0, 1.2 + ids.size() * 0.8); cam.fov = 40
	await process_frame
	cam.look_at(Vector3(0, 0.85, 0))
	for f in 12: await process_frame
	get_root().get_texture().get_image().save_png(out)
	print("saved ", ProjectSettings.globalize_path(out))
	quit()
