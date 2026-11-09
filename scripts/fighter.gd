class_name Fighter
extends Node3D
## A playable fighter (port of the web game's fighter.ts). A brain (player input, CPU, or a
## remote player) fills `intent` every frame:
##   attack tap (release < HOLD_T) -> combo hit, chains into the next l-step
##   attack hold, then release     -> charged attack (up to 1.5x at full charge)
##   block hold                    -> block; the first parry_window seconds parry
##   jump / skill "z" "x" "c" / dash direction
## The match gets `swing` when an attack reaches its active frame and resolves it.

enum S { IDLE, ATTACK, CHARGE, BLOCK, HITSTUN, STAGGER, KO, WIN }

const HOLD_T := 0.22
const CHARGE_MAX := 0.9
const ENGAGE := 1.45
const MIN_DIST := 0.95
const GRAVITY := 22.0
const GUARD_REGEN := 30.0
const DASH_CD := 3.0
const DASH_T := 0.3
const DASH_SPEED := 14.0
const DODGE_SPEED := 10.0  # FRG06 - locomotion and procedural footwork
const DODGE_DURATION := 0.20
const DODGE_COOLDOWN := 1.4
const SPRINT_MULT := 1.45
const GROUND_ACCEL := 19.0
const GROUND_BRAKE := 25.0
const AIR_CONTROL := 0.45
const RAGE_MULT := 1.2
const RANGED_REST := {"mage": 1.2, "bow": 1.3}
const STUN_DR_WINDOW := 3.0
const STUN_DR := 0.6
# FRG07 - persistent melee contact and directional knockback
const KNOCK_DAMPING := 14.0

signal swing(f: Fighter)
signal knocked_out(f: Fighter)
signal landed(f: Fighter)
signal dashed(f: Fighter)

var id := 0
var team := 0
var char_index := 0
var look: Dictionary
var kit := ""
var model: FighterModel
var brain = null          ## object with think(f, dt)
var opponent = null       ## Fighter or mob (untyped: duck-typed is_down()/position)
var owner_peer := ""
var auto_approach := false
var arena_radius := 7.0

# intent filled by the brain each frame
var in_attack := false
var in_block := false
var in_jump := false
var in_skill := ""
var in_move := Vector3.ZERO
var in_dash := Vector3.ZERO
var in_dodge := Vector3.ZERO
var in_sprint := false

var max_hp := 2500.0
var hp := 2500.0
var max_guard := 100.0
var guard := 100.0
var move_speed := 3.2
var walk_speed := 2.6
var parry_window := 0.16
var jump_v := 7.0
var attacks: Dictionary
var radius := 0.35

var state: int = S.IDLE
var state_t := 0.0
var atk: Dictionary = {}
var atk_id := ""
var atk_phase := 0
var atk_power := 1.0
var swing_serial := 0
var last_damage := 0.0
var last_crit := false
var cooldowns := {"z": 0.0, "x": 0.0, "c": 0.0}
var atk_lock := 0.0
var on_ground := true
var vel_y := 0.0
var ward_t := 0.0
var counter_t := 0.0
var invuln_t := 0.0
var rage_t := 0.0
var dash_cd := 0.0
var pose_name := "idle"
var pose_speed := 14.0

# survival perks / emblems
var dmg_mult := 1.0
var cd_mult := 1.0
var crit_chance := 0.2
var lifesteal := 0.0

var _stun := 0.0
var _stun_pose := "hit"
var _combo_next := "l1"
var _combo_timer := 0.0
var _buffered := false
var _atk_prev := false
var _jump_prev := false
var _holding := false
var _hold_t := 0.0
var _guard_delay := 0.0
var _knock := 0.0
var _knock_dir := Vector3.ZERO
var _dash_t := 0.0
var _dash_dir := Vector3.ZERO
var _dodge_t := 0.0
var _dodge_cd := 0.0
var _dodge_dir := Vector3.ZERO
var _steer_vel := Vector3.ZERO
var _leap_vel := Vector3.ZERO
var _clock := 0.0
var _stun_src := ""
var _last_stun_at := -99.0
var _stun_chain := 0

