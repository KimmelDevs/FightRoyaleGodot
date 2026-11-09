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
# FRG12B - predicted projectile defense and melee interception
var _projectile_dodge_wait := -1.0
var _projectile_dodge_dir := Vector3.ZERO
# FRG12A - deliberate spacing and cooldown-aware neutral AI
var _orbit_sign := 1.0
var _orbit_timer := 0.0
var _close_pressure_timer := 0.0
# FRG12C - grounded whiff punishment, short bait and anti-stalling
var _seen_recovery_serial := -1
var _last_self_attack_serial := -1
var _last_enemy_attack_serial := -1
var _punish_t := 0.0
var _bait_t := 0.0
var _bait_cd := 2.4
var _idle_standoff_t := 0.0
var _engage_t := 0.0

func _init(match_ref, level: int) -> void:
	threats = match_ref
	p = PRESETS[clampi(level, 0, PRESETS.size() - 1)]

static func _r(a: float, b: float) -> float: return a + randf() * (b - a)

func think(f: Fighter, dt: float) -> void:
	var o = f.opponent
	if o == null or o.is_down(): return
	if o is Fighter: _react(f, o)
	_dodge(f)
	# Resolve projectile dodge at the predicted interception time.
	if _projectile_dodge_wait >= 0.0:
		_projectile_dodge_wait -= dt
		if _projectile_dodge_wait < 0.0:
			f.in_dodge = _projectile_dodge_dir
	_analyze_openings(f, o, dt)
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
	# FRG12B - predict the closest approach to the fighter, NOT simply the
	# projectile's distance from the fighter at the current frame.  React only
	# when a projectile is actually on a collision course.
	for pr in threats.projectile_threats():
		if pr.target != f or _seen.has(pr.id):
			continue
		var velocity: Vector3 = pr.vel
		var speed_squared: float = velocity.length_squared()
		if speed_squared < 0.01:
			continue
		var toward: Vector3 = f.chest() - pr.pos
		var eta: float = toward.dot(velocity) / speed_squared
		if eta <= 0.0 or eta > 1.25:
			continue
		var closest: Vector3 = pr.pos + velocity * eta
		var danger_radius: float = f.radius + 0.30 * float(pr.get("size", 1.0)) + 0.12
		if closest.distance_to(f.chest()) > danger_radius:
			continue
		# Wait for a safe opening: hitstun, attacks, and recovery have priority
		# over newly planned reactions. Never cancel a scheduled defense with
		# an unrelated second projectile.
		if f.state != Fighter.S.IDLE and f.state != Fighter.S.BLOCK:
			continue
		if _block_wait >= 0.0 or _block_hold > 0.0 or _projectile_dodge_wait >= 0.0:
			continue
		var reaction: float = _r(float(p.react[0]), float(p.react[1]))
		if eta <= reaction + 0.02:
			_seen[pr.id] = true
			continue  # Too late for this CPU's reaction time.
		var incoming_horizontal := Vector3(-velocity.x, 0.0, -velocity.z)
		var facing_ok: bool = incoming_horizontal.length_squared() <= 0.01 or f.forward().dot(incoming_horizontal.normalized()) >= 0.20
		# Skilled melee AI can intentionally time a LIGHT attack to intercept a
		# non-explosive projectile. The match validates the actual active-frame
		# collision. This is not a guaranteed or instantly triggered defense.
		if facing_ok and _try_projectile_clash(f, pr, eta, reaction):
			_seen[pr.id] = true
			continue
		var can_guard: bool = facing_ok and f.on_ground and f.guard > 8.0 and f.state == Fighter.S.IDLE
		var can_dodge: bool = f.on_ground and f._dodge_cd <= 0.0 and f.state == Fighter.S.IDLE
		if can_guard and eta > reaction + 0.06 and randf() < float(p.parry):
			var start: float = maxf(reaction, eta - minf(f.parry_window * 0.60, 0.095))
			if start < eta - 0.02:
				_schedule(start, maxf(0.19, eta - start + 0.10))
				_seen[pr.id] = true
				continue
		if can_dodge and randf() < float(p.jump):
			var sideways := Vector3(-velocity.z, 0.0, velocity.x).normalized()
			if sideways.length_squared() < 0.01:
				sideways = Vector3(-f.forward().z, 0.0, f.forward().x)
			# Dodge inward when near the edge instead of rolling out of bounds.
			var plus: Vector3 = f.position + sideways * 1.8
			var minus: Vector3 = f.position - sideways * 1.8
			_projectile_dodge_dir = sideways if plus.length_squared() < minus.length_squared() else -sideways
			_projectile_dodge_wait = maxf(reaction, eta - 0.18)
			_seen[pr.id] = true
			continue
		if can_guard and randf() < float(p.block):
			_schedule(reaction, eta - reaction + 0.25)
			_seen[pr.id] = true
			continue
		if f.on_ground and eta > reaction + 0.24 and randf() < float(p.jump):
			_jump_wait = maxf(reaction, eta - 0.34)
		_seen[pr.id] = true
	# Keep the existing warning-marker/area-strike evasions.
	for m in threats.strike_threats():
		if m.target != f or _seen.has(m.id):
			continue
		_seen[m.id] = true
		var eta: float = m.land - threats.now()
		if randf() < 0.3 + float(p.jump):
			_side_t = clampf(eta, 0.3, 0.8)
			_side_sign = 1.0 if randf() < 0.5 else -1.0
		elif randf() < 0.5:
			_jump_wait = maxf(eta - 0.3, 0.0)
	if _seen.size() > 300:
		_seen.clear()

