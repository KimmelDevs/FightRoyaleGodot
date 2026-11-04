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
	var d: Vector3 = o.position - f.position; d.y = 0
	var dist := d.length()
	d /= maxf(dist, 0.001)
	var side := Vector3(-d.z, 0, d.x)
	if _side_t > 0.0:
		_side_t -= dt; f.in_move = side * _side_sign; return
	if f.kit in RANGED:
		_strafe_t -= dt
		if _strafe_t <= 0.0:
			_strafe_t = _r(0.6, 1.4); _side_sign = [-1.0, 0.0, 1.0][randi() % 3]
		if dist < 3.2: f.in_move = -d + side * _side_sign * 0.5
		elif dist > 6.5: f.in_move = d
		elif _side_sign != 0.0: f.in_move = side * _side_sign * 0.6

func _try_skill(f: Fighter, key: String, force := false) -> bool:
	if f.cooldowns[key] > 0.0: return false
	if not force and randf() > 0.5: return false
	f.in_skill = key
	return true

func _offense(f: Fighter, o, dt: float) -> void:
	if f.state != Fighter.S.IDLE or not _queue.is_empty() or _hold > 0.0 or _block_hold > 0.0: return
	var dist: float = f.position.distance_to(o.position)
	var ranged: bool = f.kit in RANGED
	var reach := 9.0 if ranged else 1.7 if f.kit in ["assassin", "knuckles", "kicks"] else 2.3 if f.kit == "greatsword" else 1.9
	_skill_cd -= dt
	if _skill_cd <= 0.0:
		_skill_cd = _r(p.skill[0], p.skill[1])
		var keys := ["c", "x", "z"]; keys.shuffle()
		for key in keys:
			var a: Dictionary = f.attacks[key]
			var ok := true
			match a.type:
				"melee": ok = dist < float(a.reach) + 1.5
				"strike": ok = a.at != "self" or dist < float(a.radius)
				"buff": ok = dist < 2.5 if a.mode == "counter" else f.hp < f.max_hp * 0.7
				"blink": ok = (a.mode == "behind" and dist < 6.0) or (a.mode == "back" and dist < 2.5)
			if ok and _try_skill(f, key): return
	if dist > reach: return
	if o is Fighter and o.state == Fighter.S.STAGGER: _think_cd = 0.0
	_think_cd -= dt
	if _think_cd > 0.0: return
	_think_cd = (_r(0.5, 1.1) if f.kit in ["assassin", "knuckles", "kicks"] else _r(0.7, 1.6)) * p.think
	var heavy_chance := 0.22
	if o is Fighter: heavy_chance = 0.5 if o.state == Fighter.S.STAGGER else 0.45 if o.state == Fighter.S.BLOCK else 0.22
	if randf() < heavy_chance:
		_queue.append([0.0, Fighter.HOLD_T + _r(0.3, 0.65)])
	else:
		var lights := 0
		for k in f.attacks: if k.length() == 2 and k.begins_with("l"): lights += 1
		var hits := 1 + randi() % mini(p.combo, lights)
		for i in hits: _queue.append([0.0 if i == 0 else 0.14, 0.06])
