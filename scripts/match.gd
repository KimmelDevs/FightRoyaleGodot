class_name Match
# FRG17C - elemental hit and skill VFX
# FRG17A - combat impact VFX
extends Node3D
# FRG18A - combat sound integration
const COMBAT_AUDIO_SCRIPT = preload("res://scripts/combat_audio.gd")
# FRG15A - status and passive runtime
# FRG08 - defense integration and visible fighter checks
## A running match (port of the web game.ts): duel (1v1) and team (2v2-4v4) in the 3D arena.
## Owns the fighters, resolves attacks (melee arcs, clashes, projectiles, area strikes, buffs,
## blinks), hit results (parry, block, guard break, counter), hit-stop, shake, KO and rounds.

signal ui_event(e: Dictionary)  ## {type: banner|over|reward, ...}

const DUEL_RADIUS := 7.0

var cfg: Dictionary  ## {mode, players:[{peer,name,char,loadout,emblem,team}], local_peer, cpu_char, difficulty}
var fighters: Array[Fighter] = []
var local: Fighter
var camera: Camera3D
var fx: Fx
var audio
var round_over := false
var can_restart := false
var paused := false

# FRG10 - complete Duel vs CPU match flow
var _duel_seconds_left := 120.0
var _duel_clock_running := false

var _time := 0.0
var _round := 0
var _timers: Array = []         # [time, Callable]
var _projectiles: Array = []    # dictionaries
var _strike_marks: Array = []   # {target, land, id}

# FRG19E — snow puppets live only for their current round.
var _roxy_puppets: Array[Dictionary] = []
# FRG19N — Ember ground patches are fully owned by the match and reset per round.
var _ember_patches: Array[Dictionary] = []
var _trails: Dictionary = {}    # Fighter -> Trail
var _frg19b_multi_phase: Dictionary = {}
var _melee_hits: Dictionary = {}  # FRG07 - persistent melee contact and directional knockback
const MELEE_FRONT_DOT := 0.15
const MELEE_HEIGHT_TOLERANCE := 1.3
var _player_brain: PlayerBrain
var _trauma := 0.0
var _shake_t := 0.0
var _stop_until := 0.0
var _next_id := 1
var _mote_t := {}
var _sun: DirectionalLight3D

# FRG11 - independent CPU versus CPU spectator controls
const SPECTATOR_SPEEDS := [0.5, 1.0, 1.5, 2.0]
const SPECTATOR_VIEWS := ["Cinematic", "Orbit", "Follow CPU A", "Follow CPU B"]
var _spectator_speed_index := 1
var _spectator_view := 0
var _spectator_dragging := false
var _spectator_yaw := 0.8
var _spectator_pitch := 0.36
var _spectator_distance := 9.0

# FRG09B - third-person duel camera
# The browser game's original side-view stays available with F6.
# All camera settings are runtime-only and do not touch fighter rigs/skills.
var _third_person := true
var _lock_on := true
var _camera_dragging := false
var _camera_initialized := false
var _orbit_yaw := 0.0
var _orbit_pitch := deg_to_rad(22.0)
var _follow_distance := 5.4
var _camera_hint: Label


func _ready() -> void:
	_build_world()
	fx = Fx.new()
	add_child(fx)
	audio = COMBAT_AUDIO_SCRIPT.new()
	add_child(audio)
	camera = Camera3D.new()
	camera.fov = 50
	add_child(camera)
	camera.make_current()
	camera.position = Vector3(0, 6, 10)
	_player_brain = PlayerBrain.new(camera)
	if not bool(cfg.get("spectator", false)):
		_make_camera_hint()
	start_round.call_deferred()

func _build_world() -> void:
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	# Sky gradient, gentle fill light, filmic tonemap: keeps the toon-shaded models from washing out.
	var sky := Sky.new()
	var sm := ProceduralSkyMaterial.new()
	sm.sky_top_color = Color("#4f86c6")
	sm.sky_horizon_color = Color("#a9c8e4")
	sm.ground_horizon_color = Color("#8aa48a")
	sm.ground_bottom_color = Color("#4c6a4c")
	sky.sky_material = sm
	env.environment.background_mode = Environment.BG_SKY
	env.environment.sky = sky
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color("#c8d6ee")
	env.environment.ambient_light_energy = 0.2
	env.environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.environment.tonemap_exposure = 0.85
	# FRG08C - remove distance haze from the duel arena
	env.environment.fog_enabled = false
	env.environment.fog_light_color = Color("#a9c8e4")
	env.environment.fog_light_energy = 0.6
	env.environment.fog_density = 0.004
	env.environment.fog_sky_affect = 0.0
	add_child(env)
	_sun = DirectionalLight3D.new()
	_sun.rotation_degrees = Vector3(-50, 30, 0)
	_sun.light_energy = 0.6
	_sun.light_color = Color("#fff4e2")
	_sun.shadow_enabled = true
	add_child(_sun)
	var ground := MeshInstance3D.new()
	var plane := PlaneMesh.new(); plane.size = Vector2(200, 200)
	ground.mesh = plane
	var gm := StandardMaterial3D.new(); gm.albedo_color = Color("#3e6338"); gm.roughness = 1.0
	ground.material_override = gm
	add_child(ground)
	var ring := MeshInstance3D.new()
	var t := TorusMesh.new(); t.inner_radius = DUEL_RADIUS + 0.4; t.outer_radius = DUEL_RADIUS + 0.5; t.rings = 64
	ring.mesh = t
	ring.material_override = Fx.unlit(Color("#e6c26e"))
	ring.scale.y = 0.2
	add_child(ring)

# --- lifecycle -----------------------------------------------------------------------------

func start_round() -> void:
	# FRG14A: free effects from the preceding round before clearing arrays.
	for p in _projectiles:
		if is_instance_valid(p.node):
			p.node.queue_free()
	for f in fighters: f.queue_free()
	for t in _trails.values(): t.queue_free()
	for puppet in _roxy_puppets:
		if is_instance_valid(puppet["node"]):
			puppet["node"].queue_free()
	_roxy_puppets.clear()
	for ember_patch in _ember_patches:
		if is_instance_valid(ember_patch["node"]): ember_patch["node"].queue_free()
	_ember_patches.clear()
	fighters.clear(); _trails.clear(); _melee_hits.clear(); _frg19b_multi_phase.clear(); _projectiles.clear(); _strike_marks.clear(); _timers.clear()
	_duel_seconds_left = float(cfg.get("round_seconds", 120))
	_duel_clock_running = false
	fx.clear()
	local = null
	_camera_initialized = false
	_round += 1
	round_over = false
	can_restart = false
	var id := _round
	if cfg.mode == "duel":
		var a: Dictionary = cfg.players[0]
		var b: Dictionary = cfg.players[1] if cfg.players.size() > 1 else {"peer": "cpu", "name": "CPU", "char": cfg.get("cpu_char", 0)}
		var f1 := _spawn(a, 0, Vector3(-2, 0, 0))
		var f2 := _spawn(b, 1, Vector3(2, 0, 0))
		f1.opponent = f2; f2.opponent = f1
		_ready_fight(id, [f1, f2], "")
	elif cfg.mode == "team":
		var counts := [0, 0]
		var spawned: Array[Fighter] = []
		for i in cfg.players.size():
			var p: Dictionary = cfg.players[i]
			var team: int = p.get("team", i % 2)
			var k: int = counts[team]; counts[team] += 1
			var f := _spawn(p, team, Vector3(-5 if team == 0 else 5, 0, (k - 1.5) * 1.8))
			spawned.append(f)
		_ready_fight(id, spawned, "%d vs %d" % [counts[0], counts[1]])

func _ready_fight(id: int, fs: Array, sub: String) -> void:
	banner("READY", Color("#ffe9a8"), sub)
	later(1.0, func():
		if id != _round: return
		banner("FIGHT!", Color.WHITE)
		audio.play_event("fight_start", Vector3.ZERO, false)
		_duel_clock_running = cfg.mode == "duel"
		for f in fs: f.brain = _brain_for(f))

func _brain_for(f: Fighter):
	if String(f.owner_peer).begins_with("cpu"):
		var preset := int(cfg.get("difficulty", 1))
		if bool(cfg.get("spectator", false)):
			var levels: Array = cfg.get("cpu_levels", [2, 2])
			var idx := 0 if String(f.owner_peer) == "cpu_a" else 1
			if levels.size() > idx:
				preset = int(levels[idx])
		return AiBrain.new(self, clampi(preset, 0, 3))
	if f.owner_peer == cfg.local_peer: return _player_brain
	return null

func _spawn(slot: Dictionary, team: int, pos: Vector3) -> Fighter:
	var f := Fighter.new()
	add_child(f)
	f.setup(int(slot.char), slot.get("loadout", ["z", "x", "c"]), slot.get("emblem", {}))
	if f.model != null and f.model.fallback_used:
		push_warning("Fight Royale: " + f.look.name + " uses a visible fallback. Open the VRM import errors in Godot.")
	f.id = _next_id; _next_id += 1
	f.team = team
	f.owner_peer = slot.peer
	f.arena_radius = DUEL_RADIUS
	f.position = pos
	f.rotation.y = PI / 2 if pos.x < 0 else -PI / 2
	f.swing.connect(_on_swing)
	f.knocked_out.connect(_on_ko)
	f.landed.connect(func(x: Fighter): fx.ring(x.global_position, Color.WHITE, 0.8, 0.25, 0.5))
	f.landed.connect(func(x: Fighter): audio.play_event("land", x.global_position))
	f.dashed.connect(func(x: Fighter): audio.play_event("dash", x.global_position))
	f.dashed.connect(func(x: Fighter):
		fx.smoke(x.global_position, Color(x.look.glow))
		fx.ring(x.global_position, Color(x.look.glow), 1.2, 0.2, 0.7))
	fighters.append(f)
	if f.kit != "tonfa" and f.model.blade_base and f.model.blade_tip:
		var tr := Trail.new(f.model.blade_base, f.model.blade_tip, Color(f.look.glow))
		# FRG17B: visual styling uses the existing character kit / element.
		tr.configure(String(f.kit), String(f.look.get("element", "")))
		add_child(tr)
		_trails[f] = tr
	if String(slot.peer).begins_with("cpu"): f.auto_approach = not f.kit in ["mage", "bow"]
	if slot.peer == cfg.local_peer: local = f
	return f

func later(delay: float, fn: Callable) -> void:
	_timers.append([_time + delay, fn])

func banner(text: String, color: Color, sub := "") -> void:
	ui_event.emit({"type": "banner", "text": text, "color": color, "sub": sub})

# --- frame ---------------------------------------------------------------------------------

