class_name Match
extends Node3D
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
var round_over := false
var can_restart := false
var paused := false

var _time := 0.0
var _round := 0
var _timers: Array = []         # [time, Callable]
var _projectiles: Array = []    # dictionaries
var _strike_marks: Array = []   # {target, land, id}
var _trails: Dictionary = {}    # Fighter -> Trail
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

func _ready() -> void:
	_build_world()
	fx = Fx.new()
	add_child(fx)
	camera = Camera3D.new()
	camera.fov = 50
	add_child(camera)
	camera.make_current()
	camera.position = Vector3(0, 6, 10)
	_player_brain = PlayerBrain.new(camera)
	start_round()

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
	env.environment.fog_enabled = true
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
	for f in fighters: f.queue_free()
	for t in _trails.values(): t.queue_free()
	fighters.clear(); _trails.clear(); _melee_hits.clear(); _projectiles.clear(); _strike_marks.clear(); _timers.clear()
	fx.clear()
	local = null
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
		for f in fs: f.brain = _brain_for(f))

func _brain_for(f: Fighter):
	if String(f.owner_peer).begins_with("cpu"): return AiBrain.new(self, cfg.get("difficulty", 1))
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
	f.dashed.connect(func(x: Fighter):
		fx.smoke(x.global_position, Color(x.look.glow))
		fx.ring(x.global_position, Color(x.look.glow), 1.2, 0.2, 0.7))
	fighters.append(f)
	if f.model.blade_base and f.model.blade_tip:
		var tr := Trail.new(f.model.blade_base, f.model.blade_tip, Color(f.look.glow))
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
	if not bool(cfg.get("spectator", false)):
		_player_brain.on_event(e)

func _process(real_dt: float) -> void:
	real_dt = clampf(real_dt, 0.0, 0.05)
	var now := Time.get_ticks_msec() / 1000.0
	var scale := 0.05 if now < _stop_until else 1.0
	var dt := 0.0 if paused else real_dt * scale
	_time += dt
	var due := _timers.filter(func(t): return t[0] <= _time)
	_timers = _timers.filter(func(t): return t[0] > _time)
	for t in due: t[1].call()
	if cfg.mode == "team": _retarget()
	for f in fighters:
		f.tick(dt)
		# A sword remains dangerous for the entire active window. One contact per
		# defender/swing is enforced in _melee, so framerate cannot multiply damage.
		if dt > 0.0 and not round_over and f.active_melee():
			_active_melee_contact(f)
		if _trails.has(f):
			_trails[f].emitting = f.trail_on()
			_trails[f].tick(dt)
	_update_projectiles(dt)
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
	return _projectiles.map(func(p): return {"target": p.target, "pos": p.node.global_position, "vel": p.vel, "id": p.id})

func strike_threats() -> Array:
	return _strike_marks

func now() -> float:
	return _time

# --- attack resolution -------------------------------------------------------------------

func _on_swing(f: Fighter) -> void:
	var a := f.atk
	var el: String = f.look.element
	var big: bool = f.atk_id in ["z", "x", "c", "v", "heavy", "l3"]
	if el == "earth" and big:
		fx.rocks(f.position + f.forward() * 1.1, 24 if f.atk_id in ["heavy", "v"] else 16, 1.35 if f.atk_id == "heavy" else 1.0)
		add_trauma(0.4 if f.atk_id == "heavy" else 0.25)
	elif el == "light" and a.type == "melee":
		var tip := f.model.blade_tip.global_position
		fx.flash(tip, Color("#fff6c8"), 0.26 if big else 0.18, 0.14, 0.7)
		fx.sparks(tip, Color("#fff2b0"), 18 if big else 8, 4.0)
	match a.type:
		"projectile": _fire(f, a)
		"strike": _strike(f, a, f.atk_power)
		"buff": _buff(f, a)
		"blink": _blink(f, a)
		_: _melee(f, a)

func _active_melee_contact(f: Fighter) -> void:
	_melee(f, f.atk)

func _melee(f: Fighter, a: Dictionary) -> void:
	if not f.active_melee():
		return
	var contact_key := "%d:%d" % [f.id, f.swing_serial]
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
			_melee_hits[contact_key] = landed
			var other_key := "%d:%d" % [d.id, d.swing_serial]
			var other_landed: Dictionary = _melee_hits.get(other_key, {})
			other_landed[f.id] = true
			_melee_hits[other_key] = other_landed
			_clash(f, d, f.position + dir * minf(dist * 0.5, 0.8) + Vector3(0, 1.15, 0))
			return
		if dist - d.radius + 0.35 > float(a.reach) or dy > MELEE_HEIGHT_TOLERANCE:
			continue
		# Record contact BEFORE hit handling (which can trigger counters/KO).
		landed[d.id] = true
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