func _try_projectile_clash(f: Fighter, pr: Dictionary, eta: float, reaction: float) -> bool:
	if f.kit in RANGED or f.state != Fighter.S.IDLE or not f.on_ground:
		return false
	if f.atk_lock > 0.0 or _hold > 0.0 or not _queue.is_empty():
		return false
	if bool(pr.get("pierce", false)):
		return false
	var style: String = String(pr.get("style", ""))
	if style in ["explosion", "bomb", "meteor", "grenade", "rocket"]:
		return false
	var light: Dictionary = f.attacks.get("l1", {})
	if String(light.get("type", "")) != "melee":
		return false
	var wind: float = float(light.get("wind", 0.20)) * f.attack_time_multiplier()
	if eta < reaction + wind + 0.12:
		return false
	# More accurate and frequent interception on Hard/Master than on Easy.
	var chance: float = 0.36 if float(p.think) < 0.8 else 0.20 if float(p.think) <= 1.0 else 0.08 if float(p.think) < 1.5 else 0.0
	if randf() >= chance:
		return false
	var wait_time: float = maxf(reaction, eta - wind - 0.095)
	_queue.append([wait_time, 0.06])
	return true

func _analyze_openings(f: Fighter, o: Fighter, dt: float) -> void:
	# Timers are real seconds, not frame counts, and never grant an instant hit.
	_punish_t = maxf(_punish_t - dt, 0.0)
	_bait_t = maxf(_bait_t - dt, 0.0)
	_bait_cd = maxf(_bait_cd - dt, 0.0)
	_engage_t = maxf(_engage_t - dt, 0.0)
	var offset: Vector3 = o.position - f.position
	offset.y = 0.0
	var distance: float = offset.length()
	# Read an attack ONCE, after its actual active window. A blocked/parried
	# hit or melee clash is a contact, NOT a whiff. Missing the opponent must
	# leave the attacker in recovery for the CPU to capitalize.
	if o.state == Fighter.S.ATTACK and o.atk_phase == 2 and String(o.atk.get("type", "")) == "melee":
		if o.swing_serial != _seen_recovery_serial:
			_seen_recovery_serial = o.swing_serial
			if o.last_melee_contact_serial != o.swing_serial and distance < 4.4:
				# Hard/Master see openings more consistently; lower CPUs are less
				# likely to notice a miss in time. Recovery still must be reachable.
				var read_chance: float = 0.86 if float(p.think) <= 0.75 else 0.60 if float(p.think) <= 1.0 else 0.26 if float(p.think) < 1.5 else 0.10
				if randf() < read_chance:
					_punish_t = 0.78 if float(p.think) <= 0.75 else 0.58
					_bait_t = 0.0
					_think_cd = minf(_think_cd, 0.035)
	# Never enter prolonged circling when neither fighter has committed.
	var acted: bool = f.swing_serial != _last_self_attack_serial or o.swing_serial != _last_enemy_attack_serial
	_last_self_attack_serial = f.swing_serial
	_last_enemy_attack_serial = o.swing_serial
	if acted or f.state != Fighter.S.IDLE or o.state != Fighter.S.IDLE:
		_idle_standoff_t = 0.0
	else:
		_idle_standoff_t += dt
	var standoff_limit: float = 3.2 if float(p.think) <= 1.0 else 4.7
	if _idle_standoff_t > standoff_limit:
		_engage_t = 1.6
		_idle_standoff_t = 0.0
		_bait_t = 0.0
	# Bait is a short footwork hesitation, never a fake damaging attack.
	# Keep it rare and disabled for Easy/Normal to avoid passive AI duels.
	if float(p.think) <= 1.0 and _bait_cd <= 0.0:
		_bait_cd = _r(3.2, 5.2)
		var reach: float = _preferred_range(f)
		var can_bait: bool = not (f.kit in RANGED) and not (o.kit in RANGED) and f.state == Fighter.S.IDLE and o.state == Fighter.S.IDLE and distance >= reach and distance < reach + 1.25 and _engage_t <= 0.0 and _punish_t <= 0.0
		if can_bait and randf() < 0.36:
			_bait_t = _r(0.28, 0.48)
	if o.state != Fighter.S.IDLE or f.state != Fighter.S.IDLE:
		_bait_t = 0.0

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
	# FRG12C - short proactive adjustments, always subject to edge steering.
	if _punish_t > 0.0 and not ranged and dist > preferred - 0.12:
		desired = toward * 1.0 + sideways * _orbit_sign * 0.10
		f.in_sprint = dist > 3.0
	elif _engage_t > 0.0 and dist > (2.8 if ranged else preferred - 0.1):
		desired = toward * 1.0 + sideways * _orbit_sign * 0.10
		f.in_sprint = not ranged and dist > 3.0
	elif _bait_t > 0.0 and not ranged:
		desired = -toward * 0.32 + sideways * _orbit_sign * 0.62
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
	# A bait delays offense briefly, but an actual missed attack cancels it.
	if _bait_t > 0.0 and _punish_t <= 0.0:
		return
	# Punish a genuine miss with a prompt, usually light, melee response.
	if _punish_t > 0.0 and not ranged and dist <= reach:
		_think_cd = minf(_think_cd, 0.035)
	# Try an off-cooldown skill only if the position and its action type fit.
	_skill_cd -= dt
	if _skill_cd <= 0.0 and _punish_t <= 0.0:
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
	if _punish_t > 0.0 and not ranged:
		heavy_chance = 0.04  # Fast light punishes are safer than charging.
	# Heavy swings are poor choices against a distant or mobile target.
	if not ranged and dist > float(light.get("reach", 1.8)) - 0.1:
		heavy_chance *= 0.6
	var spending_punish: bool = _punish_t > 0.0 and not ranged
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
	if spending_punish:
		_punish_t = 0.0