func _unhandled_input(e: InputEvent) -> void:
	if bool(cfg.get("spectator", false)):
		_spectator_input(e)
		return
	if paused or round_over or not _duel_clock_running:
		return
	if not bool(cfg.get("spectator", false)):
		if e is InputEventKey and e.pressed and not e.echo:
			if e.keycode == KEY_F6 or e.physical_keycode == KEY_F6:
				_third_person = not _third_person
				_camera_dragging = false
				_camera_initialized = false
				_update_camera_hint()
				get_viewport().set_input_as_handled()
				return
			if e.keycode == KEY_TAB or e.physical_keycode == KEY_TAB:
				if _third_person:
					_lock_on = not _lock_on
					_update_camera_hint()
					get_viewport().set_input_as_handled()
					return
		if e is InputEventMouseButton and _third_person:
			if e.button_index == MOUSE_BUTTON_MIDDLE:
				_camera_dragging = e.pressed
				get_viewport().set_input_as_handled()
				return
			if e.pressed and e.button_index == MOUSE_BUTTON_WHEEL_UP:
				_follow_distance = clampf(_follow_distance - 0.55, 3.2, 9.0)
				get_viewport().set_input_as_handled()
				return
			if e.pressed and e.button_index == MOUSE_BUTTON_WHEEL_DOWN:
				_follow_distance = clampf(_follow_distance + 0.55, 3.2, 9.0)
				get_viewport().set_input_as_handled()
				return
		if e is InputEventMouseMotion and _third_person and _camera_dragging:
			_lock_on = false
			_orbit_yaw -= e.relative.x * 0.006
			_orbit_pitch = clampf(_orbit_pitch + e.relative.y * 0.005, deg_to_rad(9.0), deg_to_rad(60.0))
			_update_camera_hint()
			get_viewport().set_input_as_handled()
			return
		_player_brain.on_event(e)

# --- FRG11: spectator controls ------------------------------------------------------------

func _spectator_input(e: InputEvent) -> void:
	# Esc and R remain handled by Hud. No input is sent to PlayerBrain.
	if e is InputEventKey and e.pressed and not e.echo:
		var k: int = e.keycode if e.keycode != 0 else e.physical_keycode
		if k == KEY_C:
			_spectator_view = (_spectator_view + 1) % SPECTATOR_VIEWS.size()
		elif k >= KEY_1 and k <= KEY_4:
			_spectator_view = k - KEY_1
		elif k == KEY_BRACKETLEFT:
			_spectator_speed_index = maxi(0, _spectator_speed_index - 1)
		elif k == KEY_BRACKETRIGHT:
			_spectator_speed_index = mini(SPECTATOR_SPEEDS.size() - 1, _spectator_speed_index + 1)
		else:
			return
		get_viewport().set_input_as_handled()
		return
	if e is InputEventMouseButton:
		if e.button_index == MOUSE_BUTTON_MIDDLE:
			_spectator_dragging = e.pressed
			if e.pressed:
				_spectator_view = 1
			get_viewport().set_input_as_handled()
			return
		if e.pressed and e.button_index == MOUSE_BUTTON_WHEEL_UP:
			_spectator_distance = clampf(_spectator_distance - 0.6, 4.0, 18.0)
			_spectator_view = 1
			get_viewport().set_input_as_handled()
			return
		if e.pressed and e.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_spectator_distance = clampf(_spectator_distance + 0.6, 4.0, 18.0)
			_spectator_view = 1
			get_viewport().set_input_as_handled()
			return
	if e is InputEventMouseMotion and _spectator_dragging:
		_spectator_yaw -= e.relative.x * 0.007
		_spectator_pitch = clampf(_spectator_pitch + e.relative.y * 0.005, 0.13, 1.12)
		get_viewport().set_input_as_handled()

func _process(real_dt: float) -> void:
	real_dt = clampf(real_dt, 0.0, 0.05)
	var now := Time.get_ticks_msec() / 1000.0
	var scale := 0.05 if now < _stop_until else 1.0
	var speed := float(SPECTATOR_SPEEDS[_spectator_speed_index]) if bool(cfg.get("spectator", false)) else 1.0
	var dt := 0.0 if paused else real_dt * scale * speed
	_time += dt
	_tick_duel_clock(dt)
	var due := _timers.filter(func(t): return t[0] <= _time)
	_timers = _timers.filter(func(t): return t[0] > _time)
	for t in due: t[1].call()
	if cfg.mode == "team": _retarget()
	for f in fighters:
		# Zero-delta brain calls can still schedule attacks; pause must freeze AI.
		if dt > 0.0:
			f.tick(dt)
			# FRG19L: subtle heavy footsteps with 3 Resolve; no simulation while paused.
			if f.kit == "greatsword" and f.garrick_resolve >= 3 and f.on_ground and f.model != null and f.model.walk > 0.25 and f.garrick_crack_cooldown <= 0.0:
				fx.rocks(f.position, 5, 0.25)
				f.garrick_crack_cooldown = 0.32
		# A sword remains dangerous for the entire active window. One contact per
		# defender/swing is enforced in _melee, so framerate cannot multiply damage.
		if dt > 0.0 and not round_over and f.active_melee():
			_frg19b_multi_contact(f)
			_active_melee_contact(f)
		if _trails.has(f):
			_trails[f].emitting = f.trail_on()
			_trails[f].tick(dt)
	_update_projectiles(dt)
	_roxy_step_puppets(dt)
	_ember_step_patches(dt) # FRG19N: no burning-ground ticks during pause
	_nythera_step_wells(dt)
	_veyr_step_festivals(dt)
	_blade_light(dt)
	_update_camera(real_dt)

func _retarget() -> void:
	for f in fighters:
		var best: Fighter = null
		var bd := 1e9
		for o in fighters:
			if o.team == f.team or o.is_down(): continue
			var d := o.position.distance_to(f.position)
			if d < bd: bd = d; best = o
		f.opponent = best

func enemies_of(f) -> Array:
	return fighters.filter(func(o): return o.team != f.team and not o.is_down())

## Hit-stop (brief freeze on impact).
func hit_stop(dur: float) -> void:
	_stop_until = Time.get_ticks_msec() / 1000.0 + dur

func add_trauma(x: float) -> void:
	_trauma = minf(_trauma + x, 1.0)

# --- AI threat feeds ---------------------------------------------------------------------

func projectile_threats() -> Array:
	return _projectiles.map(func(p): return {"target": p.target, "pos": p.node.global_position, "vel": p.vel, "id": p.id, "size": p.size, "style": String(p.atk.get("style", "")), "pierce": bool(p.pierce)})

func strike_threats() -> Array:
	return _strike_marks

func now() -> float:
	return _time

# --- attack resolution -------------------------------------------------------------------

func _on_swing(f: Fighter) -> void:
	var a := f.atk
	# FRG18C: independent per-fighter swing audio, with kit-aware cues.
	audio.play_attack_swing(String(f.kit), String(f.atk_id), a, f.chest(), f.get_instance_id())
	var el: String = f.look.element
	var big: bool = f.atk_id in ["z", "x", "c", "v", "heavy", "l3"]
	if el == "earth" and big:
		fx.rocks(f.position + f.forward() * 1.1, 24 if f.atk_id in ["heavy", "v"] else 16, 1.35 if f.atk_id == "heavy" else 1.0)
		add_trauma(0.4 if f.atk_id == "heavy" else 0.25)
	elif el == "light" and a.type == "melee":
		var tip := f.model.blade_tip.global_position
		fx.flash(tip, Color("#fff6c8"), 0.26 if big else 0.18, 0.14, 0.7)
		fx.sparks(tip, Color("#fff2b0"), 18 if big else 8, 4.0)
	if f.kit == "glaive" and String(f.look.get("element", "")) == "metal":
		match String(a.get("style", "")):
			"zenith_barrage": _zenith_barrage(f, a)
			"zenith_arsenal": _zenith_arsenal(f, a); return
	if f.kit == "scythe" and String(a.get("type", "")) == "melee": _nythera_schedule_beats(f, a)
	if f.kit == "sickle" and String(a.get("type", "")) == "melee": _veyr_schedule_beats(f, a)
	if f.kit == "tonfa" and String(a.get("type", "")) == "melee": _renji_schedule_beats(f, a)
	if f.kit == "tristaff" and String(a.get("type", "")) == "melee":
		_zephyr_schedule_beats(f, a)
	match a.type:
		"projectile": _fire(f, a)
		"strike": _strike(f, a, f.atk_power)
		"buff": _buff(f, a)
		"snow_puppet": _roxy_spawn_puppet(f, a)
		"blink": _blink(f, a)
		_: _melee(f, a)


# FRG19N — Ember ground fire: four max per caster, 20 seconds each.
func _ember_add_patch(caster: Fighter, at: Vector3, radius: float) -> void:
	if not is_instance_valid(caster) or caster.is_down() or round_over: return
	var owned: Array = _ember_patches.filter(func(p): return p["owner"] == caster)
	if owned.size() >= 4:
		var oldest: Dictionary = owned[0]
		if is_instance_valid(oldest["node"]): oldest["node"].queue_free()
		_ember_patches.erase(oldest)
		caster.ember_ground_patches = maxi(0, caster.ember_ground_patches - 1)
	var marker := MeshInstance3D.new()
	var mesh := CylinderMesh.new()
	mesh.top_radius = 1.0
	mesh.bottom_radius = 1.0
	mesh.height = 0.015
	marker.mesh = mesh
	marker.material_override = Fx.unlit(Color("#ed692c"), 0.36, true)
	marker.scale = Vector3(radius, 1.0, radius)
	add_child(marker)
	marker.global_position = Vector3(at.x, 0.045, at.z)
	_ember_patches.append({"node": marker, "owner": caster, "center": Vector3(at.x, 0.0, at.z), "radius": radius, "left": 20.0, "tick": 0.0})
	caster.ember_ground_patches += 1
	fx.ring(at, Color("#ff8e36"), radius, 0.4, 0.7)

func _ember_step_patches(dt: float) -> void:
	if dt <= 0.0 or round_over: return
	for patch in _ember_patches.duplicate():
		var caster: Fighter = patch["owner"]
		patch["left"] = float(patch["left"]) - dt
		if not is_instance_valid(caster) or caster.is_down() or float(patch["left"]) <= 0.0:
			if is_instance_valid(patch["node"]): patch["node"].queue_free()
			_ember_patches.erase(patch)
			if is_instance_valid(caster): caster.ember_ground_patches = maxi(0, caster.ember_ground_patches - 1)
			continue
		patch["tick"] = float(patch["tick"]) + dt
		if float(patch["tick"]) < 0.75: continue
		patch["tick"] = 0.0
		for defender in enemies_of(caster):
			var to_fire: Vector3 = defender.position - patch["center"]
			to_fire.y = 0.0
			if to_fire.length() <= float(patch["radius"]) + defender.radius * 0.35 and not defender.airborne():
				defender.add_status("burn", 1, 1.25)
				fx.motes(defender.position + Vector3(0.0, 0.12, 0.0), Color("#ff9a39"), 2)