func _spawn_projectile(shooter, a: Dictionary, power: float, pos: Vector3, vel: Vector3, color: Color, target) -> void:
	var node := MeshInstance3D.new()
	var size: float = float(a.size)
	if a.style == "arrow":
		var b := BoxMesh.new(); b.size = Vector3(0.02, 0.02, 0.7) * size; node.mesh = b
	else:
		var s := SphereMesh.new(); s.radius = 0.14 * size; s.height = 0.28 * size; node.mesh = s
	node.material_override = Fx.unlit(color, 1.0, true)
	add_child(node)
	node.global_position = pos
	if vel.length() > 0.01: node.look_at(pos + vel, Vector3.UP)
	_projectiles.append({"id": _next_id, "node": node, "vel": vel, "life": 2.2, "shooter": shooter, "team": shooter.team,
		"atk": a, "power": power, "pierce": bool(a.pierce), "hit": {}, "target": target, "color": color, "size": size})
	_next_id += 1

## Closest point on projectile travel segment, including both end points.
func _swept_projectile_point(target: Vector3, a: Vector3, b: Vector3) -> Vector3:
	var travel := b - a
	var length_sq := travel.length_squared()
	if length_sq < 0.000001:
		return a
	var along := clampf((target - a).dot(travel) / length_sq, 0.0, 1.0)
	return a + travel * along

func _update_projectiles(dt: float) -> void:
	for p in _projectiles.duplicate():
		var node: MeshInstance3D = p.node
		var old_pos: Vector3 = node.global_position
		node.global_position += p.vel * dt
		p.life -= dt
		var done := false
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
		if p.life <= 0 or gp.y < 0.05 or Vector2(gp.x, gp.z).length() > 16: done = true
		if done:
			node.queue_free()
			_projectiles.erase(p)

