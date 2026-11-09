class_name AiBrain
extends RefCounted
## CPU opponent (port of the web ai.ts). Presses the same virtual buttons a player would, with
## human-ish reaction times: reacts once per enemy swing / projectile / ground marker (block,
## parry, jump, sidestep), keeps its range (ranged kits kite), and picks attacks and skills.

const LEVELS := ["Easy", "Normal", "Hard", "Master"]
const PRESETS := [
	{"block": 0.2, "parry": 0.0, "jump": 0.1, "react": [0.3, 0.5], "think": 1.8, "skill": [3.5, 6.0], "combo": 2},
	{"block": 0.38, "parry": 0.06, "jump": 0.22, "react": [0.18, 0.34], "think": 1.25, "skill": [2.0, 3.8], "combo": 3},
	{"block": 0.5, "parry": 0.14, "jump": 0.3, "react": [0.12, 0.26], "think": 1.0, "skill": [1.2, 2.6], "combo": 4},
	{"block": 0.65, "parry": 0.3, "jump": 0.45, "react": [0.08, 0.16], "think": 0.7, "skill": [0.8, 1.6], "combo": 5},
]
const RANGED := ["mage", "bow"]

var p: Dictionary
var threats  ## match: projectiles(), strikes(), now()
var _queue: Array = []   # [wait, hold]
var _hold := 0.0
var _block_wait := -1.0
var _block_dur := 0.0
var _block_hold := 0.0
var _jump_wait := -1.0
var _side_t := 0.0
var _side_sign := 1.0
var _strafe_t := 0.0
var _think_cd := 1.0
var _skill_cd := 2.0
var _seen_swing := -1
var _seen_charge := false
var _seen := {}
# FRG12A - deliberate spacing and cooldown-aware neutral AI
var _orbit_sign := 1.0
var _orbit_timer := 0.0
var _close_pressure_timer := 0.0

func _init(match_ref, level: int) -> void:
	threats = match_ref
	p = PRESETS[clampi(level, 0, PRESETS.size() - 1)]

static func _r(a: float, b: float) -> float: return a + randf() * (b - a)

func think(f: Fighter, dt: float) -> void:
	var o = f.opponent
	if o == null or o.is_down(): return
	if o is Fighter: _react(f, o)
	_dodge(f)
	_position(f, o, dt)
	_offense(f, o, dt)
	if _jump_wait >= 0.0:
		_jump_wait -= dt
		if _jump_wait < 0.0: f.in_jump = true
	if _block_wait >= 0.0:
		_block_wait -= dt
		if _block_wait < 0.0: _block_hold = _block_dur
	if _block_hold > 0.0:
		_block_hold -= dt
		f.in_block = true
		_queue.clear(); _hold = 0.0
		return
	if _hold > 0.0:
		_hold -= dt
		f.in_attack = _hold > 0.0
	elif not _queue.is_empty():
		_queue[0][0] -= dt
		if _queue[0][0] <= 0.0:
			_hold = _queue[0][1]; _queue.pop_front(); f.in_attack = true

func _schedule(wait: float, dur: float) -> void:
	if _block_hold > 0.0 or _block_wait >= 0.0: return
	_block_wait = wait; _block_dur = dur

func _react(f: Fighter, o: Fighter) -> void:
	if o.state == Fighter.S.ATTACK and o.atk_phase == 0 and o.atk.type == "melee" and o.swing_serial != _seen_swing:
		_seen_swing = o.swing_serial
		if f.state == Fighter.S.HITSTUN or f.state == Fighter.S.STAGGER: return
		var tth: float = float(o.atk.wind) - o.state_t
		var r := randf()
		var bc: float = p.block * (0.75 if o.atk.heavy else 1.0)
		if r < p.parry: _schedule(maxf(tth - 0.07, 0.0), 0.3)
		elif r < p.parry + bc: _schedule(_r(p.react[0], p.react[1]) * 0.6, tth + 0.45)
		elif r < p.parry + bc + 0.15: _try_skill(f, "z", true)
	var charging := o.state == Fighter.S.CHARGE
	if charging and not _seen_charge:
		_seen_charge = true
		if randf() < 0.45: _schedule(_r(p.react[0], p.react[1]), 1.4)
	elif not charging: _seen_charge = false