func _ember_absolute_combustion(caster: Fighter, attack: Dictionary) -> void:
	if not is_instance_valid(caster) or caster.is_down() or round_over: return
	var total_fire := 0
	for patch in _ember_patches.duplicate():
		if patch["owner"] != caster: continue
		# The beam consumes nearby owned ground fire, not an enemy's fire.
		if caster.position.distance_to(patch["center"]) > 12.0: continue
		total_fire += 1
		if is_instance_valid(patch["node"]): patch["node"].queue_free()
		_ember_patches.erase(patch)
		caster.ember_ground_patches = maxi(0, caster.ember_ground_patches - 1)
	var start_pos: Vector3 = caster.chest()
	var direction: Vector3 = caster.forward()
	if caster.opponent != null and not caster.opponent.is_down():
		direction = caster.opponent.chest() - start_pos
		direction.y = 0.0
		if direction.length_squared() > 0.01: direction = direction.normalized()
		else: direction = caster.forward()
	direction.y = 0.0
	direction = direction.normalized()
	# Strong beam visuals use the existing FX API, no new audio or materials required.
	for i in range(8):
		var pos: Vector3 = start_pos + direction * (0.8 + float(i) * 1.20)
		fx.flash(pos, Color("#fff1b5"), 0.45 + float(total_fire) * 0.07, 0.20, 0.9)
	fx.ring(caster.position, Color("#ff8c41"), 2.2 + float(total_fire) * 0.28, 0.36, 0.85)
	var hit_count := 0
	for defender in enemies_of(caster):
		var to_target: Vector3 = defender.chest() - start_pos
		var forward_distance: float = to_target.dot(direction)
		if forward_distance < 0.0 or forward_distance > 10.2: continue
		var nearest: Vector3 = start_pos + direction * forward_distance
		if defender.chest().distance_to(nearest) > 1.10 + defender.radius: continue
		var burn_consumed := 0
		if defender.status_runtime != null and defender.status_runtime.has_effect("burn"):
			defender.remove_status("burn")
			burn_consumed = 1
		var beam_attack: Dictionary = attack.duplicate(true)
		beam_attack["type"] = "strike"
		beam_attack["style"] = "ember_beam"
		beam_attack["dmg"] = 150.0 + 32.0 * float(total_fire) + 50.0 * float(burn_consumed)
		beam_attack["guard"] = 48.0 + 12.0 * float(total_fire)
		beam_attack["knock"] = 5.0
		beam_attack["stun"] = 0.55
		beam_attack["heavy"] = true
		beam_attack["apply_status"] = "burn"
		beam_attack["status_duration"] = 4.0
		apply_hit(caster, defender, beam_attack, caster.atk_power, defender.chest(), direction, true)
		hit_count += 1
	fx.number(start_pos + Vector3(0.0, 0.65, 0.0), "ABSOLUTE COMBUSTION", Color("#fff2b5"), 0.85)
	if hit_count == 0: fx.number(start_pos, "MISS", Color("#ffc9a7"), 0.7)

# FRG19E — real moving snow-puppet summon, not a fake projectile or a strike.
func _roxy_spawn_puppet(f: Fighter, a: Dictionary) -> void:
	if f.is_down() or f.opponent == null or f.opponent.is_down():
		return
	var puppet := Node3D.new()
	puppet.name = "RoxyFrostMarionette19E"
	add_child(puppet)
	puppet.global_position = f.global_position + f.forward() * 0.85 + Vector3(0.0, 0.28, 0.0)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color("#bbebff")
	mat.roughness = 0.35
	var body := MeshInstance3D.new()
	var body_mesh := SphereMesh.new()
	body_mesh.radius = 0.30
	body_mesh.height = 0.60
	body.mesh = body_mesh
	body.material_override = mat
	puppet.add_child(body)
	var head := MeshInstance3D.new()
	var head_mesh := SphereMesh.new()
	head_mesh.radius = 0.21
	head_mesh.height = 0.42
	head.mesh = head_mesh
	head.material_override = mat
	head.position = Vector3(0.0, 0.38, 0.0)
	puppet.add_child(head)
	var orb := MeshInstance3D.new()
	var orb_mesh := SphereMesh.new()
	orb_mesh.radius = 0.07
	orb_mesh.height = 0.14
	orb.mesh = orb_mesh
	orb.material_override = Fx.unlit(Color("#ecffff"))
	orb.position = Vector3(0.0, 0.67, 0.0)
	puppet.add_child(orb)
	_roxy_puppets.append({"node": puppet, "caster": f, "target": f.opponent, "atk": a.duplicate(true), "power": f.atk_power, "life": float(a.get("duration", 8.5)), "speed": float(a.get("speed", 4.5))})
	fx.flash(puppet.global_position, Color("#a6edff"), 0.4, 0.20, 0.75)

func _roxy_step_puppets(dt: float) -> void:
	if dt <= 0.0 or round_over:
		return
	for record in _roxy_puppets.duplicate():
		var puppet: Node3D = record["node"]
		var caster: Fighter = record["caster"]
		var target: Fighter = record["target"]
		record["life"] = float(record["life"]) - dt
		if not is_instance_valid(puppet) or not is_instance_valid(caster) or not is_instance_valid(target) or caster.is_down() or target.is_down() or float(record["life"]) <= 0.0:
			if is_instance_valid(puppet):
				puppet.queue_free()
			_roxy_puppets.erase(record)
			continue
		var delta_to: Vector3 = target.position - puppet.global_position
		delta_to.y = 0.0
		var distance := delta_to.length()
		if distance > 0.01:
			puppet.global_position += delta_to.normalized() * minf(float(record["speed"]) * dt, distance)
		puppet.rotation.y += dt * 2.3
		if distance <= float(record["atk"].get("radius", 0.9)) + target.radius:
			var hit: Dictionary = record["atk"]
			var direction := delta_to.normalized() if distance > 0.01 else caster.forward()
			apply_hit(caster, target, hit, float(record["power"]), target.chest(), direction, true)
			fx.ring(puppet.global_position, Color("#b7f2ff"), 1.0, 0.32, 0.85)
			puppet.queue_free()
			_roxy_puppets.erase(record)


# FRG19F — 17 visual spear sentinels; 12 outward shots and 2 final rails.
# Kept distinct from Zarek's glaive V; all delayed events are tied to the round.
func _zenith_spear_projectile(f: Fighter, attack: Dictionary, offset: float, speed: float) -> void:
	if not is_instance_valid(f) or f.is_down() or round_over:
		return
	var origin: Vector3 = f.model.cast_point.global_position
	var opponent = f.opponent
	var aim: Vector3 = opponent.chest() - origin if is_instance_valid(opponent) and not opponent.is_down() else f.forward()
	var direction := aim.normalized().rotated(Vector3.UP, offset)
	_spawn_projectile(f, attack, f.atk_power, origin, direction * speed, Color(f.look.glow), opponent)

func _zenith_barrage(f: Fighter, a: Dictionary) -> void:
	var rnd: int = _round
	for i in range(3):
		var shot: Dictionary = a.duplicate(true)
		shot["type"] = "projectile"
		shot["style"] = "zenith_spear"
		shot["dmg"] = 24.0
		shot["guard"] = 9.0
		shot["pierce"] = false
		shot["size"] = 0.8
		shot["speed"] = 22.0
		var angle: float = (float(i) - 1.0) * 0.13
		later(0.23 + float(i) * 0.14, func():
			if rnd == _round and is_instance_valid(f) and not f.is_down():
				_zenith_spear_projectile(f, shot, angle, 22.0))

func _zenith_arsenal(f: Fighter, a: Dictionary) -> void:
	var rnd: int = _round
	var bloom := Node3D.new()
	bloom.name = "ZenithMetalBloom19F"
	f.add_child(bloom)
	bloom.position = Vector3(0.0, 1.15, 0.0)
	var material := Fx.unlit(Color("#c5fff1"), 0.95, true)
	for i in range(17):
		var spear := MeshInstance3D.new()
		var blade := BoxMesh.new()
		blade.size = Vector3(0.055, 0.055, 0.85)
		spear.mesh = blade
		spear.material_override = material
		var a_rad: float = TAU * float(i) / 17.0
		spear.position = Vector3(cos(a_rad) * 1.4, sin(a_rad * 2.0) * 0.22, sin(a_rad) * 1.4)
		spear.rotation.y = -a_rad
		bloom.add_child(spear)
	fx.ring(f.position, Color("#bbffe8"), 2.1, 0.32, 0.84)
	later(1.25, func():
		if is_instance_valid(bloom): bloom.queue_free())
	for i in range(12):
		var shot: Dictionary = a.duplicate(true)
		shot["style"] = "zenith_spear"
		shot["dmg"] = 21.5
		shot["guard"] = 8.0
		shot["size"] = 0.8
		shot["pierce"] = false
		var angle: float = (float(i) - 5.5) * 0.072
		later(0.07 + float(i) * 0.085, func():
			if rnd == _round and is_instance_valid(f) and not f.is_down():
				_zenith_spear_projectile(f, shot, angle, 17.0))
	for i in range(2):
		var finisher: Dictionary = a.duplicate(true)
		finisher["style"] = "zenith_finisher"
		finisher["dmg"] = 43.0
		finisher["size"] = 1.15
		finisher["pierce"] = true
		var angle: float = -0.055 if i == 0 else 0.055
		later(1.06 + float(i) * 0.13, func():
			if rnd == _round and is_instance_valid(f) and not f.is_down():
				_zenith_spear_projectile(f, finisher, angle, 23.0))


# FRG19G — independently timed, defendable strikes (no guaranteed damage).

# FRG19H — scythe skill beats use the ordinary hit/parry/block/clash pipeline.
func _nythera_schedule_beats(f: Fighter, a: Dictionary) -> void:
	var count: int = int(a.get("multi_hit", 1))
	if count <= 1 or not f.active_melee(): return
	var serial: int = f.swing_serial
	var round_id: int = _round
	var span: float = float(a.get("active", 0.0)) * f.attack_time_multiplier()
	for beat in range(1, count):
		var wait_time: float = span * float(beat) / float(count)
		later(wait_time, func():
			_nythera_beat(f, a, serial, round_id, beat))

func _nythera_beat(f: Fighter, a: Dictionary, serial: int, round_id: int, beat: int) -> void:
	if round_over or _round != round_id or not is_instance_valid(f) or f.is_down(): return
	if f.swing_serial != serial or not f.active_melee(): return
	_melee(f, a, beat)