## Area attack(s) at the target (or around the caster) after a telegraphed delay.
func _strike(f: Fighter, a: Dictionary, power: float) -> void:
	var rnd := _round
	var color := Color(f.look.glow)
	var one := func(i: int, self_ref: Callable) -> void:
		if rnd != _round or f.is_down(): return
		var src = f if a.at == "self" or f.opponent == null else f.opponent
		var center: Vector3 = src.position; center.y = 0
		var wait: float = float(a.delay) if i == 0 else float(a.interval)
		var mark := {"target": f.opponent, "land": _time + wait, "id": _next_id}
		_next_id += 1
		_strike_marks.append(mark)
		fx.telegraph(center, color, float(a.radius), wait)
		later(wait, func():
			_strike_marks.erase(mark)
			if rnd != _round: return
			var at: Vector3 = Vector3(f.position.x, 0, f.position.z) if a.at == "self" else center
			_impact(a, at, color, float(a.radius))
			for d in enemies_of(f):
				var to: Vector3 = d.position - at; to.y = 0
				if to.length() <= float(a.radius) + d.radius * 0.5 and not d.airborne():
					var dir: Vector3 = to.normalized() if to.length() > 0.05 else (d.position - f.position).normalized()
					apply_hit(f, d, a, power, d.chest(), dir, true)
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
		"spin":
			fx.ring(g + Vector3(0, 1.0, 0), color, radius, 0.2, 0.9)
		_:
			fx.sparks(pos, color, 14, 5.0)

func _buff(f: Fighter, a: Dictionary) -> void:
	var pvp: bool = cfg.mode != "survival"
	match a.mode:
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
	var result := d.receive_hit(attacker, a, power)
	var glow := Color(attacker.look.glow) if attacker is Fighter else Color.WHITE
	var heavy: bool = bool(a.get("heavy", false)) or String(a.get("id", "")) == "l3"
	var shield_pos := d.model.shield_node.global_position if d.model.shield_node else hit_pos
	match result:
		"hit", "crit", "ko":
			var crit := d.last_crit
			fx.sparks(hit_pos, glow, 30 if heavy else 18, 8.0 if heavy else 6.0, dir)
			fx.flash(hit_pos, glow, 0.45 if heavy else 0.3, 0.14, 0.8)
			if a.heavy: fx.ring(hit_pos, glow, 2.2, 0.35, 0.9)
			fx.number(hit_pos + Vector3(0, 0.5, 0), "%d%s" % [int(d.last_damage), "!" if crit else ""], Color("#ffb347") if crit else Color.WHITE, 1.5 if crit else 1.0)
			if attacker is Fighter and attacker.lifesteal > 0: attacker.heal(d.last_damage * attacker.lifesteal)
			if attacker is Fighter and attacker.look.element == "earth": fx.rocks(d.position, 12 if heavy else 6, 0.9 if heavy else 0.6)
			add_trauma(0.5 if a.heavy else 0.3 if heavy else 0.18)
			hit_stop(0.11 if a.heavy else 0.07 if heavy else 0.045)
		"blocked":
			if attacker is Fighter: attacker.add_guard_fatigue()
			fx.sparks(shield_pos, Color("#ffd27a"), 16, 5.0, -dir + Vector3(0, 0.3, 0))
			fx.number(shield_pos + Vector3(0, 0.4, 0), "BLOCK", Color("#c9d3e6"), 0.7)
			add_trauma(0.14); hit_stop(0.04)
		"parry":
			if attacker is Fighter: attacker.add_guard_fatigue()
			# Parry delays attacks with hit-stop, not a full stun.
			fx.sparks(shield_pos, Color("#aee9ff"), 40, 9.0)
			fx.ring(shield_pos, Color("#b3f2ff"), 1.6, 0.35, 0.9)
			fx.number(shield_pos + Vector3(0, 0.5, 0), "PARRY!", Color("#8fe6ff"), 1.4)
			add_trauma(0.4); hit_stop(0.35)
		"counter":
			fx.number(d.chest() + Vector3(0, 0.6, 0), "COUNTER!", Color("#ff9aa8"), 1.4)
			if attacker:
				var counter: Dictionary = d.attacks.heavy.duplicate()
				counter.dmg = 180; counter.heavy = true; counter.stun = 0.8
				apply_hit(d, attacker, counter, d.dmg_mult, attacker.chest(), -dir, false)
		"guard_break":
			fx.sparks(hit_pos, Color("#ffb347"), 40, 9.0)
			fx.number(hit_pos + Vector3(0, 0.55, 0), "GUARD BREAK", Color("#ff8a50"), 1.2)
			add_trauma(0.55); hit_stop(0.12)
		"warded":
			fx.number(hit_pos + Vector3(0, 0.5, 0), "ABSORBED", Color("#8fe6ff"), 0.8)
		"miss":
			fx.number(hit_pos + Vector3(0, 0.5, 0), "MISS", Color("#c9d3e6"), 0.8)

func _clash(a: Fighter, b: Fighter, pos: Vector3) -> void:
	a.clash_recoil(); b.clash_recoil()
	fx.sparks(pos, Color("#fff2c0"), 50, 10.0)
	fx.ring(pos, Color("#ffe699"), 3.0, 0.45, 0.9)
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
	if cfg.mode == "duel":
		if round_over: return
		round_over = true
		var winner: Fighter = fighters.filter(func(x): return x != f)[0]
		for x in fighters: x.brain = null
		add_trauma(0.8); hit_stop(0.9)
		later(0.4, func():
			winner.win()
			var spectator_mode: bool = bool(cfg.get("spectator", false))
			var won: bool = winner.owner_peer == cfg.local_peer
			var result_text: String = ("%s WINS!" % winner.look.name) if spectator_mode else ("VICTORY" if won else "DEFEAT")
			var result_color: Color = Color("#ffe08a") if spectator_mode or won else Color("#ff7b7b")
			ui_event.emit({"type": "over", "text": result_text, "sub": "Press R or click Rematch", "color": result_color})
			can_restart = true)
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

# --- camera --------------------------------------------------------------------------------

func _update_camera(dt: float) -> void:
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

# --- HUD feed ------------------------------------------------------------------------------

func hud() -> Dictionary:
	# The spectator has no local fighter; show CPU A/CPU B in the two HUD bars.
	var me: Fighter = local if local else (fighters[0] if not fighters.is_empty() else null)
	var info := func(f: Fighter) -> Dictionary:
		return {"id": Data.character(f.char_index).id, "name": f.look.name, "hp": f.hp, "max_hp": f.max_hp, "guard": f.guard, "max_guard": f.max_guard, "down": f.is_down(), "glow": f.look.glow, "fatigue": f.guard_fatigue}
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
		"can_restart": can_restart,
	}