func setup(index: int, loadout: Array = ["z", "x", "c"], emblem: Dictionary = {}) -> void:
	char_index = index
	var c: Dictionary = Data.character(index)
	look = c.look
	kit = look.kit
	var st: Dictionary = Data.stats[kit]
	max_hp = st.hp; max_guard = st.guard; move_speed = st.move; walk_speed = st.walk
	parry_window = st.parry; jump_v = st.jump
	attacks = Data.attacks_for(c.id)
	var pool := {"z": attacks.z, "x": attacks.x, "c": attacks.c, "v": attacks.v}
	var slots: Array = loadout if loadout.size() == 3 else ["z", "x", "c"]
	for i in 3:
		attacks[["z", "x", "c"][i]] = pool.get(slots[i], pool[["z", "x", "c"][i]])
	if not emblem.is_empty():
		_apply_emblem(emblem.get("id", "fighter"), int(emblem.get("level", 1)))
	hp = max_hp; guard = max_guard
	model = FighterModel.new()
	add_child(model)
	model.setup(look)

func _apply_emblem(eid: String, level: int) -> void:
	for e in Data.economy.emblems:
		if e.id != eid: continue
		var b: Dictionary = e.per_level
		var l := clampi(level, 1, int(Data.economy.emblem_max))
		max_hp *= 1.0 + b.get("hp", 0.0) * l
		max_guard *= 1.0 + b.get("guard", 0.0) * l
		dmg_mult *= 1.0 + b.get("dmg", 0.0) * l
		crit_chance += b.get("crit", 0.0) * l
		cd_mult *= 1.0 - b.get("cd", 0.0) * l
		move_speed *= 1.0 + b.get("speed", 0.0) * l

func is_down() -> bool: return state == S.KO
func chest() -> Vector3: return global_position + Vector3(0, 1.2, 0)
func airborne() -> bool: return not on_ground and position.y > 0.7

func tick(dt: float) -> void:
	in_attack = false; in_block = false; in_jump = false; in_skill = ""; in_move = Vector3.ZERO; in_dash = Vector3.ZERO
	in_dodge = Vector3.ZERO; in_sprint = false
	if brain != null and state != S.KO and state != S.WIN:
		brain.think(self, dt)
	if not on_ground: in_block = false
	state_t += dt
	_clock += dt
	for k in cooldowns: cooldowns[k] = maxf(cooldowns[k] - dt, 0.0)
	atk_lock = maxf(atk_lock - dt, 0.0)
	dash_cd = maxf(dash_cd - dt, 0.0)
	_dash_t = maxf(_dash_t - dt, 0.0)
	_dodge_t = maxf(_dodge_t - dt, 0.0)
	_dodge_cd = maxf(_dodge_cd - dt, 0.0)
	ward_t = maxf(ward_t - dt, 0.0)
	rage_t = maxf(rage_t - dt, 0.0)
	counter_t = maxf(counter_t - dt, 0.0)
	invuln_t = maxf(invuln_t - dt, 0.0)
	_read_dash()
	_read_dodge()
	_read_attack(dt)
	_read_jump()
	_read_skill()
	match state:
		S.IDLE:
			_combo_timer -= dt
			if _combo_timer <= 0.0: _combo_next = "l1"
			if in_block: _set_state(S.BLOCK)
		S.ATTACK: _attack_step()
		S.CHARGE:
			if in_block: _holding = false; _set_state(S.BLOCK)
			elif state_t >= CHARGE_MAX: _holding = false; _start_attack("heavy")
		S.BLOCK:
			if not in_block: _set_state(S.IDLE)
		S.HITSTUN, S.STAGGER:
			if state_t >= _stun: _set_state(S.IDLE)
	_move(dt)
	_vertical(dt)
	if state != S.BLOCK:
		_guard_delay -= dt
		if _guard_delay <= 0.0: guard = minf(guard + GUARD_REGEN * dt, max_guard)
	model.charge = minf(state_t / CHARGE_MAX, 1.0) if state == S.CHARGE else maxf(model.charge - dt * 4.0, 0.0)
	_compute_pose()
	model.play_pose(pose_name, pose_speed)