func _nythera_step_wells(dt: float) -> void:
	if dt <= 0.0 or round_over: return
	for f in fighters:
		if f.kit != "scythe" or f.is_down() or f.nythera_well_seconds <= 0.0: continue
		f.nythera_well_seconds = maxf(0.0, f.nythera_well_seconds - dt)
		var center: Vector3 = f.global_position
		for target in enemies_of(f):
			var delta: Vector3 = center - target.global_position
			delta.y = 0.0
			var gap: float = delta.length()
			if gap > 0.95 and gap <= 2.8:
				var pull: float = minf(gap - 0.95, dt * 1.3)
				target.position += delta.normalized() * pull


# FRG19I — each tonfa beat is separately blockable, parryable, clashable and dodgeable.
# Never invoke a magical slash; all contacts share ordinary melee collision.

# FRG19J Carrion Sweep: five distinct contact frames; ordinary blocks/parries/clashes.
func _veyr_schedule_beats(f: Fighter, a: Dictionary) -> void:
	var count: int = int(a.get("multi_hit", 1))
	if count <= 1 or not f.active_melee(): return
	var serial: int = f.swing_serial
	var round_id: int = _round
	var span: float = float(a.get("active", 0.0)) * f.attack_time_multiplier()
	for beat in range(1, count):
		var wait_time: float = span * float(beat) / float(count)
		later(wait_time, func(): _veyr_beat(f, a, serial, round_id, beat))

func _veyr_beat(f: Fighter, a: Dictionary, serial: int, round_id: int, beat: int) -> void:
	if round_over or _round != round_id or not is_instance_valid(f) or f.is_down(): return
	if f.swing_serial != serial or not f.active_melee(): return
	_melee(f, a, beat)

# A lightweight, dodgeable scythe perimeter around Veyr. First-port visual
# approximation, not the browser's final cinematic scythe ring choreography.
func _veyr_step_festivals(dt: float) -> void:
	if dt <= 0.0 or round_over: return
	for f in fighters:
		if not is_instance_valid(f) or f.is_down() or f.kit != "sickle" or f.veyr_festival_t <= 0.0:
			continue
		f.veyr_festival_tick -= dt
		if f.veyr_festival_tick > 0.0: continue
		f.veyr_festival_tick = 0.65
		fx.ring(f.position, Color("#e94468"), 3.5, 0.35, 0.55)
		for d in enemies_of(f):
			var delta: Vector3 = d.position - f.position
			delta.y = 0.0
			var distance: float = delta.length()
			if distance < 2.65 or distance > 3.85: continue
			var rim: Dictionary = f.attacks.l1.duplicate(true)
			rim["id"] = "festival_rim"
			rim["dmg"] = 16.0
			rim["guard"] = 10.0
			rim["knock"] = 0.0
			rim["stun"] = 0.12
			rim["apply_status"] = ""
			apply_hit(f, d, rim, f.dmg_mult, d.chest(), delta.normalized(), false)
			if not d.is_down():
				var pull: Vector3 = -delta.normalized() * 0.25
				d.position += pull

func _renji_schedule_beats(f: Fighter, a: Dictionary) -> void:
	var count: int = int(a.get("multi_hit", 1))
	if count <= 1 or not f.active_melee(): return
	var serial: int = f.swing_serial
	var round_id: int = _round
	var span: float = float(a.get("active", 0.0)) * f.attack_time_multiplier()
	for beat in range(1, count):
		var wait_time: float = span * float(beat) / float(count)
		later(wait_time, func():
			_renji_beat(f, a, serial, round_id, beat))

func _renji_beat(f: Fighter, a: Dictionary, serial: int, round_id: int, beat: int) -> void:
	if round_over or _round != round_id or not is_instance_valid(f) or f.is_down(): return
	if f.swing_serial != serial or not f.active_melee(): return
	_melee(f, a, beat)

func _zephyr_schedule_beats(f: Fighter, a: Dictionary) -> void:
	var count: int = int(a.get("multi_hit", 1))
	if count <= 1 or not f.active_melee():
		return
	var serial: int = f.swing_serial
	var round_id: int = _round
	var span: float = float(a.get("active", 0.0)) * f.attack_time_multiplier()
	for beat in range(1, count):
		var wait_time: float = span * float(beat) / float(count)
		later(wait_time, func():
			_zephyr_beat(f, a, serial, round_id, beat))

func _zephyr_beat(f: Fighter, a: Dictionary, serial: int, round_id: int, beat: int) -> void:
	if round_over or _round != round_id or not is_instance_valid(f) or f.is_down():
		return
	if f.swing_serial != serial or not f.active_melee():
		return
	_melee(f, a, beat)

func _active_melee_contact(f: Fighter) -> void:
	_melee(f, f.atk)

func _melee(f: Fighter, a: Dictionary, beat: int = 0) -> void:
	if not f.active_melee():
		return
	var contact_key := "%d:%d:%d" % [f.id, f.swing_serial, beat]
	var landed: Dictionary = _melee_hits.get(contact_key, {})
	var fwd := f.forward()
	for d in enemies_of(f):
		if landed.has(d.id):
			continue
		var to: Vector3 = d.position - f.position
		var dy := absf(to.y)
		to.y = 0.0
		var dist := to.length()
		var dir := to / maxf(dist, 0.001)
		var front_ok := dist <= 0.6 or dir.dot(fwd) >= MELEE_FRONT_DOT
		if not front_ok:
			continue
		# Two overlapping melee active windows can clash. Check BOTH fighters'
		# facings, so a hit from behind doesn't produce a fake frontal clash.
		if d is Fighter and d.active_melee() and dy < 0.8 \
			and dist <= minf(float(a.reach), float(d.atk.reach)) + 0.3 \
			and (dist <= 0.6 or (-dir).dot(d.forward()) >= MELEE_FRONT_DOT):
			landed[d.id] = true
			# FRG12C - record confirmed melee contact for AI recovery reads
			f.last_melee_contact_serial = f.swing_serial
			d.last_melee_contact_serial = d.swing_serial
			_melee_hits[contact_key] = landed
			var other_key := "%d:%d:0" % [d.id, d.swing_serial]
			var other_landed: Dictionary = _melee_hits.get(other_key, {})
			other_landed[f.id] = true
			_melee_hits[other_key] = other_landed
			_clash(f, d, f.position + dir * minf(dist * 0.5, 0.8) + Vector3(0, 1.15, 0))
			return
		if dist - d.radius + 0.35 > float(a.reach) or dy > MELEE_HEIGHT_TOLERANCE:
			continue
		# Record contact BEFORE hit handling (which can trigger counters/KO).
		landed[d.id] = true
		f.last_melee_contact_serial = f.swing_serial
		_melee_hits[contact_key] = landed
		apply_hit(f, d, a, f.atk_power, d.chest() - dir * 0.15, dir, false)

func _fire(f: Fighter, a: Dictionary) -> void:
	var origin := f.model.cast_point.global_position
	var tgt = f.opponent
	var aim: Vector3 = (tgt.chest() - origin) if tgt else f.forward()
	var base := aim.normalized()
	var n: int = int(a.count)
	for i in n:
		var off: float = 0.0 if n == 1 else -float(a.spread) + 2.0 * float(a.spread) * i / (n - 1)
		_spawn_projectile(f, a, f.atk_power, origin, base.rotated(Vector3.UP, off) * float(a.speed), Color(f.look.glow), tgt)
	fx.flash(origin, Color(f.look.glow), 0.25, 0.1, 0.7)

# FRG14B - readable projectile silhouettes and ribbon trails
# Visual-only change: projectile hitboxes, speed, damage and clash rules stay unchanged.
const PROJECTILE_TRAIL_SAMPLES := 8

func _projectile_shape(style: String, size: float) -> Mesh:
	match style:
		"zenith_rail", "zenith_heavy", "zenith_spear", "zenith_finisher":
			var spear := BoxMesh.new()
			spear.size = Vector3(0.08, 0.09, 0.78) * size
			return spear

		"bloodcrescent":
			var crescent := BoxMesh.new()
			crescent.size = Vector3(0.46, 0.11, 0.25) * size
			return crescent
		"arrow":
			var arrow := BoxMesh.new()
			arrow.size = Vector3(0.05, 0.05, 0.70) * size
			return arrow
		"wave":
			var wave := BoxMesh.new()
			wave.size = Vector3(0.95, 0.14, 0.14) * size
			return wave
		"shuriken":
			var star := BoxMesh.new()
			star.size = Vector3(0.34, 0.34, 0.055) * size
			return star
		"shock":
			var pulse := SphereMesh.new()
			pulse.radius = 0.20 * size
			pulse.height = 0.40 * size
			return pulse
		_:
			var bolt := SphereMesh.new()
			bolt.radius = 0.14 * size
			bolt.height = 0.28 * size
			return bolt

func _attach_projectile_trail(p: Dictionary) -> void:
	var node: MeshInstance3D = p.node
	var ribbon := MeshInstance3D.new()
	ribbon.name = "ProjectileTrail"
	var immediate := ImmediateMesh.new()
	ribbon.mesh = immediate
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.vertex_color_use_as_albedo = true
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	ribbon.material_override = mat
	node.add_child(ribbon)
	p["trail_mesh"] = immediate
	p["trail_points"] = [node.global_position]

func _update_projectile_trail(p: Dictionary) -> void:
	var node: MeshInstance3D = p.node
	if not is_instance_valid(node):
		return
	var points: Array = p.get("trail_points", [])
	points.append(node.global_position)
	while points.size() > PROJECTILE_TRAIL_SAMPLES:
		points.pop_front()
	var ribbon: ImmediateMesh = p.get("trail_mesh")
	if ribbon == null:
		return
	ribbon.clear_surfaces()
	if points.size() < 2:
		return
	ribbon.surface_begin(Mesh.PRIMITIVE_TRIANGLE_STRIP)
	for i in range(points.size()):
		var before: Vector3 = points[maxi(i - 1, 0)]
		var after: Vector3 = points[mini(i + 1, points.size() - 1)]
		var side: Vector3 = (after - before).cross(Vector3.UP)
		if side.length_squared() < 0.00001:
			side = Vector3.RIGHT
		side = side.normalized() * (0.065 * float(p.size))
		var alpha: float = 0.72 * float(i) / float(points.size() - 1)
		var here: Vector3 = points[i]
		ribbon.surface_set_color(Color(p.color, alpha))
		ribbon.surface_add_vertex(node.to_local(here - side))
		ribbon.surface_set_color(Color(p.color, alpha))
		ribbon.surface_add_vertex(node.to_local(here + side))
	ribbon.surface_end()

func _spawn_projectile(shooter, a: Dictionary, power: float, pos: Vector3, vel: Vector3, color: Color, target) -> void:
	var node := MeshInstance3D.new()
	var size: float = float(a.size)
	node.mesh = _projectile_shape(String(a.get("style", "bolt")), size)
	node.material_override = Fx.unlit(color, 1.0, true)
	add_child(node)
	node.global_position = pos
	if vel.length() > 0.01: node.look_at(pos + vel, Vector3.UP)
	_projectiles.append({"id": _next_id, "node": node, "vel": vel, "life": 2.2, "shooter": shooter, "team": shooter.team,
		"atk": a, "power": power, "pierce": bool(a.pierce), "hit": {}, "target": target, "color": color, "size": size})
	_attach_projectile_trail(_projectiles[_projectiles.size() - 1])
	_next_id += 1