func _dodge(f: Fighter) -> void:
	for pr in threats.projectile_threats():
		if pr.target != f or _seen.has(pr.id): continue
		_seen[pr.id] = true
		var eta: float = f.chest().distance_to(pr.pos) / maxf(pr.vel.length(), 0.1)
		var r := randf()
		if r < p.jump and f.on_ground: _jump_wait = maxf(eta - 0.28, 0.0)
		elif r < p.jump + p.block: _schedule(minf(maxf(eta - 0.2, 0.0), p.react[1]), eta + 0.2)
	for m in threats.strike_threats():
		if m.target != f or _seen.has(m.id): continue
		_seen[m.id] = true
		var eta: float = m.land - threats.now()
		if randf() < 0.3 + p.jump:
			_side_t = clampf(eta, 0.3, 0.8); _side_sign = 1.0 if randf() < 0.5 else -1.0
		elif randf() < 0.5: _jump_wait = maxf(eta - 0.3, 0.0)
	if _seen.size() > 300: _seen.clear()

func _position(f: Fighter, o, dt: float) -> void:
	# Every CPU issues explicit movement intents; Fighter._move handles the
	# acceleration, footwork and arena clamp. Keep behavior independent of FPS.
	var to_enemy: Vector3 = o.position - f.position
	to_enemy.y = 0.0
	var dist: float = to_enemy.length()
	if dist <= 0.01:
		return
	var toward: Vector3 = to_enemy / dist
	var sideways := Vector3(-toward.z, 0.0, toward.x)
	_orbit_timer -= dt
	if _orbit_timer <= 0.0:
		_orbit_timer = _r(0.65, 1.6)
		_orbit_sign = -1.0 if randf() < 0.5 else 1.0
	# Ground-targeted strike evasions take priority over normal spacing.
	if _side_t > 0.0:
		_side_t = maxf(_side_t - dt, 0.0)
		f.in_move = sideways * _side_sign
		return
	var desired := Vector3.ZERO
	var ranged: bool = f.kit in RANGED
	var preferred: float = _preferred_range(f)
	if ranged:
		# Ranged fighters kite only when threatened at close range; otherwise
		# they actively re-enter their usable firing zone instead of fleeing forever.
		if dist < preferred - 0.9:
			desired = -toward * 0.85 + sideways * _orbit_sign * 0.5
		elif dist > preferred + 1.0:
			desired = toward * 0.95 + sideways * _orbit_sign * 0.2
		else:
			desired = sideways * _orbit_sign * 0.48
	else:
		# Melee fighters approach to actual light-attack reach rather than
		# stopping at a global distance that can be wrong for their weapon.
		if dist > preferred + 0.18:
			desired = toward
		elif dist < 1.08:
			desired = sideways * _orbit_sign * 0.75 - toward * 0.12
		else:
			desired = sideways * _orbit_sign * 0.32
		# Run to a distant opponent, especially a ranged fighter.
		f.in_sprint = dist > 4.2 and f.state == Fighter.S.IDLE
	# Do not retreat forever along the ring. Both classes must steer inward
	# at the boundary, even when the enemy is pushing from the center.
	var from_center := Vector3(f.position.x, 0.0, f.position.z)
	var edge_dist: float = from_center.length()
	var limit: float = maxf(f.arena_radius - 1.15, 0.5)
	if edge_dist > limit:
		var outward: Vector3 = from_center / maxf(edge_dist, 0.001)
		var edge_pressure: float = clampf((edge_dist - limit) / 0.85, 0.0, 1.0)
		if desired.dot(outward) > 0.0:
			desired -= outward * desired.dot(outward)
		desired -= outward * (0.25 + 0.9 * edge_pressure)
	if desired.length_squared() > 0.0001:
		f.in_move = desired.normalized()