## True throughout the *entire* damaging window, not just on the first active frame.
func active_melee() -> bool:
	return state == S.ATTACK and not atk.is_empty() and String(atk.get("type", "")) == "melee" \
		and atk_phase == 1 and state_t <= float(atk.wind) + float(atk.active) + 0.0001

## Melee trail should show (wind-up end, active, just after).
func trail_on() -> bool:
	if state != S.ATTACK or atk.is_empty() or atk.type != "melee": return false
	return atk_phase == 1 or (atk_phase == 0 and state_t > atk.wind * 0.6) or (atk_phase == 2 and state_t < atk.wind + atk.active + 0.05)

# --- input -> actions ------------------------------------------------------------------

func _read_dash() -> void:
	if in_dash.length_squared() < 0.01 or dash_cd > 0.0: return
	if not state in [S.IDLE, S.BLOCK, S.CHARGE, S.ATTACK]: return
	if state != S.IDLE:
		if state == S.ATTACK: _finish_attack()
		_holding = false
		_set_state(S.IDLE)
	_dash_dir = Vector3(in_dash.x, 0, in_dash.z).normalized()
	_dash_t = DASH_T
	dash_cd = DASH_CD
	invuln_t = maxf(invuln_t, 0.15)
	dashed.emit(self)

func _read_dodge() -> void:
	# Short evasive sidestep, independent of the double-tap dash cooldown.
	if in_dodge.length_squared() < 0.01 or _dodge_cd > 0.0 or _dash_t > 0.0:
		return
	if state != S.IDLE and state != S.BLOCK:
		return
	_dodge_dir = Vector3(in_dodge.x, 0.0, in_dodge.z).normalized()
	if _dodge_dir.length_squared() < 0.01:
		return
	_steer_vel = Vector3.ZERO
	_dodge_t = DODGE_DURATION
	_dodge_cd = DODGE_COOLDOWN
	invuln_t = maxf(invuln_t, 0.14)
	if state == S.BLOCK:
		_set_state(S.IDLE)
	dashed.emit(self)

func _read_attack(dt: float) -> void:
	var on := in_attack
	var pressed := on and not _atk_prev
	var released := not on and _atk_prev
	_atk_prev = on
	if state in [S.HITSTUN, S.STAGGER, S.KO, S.WIN]:
		_holding = false; return
	if pressed and atk_lock > 0.0: return
	if pressed: _holding = true; _hold_t = 0.0
	if _holding:
		_hold_t += dt
		if _hold_t >= HOLD_T and state == S.IDLE and not in_block: _set_state(S.CHARGE)
	if released and _holding:
		_holding = false
		if state == S.CHARGE: _start_attack("heavy")
		elif _hold_t < HOLD_T: _request_light()

func _read_jump() -> void:
	var pressed := in_jump and not _jump_prev
	_jump_prev = in_jump
	if pressed and on_ground and (state == S.IDLE or state == S.BLOCK):
		vel_y = jump_v
		on_ground = false
		if state == S.BLOCK: _set_state(S.IDLE)

func _read_skill() -> void:
	var k := in_skill
	if k == "" or cooldowns.get(k, 1.0) > 0.0: return
	var free: bool = state in [S.IDLE, S.BLOCK, S.CHARGE] or (state == S.ATTACK and atk_phase == 2)
	if not free: return
	_holding = false
	cooldowns[k] = float(attacks[k].cd) * cd_mult
	_start_attack(k)

func _request_light() -> void:
	if state == S.IDLE or state == S.BLOCK:
		_start_attack(_combo_next if _combo_timer > 0.0 else "l1")
	elif state == S.ATTACK and not atk.is_empty() and atk.next != "":
		_buffered = true