## Closest point on projectile travel segment, including both end points.
func _swept_projectile_point(target: Vector3, a: Vector3, b: Vector3) -> Vector3:
	var travel := b - a
	var length_sq := travel.length_squared()
	if length_sq < 0.000001:
		return a
	var along := clampf((target - a).dot(travel) / length_sq, 0.0, 1.0)
	return a + travel * along

# FRG14A - swept projectile versus projectile clashes
# Only ordinary non-piercing enemy projectiles can cancel each other.
# Explosive and piercing attacks continue through their normal impact rules.
func _projectile_can_clash(p: Dictionary) -> bool:
	if bool(p.get("pierce", false)):
		return false
	var style: String = String(p.atk.get("style", ""))
	return not (style in ["explosion", "bomb", "meteor", "grenade", "rocket"])

func _resolve_projectile_duels(dt: float) -> void:
	# Compare trajectories over this frame so fast bolts crossing between
	# discrete positions can still collide, even at lower frame rates.
	if dt <= 0.0 or _projectiles.size() < 2:
		return
	var claimed: Dictionary = {}
	var destroyed: Array = []
	for i in range(_projectiles.size()):
		var a: Dictionary = _projectiles[i]
		if claimed.has(a.id) or not _projectile_can_clash(a):
			continue
		if not is_instance_valid(a.node):
			continue
		for j in range(i + 1, _projectiles.size()):
			var b: Dictionary = _projectiles[j]
			if claimed.has(b.id) or int(a.team) == int(b.team) or not _projectile_can_clash(b):
				continue
			if not is_instance_valid(b.node):
				continue
			var relative_position: Vector3 = a.node.global_position - b.node.global_position
			var relative_velocity: Vector3 = a.vel - b.vel
			var relative_speed_sq: float = relative_velocity.length_squared()
			var hit_t: float = 0.0
			if relative_speed_sq > 0.000001:
				hit_t = clampf(-relative_position.dot(relative_velocity) / relative_speed_sq, 0.0, dt)
			var a_at: Vector3 = a.node.global_position + a.vel * hit_t
			var b_at: Vector3 = b.node.global_position + b.vel * hit_t
			# Projectile meshes use a 0.14*size sphere. Slight tolerance
			# accounts for narrow arrow meshes and near-miss visual contact.
			var hit_radius: float = 0.18 * (maxf(float(a.size), 0.3) + maxf(float(b.size), 0.3))
			if a_at.distance_squared_to(b_at) > hit_radius * hit_radius:
				continue
			var impact: Vector3 = (a_at + b_at) * 0.5
			fx.sparks(impact, Color("#fff1bd"), 24, 6.0)
			fx.ring(impact, Color("#f6d78c"), 0.9, 0.20, 0.75)
			fx.number(impact + Vector3(0.0, 0.3, 0.0), "CLASH!", Color("#ffe6a0"), 0.65)
			audio.play_event("projectile_clash", impact)
			claimed[a.id] = true
			claimed[b.id] = true
			if a.shooter is Fighter:
				a.shooter.notify_passive_event("projectile_destroyed", b.shooter if b.shooter is Fighter else null)
			if b.shooter is Fighter:
				b.shooter.notify_passive_event("projectile_destroyed", a.shooter if a.shooter is Fighter else null)
			destroyed.append(a)
			destroyed.append(b)
			break
	for p in destroyed:
		if is_instance_valid(p.node):
			p.node.queue_free()
		_projectiles.erase(p)

# FRG14C - projectile spin and environment impacts
# Visual-only: projectile velocity, damage, collisions and cooldowns unchanged.
func _projectile_visual_update(p: Dictionary, dt: float) -> void:
	var node: MeshInstance3D = p.node
	if not is_instance_valid(node):
		return
	var style: String = String(p.atk.get("style", ""))
	# Shuriken spin about flight axis while their world travel stays untouched.
	if style == "shuriken":
		node.rotate_object_local(Vector3.FORWARD, dt * 15.0)

func _projectile_world_visual(p: Dictionary, at: Vector3, is_world: bool) -> void:
	# Cosmetic only. Do not call apply_hit or spawn area damage here.
	var col: Color = p.color
	var scale: float = clampf(float(p.size), 0.35, 2.0)
	if not is_world:
		# Timeouts should quietly dissipate to avoid fake impact cues.
		fx.flash(at, col, 0.12 * scale, 0.11, 0.32)
		return
	var style: String = String(p.atk.get("style", ""))
	if style in ["explosion", "bomb", "meteor", "grenade", "rocket"]:
		# A MISS is cosmetic only, even when the projectile style is explosive.
		fx.flash(at, col, 0.45 * scale, 0.17, 0.65)
		fx.ring(at, col, 0.65 * scale, 0.22, 0.55)
	else:
		fx.sparks(at, col, 9, 3.0)
		fx.flash(at, col, 0.22 * scale, 0.12, 0.50)
		if at.y < 0.12:
			fx.ring(at, col, 0.40 * scale, 0.20, 0.4)

func _update_projectiles(dt: float) -> void:
	# Never let paused / concluded duels advance or apply projectile damage.
	if dt <= 0.0 or round_over:
		return
	_resolve_projectile_duels(dt)
	for p in _projectiles.duplicate():
		var node: MeshInstance3D = p.node
		var old_pos: Vector3 = node.global_position
		node.global_position += p.vel * dt
		_update_projectile_trail(p)
		p.life -= dt
		_projectile_visual_update(p, dt)
		var done := false
		# FRG12B - predicted projectile defense and melee interception - melee-vs-projectile clash. No free block: only an actual
		# active melee swing facing the incoming bolt can destroy it. Explosive
		# and piercing projectiles retain their original collision behavior.
		var style: String = String(p.atk.get("style", ""))
		if not bool(p.pierce) and not (style in ["explosion", "bomb", "meteor", "grenade", "rocket"]):
			for defender in fighters:
				if defender.team == p.team or defender.is_down() or not defender.active_melee():
					continue
				var cut: Vector3 = _swept_projectile_point(defender.chest(), old_pos, node.global_position)
				var local_cut: Vector3 = cut - defender.global_position
				if local_cut.y < 0.55 or local_cut.y > 2.2:
					continue
				local_cut.y = 0.0
				var reach: float = clampf(float(defender.atk.get("reach", 1.8)) * 0.65, 0.8, 1.45)
				if local_cut.length() > reach:
					continue
				if local_cut.length() > 0.1 and local_cut.normalized().dot(defender.forward()) < 0.25:
					continue
				fx.sparks(cut, Color(defender.look.glow), 18, 5.0, -p.vel.normalized())
				fx.ring(cut, Color("#ffe6a4"), 0.85, 0.2, 0.65)
				fx.number(cut + Vector3(0, 0.22, 0), "CLASH!", Color("#ffe6a4"), 0.65)
				audio.play_event("projectile_clash", cut)
				defender.notify_passive_event("projectile_destroyed", p.shooter if p.shooter is Fighter else null)
				done = true
				break
		if done:
			node.queue_free()
			_projectiles.erase(p)
			continue
		for e in fighters:
			if e.team == p.team or e.is_down() or p.hit.has(e.id): continue
			var contact: Vector3 = _swept_projectile_point(e.chest(), old_pos, node.global_position)
			if contact.distance_to(e.chest()) < 0.3 * p.size + e.radius:
				p.hit[e.id] = true
				var dir: Vector3 = p.vel
				dir.y = 0.0
				dir = dir.normalized()
				_impact(p.atk, contact, p.color, 0.7)
				apply_hit(p.shooter, e, p.atk, p.power, contact, dir, true)
				if not p.pierce: done = true; break
		var gp := node.global_position
		if not done:
			var world_end: bool = gp.y < 0.05 or Vector2(gp.x, gp.z).length() > 16
			if world_end or p.life <= 0.0:
				var visual_pos: Vector3 = gp
				if visual_pos.y < 0.05:
					visual_pos.y = 0.05
				_projectile_world_visual(p, visual_pos, world_end)
				done = true
		if done:
			node.queue_free()
			_projectiles.erase(p)

## Area attack(s) at the target (or around the caster) after a telegraphed delay.
func _strike(f: Fighter, a: Dictionary, power: float) -> void:
	var rnd := _round
	var color := Color(f.look.glow)
	# FRG19M — capture the initial target point; no homing between slices.
	var kaede_cuts: bool = f.kit == "katana" and String(a.get("style", "")) == "kaede_thousand_cuts"
	var kaede_origin: Vector3 = f.opponent.position if kaede_cuts and f.opponent != null else f.position
	kaede_origin.y = 0.0
	var kaede_contact: Dictionary = {"connected": false}
	var kaede_serial: int = f.swing_serial
	var one := func(i: int, self_ref: Callable) -> void:
		if rnd != _round or f.is_down(): return
		if kaede_cuts and (f.swing_serial != kaede_serial or (i >= 3 and not bool(kaede_contact["connected"]))): return
		var src = f if a.at == "self" or f.opponent == null else f.opponent

		var center: Vector3 = kaede_origin if kaede_cuts else src.position; center.y = 0
		# FRG19D: Nesa C advances the three heart impacts away from her.
		if String(a.get("style", "")) == "nesa_heart_slam" and f.kit == "hammer":
			center += f.forward() * (1.05 + float(i) * 0.75)
		var wait: float = float(a.delay) if i == 0 else float(a.interval)
		var mark := {"target": f.opponent, "land": _time + wait, "id": _next_id}
		_next_id += 1
		_strike_marks.append(mark)
		fx.telegraph(center, color, float(a.radius), wait)
		later(wait, func():
			_strike_marks.erase(mark)
			if rnd != _round: return
			if kaede_cuts and (f.is_down() or f.swing_serial != kaede_serial or (i >= 3 and not bool(kaede_contact["connected"]))): return

			var at: Vector3 = Vector3(f.position.x, 0, f.position.z) if a.at == "self" else center
			if String(a.get("style", "")) == "nesa_heart_slam" and f.kit == "hammer":
				at = center
			_impact(a, at, color, float(a.radius))
			if f.kit == "mage" and String(f.look.get("element", "")) == "fire" and bool(a.get("fire_patch", false)):
				_ember_add_patch(f, at, float(a.get("radius", 1.0)))
			for d in enemies_of(f):
				var to: Vector3 = d.position - at; to.y = 0
				if to.length() <= float(a.radius) + d.radius * 0.5 and not d.airborne():
					var dir: Vector3 = to.normalized() if to.length() > 0.05 else (d.position - f.position).normalized()
					var hp_before: float = d.hp
					apply_hit(f, d, a, power, d.chest(), dir, true)
					# FRG19M — shield blocks and invulnerable misses do NOT count.
					if kaede_cuts and i < 3 and d.hp < hp_before:
						kaede_contact["connected"] = true
				elif to.length() <= float(a.radius) + 1.0:
					fx.number(d.chest() + Vector3(0, 0.8, 0), "DODGE", Color("#c9d3e6"), 0.7)
			if i + 1 < int(a.repeat): self_ref.call(i + 1, self_ref))
	one.call(0, one)

