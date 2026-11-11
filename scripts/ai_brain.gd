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
const RANGED := ["mage", "bow", "bomb"] # FRG19S
# FRG13A - fighter-specific AI personality profiles
const PERSONALITY_FILE := "res://data/ai_personalities.json"
# FRG13B - tactical identity (guard reset, pressure and skill bias)
const TACTICS_FILE := "res://data/ai_tactics_13b.json"
# FRG13C - adaptive opponent reading (observed patterns only)
# FRG13C - learn only actions the opponent visibly commits to
const ADAPTATION_FILE := "res://data/ai_adaptation_13c.json"
var _difficulty_level: int = 0
var _read_settings: Dictionary = {}
var _enemy_last_read_swing: int = -1
var _enemy_light_reads: int = 0
var _enemy_heavy_reads: int = 0
var _enemy_block_memory: float = 0.0
var _enemy_read_decay_timer: float = 9.0
var _personality: Dictionary = {}
var _personality_loaded := false
var _tactics: Dictionary = {}
var _guard_reset_t := 0.0
var _guard_reset_cd := 0.0

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
# FRG12D - master tactical skill choice and interruption-safe inputs
var _tactical_tries := 0

func _init(match_ref, level: int) -> void:
	threats = match_ref
	_difficulty_level = clampi(level, 0, PRESETS.size() - 1)
	p = PRESETS[_difficulty_level].duplicate(true)
	_load_read_settings()

static func _r(a: float, b: float) -> float: return a + randf() * (b - a)

func _load_fighter_personality(f: Fighter) -> void:
	# Resolve the actual roster ID, not a possibly reused VRM file name.
	_personality_loaded = true
	var fighter_id: String = String(Data.character(f.char_index).get("id", ""))
	if not FileAccess.file_exists(PERSONALITY_FILE):
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(PERSONALITY_FILE))
	if not (parsed is Dictionary):
		push_warning("FRG13A: malformed personality JSON, using default CPU behavior")
		return
	var archetypes: Dictionary = parsed.get("archetypes", {})
	var fighters: Dictionary = parsed.get("fighters", {})
	var specific: Dictionary = fighters.get(fighter_id, {})
	var archetype: String = String(specific.get("archetype", f.kit))
	_personality = archetypes.get(archetype, {}).duplicate(true)
	_personality.merge(specific, true)
	# FRG13B - load per-fighter tactical preferences safely; no file is required
	if FileAccess.file_exists(TACTICS_FILE):
		var tactics_data: Variant = JSON.parse_string(FileAccess.get_file_as_string(TACTICS_FILE))
		if tactics_data is Dictionary:
			var common: Dictionary = tactics_data.get("archetypes", {})
			var unique: Dictionary = tactics_data.get("fighters", {})
			_tactics = common.get(archetype, {}).duplicate(true)
			_tactics.merge(unique.get(fighter_id, {}), true)
		else:
			push_warning("FRG13B: invalid tactical JSON; defaults will be used")
	# Apply personal tendencies as *bounded multipliers* to the difficulty
	# preset. Easy stays Easy and Master stays Master.
	p["block"] = clampf(float(p["block"]) * float(_personality.get("block_scale", 1.0)), 0.0, 0.88)
	p["parry"] = clampf(float(p["parry"]) * float(_personality.get("parry_scale", 1.0)), 0.0, 0.52)
	p["jump"] = clampf(float(p["jump"]) * float(_personality.get("dodge_scale", 1.0)), 0.0, 0.70)
	p["think"] = clampf(float(p["think"]) / maxf(float(_personality.get("attack_pace", 1.0)), 0.5), 0.36, 2.3)
	var skill_pace: float = maxf(float(_personality.get("skill_pace", 1.0)), 0.5)
	var timings: Array = p["skill"]
	p["skill"] = [maxf(float(timings[0]) / skill_pace, 0.4), maxf(float(timings[1]) / skill_pace, 0.7)]

