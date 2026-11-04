extends Node
## Smoke test: runs a CPU-only match for a while, saves screenshots and prints the outcome.
## Usage: godot --path . tools/sim_match.tscn -- <mode duel|team> <seconds> <out_prefix>
func _ready() -> void:
	var a := OS.get_cmdline_user_args()
	var mode: String = a[0] if a.size() > 0 else "duel"
	var secs: float = float(a[1]) if a.size() > 1 else 20.0
	var out: String = a[2] if a.size() > 2 else "user://sim"
	await get_tree().process_frame
	var players: Array = []
	var n := 2 if mode == "duel" else 6
	for i in n:
		players.append({"peer": "cpu%d" % i, "name": "CPU%d" % i, "char": i % 7, "team": i % 2})
	var m := Match.new()
	m.cfg = {"mode": mode, "players": players, "local_peer": "none", "difficulty": 2}
	add_child(m)
	var hud := Hud.new(m)
	add_child(hud)
	var t := 0.0
	var shot := 0
	var events := []
	m.ui_event.connect(func(e): events.append(e.get("text", e.type)))
	while t < secs and not m.can_restart:
		await get_tree().process_frame
		t += 1.0 / 60.0
		if t > 2.5 + shot * 4.0 and shot < 5:
			await RenderingServer.frame_post_draw
			get_viewport().get_texture().get_image().save_png("%s_%d.png" % [out, shot])
			shot += 1
	for f in m.fighters: print(f.look.name, " team ", f.team, " hp ", int(f.hp), "/", int(f.max_hp), " state ", f.state)
	print("events ", events, " time ", snappedf(t, 0.1))
	get_tree().quit()