func _impact(a: Dictionary, pos: Vector3, color: Color, radius: float) -> void:
	var g := Vector3(pos.x, 0, pos.z)
	match a.style:
		"explosion", "meteor":
			fx.explosion(g, color, radius); add_trauma(0.35 if a.style == "explosion" else 0.6)
		"lightning":
			fx.flash(g + Vector3(0, 0.4, 0), Color("#fff2b0"), radius * 0.6, 0.15, 0.9)
			fx.sparks(g + Vector3(0, 0.2, 0), color, 30, 7.0, Vector3.UP)
			fx.ring(g, color, radius * 1.3, 0.3, 0.9); add_trauma(0.3)
		"slam", "cleave":
			if a.style == "slam": fx.rocks(g, 22, 1.4)
			fx.ring(g, color, radius * 1.3, 0.35, 0.9)
			fx.sparks(g + Vector3(0, 0.2, 0), Color("#d8c8a8"), 40, 7.0, Vector3.UP)
			add_trauma(0.65 if a.style == "cleave" else 0.45)

		"nesa_heart_slam", "nesa_giant_heart": # FRG19D heart hammer hit treatment
			fx.rocks(g, 20 if a.style == "nesa_heart_slam" else 34, 1.5)
			fx.ring(g, Color("#ff95c1"), radius * 1.3, 0.38, 0.94)
			fx.flash(g + Vector3(0, 0.7, 0), Color("#ffe1f0"), radius * 0.60, 0.18, 0.88)
			add_trauma(0.55 if a.style == "nesa_heart_slam" else 0.82)
		"kaede_thousand_cuts": # FRG19M — sharp, stationary katana cut beats
			fx.sparks(g + Vector3(0, 1.1, 0), color, 15, 6.0)
			fx.flash(g + Vector3(0, 1.0, 0), Color("#ffe0eb"), 0.42, 0.10, 0.75)
		"iron_tempest": # FRG19L: individual greatsword swing contact VFX
			fx.sparks(g + Vector3(0, 0.9, 0), color, 18, 5.3)
			fx.ring(g + Vector3(0, 0.65, 0), color, radius * 0.75, 0.18, 0.68)
		"spin":
			fx.ring(g + Vector3(0, 1.0, 0), color, radius, 0.2, 0.9)
		_:
			fx.sparks(pos, color, 14, 5.0)
	# FRG18A: small selection of per-element and skill-impact sounds.
	var style_sound := String(a.get("style", ""))
	var element_sound := String(a.get("element", ""))
	var cue := "skill_impact"
	if style_sound in ["explosion", "meteor"]:
		cue = "explosion"
	elif style_sound == "lightning" or element_sound == "lightning":
		cue = "lightning"
	elif element_sound in ["water", "ice", "fire"]:
		cue = element_sound
	audio.play_event(cue, g)
	# FRG17C: visual-only elemental accent for skill impact events.
	fx.elemental_skill_17c(g, String(a.get("element", "")), String(a.get("style", "")), color, radius)

func _buff(f: Fighter, a: Dictionary) -> void:
	var pvp: bool = cfg.mode != "survival"
	match a.mode:
		"ember_ignition": # FRG19N: consume owned ground fire and an active burn
			_ember_absolute_combustion(f, a)
		"aster_judgment": # FRG19K — temporary damage and sword speed transformation
			if f.kit == "knight" and String(f.look.get("element", "")) == "light":
				f.aster_judgment_t = float(a.get("duration", 10.0))
				if f.model != null and f.model.shield_node != null:
					f.model.shield_node.visible = false
				f.model.flash(Color("#fff6bd"), 0.5)
				fx.ring(f.position, Color("#ffe59c"), 2.4, 0.5, 0.8)
				fx.number(f.chest() + Vector3(0, 0.6, 0), "JUDGMENT", Color("#fff0b4"), 1.2)


		"gravity_well":
			# Moonfloat pulls enemies, Dreadfall collapses in a dodgeable circle.
			if f.kit == "scythe" and f.nythera_mode == 0:
				f.nythera_well_seconds = 2.6
				fx.ring(f.position, Color("#a98bef"), 2.8, 0.38, 0.75)
				fx.number(f.chest() + Vector3(0, 0.7, 0), "EVENT HORIZON", Color("#d7c4ff"), 0.85)
			else:
				f.nythera_well_seconds = 0.0
				var pulse: Dictionary = a.duplicate(true)
				pulse["type"] = "strike"
				pulse["at"] = "self"
				pulse["dmg"] = 116.0
				pulse["guard"] = 37.0
				pulse["knock"] = 4.6
				pulse["stun"] = 0.34
				pulse["heavy"] = true
				pulse["delay"] = 0.36
				pulse["radius"] = 2.7
				pulse["repeat"] = 1
				pulse["style"] = "gravity_meteor"
				_strike(f, pulse, f.atk_power)



		"blood_feint":
			f.veyr_feint_t = float(a.get("duration", 0.30))
			f.veyr_feint_counter = false
			fx.flash(f.chest(), Color("#ff5577"), 0.45, 0.18, 0.8)
		"blood_festival":
			f.veyr_festival_t = float(a.get("duration", 8.0))
			f.veyr_festival_tick = 0.38
			if f.opponent != null and not f.opponent.is_down():
				var away: Vector3 = f.position - f.opponent.position
				away.y = 0.0
				if away.length_squared() < 0.001: away = Vector3.RIGHT
				f.teleport(f.opponent.position + away.normalized() * 1.75)
			fx.ring(f.position, Color("#f34669"), 3.5, 0.4, 0.85)
			fx.number(f.chest() + Vector3(0, 0.8, 0), "BLOOD FESTIVAL", Color("#ff9daf"), 1.2)
		"renji_reflection": # FRG19I — no invulnerability to truly unparryable hits
			f.renji_reflection_t = float(a.get("duration", 15.0))
			fx.ring(f.position, Color("#bc8cff"), 1.4, 0.3, 0.8)
			fx.number(f.chest() + Vector3(0, 0.7, 0), "IRON REFLECTION", Color("#e4c8ff"), 0.8)
		"frost_aegis":
			# FRG19E: four charges for a maximum of seven seconds (no stacking).
			f.roxy_aegis_charges = 4
			f.roxy_aegis_t = float(a.get("duration", 7.0))
			fx.ring(f.position, Color("#a7efff"), 1.5, 0.38, 0.85)
			fx.number(f.chest() + Vector3(0, 0.8, 0), "SNOWGLASS x4", Color("#e1faff"), 1.0)
		"ward":
			f.ward_t = minf(float(a.duration), 2.0) if pvp else float(a.duration)
			fx.number(f.chest() + Vector3(0, 0.9, 0), "WARD", Color("#8fe6ff"), 0.9)
		"heal":
			var frac := 0.16 if pvp else 0.25
			f.heal(f.max_hp * frac)
			fx.ring(f.position, Color("#9dff9a"), 1.6, 0.4, 0.9)
			fx.number(f.chest() + Vector3(0, 0.9, 0), "+%d" % int(f.max_hp * frac), Color("#9dff9a"), 1.1)
		"rage":
			f.rage_t = float(a.duration)
			fx.flash(f.chest(), Color("#ff5a3d"), 0.7, 0.3, 0.8)
			fx.number(f.chest() + Vector3(0, 0.9, 0), "BERSERK", Color("#ff8a50"), 1.0)
		"counter":
			f.counter_t = float(a.duration)

		"nesa_high_striker": # FRG19D Nesa V, only valid incoming hits trigger the giant riposte
			f.counter_t = 0.55
			f.nesa_counter_pending = true
			f.nesa_counter_slot = f.atk_id
			f.nesa_counter_max_cd = float(a.get("cd", 26.0)) * f.cd_mult
			fx.number(f.chest() + Vector3(0, 0.9, 0), "HEART COUNTER", Color("#ffd5e5"), 0.8)
			fx.number(f.chest() + Vector3(0, 0.9, 0), "COUNTER STANCE", Color("#ffd1da"), 0.7)

func _blink(f: Fighter, a: Dictionary) -> void:
	var from := f.position
	var o = f.opponent
	var d: Vector3 = (o.position - from).normalized() if o else f.forward()
	d.y = 0
	var to := from - d * 3.0
	if a.mode == "behind" and o: to = o.position + d * 1.3
	fx.smoke(from, Color(f.look.glow))
	f.teleport(to)
	fx.smoke(f.position, Color(f.look.glow))