func think(f: Fighter, dt: float) -> void:
	var o = f.opponent
	if o == null or o.is_down(): return
	if not _personality_loaded:
		_load_fighter_personality(f)
	# Count real elapsed time while a fighter is attacking, blocking or recovering.
	_skill_cd = maxf(_skill_cd - dt, 0.0)
	# An interrupted windup must not resume an old combo, parry or delayed dodge.
	if f.state in [Fighter.S.HITSTUN, Fighter.S.STAGGER, Fighter.S.KO, Fighter.S.WIN]:
		_queue.clear()
		_hold = 0.0
		_block_wait = -1.0
		_block_hold = 0.0
		_jump_wait = -1.0
		_projectile_dodge_wait = -1.0
		_bait_t = 0.0
		_punish_t = 0.0
		return
	if o is Fighter: _react(f, o)
	_observe_opponent(f, o, dt)
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
		var bc: float = float(p.block) * (0.75 if o.atk.heavy else 1.0)
		var parry_read: float = clampf(float(p.parry) + _heavy_habit_parry_bonus(), 0.0, 0.52)
		if r < parry_read: _schedule(maxf(tth - 0.07, 0.0), 0.3)
		elif r < parry_read + bc: _schedule(_r(p.react[0], p.react[1]) * 0.6, tth + 0.45)
		elif r < parry_read + bc + 0.15: _try_skill(f, "z", true)
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
	# FRG13B - one brief guard recovery step, never a persistent retreat
	_guard_reset_t = maxf(_guard_reset_t - dt, 0.0)
	_guard_reset_cd = maxf(_guard_reset_cd - dt, 0.0)
	# Guard reset is brief and on cooldown. Don't retreat indefinitely or
	# interrupt an enemy attack, a whiff punish, or anti-stall engagement.
	var guard_threshold: float = clampf(float(_tactics.get("guard_reset_threshold", 0.18)), 0.06, 0.40)
	if _guard_reset_cd <= 0.0 and _guard_reset_t <= 0.0 and f.kit not in RANGED:
		if f.guard < f.max_guard * guard_threshold and f.state == Fighter.S.IDLE and o.state == Fighter.S.IDLE and _engage_t <= 0.0 and _punish_t <= 0.0:
			if distance < _preferred_range(f) + 0.75:
				_guard_reset_t = 0.38
				_guard_reset_cd = 4.0
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
	var orbit: float = clampf(float(_personality.get("orbit_scale", 1.0)), 0.4, 1.8)
	var approach: float = clampf(float(_personality.get("approach_scale", 1.0)), 0.6, 1.6)
	var retreat: float = clampf(float(_personality.get("retreat_scale", 1.0)), 0.5, 1.6)
	if ranged:
		# Ranged fighters kite only when threatened at close range; otherwise
		# they actively re-enter their usable firing zone instead of fleeing forever.
		if dist < preferred - 0.9:
			desired = -toward * (0.85 * retreat) + sideways * _orbit_sign * (0.5 * orbit)
		elif dist > preferred + 1.0:
			desired = toward * (0.95 * approach) + sideways * _orbit_sign * (0.2 * orbit)
		else:
			desired = sideways * _orbit_sign * (0.48 * orbit)
	else:
		# Melee fighters approach to actual light-attack reach rather than
		# stopping at a global distance that can be wrong for their weapon.
		if dist > preferred + 0.18:
			desired = toward * approach + sideways * _orbit_sign * (0.12 * orbit)
		elif dist < 1.08:
			desired = sideways * _orbit_sign * (0.75 * orbit) - toward * 0.12
		else:
			desired = sideways * _orbit_sign * (0.32 * orbit)
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
	# FRG13B - short guard-reset sidestep and controlled guard-break pressure
	# Both decisions still pass through the existing edge-avoidance code.
	if _guard_reset_t > 0.0 and not ranged and _punish_t <= 0.0 and _engage_t <= 0.0 and o.state == Fighter.S.IDLE:
		desired = sideways * (_orbit_sign * 0.70) - toward * 0.48
	elif not ranged and f.state == Fighter.S.IDLE and _punish_t <= 0.0:
		var pressure: float = clampf(float(_tactics.get("guard_pressure", 1.0)), 0.3, 1.6)
		var broken_guard: bool = o.guard < o.max_guard * 0.33 and o.state in [Fighter.S.IDLE, Fighter.S.BLOCK]
		if broken_guard and dist > preferred - 0.12 and dist < preferred + 1.9:
			desired = toward * pressure + sideways * (_orbit_sign * 0.08)
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
	var base: float = 0.0
	if f.kit in RANGED:
		base = 5.0 if f.kit == "mage" else 5.5
	else:
		var light: Dictionary = f.attacks.get("l1", {})
		base = clampf(float(light.get("reach", 1.8)) - 0.15, 1.2, 2.4)
	return base * clampf(float(_personality.get("range_scale", 1.0)), 0.75, 1.3)