func _start_attack(aid: String) -> void:
	atk_power = 1.0
	if aid == "heavy" and state == S.CHARGE: atk_power = 1.0 + 0.5 * minf(state_t / CHARGE_MAX, 1.0)
	atk_power *= dmg_mult * (RAGE_MULT if rage_t > 0.0 else 1.0)
	atk_id = aid
	atk = attacks[aid]
	atk_phase = 0
	_buffered = false
	swing_serial += 1
	if float(atk.self_jump) > 0.0 and atk.mode != "leap":
		vel_y = float(atk.self_jump); on_ground = false
	_set_state(S.ATTACK)

func _attack_step() -> void:
	var w: float = atk.wind
	var ac: float = atk.active
	var r: float = atk.recover
	if atk.mode == "leap":
		# Wind-up crouch -> jump toward the target -> the hit lands on touchdown.
		if atk_phase == 0 and state_t >= w:
			atk_phase = 1
			vel_y = float(atk.self_jump)
			on_ground = false
			var air := 2.0 * vel_y / GRAVITY
			if opponent and not opponent.is_down():
				var to: Vector3 = opponent.global_position - global_position; to.y = 0
				_leap_vel = to.normalized() * minf(maxf(to.length() - 0.9, 0.0) / air, 9.0)
			else:
				_leap_vel = forward() * 3.0
		elif atk_phase == 1:
			if on_ground and state_t > w + 0.1:
				atk_phase = 2; state_t = w + ac; _leap_vel = Vector3.ZERO
				swing.emit(self)
		elif atk_phase == 2 and state_t >= w + ac + r:
			_finish_attack(); _set_state(S.IDLE)
		return
	if atk_phase == 0 and state_t >= w:
		atk_phase = 1
		swing.emit(self)
	elif atk_phase == 1 and state_t >= w + ac:
		atk_phase = 2
	elif atk_phase == 2:
		if _buffered and atk.next != "" and state_t >= w + ac + minf(0.1, r): _start_attack(atk.next)
		elif in_block and state_t >= w + ac + 0.06: _finish_attack(); _set_state(S.BLOCK)
		elif state_t >= w + ac + r: _finish_attack(); _set_state(S.IDLE)

func _finish_attack() -> void:
	if atk.is_empty(): return
	if atk_id.begins_with("l") and atk.next == "" and atk.type != "melee":
		atk_lock = RANGED_REST.get(kit, 1.2)
	_combo_next = atk.next if atk.next != "" else "l1"
	_combo_timer = 0.45 if atk.next != "" else 0.0

func _set_state(s: int) -> void:
	state = s
	state_t = 0.0

func forward() -> Vector3:
	return Vector3(sin(rotation.y), 0, cos(rotation.y))

# --- movement ----------------------------------------------------------------------------