func apply_hit(attacker, d: Fighter, a: Dictionary, power: float, hit_pos: Vector3, dir: Vector3, ranged: bool) -> void:
	# FRG19L: pass per-hit metadata rather than mutating shared attack dictionaries.
	var incoming_attack: Dictionary = a
	if ranged and String(a.get("type", "")) == "projectile" and d.kit == "greatsword" and d.garrick_resolve >= 2 and d.opponent != null and not d.opponent.is_down():
		var approach: Vector3 = d.opponent.position - d.position
		approach.y = 0.0
		if approach.length_squared() > 0.01 and d.in_move.length_squared() > 0.01 and d.in_move.normalized().dot(approach.normalized()) > 0.25:
			incoming_attack = a.duplicate(true)
			incoming_attack["_garrick_resolve_defense"] = true
	var result := d.receive_hit(attacker, incoming_attack, power)

	# FRG19E: four landed frost shards freeze, with a brief re-freeze cooldown.
	if attacker is Fighter and String(attacker.look.get("element", "")) == "frost" and String(a.get("style", "")) == "frost_shard" and result in ["hit", "crit", "ko"]:
		attacker.roxy_frost_stacks = mini(attacker.roxy_frost_stacks + 1, 4)
		if attacker.roxy_frost_stacks >= 4 and attacker.roxy_freeze_cd <= 0.0 and not d.is_down():
			if d.add_status("freeze", 1, 2.0):
				fx.number(d.chest() + Vector3(0, 0.65, 0), "FROZEN!", Color("#a8eeff"), 1.1)
				attacker.roxy_frost_stacks = 0
				attacker.roxy_freeze_cd = 4.0

	# FRG19C: confirmed contacts only. Blocks, parries, clashes and invulnerable
	# enemies cannot be chain-bound. The victim's existing CC rules do the locking.
	if attacker is Fighter and attacker.kit == "chainblade" and result in ["hit", "crit"]:
		var chain_style: String = String(a.get("style", ""))
		if chain_style == "chain_predator_hook":
			if d.add_status("root", 1, 4.0):
				attacker.kaizen_bound_target = d
				attacker.kaizen_bind_seconds = 4.0
				fx.ring(hit_pos, Color(attacker.look.glow), 1.0, 0.25, 0.7)
		elif chain_style == "chain_serpent_bind":
			d.add_status("root", 1, 1.4)
			fx.ring(hit_pos, Color(attacker.look.glow), 1.6, 0.30, 0.9)
	if result in ["hit", "crit", "ko"]:
		d.notify_passive_event("received_hit", attacker if attacker is Fighter else null)
		if attacker is Fighter:
			attacker.notify_passive_event("landed_hit", d)
		var effect_id: String = String(a.get("apply_status", ""))
		if effect_id != "" and randf() <= clampf(float(a.get("status_chance", 1.0)), 0.0, 1.0):
			d.add_status(effect_id, maxi(int(a.get("status_stacks", 1)), 1), float(a.get("status_duration", -1.0)))
	elif result == "blocked":
		d.notify_passive_event("blocked", attacker if attacker is Fighter else null)
		if attacker is Fighter:
			attacker.notify_passive_event("blocked_attack", d)
	elif result == "parry":
		d.notify_passive_event("parried", attacker if attacker is Fighter else null)
		# FRG19L: only projectile parries, never melee parries, build Resolve.
		if ranged and String(a.get("type", "")) == "projectile":
			d.notify_passive_event("projectile_parried", attacker if attacker is Fighter else null)
		if attacker is Fighter:
			attacker.notify_passive_event("was_parried", d)
	elif result == "guard_break":
		d.notify_passive_event("guard_broken", attacker if attacker is Fighter else null)
		if attacker is Fighter and attacker.kit == "knuckles" and String(attacker.look.get("vrm", "")) == "rook":
			attacker.notify_passive_event("guard_break_attack", d) # FRG19O
	var glow := Color(attacker.look.glow) if attacker is Fighter else Color.WHITE
	var heavy: bool = bool(a.get("heavy", false)) or String(a.get("id", "")) == "l3"
	var shield_pos := d.model.shield_node.global_position if d.model.shield_node else hit_pos
	match result:
		"hit", "crit", "ko":
			audio.play_event("hit_heavy" if heavy else "hit_light", hit_pos, true, d.get_instance_id())
			if attacker is Fighter:
				var special_audio: bool = heavy or String(attacker.atk_id) in ["z", "x", "c", "v", "l3"]
				audio.play_special_elemental_hit(String(attacker.look.element), hit_pos, attacker.get_instance_id(), special_audio)
			var crit := d.last_crit
			fx.combat_hit(hit_pos, glow, dir, heavy)
			# FRG17C: cosmetic accent only after a landed hit.
			if attacker is Fighter:
				fx.elemental_hit_17c(hit_pos, String(attacker.look.element), glow, heavy)
			fx.number(hit_pos + Vector3(0, 0.5, 0), "%d%s" % [int(d.last_damage), "!" if crit else ""], Color("#ffb347") if crit else Color.WHITE, 1.5 if crit else 1.0)
			if attacker is Fighter and attacker.lifesteal > 0: attacker.heal(d.last_damage * attacker.lifesteal)
			if attacker is Fighter and attacker.look.element == "earth": fx.rocks(d.position, 12 if heavy else 6, 0.9 if heavy else 0.6)
			add_trauma(0.5 if a.heavy else 0.3 if heavy else 0.18)
			hit_stop(0.11 if a.heavy else 0.07 if heavy else 0.045)
		"blocked":
			audio.play_event("block", shield_pos, true, d.get_instance_id())
			if attacker is Fighter: attacker.add_guard_fatigue()
			fx.combat_guard(shield_pos, dir, false)
			fx.number(shield_pos + Vector3(0, 0.4, 0), "BLOCK", Color("#c9d3e6"), 0.7)
			add_trauma(0.14); hit_stop(0.04)
		"parry":
			audio.play_event("parry", shield_pos, true, d.get_instance_id())
			if attacker is Fighter: attacker.add_guard_fatigue()
			# Parry delays attacks with hit-stop, not a full stun.
			fx.combat_guard(shield_pos, dir, true)
			fx.number(shield_pos + Vector3(0, 0.5, 0), "PARRY!", Color("#8fe6ff"), 1.4)
			add_trauma(0.4); hit_stop(0.35)

		"counter":
			# FRG19O — a counter breaks Rook's active hit chain.
			if attacker is Fighter and attacker.kit == "knuckles" and String(attacker.look.get("vrm", "")) == "rook":
				attacker.notify_passive_event("countered_attack", d)

			if d.kit == "sickle" and d.veyr_feint_counter:
				d.veyr_feint_counter = false
				fx.number(d.chest() + Vector3(0, 0.5, 0), "DEATH FEINT!", Color("#ff849d"), 0.9)
				if attacker is Fighter and not attacker.is_down():
					d.teleport(attacker.position - attacker.forward() * 1.3)
					var riposte: Dictionary = d.attacks.heavy.duplicate(true)
					riposte["dmg"] = 145.0
					riposte["knock"] = 2.2
					riposte["stun"] = 0.40
					apply_hit(d, attacker, riposte, d.dmg_mult, attacker.chest(), d.forward(), false)
			elif d.kit == "hammer" and d.nesa_counter_pending:
				# An actual successful counter, not an unconditional giant attack.
				d.nesa_counter_pending = false
				d.nesa_counter_slot = ""
				fx.number(d.chest() + Vector3(0, 0.6, 0), "HEARTBREAKER!", Color("#ffd5e5"), 1.4)
				var boom := d.attacks.heavy.duplicate(true)
				boom["type"] = "strike"
				boom["style"] = "nesa_giant_heart"
				boom["at"] = "self"
				boom["dmg"] = 580
				boom["guard"] = 90
				boom["knock"] = 12.5
				boom["stun"] = 1.0
				boom["heavy"] = true
				boom["radius"] = 3.5
				boom["delay"] = 0.05
				boom["repeat"] = 1
				_strike(d, boom, d.dmg_mult)
			else:
				fx.number(d.chest() + Vector3(0, 0.6, 0), "COUNTER!", Color("#ff9aa8"), 1.4)
				if attacker:
					var counter: Dictionary = d.attacks.heavy.duplicate()
					counter.dmg = 180; counter.heavy = true; counter.stun = 0.8
					var counter_power: float = d.dmg_mult
					if d.kit == "katana": counter_power *= 0.80 + 0.05 * float(d.kaede_counter_bloom)
					apply_hit(d, attacker, counter, counter_power, attacker.chest(), -dir, false)
		"guard_break":
			audio.play_event("guard_break", hit_pos, true, d.get_instance_id())
			fx.combat_guard_break(hit_pos)
			fx.number(hit_pos + Vector3(0, 0.55, 0), "GUARD BREAK", Color("#ff8a50"), 1.2)
			add_trauma(0.55); hit_stop(0.12)
		"warded":
			fx.number(hit_pos + Vector3(0, 0.5, 0), "ABSORBED", Color("#8fe6ff"), 0.8)
		"miss":
			fx.number(hit_pos + Vector3(0, 0.5, 0), "MISS", Color("#c9d3e6"), 0.8)

func _clash(a: Fighter, b: Fighter, pos: Vector3) -> void:
	a.clash_recoil(); b.clash_recoil()
	a.notify_passive_event("clashed", b)
	b.notify_passive_event("clashed", a)
	audio.play_event("clash", pos)
	fx.combat_clash(pos)
	fx.number(pos + Vector3(0, 0.45, 0), "CLASH!", Color("#ffe08a"), 1.3)
	add_trauma(0.45); hit_stop(0.13)

## Light-element blades shed glowing motes (stream while swinging, sparkle at rest).
func _blade_light(dt: float) -> void:
	for f in fighters:
		if f.look.element != "light" or f.is_down() or f.model.blade_tip == null: continue
		var t: float = _mote_t.get(f, 0.0) - dt
		if t <= 0.0:
			var at := f.model.blade_base.global_position.lerp(f.model.blade_tip.global_position, 0.3 + randf() * 0.7)
			var swinging := f.trail_on()
			fx.motes(at, Color("#fff3c4") if randf() < 0.6 else Color(f.look.glow), 4 if swinging else 2)
			t = 0.025 if swinging else 0.1 + randf() * 0.08
		_mote_t[f] = t

# --- rounds --------------------------------------------------------------------------------

func _on_ko(f: Fighter) -> void:
	audio.play_event("ko", f.chest())
	if cfg.mode == "duel":
		if round_over:
			return
		var survivor: Fighter = null
		for candidate in fighters:
			if candidate != f and not candidate.is_down():
				survivor = candidate
				break
		_finish_duel(survivor)
	elif cfg.mode == "team":
		fx.number(f.chest() + Vector3(0, 0.8, 0), "DOWN!", Color("#ff7b7b"), 1.1)
		if round_over: return
		for x in fighters:
			if x.team == f.team and not x.is_down(): return
		round_over = true
		var winner_team := 1 - f.team
		for x in fighters: x.brain = null
		hit_stop(0.9)
		later(0.5, func():
			var mine: int = local.team if local else 0
			for x in fighters:
				if x.team == winner_team:
					x.win()
					# Legacy team mode no longer grants currency.
			ui_event.emit({"type": "over", "text": "VICTORY" if winner_team == mine else "DEFEAT", "sub": "Team %s wins" % ("Blue" if winner_team == 0 else "Red"), "color": Color("#ffe08a") if winner_team == mine else Color("#ff7b7b")})
			can_restart = true)

# --- FRG10: complete duel clock and end-of-round handling ----------------------------------

func _tick_duel_clock(dt: float) -> void:
	if cfg.mode != "duel" or round_over or not _duel_clock_running or dt <= 0.0:
		return
	if float(cfg.get("round_seconds", 120)) <= 0.0:
		return  # Unlimited mode
	_duel_seconds_left = maxf(_duel_seconds_left - dt, 0.0)
	if _duel_seconds_left > 0.0 or fighters.size() < 2:
		return
	# Remaining HP percentage determines the result. Exact ties are draws.
	var a: Fighter = fighters[0]
	var b: Fighter = fighters[1]
	var a_ratio: float = a.hp / maxf(a.max_hp, 1.0)
	var b_ratio: float = b.hp / maxf(b.max_hp, 1.0)
	var winner: Fighter = null
	if a_ratio > b_ratio + 0.0001:
		winner = a
	elif b_ratio > a_ratio + 0.0001:
		winner = b
	_finish_duel(winner, true)