func _usable_skill(f: Fighter, o: Fighter, key: String, dist: float) -> bool:
	if float(f.cooldowns.get(key, 999.0)) > 0.0:
		return false
	var a: Dictionary = f.attacks.get(key, {})
	if a.is_empty():
		return false
	match String(a.get("type", "")):
		"melee":
			return dist <= float(a.get("reach", 2.0)) + 0.65
		"projectile", "lob":
			return dist >= 1.1 and dist < 10.5
		"mine":
			return dist < 5.2 and f.bob_mine_charges > 0
		"barrel":
			return dist < 6.5
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

func _select_tactical_skill(f: Fighter, o: Fighter, dist: float) -> String:
	# Only choose *equipped* skills that can execute from current range.
	# Lower difficulties retain their original random skill choices.
	var best_key := ""
	var best_score := -999.0
	var enemy_open: bool = o.state in [Fighter.S.HITSTUN, Fighter.S.STAGGER]
	var enemy_attacking: bool = o.state in [Fighter.S.ATTACK, Fighter.S.CHARGE]
	for key in ["z", "x", "c"]:
		if not _usable_skill(f, o, key, dist):
			continue
		var ability: Dictionary = f.attacks.get(key, {})
		var kind: String = String(ability.get("type", ""))
		var score: float = 0.25 + randf_range(-0.10, 0.10)
		# FRG13B - character preference never overrides range/cooldown eligibility
		var preferred_skills: Dictionary = _tactics.get("skill_bias", {})
		score += clampf(float(preferred_skills.get(key, 0.0)), -0.3, 0.3)
		match kind:
			"melee":
				var reach: float = float(ability.get("reach", 2.0))
				score += 0.55 if dist <= reach else 0.10
				if enemy_open: score += 0.75
				if o.state == Fighter.S.BLOCK: score += 0.18
			"projectile", "lob":
				score += 0.55 if dist > 3.0 else 0.05
			"mine":
				score += 0.65 if dist < 3.4 else 0.30
			"barrel":
				score += 0.80 if dist < 4.0 else 0.20
				if enemy_open: score += 0.25
			"strike":
				var self_centered: bool = String(ability.get("at", "target")) == "self"
				score += (0.55 if dist < 2.8 else 0.10) if self_centered else 0.48
				if enemy_open: score += 0.30
			"blink":
				score += 0.75 if dist > 2.6 else 0.08
				if o.kit in RANGED: score += 0.20
			"buff":
				if String(ability.get("mode", "")) == "counter":
					score += 1.0 if enemy_attacking else -0.5
				else:
					var hp_fraction: float = f.hp / maxf(f.max_hp, 1.0)
					var guard_fraction: float = f.guard / maxf(f.max_guard, 1.0)
					score += 0.90 if hp_fraction < 0.45 or guard_fraction < 0.3 else 0.15
			_:
				continue
		# FRG13C - favor high-guard-damage melee skills only against a
		# repeatedly observed blocking habit, never bypassing eligibility.
		if _guard_habit() and kind == "melee" and o.state == Fighter.S.BLOCK:
			var guard_value: float = clampf(float(ability.get("guard", 0.0)) / 65.0, 0.0, 1.0)
			score += guard_value * clampf(float(_read_level().get("skill_guard_bias", 0.0)), 0.0, 0.3)
		if score > best_score:
			best_score = score
			best_key = key
	return best_key

func _try_skill(f: Fighter, key: String, force := false) -> bool:
	if float(f.cooldowns.get(key, 999.0)) > 0.0: return false
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
	# Do not spend an entire decision interval when no equipped skill fits.
	if _skill_cd <= 0.0 and _punish_t <= 0.0:
		var picked := ""
		if float(p.think) <= 1.0:
			# Hard/Master consider range, counters and punishable openings.
			picked = _select_tactical_skill(f, o, dist)
			if randf() > (0.82 if float(p.think) <= 0.75 else 0.63):
				picked = ""
		else:
			var keys := ["c", "x", "z"]
			keys.shuffle()
			if randf() < 0.50:
				for key in keys:
					if _usable_skill(f, o, key, dist):
						picked = key
						break
		if picked != "" and _try_skill(f, picked, true):
			_skill_cd = _r(float(p.skill[0]), float(p.skill[1]))
			_queue.clear()
			return
		# Retry occasionally, but not every frame.
		_skill_cd = 0.24 if float(p.think) <= 1.0 else 0.45
	# Don't throw away attacks outside their actual reach.
	if dist > reach:
		return
	var vulnerable: bool = o.state in [Fighter.S.HITSTUN, Fighter.S.STAGGER]
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
	heavy_chance = clampf(heavy_chance * float(_personality.get("heavy_scale", 1.0)), 0.03, 0.65)
	# FRG13C - moderately favor heavy pressure against persistent blockers.
	# Do not slow down immediate whiff punishments.
	if _punish_t <= 0.0 and not ranged and o.state == Fighter.S.BLOCK and _guard_habit():
		heavy_chance = clampf(heavy_chance + clampf(float(_read_level().get("charged_bias", 0.0)), 0.0, 0.16), 0.03, 0.68)
	# FRG13B - heavy strikes are more attractive against guard-starved foes.
	# Always leave genuine whiff punishes fast (from Update 12C).
	if _punish_t <= 0.0 and o.state == Fighter.S.BLOCK and o.guard < o.max_guard * 0.40:
		var break_bias: float = clampf(float(_tactics.get("guard_break_bias", 1.0)), 0.35, 1.6)
		heavy_chance = clampf(heavy_chance + 0.10 * break_bias, 0.03, 0.68)
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