func _move(dt: float) -> void:
	var pos := position
	var o = opponent
	var dir := forward()
	var dist := 99.0
	if o and not o.is_down():
		var to: Vector3 = o.position - pos
		to.y = 0.0
		dist = to.length()
		dir = to / maxf(dist, 0.001)
	elif in_move.length_squared() > 0.01:
		dir = in_move.normalized()
	if state != S.KO:
		var target := atan2(dir.x, dir.z)
		rotation.y += wrapf(target - rotation.y, -PI, PI) * (1.0 - exp(-12.0 * dt))

	var walking := false
	var running := false
	var burst := false
	if state == S.ATTACK and atk.get("mode", "") == "leap" and atk_phase == 1:
		pos += _leap_vel * dt
		_steer_vel = Vector3.ZERO
	elif _dash_t > 0.0:
		pos += _dash_dir * DASH_SPEED * dt
		_steer_vel = Vector3.ZERO
		burst = true
		walking = on_ground
	elif _dodge_t > 0.0:
		pos += _dodge_dir * DODGE_SPEED * dt
		_steer_vel = Vector3.ZERO
		burst = true
		walking = on_ground
	else:
		var v := 0.0
		if state == S.IDLE and auto_approach and brain != null and o and not o.is_down() and dist > ENGAGE:
			v = walk_speed
			walking = on_ground
		if state == S.ATTACK and not atk.is_empty() and atk_phase <= 1 and dist > MIN_DIST + 0.15:
			v += float(atk.lunge)
		# Knockback uses the ORIGINAL impact direction, independent of facing changes.
		_knock = maxf(_knock - KNOCK_DAMPING * dt, 0.0)
		if dist < MIN_DIST and v > 0.0:
			v = 0.0
		pos += dir * v * dt
		if _knock > 0.0:
			pos += _knock_dir * _knock * dt

		var steer := 1.0 if state == S.IDLE else 0.5 if state == S.BLOCK else 0.4 if state == S.CHARGE else 0.0
		# Don't let direct input instantly erase a strong knockback reaction.
		if _knock > 0.2: steer *= 0.35
		var requested := Vector3.ZERO
		if steer > 0.0 and in_move.length_squared() > 0.0001:
			var sprint_now := in_sprint and state == S.IDLE and on_ground
			var speed := move_speed * (SPRINT_MULT if sprint_now else 1.0)
			requested = in_move.normalized() * speed * steer
			running = sprint_now
		var response := GROUND_ACCEL if requested.length_squared() > 0.01 else GROUND_BRAKE
		var air_factor := 1.0 if on_ground else AIR_CONTROL
		_steer_vel = _steer_vel.move_toward(requested, response * air_factor * dt)
		var travel := _steer_vel * dt
		if dist < MIN_DIST and travel.dot(dir) > 0.0:
			travel -= dir * travel.dot(dir)
		pos += travel
		walking = walking or (on_ground and _steer_vel.length_squared() > 0.04)
		if dist < MIN_DIST * 0.9:
			pos -= dir * (MIN_DIST * 0.9 - dist) * 0.5
	var flat := Vector2(pos.x, pos.z).length()
	if flat > arena_radius:
		pos.x *= arena_radius / flat
		pos.z *= arena_radius / flat
	position = pos

	# The motion modifier controls gait AFTER the animation library poses.
	var w := 1.0 if walking else 0.0
	model.walk = clampf(lerpf(model.walk, w, 1.0 - exp(-9.0 * dt)), 0.0, 1.0)
	model.run = lerpf(model.run, 1.0 if running else 0.0, 1.0 - exp(-7.0 * dt))
	var side := Vector3(cos(rotation.y), 0.0, -sin(rotation.y))
	var side_value := clampf(_steer_vel.dot(side) / maxf(move_speed, 0.01), -1.0, 1.0)
	model.strafe = lerpf(model.strafe, side_value, 1.0 - exp(-9.0 * dt))
	model.airborne = not on_ground
	model.burst = lerpf(model.burst, 1.0 if burst else 0.0, 1.0 - exp(-15.0 * dt))

func _vertical(dt: float) -> void:
	if on_ground: return
	vel_y -= GRAVITY * dt
	position.y += vel_y * dt
	if position.y <= 0.0:
		position.y = 0.0; vel_y = 0.0; on_ground = true
		landed.emit(self)

func teleport(to: Vector3) -> void:
	var flat := Vector2(to.x, to.z).length()
	var k := arena_radius / flat if flat > arena_radius else 1.0
	position = Vector3(to.x * k, position.y, to.z * k)
	invuln_t = 0.3
	if opponent:
		var d: Vector3 = opponent.position - position
		rotation.y = atan2(d.x, d.z)

func _apply_knock(attacker, speed: float) -> void:
	if speed <= 0.0: return
	_knock = maxf(_knock, speed)
	var away := -forward()
	if attacker is Node3D:
		away = global_position - attacker.global_position
		away.y = 0.0
	if away.length_squared() > 0.0001:
		_knock_dir = away.normalized()
	else:
		_knock_dir = -forward()

func _interrupt_attack() -> void:
	# A hit or clash cancels pending combo inputs; the next tap starts from l1.
	_holding = false
	_buffered = false
	_combo_next = "l1"
	_combo_timer = 0.0

func push_back(speed: float) -> void:
	_apply_knock(opponent, speed)

# --- getting hit -------------------------------------------------------------------------

