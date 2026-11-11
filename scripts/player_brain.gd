class_name PlayerBrain
extends RefCounted
## Local player controls (same as the web game): WASD move (camera-relative), Space jump,
## left mouse attack (tap) / charged attack (hold), right mouse block, Z X C skills,
## double-tap a direction to dash. Bindings come from Keys (settings).

const DOUBLE_TAP := 0.26

var camera: Camera3D
var _skills: Array[String] = []
var _last_tap := {}
var _dash := Vector2.ZERO
var _prev := {}
var _mode_pending := false # FRG19G
var _dodge_pending := false  # FRG06 - locomotion and procedural footwork

func _init(cam: Camera3D) -> void:
	camera = cam

## Called from the match's _input for edge-triggered keys (skills, double-tap dash).
func on_event(e: InputEvent) -> void:
	if e is InputEventKey and e.pressed and not e.echo:
		if Keys.matches("dodge", e): _dodge_pending = true
		if Keys.matches("mode", e): _mode_pending = true
		for pair in [["skill1", "z"], ["skill2", "x"], ["skill3", "c"]]:
			if Keys.matches(pair[0], e): _skills.append(pair[1])
		var dirs := {"right": Vector2(1, 0), "left": Vector2(-1, 0), "up": Vector2(0, 1), "down": Vector2(0, -1)}
		for a in dirs:
			if Keys.matches(a, e):
				var now := Time.get_ticks_msec() / 1000.0
				if now - float(_last_tap.get(a, -9.0)) < DOUBLE_TAP:
					_dash = dirs[a]; _last_tap[a] = -9.0
				else:
					_last_tap[a] = now

func think(f: Fighter, _dt: float) -> void:
	var x := 0.0
	var y := 0.0
	if Keys.held("right"): x += 1
	if Keys.held("left"): x -= 1
	if Keys.held("up"): y += 1
	if Keys.held("down"): y -= 1
	var right := camera.global_basis.x; right.y = 0; right = right.normalized()
	var fwd := -camera.global_basis.z; fwd.y = 0; fwd = fwd.normalized()
	if x != 0 or y != 0: f.in_move = (right * x + fwd * y).normalized()
	f.in_sprint = Keys.held("sprint")
	if f.kit == "tristaff" and _mode_pending: f.in_mode_switch = true
	_mode_pending = false
	if _dodge_pending:
		# A stationary dodge retreats from the opponent; moving dodge follows input.
		f.in_dodge = f.in_move if f.in_move.length_squared() > 0.01 else -f.forward()
		_dodge_pending = false
	f.in_attack = Keys.held("attack")
	f.in_block = Keys.held("block")
	f.in_jump = Keys.held("jump")
	if not _skills.is_empty(): f.in_skill = _skills.pop_front()
	if _dash != Vector2.ZERO:
		f.in_dash = (right * _dash.x + fwd * _dash.y).normalized()
		_dash = Vector2.ZERO