func _load_read_settings() -> void:
	_read_settings = {
		"sample_min": 4,
		"max_read_events": 12,
		"decay_seconds": 9.0,
		"heavy_ratio_threshold": 0.60,
		"block_memory_threshold": 0.43,
		"difficulty": {
			"Hard": {"parry_bonus": 0.025, "charged_bias": 0.07, "skill_guard_bias": 0.12},
			"Master": {"parry_bonus": 0.060, "charged_bias": 0.12, "skill_guard_bias": 0.22},
		},
	}
	if not FileAccess.file_exists(ADAPTATION_FILE):
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(ADAPTATION_FILE))
	if parsed is Dictionary:
		_read_settings.merge(parsed, true)
	else:
		push_warning("FRG13C: malformed adaptation JSON; using built-in limits")

func _read_level() -> Dictionary:
	if _difficulty_level < 2:
		return {}
	var difficulty_data: Dictionary = _read_settings.get("difficulty", {})
	return difficulty_data.get("Master" if _difficulty_level >= 3 else "Hard", {})

func _observe_opponent(f: Fighter, o: Fighter, dt: float) -> void:
	# Each new melee swing is observed once, regardless of frame rate. No
	# future inputs, cooldown inspection, or hidden states are used.
	if o.state == Fighter.S.ATTACK and String(o.atk.get("type", "")) == "melee":
		if o.swing_serial != _enemy_last_read_swing:
			_enemy_last_read_swing = o.swing_serial
			if bool(o.atk.get("heavy", false)):
				_enemy_heavy_reads += 1
			else:
				_enemy_light_reads += 1
			var cap: int = clampi(int(_read_settings.get("max_read_events", 12)), 4, 24)
			if _enemy_heavy_reads + _enemy_light_reads > cap:
				# Decay the larger bucket so old habits gradually lose weight.
				if _enemy_heavy_reads >= _enemy_light_reads:
					_enemy_heavy_reads -= 1
				else:
					_enemy_light_reads -= 1
	_enemy_read_decay_timer -= dt
	if _enemy_read_decay_timer <= 0.0:
		_enemy_read_decay_timer = clampf(float(_read_settings.get("decay_seconds", 9.0)), 3.0, 30.0)
		_enemy_heavy_reads = maxi(0, _enemy_heavy_reads - 1)
		_enemy_light_reads = maxi(0, _enemy_light_reads - 1)
	var dist: float = f.position.distance_to(o.position)
	var nearby_guard: bool = o.state == Fighter.S.BLOCK and dist <= _preferred_range(f) + 1.0
	var delta_memory: float = 0.23 if nearby_guard else -0.14
	_enemy_block_memory = clampf(_enemy_block_memory + delta_memory * dt, 0.0, 1.0)

func _heavy_habit_parry_bonus() -> float:
	var options: Dictionary = _read_level()
	if options.is_empty():
		return 0.0
	var samples: int = _enemy_heavy_reads + _enemy_light_reads
	if samples < clampi(int(_read_settings.get("sample_min", 4)), 3, 12):
		return 0.0
	var ratio: float = float(_enemy_heavy_reads) / float(maxi(samples, 1))
	if ratio < clampf(float(_read_settings.get("heavy_ratio_threshold", 0.60)), 0.50, 0.90):
		return 0.0
	return clampf(float(options.get("parry_bonus", 0.0)), 0.0, 0.08)

func _guard_habit() -> bool:
	return not _read_level().is_empty() and _enemy_block_memory >= clampf(float(_read_settings.get("block_memory_threshold", 0.43)), 0.2, 0.85)