## Returns "none", "miss", "warded", "counter", "parry", "blocked", "guard_break", "hit", "crit" or "ko".
func receive_hit(attacker, a: Dictionary, power: float) -> String:
	if state == S.KO: return "none"
	if invuln_t > 0.0: return "miss"
	if ward_t > 0.0: return "warded"
	if counter_t > 0.0: counter_t = 0.0; return "counter"
	var dmg: float = float(a.dmg) * power
	if state == S.BLOCK:
		if state_t <= parry_window:
			guard = minf(guard + 20.0, max_guard)
			model.flash(Color("#99e6ff"), 0.15)
			return "parry"
		guard -= float(a.guard) * power
		_guard_delay = 1.0
		if guard <= 0.0:
			guard = 0.0
			last_damage = dmg * 0.4; last_crit = false
			hp = maxf(hp - last_damage, 0.0)
			_apply_knock(attacker, 3.5)
			if hp <= 0.0: _ko(); return "ko"
			stagger(0.85)
			model.flash(Color("#ffd966"), 0.18)
			return "guard_break"
		_apply_knock(attacker, float(a.knock) * 0.5)
		return "blocked"
	var cc: float = attacker.crit_chance if attacker is Fighter else 0.2
	last_crit = randf() < cc
	if last_crit: dmg *= 1.6
	last_damage = dmg
	hp = maxf(hp - dmg, 0.0)
	_apply_knock(attacker, float(a.knock))
	model.flash()
	if hp <= 0.0: _ko(); return "ko"
	# One stun per skill use; repeated stuns within a few seconds get shorter.
	var src := "%d:%d" % [attacker.id, attacker.swing_serial] if attacker is Fighter else ""
	var reeling := state == S.HITSTUN or state == S.STAGGER
	if src != "" and src == _stun_src and reeling:
		return "crit" if last_crit else "hit"
	_stun_src = src
	_stun_chain = _stun_chain + 1 if _clock - _last_stun_at < STUN_DR_WINDOW else 0
	_last_stun_at = _clock
	var stun := maxf(0.1, float(a.stun) * pow(STUN_DR, _stun_chain))
	if a.heavy or a.stagger: stagger(stun)
	else: _stun = stun; _stun_pose = "hit"; _interrupt_attack(); _set_state(S.HITSTUN)
	return "crit" if last_crit else "hit"

func stagger(d: float) -> void:
	_stun = d; _stun_pose = "stagger"; _interrupt_attack(); _set_state(S.STAGGER)

func clash_recoil() -> void:
	_stun = 0.38; _stun_pose = "clash"; _interrupt_attack(); _apply_knock(opponent, 4.0); _set_state(S.HITSTUN)

func win() -> void:
	if state != S.KO: _set_state(S.WIN)

func heal(amount: float) -> void: hp = minf(hp + amount, max_hp)

func _ko() -> void:
	_set_state(S.KO)
	knocked_out.emit(self)

# --- posing ------------------------------------------------------------------------------

func _compute_pose() -> void:
	var p := "idle"
	var sp := 14.0
	match state:
		S.IDLE:
			if not on_ground: p = "jump"; sp = 12.0
		S.BLOCK: p = "block"; sp = 30.0
		S.CHARGE: p = attacks.heavy.pose_w; sp = 10.0
		S.ATTACK:
			if atk.mode == "leap":
				if atk_phase == 0: p = atk.pose_w; sp = 16.0
				elif atk_phase == 1: p = "slam_air"; sp = 14.0
				else: p = atk.pose_s; sp = 40.0
			elif atk_phase == 0: p = atk.pose_w; sp = 22.0
			elif atk_phase == 1: p = atk.pose_s; sp = 45.0
			elif state_t < atk.wind + atk.active + atk.recover * 0.5: p = atk.pose_s; sp = 20.0
			else: sp = 9.0
		S.HITSTUN, S.STAGGER: p = _stun_pose; sp = 28.0
		S.KO: p = "down"; sp = 10.0
		S.WIN: p = "win"; sp = 6.0
	pose_name = p
	pose_speed = sp