func _finish_duel(winner: Fighter, by_time: bool = false) -> void:
	if round_over:
		return
	round_over = true
	_duel_clock_running = false
	for f in fighters:
		f.brain = null
	add_trauma(0.65)
	hit_stop(0.35)
	later(0.35, func():
		if not is_instance_valid(self):
			return
		if is_instance_valid(winner):
			winner.win()
		var spectator_mode: bool = bool(cfg.get("spectator", false))
		var draw: bool = winner == null
		var player_wins: bool = winner != null and winner == local
		var result_text: String = "DRAW"
		if not draw:
			if spectator_mode:
				result_text = "%s WINS!" % winner.look.name
			else:
				result_text = "VICTORY" if player_wins else "DEFEAT"
		var result_color: Color = Color("#d2e7ff") if draw else (Color("#ffe08a") if spectator_mode or player_wins else Color("#ff7b7b"))
		var detail: String = "Time limit reached" if by_time else "Knockout"
		ui_event.emit({"type": "over", "text": result_text, "sub": detail + "  |  R to rematch", "color": result_color})
		audio.play_event("victory", Vector3.ZERO, false)
		can_restart = true)

# --- camera --------------------------------------------------------------------------------

func _update_camera(dt: float) -> void:
	if bool(cfg.get("spectator", false)) and _spectator_view != 0:
		_update_spectator_camera(dt)
		return
	if _third_person and not bool(cfg.get("spectator", false)) and local != null:
		_update_third_person_camera(dt)
		return
	camera.fov = lerpf(camera.fov, 50.0, 1.0 - exp(-7.0 * dt))
	var me: Fighter = local if local else (fighters[0] if not fighters.is_empty() else null)
	if me == null: return
	var goal: Vector3
	var look: Vector3
	if cfg.mode == "duel" and fighters.size() >= 2:
		var other: Fighter = fighters.filter(func(x): return x != me)[0]
		var mid := (me.position + other.position) * 0.5
		var d := other.position - me.position; d.y = 0
		var sep := d.length()
		d /= maxf(sep, 0.01)
		var side := Vector3(-d.z, 0, d.x)
		var lift := mid.y * 0.5
		mid.y = 0
		goal = mid + side * (3.4 + sep * 0.6) - d * 0.5 + Vector3(0, 1.45 + lift, 0)
		look = mid + Vector3(0, 1.0 + lift, 0)
	else:
		var p := Vector3(me.position.x, 0, me.position.z)
		goal = p + Vector3(0, 7.5, 8)
		look = p + Vector3(0, 1.0, 0)
	camera.position = camera.position.lerp(goal, 1.0 - exp(-5.0 * dt))
	camera.look_at(look, Vector3.UP)
	_trauma = maxf(_trauma - 1.4 * dt, 0.0)
	var sh := _trauma * _trauma
	_shake_t += dt * 32.0
	camera.position += Vector3(0.22 * sh * sin(_shake_t * 1.7), 0.16 * sh * sin(_shake_t * 2.3), 0)

func _update_spectator_camera(dt: float) -> void:
	if fighters.size() < 2:
		return
	var a: Fighter = fighters[0]
	var b: Fighter = fighters[1]
	var mid: Vector3 = (a.chest() + b.chest()) * 0.5
	var target: Vector3 = mid
	if _spectator_view == 2:
		target = a.chest().lerp(b.chest(), 0.15)
	elif _spectator_view == 3:
		target = b.chest().lerp(a.chest(), 0.15)
	var dist := _spectator_distance
	if _spectator_view == 2 or _spectator_view == 3:
		dist = maxf(5.0, _spectator_distance * 0.72)
	else:
		dist = maxf(dist, a.position.distance_to(b.position) * 0.85 + 3.0)
	var dir := Vector3(sin(_spectator_yaw) * cos(_spectator_pitch),
		sin(_spectator_pitch), cos(_spectator_yaw) * cos(_spectator_pitch))
	var desired := target + dir * dist
	var alpha := 1.0 - exp(-6.0 * dt)
	camera.fov = lerpf(camera.fov, 56.0, alpha)
	camera.global_position = camera.global_position.lerp(desired, alpha)
	camera.look_at(target, Vector3.UP)
	_trauma = maxf(_trauma - 1.4 * dt, 0.0)

func _make_camera_hint() -> void:
	# Lightweight, non-interactive label. HUD and pause UI remain on top.
	var layer := CanvasLayer.new()
	layer.layer = 0
	add_child(layer)
	_camera_hint = Label.new()
	_camera_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_camera_hint.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_camera_hint.add_theme_font_size_override("font_size", 14)
	_camera_hint.add_theme_color_override("font_color", Color("#fff3dc"))
	_camera_hint.add_theme_color_override("font_outline_color", Color.BLACK)
	_camera_hint.add_theme_constant_override("outline_size", 5)
	layer.add_child(_camera_hint)
	_camera_hint.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_camera_hint.position = Vector2(-240, 6)
	_camera_hint.size = Vector2(480, 24)
	_update_camera_hint()

func _update_camera_hint() -> void:
	if _camera_hint == null:
		return
	if _third_person:
		_camera_hint.text = "THIRD PERSON  |  F6 side view  |  Tab lock: %s  |  MMB orbit  |  Wheel zoom" % ("ON" if _lock_on else "OFF")
	else:
		_camera_hint.text = "SIDE VIEW  |  F6 third person"

func _update_third_person_camera(dt: float) -> void:
	if local == null or not is_instance_valid(local):
		return
	var me: Fighter = local
	if not _camera_initialized:
		var facing: Vector3 = me.forward()
		_orbit_yaw = atan2(facing.x, facing.z)
		_camera_initialized = true
	var focus: Vector3 = me.chest()
	var distance: float = _follow_distance
	var enemy: Fighter = me.opponent
	if _lock_on and is_instance_valid(enemy) and not enemy.is_down():
		var delta: Vector3 = enemy.global_position - me.global_position
		delta.y = 0.0
		if delta.length_squared() > 0.02:
			var desired_yaw: float = atan2(delta.x, delta.z)
			_orbit_yaw = lerp_angle(_orbit_yaw, desired_yaw, 1.0 - exp(-7.0 * dt))
		# In lock-on, a little of the opponent is framed beside the player.
		# Pull backward as they separate so both remain in view.
		focus = me.chest().lerp(enemy.chest(), 0.27)
		distance = maxf(distance, delta.length() * 0.54 + 2.7)
	var back := Vector3(
		-sin(_orbit_yaw) * cos(_orbit_pitch),
		sin(_orbit_pitch),
		-cos(_orbit_yaw) * cos(_orbit_pitch)
	)
	var desired: Vector3 = focus + back * distance
	# Future-proof for levels with walls/obstacles; does not require a hand-made camera rig.
	var query := PhysicsRayQueryParameters3D.create(focus, desired)
	query.collide_with_areas = false
	var hit: Dictionary = get_world_3d().direct_space_state.intersect_ray(query)
	if not hit.is_empty():
		desired = focus.lerp(hit.position, 0.86)
	camera.fov = lerpf(camera.fov, 64.0, 1.0 - exp(-7.0 * dt))
	camera.global_position = camera.global_position.lerp(desired, 1.0 - exp(-9.0 * dt))
	camera.look_at(focus, Vector3.UP)
	# Preserve the pre-existing impact shake instead of losing hit feel.
	_trauma = maxf(_trauma - 1.4 * dt, 0.0)
	var shake: float = _trauma * _trauma
	_shake_t += dt * 32.0
	camera.global_position += Vector3(
		0.22 * shake * sin(_shake_t * 1.7),
		0.16 * shake * sin(_shake_t * 2.3),
		0.0
	)

# FRG15D - status HUD and countdown indicators
# --- HUD feed ------------------------------------------------------------------------------

func hud() -> Dictionary:
	# The spectator has no local fighter; show CPU A/CPU B in the two HUD bars.
	var me: Fighter = local if local else (fighters[0] if not fighters.is_empty() else null)
	var info := func(f: Fighter) -> Dictionary:
		return {"id": Data.character(f.char_index).id, "name": f.look.name, "hp": f.hp, "max_hp": f.max_hp, "guard": f.guard, "max_guard": f.max_guard, "down": f.is_down(), "glow": f.look.glow, "fatigue": f.guard_fatigue, "status": f.status_summary(), "status_effects": f.status_details()}
	var other: Fighter = null
	if cfg.mode == "duel":
		for f in fighters: if f != me: other = f
	return {
		"mode": cfg.mode,
		"me": info.call(me) if me else {},
		"other": info.call(other) if other else {},
		"team": fighters.filter(func(f): return f != me and me and f.team == me.team).map(info),
		"foes": fighters.filter(func(f): return me and f.team != me.team).map(info) if cfg.mode == "team" else [],
		"skills": (["z", "x", "c"].map(func(k): return {"key": k, "name": me.attacks[k].name, "cd": me.cooldowns[k], "max": float(me.attacks[k].cd) * me.cd_mult})) if me else [],
		"dash": {"t": me.dash_cd, "max": Fighter.DASH_CD} if me else {},
		"atk_lock": {"t": me.atk_lock, "max": Fighter.RANGED_REST.get(me.kit, 1.2)} if me and me.attacks.l1.type != "melee" else {},
		"seconds_left": _duel_seconds_left,
		"time_limit": float(cfg.get("round_seconds", 120)),
		"clock_running": _duel_clock_running,
		"spectator": bool(cfg.get("spectator", false)),
		"spectator_speed": float(SPECTATOR_SPEEDS[_spectator_speed_index]),
		"spectator_view": SPECTATOR_VIEWS[_spectator_view],
		"paused": paused,
		"can_restart": can_restart,
	}


# FRG19B: multi-pass moves use real melee checks, once per target each beat.
func _frg19b_multi_contact(f: Fighter) -> void:
	if not f.active_melee():
		_frg19b_multi_phase.erase(f.id)
		return
	var hits: int = clampi(int(f.atk.get("multi_hit", 1)), 1, 12)
	if hits <= 1:
		return
	var attack_t: float = (f.state_t - float(f.atk.wind) * f.attack_time_multiplier())
	var length: float = maxf(float(f.atk.active) * f.attack_time_multiplier(), 0.025)
	var phase: int = clampi(int(floor(maxf(attack_t, 0.0) * hits / length)), 0, hits - 1)
	var key: String = str(f.id)
	var saved: Dictionary = _frg19b_multi_phase.get(key, {})
	var original: int = f.swing_serial
	if saved.get("move", "") != f.atk_id or int(saved.get("serial", -1)) != original:
		saved = {"move": f.atk_id, "phase": 0, "serial": original}
	if phase > int(saved.get("phase", 0)):
		f.swing_serial += phase - int(saved.get("phase", 0))
		saved["phase"] = phase
		saved["serial"] = f.swing_serial
	_frg19b_multi_phase[key] = saved