func _preferred_range(f: Fighter) -> float:
	if f.kit in RANGED:
		return 5.0 if f.kit == "mage" else 5.5
	var light: Dictionary = f.attacks.get("l1", {})
	return clampf(float(light.get("reach", 1.8)) - 0.15, 1.2, 2.4)

func _usable_skill(f: Fighter, o: Fighter, key: String, dist: float) -> bool:
	if float(f.cooldowns.get(key, 999.0)) > 0.0:
		return false
	var a: Dictionary = f.attacks.get(key, {})
	if a.is_empty():
		return false
	match String(a.get("type", "")):
		"melee":
			return dist <= float(a.get("reach", 2.0)) + 0.65
		"projectile":
			return dist >= 1.1 and dist < 10.5
		"strike":
			if String(a.get("at", "target")) == "self":
				return dist <= float(a.get("radius", 1.5)) + 0.6
			return dist <= 10.5
		"blink":
			var mode: String = String(a.get("mode", ""))
			return (dist > 1.6 and dist < 6.0) if mode == "behind" else dist < 2.6
		"buff":
			var mode: String = String(a.get("mode", ""))
			if mode == "counter":
				return dist < 3.0 and o.state in [Fighter.S.ATTACK, Fighter.S.CHARGE]
			# Defensive ward: do not waste when already protected or healthy.
			return f.ward_t <= 0.0 and (f.hp < f.max_hp * 0.72 or f.guard < f.max_guard * 0.45)
	return false

func _try_skill(f: Fighter, key: String, force := false) -> bool:
	if f.cooldowns[key] > 0.0: return false
	if not force and randf() > 0.5: return false
	f.in_skill = key
	return true

func _offense(f: Fighter, o, dt: float) -> void:
	if f.state != Fighter.S.IDLE or not _queue.is_empty() or _hold > 0.0 or _block_hold > 0.0 or _block_wait >= 0.0:
		return
	var horizontal: Vector3 = o.position - f.position
	horizontal.y = 0.0
	var dist: float = horizontal.length()
	var ranged: bool = f.kit in RANGED
	var light: Dictionary = f.attacks.get("l1", {})
	var reach: float = 10.0 if ranged else float(light.get("reach", 1.8)) + 0.35
	# Try an off-cooldown skill only if the position and its action type fit.
	_skill_cd -= dt
	if _skill_cd <= 0.0:
		_skill_cd = _r(float(p.skill[0]), float(p.skill[1]))
		var keys := ["c", "x", "z"]
		keys.shuffle()
		if randf() < (0.65 if p.think <= 0.75 else 0.5):
			for key in keys:
				if _usable_skill(f, o, key, dist) and _try_skill(f, key, true):
					_queue.clear()
					return
	# Don't throw away attacks outside their actual reach.
	if dist > reach:
		return
	var vulnerable := o.state in [Fighter.S.HITSTUN, Fighter.S.STAGGER]
	if vulnerable:
		_think_cd = minf(_think_cd, 0.12)
	_think_cd -= dt
	if _think_cd > 0.0:
		return
	_think_cd = (_r(0.48, 0.95) if f.kit in ["assassin", "knuckles", "kicks"] else _r(0.65, 1.3)) * float(p.think)
	var heavy_chance := 0.17 if ranged else 0.23
	if o.state == Fighter.S.BLOCK:
		heavy_chance = 0.52
	elif vulnerable:
		heavy_chance = 0.41
	# Heavy swings are poor choices against a distant or mobile target.
	if not ranged and dist > float(light.get("reach", 1.8)) - 0.1:
		heavy_chance *= 0.6
	if randf() < heavy_chance:
		_queue.append([0.0, Fighter.HOLD_T + _r(0.26, 0.55)])
	else:
		var chain_count := 0
		for name in f.attacks:
			if String(name).begins_with("l") and String(name).length() == 2:
				chain_count += 1
		var max_hits := maxi(1, mini(int(p.combo), chain_count))
		var hits := randi_range(1, max_hits)
		for i in hits:
			_queue.append([0.0 if i == 0 else 0.13, 0.06])

