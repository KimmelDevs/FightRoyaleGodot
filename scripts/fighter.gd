class_name Fighter
extends Node3D
# FRG15A - status and passive runtime
# FRG15B - control status protections
# FRG15C - damage/healing/cleanse status support
const STATUS_SCRIPT = preload("res://scripts/combat_status.gd")
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
# FRG09 - queued skills and combo input
const SKILL_BUFFER_SECONDS := 0.45  # Valid skill presses wait briefly for recovery
const LIGHT_BUFFER_SECONDS := 0.24  # Late taps during attack rest

const ENGAGE := 1.45
const MIN_DIST := 0.95
const GRAVITY := 22.0
const GUARD_REGEN := 30.0
# FRG08 - defense and guard fatigue
const FATIGUE_CAP := 10
const FATIGUE_DECAY_SECONDS := 3.0
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
const RANGED_REST := {"mage": 1.2, "bow": 1.3, "bomb": 1.2} # FRG19S
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
var status_runtime
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
var guard_fatigue := 0

# FRG19D Nesa's V skill: successful counter produces a strong heart finisher.

# FRG19E — Roxy's four shield charges and frost-shard freeze buildup.
# FRG19K — Aster-only 10-second Judgment state.
var aster_judgment_t := 0.0
var roxy_aegis_charges := 0
var roxy_aegis_t := 0.0
var roxy_frost_stacks := 0
var roxy_freeze_cd := 0.0
var nesa_counter_pending := false
var nesa_counter_slot := ""
var nesa_counter_max_cd := 0.0

# FRG19C Kaizen: target captured by a confirmed Predator's Hook contact.
var kaizen_bound_target: Fighter = null
var kaizen_bind_seconds := 0.0
# FRG19F Zenith - +0.01 action speed per real damage event, 14-stack cap.

# FRG19G Zephyr: STAFF / SPLIT / WHIP / FOLDED and 25-second Dragon Rhythm.

# FRG19I — Renji: Reads only from confirmed parries; reflection only auto-parries
# attacks the ordinary parry system would allow.

# FRG19J — Veyr's resources are per-fighter and reset when a new Fighter is created.
var veyr_bloodlust := 0.0
var veyr_frenzy_t := 0.0
var veyr_festival_t := 0.0
var veyr_festival_tick := 0.0
var veyr_feint_t := 0.0
var veyr_feint_counter := false
var renji_reflection_t := 0.0
var renji_reads := 0
var renji_read_timer := 0.0
var in_mode_switch := false

# FRG19H — Nythera's Moonfloat / Dreadfall stance and temporary Orbit Marks.
var nythera_mode := 0 # 0 Moonfloat, 1 Dreadfall
var nythera_mode_cd := 0.0
var nythera_orbit_marks := 0 # On the DEFENDER, stacked only by Nythera
var nythera_orb_seconds := 0.0
var nythera_dread_stacks := 0 # On Nythera, +0.1 attack speed per consumed mark
var nythera_well_seconds := 0.0
var zephyr_mode := 0
var zephyr_mode_cooldown := 0.0
var zephyr_rhythm_stacks := 0
var zephyr_rhythm_seconds := 0.0
var zenith_magnetic_stacks := 0
var zenith_magnetic_timer := 0.0
# FRG19L — Garrick receives Resolve from confirmed projectile parries/interceptions.
# FRG19M — Kaede Counter Bloom, round-local (new Fighter each rematch).
var kaede_counter_bloom := 0
# FRG19N — tracks fire-mage ground hazards; each Fighter is round-local.
var ember_ground_patches := 0
# FRG19O — Rook: consecutive genuine hits build round-local Beatdown.
# FRG19Q — Nyx: real Phantom Rush contacts boost ranged SKILLS only.
var nyx_ambush_stacks := 0
var nyx_air_strikes := 0
# FRG19R — three aerial kicks per jump; resets upon landing.
var kira_air_strikes := 0
# FRG19S — Bob: four stored mine charges, a single active powder keg.
var bob_mine_charges := 4
var bob_mine_recharge := 0.0
var bob_barrel_active := false
var bob_barrel_skill_key := ""
var bob_barrel_request := false
var rook_combo_hits := 0
var rook_best_hits := 0
var rook_last_hit_at := -99.0
var garrick_resolve := 0
var garrick_crack_cooldown := 0.0
var zarek_momentum := 0  # FRG19B projectile-destroy Clash Momentum
var _fatigue_decay := 3.0
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
# FRG12C - actual melee contact serial for truthful whiff checks
var last_melee_contact_serial := -1
var last_damage := 0.0
var last_crit := false
var cooldowns := {"z": 0.0, "x": 0.0, "c": 0.0}
var atk_lock := 0.0
var on_ground := true
var vel_y := 0.0
var ward_t := 0.0
# FRG19P — Marina's Bubble Ward mitigates HP damage, never makes her immune.
var marina_bubble_t := 0.0
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
var _queued_skill := ""
var _queued_skill_t := 0.0
var _queued_light_t := 0.0
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
	guard_fatigue = 0; _fatigue_decay = FATIGUE_DECAY_SECONDS
	model = FighterModel.new()
	add_child(model)
	# FRG16A - interactive animation lab
	model.character_id = String(c.id)
	model.setup(look)
	status_runtime = STATUS_SCRIPT.new()
	add_child(status_runtime)
	status_runtime.bind_host(self, String(c.id))

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

# Status API used by later character installers and ability definitions.
func _rook_meteor_armor() -> bool:
	return kit == "knuckles" and String(look.get("vrm", "")) == "rook" and state == S.ATTACK and atk_id == "c" and String(atk.get("name", "")) == "Meteor Fist"

func add_status(effect_id: String, stacks: int = 1, seconds: float = -1.0) -> bool:
	# FRG19O — super armor resists control application, never damage-over-time.
	if _rook_meteor_armor() and effect_id in ["freeze", "paralyze", "root", "slow", "stun"]:
		return false
	if status_runtime == null:
		return false
	var applied: bool = status_runtime.apply_effect(effect_id, stacks, seconds)
	if applied and model != null:
		if effect_id in ["freeze", "paralyze"]:
			model.flash(Color("#8acfff"), 0.25)
		elif effect_id == "root":
			model.flash(Color("#a6a2ff"), 0.15)
		elif effect_id == "silence":
			model.flash(Color("#d89bf0"), 0.15)
		elif effect_id in ["scorch", "poison"]:
			model.flash(Color("#ff9456") if effect_id == "scorch" else Color("#78c66a"), 0.16)
		elif effect_id == "bleed":
			model.flash(Color("#d74c5a"), 0.16)
		elif effect_id == "regeneration":
			model.flash(Color("#52db99"), 0.17)
	return applied

func cleanse_debuffs(max_count: int = -1) -> int:
	if status_runtime == null:
		return 0
	return status_runtime.cleanse_negative(max_count)

func remove_status(effect_id: String) -> void:
	if status_runtime != null:
		status_runtime.clear_effect(effect_id)

func notify_passive_event(event_id: String, other: Node = null) -> void:
	# FRG19O — Beatdown only counts confirmed HP-damaging contacts.
	if kit == "knuckles" and String(look.get("vrm", "")) == "rook":
		if event_id == "landed_hit":
			if _clock - rook_last_hit_at > 2.8: rook_combo_hits = 0
			rook_last_hit_at = _clock
			rook_combo_hits += 1
			rook_best_hits = maxi(rook_best_hits, rook_combo_hits)
		elif event_id in ["blocked_attack", "was_parried", "guard_break_attack", "countered_attack"]:
			rook_combo_hits = 0


	# Only genuinely damaging hits build / consume Orbit Marks. No reward from blocks/parries.
	if kit == "scythe" and event_id == "landed_hit" and other is Fighter:
		if nythera_mode == 0:
			other.nythera_orbit_marks = mini(6, other.nythera_orbit_marks + 1)
			other.nythera_orb_seconds = 10.0
		else:
			if other.nythera_orbit_marks > 0:
				other.nythera_orbit_marks -= 1
				nythera_dread_stacks = mini(14, nythera_dread_stacks + 1)
	# Dragon Rhythm earns stacks only on real contacts and defense success.
	if kit == "tristaff" and event_id in ["landed_hit", "blocked", "parried", "clashed", "projectile_destroyed"]:
		zephyr_rhythm_stacks = mini(zephyr_rhythm_stacks + 1, 3)
		zephyr_rhythm_seconds = 25.0
	# FRG19F: ONLY landed damaging hits grant the iron sovereign momentum.
	if kit == "glaive" and String(look.get("element", "")) == "metal" and event_id == "landed_hit":
		zenith_magnetic_stacks = mini(zenith_magnetic_stacks + 1, 14)
		zenith_magnetic_timer = 5.0

	# FRG19L: never award Resolve for a normal melee block/parry.
	if kit == "greatsword" and event_id in ["projectile_parried", "projectile_destroyed"]:
		garrick_resolve = mini(3, garrick_resolve + 1)
	# FRG19B: only real projectile destroys earn Zarek's Clash Momentum.
	if kit == "glaive" and String(look.get("element", "")) == "storm" and event_id == "projectile_destroyed":
		zarek_momentum += 1


	# FRG19J: bloodlust is only earned on landed damaging attacks, never on cast.
	if kit == "sickle" and event_id == "landed_hit":
		veyr_bloodlust = minf(100.0, veyr_bloodlust + 9.0)
	if kit == "tonfa" and event_id == "parried":
		renji_reads = mini(3, renji_reads + 1)
		renji_read_timer = 30.0
	if status_runtime != null:
		status_runtime.on_event(event_id, other)

func status_summary() -> String:
	# FRG19S — Bob's remote keg and mine charges are readable in both modes.
	if kit == "bomb":
		var btext: String = "MINES %d/4" % bob_mine_charges
		if bob_barrel_active: btext += " · KEG ARMED"
		return btext
	var summary: String = status_runtime.short_label() if status_runtime != null else ""
	# FRG19Q — Nyx HUD: +2% ranged skill damage per landed Phantom Rush.
	# FRG19R: Kira can make three distinct airborne kicks per jump.
	if kit == "kicks":
		var kick_text: String = "AIR KICKS %d/3" % kira_air_strikes
		return kick_text if summary.is_empty() else kick_text + ", " + summary
	if kit == "assassin":
		var ambush_text: String = "AMBUSH x%d (+%d%% RANGED SKILLS)" % [nyx_ambush_stacks, nyx_ambush_stacks * 2]
		return ambush_text if summary.is_empty() else ambush_text + ", " + summary
	# FRG19O — permanent best-of-round bonus, temporary active hit chain.
	if kit == "knuckles" and String(look.get("vrm", "")) == "rook":
		var label: String = "BEATDOWN %d | BEST %d (+%d%%)" % [rook_combo_hits, rook_best_hits, rook_best_hits]
		return label if summary.is_empty() else label + ", " + summary
	if kit == "glaive" and zarek_momentum > 0:
		return "Momentum x%d" % zarek_momentum if summary.is_empty() else "Momentum x%d, %s" % [zarek_momentum, summary]
	if kit == "glaive" and String(look.get("element", "")) == "metal" and zenith_magnetic_stacks > 0:
		return "Magnetic x%d" % zenith_magnetic_stacks if summary.is_empty() else "Magnetic x%d, %s" % [zenith_magnetic_stacks, summary]

	if kit == "sickle":
		var label: String = "BLOODLUST %d%%" % int(veyr_bloodlust)
		if veyr_frenzy_t > 0.0: label += " · FRENZY %.1fs" % veyr_frenzy_t
		if veyr_festival_t > 0.0: label += " · FESTIVAL %.1fs" % veyr_festival_t
		return label if summary.is_empty() else label + ", " + summary
	# FRG19K: show the remaining Judgment time in both match HUDs.
	if kit == "knight" and String(look.get("element", "")) == "light" and aster_judgment_t > 0.0:
		var aster_tag: String = "JUDGMENT %.1fs" % aster_judgment_t
		return aster_tag if summary.is_empty() else aster_tag + ", " + summary
	if kit == "tonfa":
		var tag: String = "READ x%d" % renji_reads
		if renji_reflection_t > 0.0: tag += " · REFLECT %.1fs" % renji_reflection_t
		return tag if summary.is_empty() else tag + ", " + summary
	# FRG19M — Kaede-only counter passive (0.80× to 1.00× damage).
	if kit == "katana":
		var bloom: String = "COUNTER BLOOM %d/4" % kaede_counter_bloom
		return bloom if summary.is_empty() else bloom + ", " + summary
	# FRG19P — separate Marina bubble timer visible in both game modes.
	if kit == "mage" and String(look.get("element", "")) == "water" and marina_bubble_t > 0.0:
		var bubble_tag: String = "BUBBLE %.1fs · 50%% HP DMG" % marina_bubble_t
		return bubble_tag if summary.is_empty() else bubble_tag + ", " + summary
	if kit == "mage" and String(look.get("element", "")) == "fire":
		var fire_tag: String = "FIRE PATCHES %d" % ember_ground_patches
		return fire_tag if summary.is_empty() else fire_tag + ", " + summary
	if kit == "greatsword" and garrick_resolve > 0:
		var resolve_tag: String = "RESOLVE %d/3" % garrick_resolve
		return resolve_tag if summary.is_empty() else resolve_tag + ", " + summary
	if kit == "tristaff":
		var tag: String = ["STAFF", "SPLIT", "WHIP", "FOLDED"][zephyr_mode] + " · Rhythm x%d" % zephyr_rhythm_stacks
		return tag if summary.is_empty() else tag + ", " + summary
	if kit == "scythe":
		var label: String = ("MOONFLOAT" if nythera_mode == 0 else "DREADFALL")
		label += " · Dread x%d" % nythera_dread_stacks if nythera_dread_stacks > 0 else ""
		return label if summary.is_empty() else label + ", " + summary
	if nythera_orbit_marks > 0:
		var marks: String = "Orbit x%d" % nythera_orbit_marks
		return marks if summary.is_empty() else marks + ", " + summary
	return summary

# FRG15D - status HUD and countdown indicators
func status_details() -> Array[Dictionary]:
	if status_runtime == null:
		return []
	return status_runtime.hud_effects()

func receive_status_damage(amount: float) -> void:
	if state == S.KO or amount <= 0.0:
		return
	hp = maxf(hp - amount, 0.0)
	if hp <= 0.0:
		_ko()

func is_down() -> bool: return state == S.KO
func chest() -> Vector3: return global_position + Vector3(0, 1.2, 0)
func airborne() -> bool: return not on_ground and position.y > 0.7

func tick(dt: float) -> void:
	in_mode_switch = false; in_attack = false; in_block = false; in_jump = false; in_skill = ""; in_move = Vector3.ZERO; in_dash = Vector3.ZERO
	in_dodge = Vector3.ZERO; in_sprint = false; in_mode_switch = false # FRG19H
	if brain != null and state != S.KO and state != S.WIN:
		brain.think(self, dt)
	if not on_ground: in_block = false
	state_t += dt
	_clock += dt
	if kit == "knuckles" and String(look.get("vrm", "")) == "rook" and rook_combo_hits > 0 and _clock - rook_last_hit_at > 2.8:
		rook_combo_hits = 0
	if status_runtime != null:
		status_runtime.step(dt)
		# FRG15B - Apply CC to both player and AI inputs; no editor setup needed.
		if not _rook_meteor_armor() and status_runtime.control_blocks("movement"):
			in_move = Vector3.ZERO
			in_dash = Vector3.ZERO
			in_dodge = Vector3.ZERO
			in_sprint = false
			in_jump = false
			_steer_vel = Vector3.ZERO
			_dash_t = 0.0
			_dodge_t = 0.0
		if not _rook_meteor_armor() and status_runtime.control_blocks("attack"):
			in_attack = false
			_atk_prev = false
			_holding = false
			if state in [S.ATTACK, S.CHARGE]:
				_interrupt_attack()
				_set_state(S.IDLE)
		if not _rook_meteor_armor() and status_runtime.control_blocks("skill"):
			in_skill = ""
			_queued_skill = ""
			_queued_skill_t = 0.0
		if not _rook_meteor_armor() and status_runtime.control_blocks("defense"):
			in_block = false
			if state == S.BLOCK:
				_set_state(S.IDLE)
	if guard_fatigue > 0 and dt > 0.0:
		_fatigue_decay -= dt
		if _fatigue_decay <= 0.0:
			guard_fatigue -= 1
			_fatigue_decay = FATIGUE_DECAY_SECONDS


	# FRG19C: bind lifetime, no persistence across KO or another match.
	if kaizen_bind_seconds > 0.0:
		kaizen_bind_seconds = maxf(0.0, kaizen_bind_seconds - dt)
		if kaizen_bind_seconds <= 0.0 or not is_instance_valid(kaizen_bound_target) or kaizen_bound_target.is_down():
			kaizen_bound_target = null
	# FRG19S: restore one stored mine every 8s, up to four.
	if kit == "bomb" and bob_mine_charges < 4:
		bob_mine_recharge -= dt
		if bob_mine_recharge <= 0.0:
			bob_mine_charges += 1
			bob_mine_recharge = 8.0 if bob_mine_charges < 4 else 0.0
	for k in cooldowns: cooldowns[k] = maxf(cooldowns[k] - dt, 0.0)
	atk_lock = maxf(atk_lock - dt, 0.0)
	dash_cd = maxf(dash_cd - dt, 0.0)
	_dash_t = maxf(_dash_t - dt, 0.0)
	_dodge_t = maxf(_dodge_t - dt, 0.0)
	_dodge_cd = maxf(_dodge_cd - dt, 0.0)
	ward_t = maxf(ward_t - dt, 0.0)
	marina_bubble_t = maxf(marina_bubble_t - dt, 0.0) # FRG19P

	# FRG19E - only in-game simulation time advances these timers.
	if roxy_aegis_t > 0.0:
		roxy_aegis_t = maxf(0.0, roxy_aegis_t - dt)
		if roxy_aegis_t <= 0.0:
			roxy_aegis_charges = 0
	roxy_freeze_cd = maxf(0.0, roxy_freeze_cd - dt)



	# FRG19J: real simulation time; no buffs continue while spectators pause.
	if kit == "sickle":
		veyr_festival_t = maxf(0.0, veyr_festival_t - dt)
		veyr_feint_t = maxf(0.0, veyr_feint_t - dt)
		veyr_frenzy_t = maxf(0.0, veyr_frenzy_t - dt)
		if veyr_frenzy_t <= 0.0:
			veyr_bloodlust = maxf(0.0, veyr_bloodlust - dt * 1.0)
		if veyr_bloodlust >= 100.0:
			veyr_bloodlust = 0.0
			veyr_frenzy_t = 5.0
		lifesteal = 0.12 if veyr_festival_t > 0.0 else (0.08 if veyr_frenzy_t > 0.0 else 0.0)
	# FRG19K: Judgment belongs to the light knight only. Its timer
	# advances during the actual match simulation, not during pause.
	if kit == "knight" and String(look.get("element", "")) == "light":
		var was_judging: bool = aster_judgment_t > 0.0
		aster_judgment_t = maxf(0.0, aster_judgment_t - dt)
		if aster_judgment_t > 0.0 and state == S.BLOCK:
			hp = maxf(1.0, hp - max_hp * 0.006 * dt)
		if was_judging and aster_judgment_t <= 0.0 and model != null and model.shield_node != null:
			model.shield_node.visible = true
	# FRG19L: timer only advances with active match time.
	if kit == "greatsword":
		garrick_crack_cooldown = maxf(0.0, garrick_crack_cooldown - dt)
	# FRG19I reflection decays in match-time; cannot block manually while active.
	if kit == "tonfa":
		renji_reflection_t = maxf(0.0, renji_reflection_t - dt)
		if renji_reflection_t > 0.0:
			in_block = false
		if renji_read_timer > 0.0:
			renji_read_timer = maxf(0.0, renji_read_timer - dt)
			if renji_read_timer <= 0.0: renji_reads = 0
	if kit == "tristaff":
		zephyr_mode_cooldown = maxf(zephyr_mode_cooldown - dt, 0.0)
		if zephyr_rhythm_seconds > 0.0:
			zephyr_rhythm_seconds = maxf(0.0, zephyr_rhythm_seconds - dt)
			if zephyr_rhythm_seconds <= 0.0:
				zephyr_rhythm_stacks = 0
		if in_mode_switch and zephyr_mode_cooldown <= 0.0 and state in [S.IDLE, S.BLOCK]:
			zephyr_mode = (zephyr_mode + 1) % 4
			zephyr_mode_cooldown = 0.38
			if model != null:
				model.set_tristaff_mode(zephyr_mode)

	# FRG19H: F switches between Moonfloat and Dreadfall; do not reuse a held switch.
	if kit == "scythe":
		nythera_mode_cd = maxf(0.0, nythera_mode_cd - dt)
		if in_mode_switch and nythera_mode_cd <= 0.0 and state in [S.IDLE, S.BLOCK]:
			nythera_mode = 1 - nythera_mode
			nythera_mode_cd = 0.35
			if model != null: model.flash(Color("#b6aaff") if nythera_mode == 0 else Color("#e9a5ff"), 0.18)
	if nythera_orb_seconds > 0.0:
		nythera_orb_seconds = maxf(0.0, nythera_orb_seconds - dt)
		if nythera_orb_seconds <= 0.0: nythera_orbit_marks = 0
	# FRG19F Zenith: consecutive landed hits refresh the 5s charge duration.
	if zenith_magnetic_timer > 0.0:
		zenith_magnetic_timer = maxf(0.0, zenith_magnetic_timer - dt)
		if zenith_magnetic_timer <= 0.0:
			zenith_magnetic_stacks = 0
	rage_t = maxf(rage_t - dt, 0.0)
	counter_t = maxf(counter_t - dt, 0.0)

	# FRG19D: grant the stated partial cooldown refund only when V fails to counter.
	if nesa_counter_pending and counter_t <= 0.0:
		nesa_counter_pending = false
		if nesa_counter_slot != "" and cooldowns.has(nesa_counter_slot):
			cooldowns[nesa_counter_slot] = maxf(0.0, float(cooldowns[nesa_counter_slot]) - nesa_counter_max_cd * 0.40)
		nesa_counter_slot = ""
	invuln_t = maxf(invuln_t - dt, 0.0)
	_read_dash()
	_read_dodge()
	_read_attack(dt)
	_read_jump()
	_read_skill(dt)
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
	# Execute buffered inputs after state transitions as well as before them.
	# Skills take priority over an attack buffered during ranged rest.
	_try_queued_skill()
	_try_queued_light(dt)
	_move(dt)
	_vertical(dt)
	# FRG19Q — landing restores air charges; interrupted air combos cannot
	# restart a third airborne strike on the ground.
	# FRG19R: air combo cannot be resumed once Kira touches the ground.
	if kit == "kicks" and on_ground and kira_air_strikes != 0:
		kira_air_strikes = 0
		_combo_next = "l1"
		_combo_timer = 0.0
		if atk_id in ["air_l1", "air_l2", "air_l3"]:
			_buffered = false
			atk["next"] = ""
	if kit == "assassin" and on_ground and nyx_air_strikes != 0:
		nyx_air_strikes = 0
		_combo_next = "l1"
		_combo_timer = 0.0
		if atk_id in ["air_l1", "air_l2"]:
			_buffered = false
			atk["next"] = ""
	if state != S.BLOCK:
		_guard_delay -= dt
		if _guard_delay <= 0.0: guard = minf(guard + GUARD_REGEN * dt * status_runtime.guard_regen_multiplier() * (1.0 - 0.05 * float(nythera_orbit_marks)), max_guard)
	model.charge = minf(state_t / CHARGE_MAX, 1.0) if state == S.CHARGE else maxf(model.charge - dt * 4.0, 0.0)
	_compute_pose()
	model.play_pose(pose_name, pose_speed)
	_frg16b_update_choreography()

func add_guard_fatigue() -> void:
	guard_fatigue = mini(guard_fatigue + 1, FATIGUE_CAP)
	_fatigue_decay = FATIGUE_DECAY_SECONDS

func attack_time_multiplier() -> float:
	# Each stack makes attack/skill execution 2% slower; maximum 10 stacks.
	var factor: float = 1.0 + 0.20 * float(mini(zarek_momentum, 5)) if kit == "glaive" and atk_id.begins_with("l") else 1.0
	var metal_factor: float = 1.0 + 0.01 * float(zenith_magnetic_stacks) if kit == "glaive" and String(look.get("element", "")) == "metal" else 1.0
	var dragon_mode_speed: float = [1.0, 1.20, 0.94, 1.50][zephyr_mode] if kit == "tristaff" else 1.0
	var dragon_rhythm_speed: float = 1.0 + 0.20 * float(zephyr_rhythm_stacks) if kit == "tristaff" else 1.0
	var veyr_frenzy_speed: float = 1.25 if kit == "sickle" and veyr_frenzy_t > 0.0 else 1.0
	var aster_sword_speed: float = 1.5 if kit == "knight" and String(look.get("element", "")) == "light" and aster_judgment_t > 0.0 and (atk_id.begins_with("l") or atk_id in ["heavy", "x"]) else 1.0
	return (1.0 / maxf(1.0 - 0.02 * float(guard_fatigue), 0.5)) * status_runtime.attack_time_multiplier() / veyr_frenzy_speed / (factor * metal_factor * dragon_mode_speed * dragon_rhythm_speed * aster_sword_speed) * (1.0 + 0.05 * float(nythera_orbit_marks)) / (1.0 + 0.10 * float(nythera_dread_stacks))

## True throughout the *entire* damaging window, not just on the first active frame.
func active_melee() -> bool:
	return state == S.ATTACK and not atk.is_empty() and String(atk.get("type", "")) == "melee" \
		and atk_phase == 1 and state_t <= (float(atk.wind) + float(atk.active)) * attack_time_multiplier() + 0.0001

## Melee trail should show (wind-up end, active, just after).
func trail_on() -> bool:
	if state != S.ATTACK or atk.is_empty() or atk.type != "melee": return false
	return atk_phase == 1 or (atk_phase == 0 and state_t > float(atk.wind) * attack_time_multiplier() * 0.6) or (atk_phase == 2 and state_t < (float(atk.wind) + float(atk.active)) * attack_time_multiplier() + 0.05)

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
		_holding = false
		return
	# Record a tap even during ranged attack rest; whether it executes is
	# decided when the input is released, not when the button goes down.
	if pressed:
		_holding = true
		_hold_t = 0.0
	if _holding:
		_hold_t += dt
		if _hold_t >= HOLD_T and state == S.IDLE and atk_lock <= 0.0 and not in_block:
			_set_state(S.CHARGE)
	if released and _holding:
		_holding = false
		if state == S.CHARGE:
			_start_attack("heavy")
		elif _hold_t < HOLD_T:
			_request_light()

func _read_jump() -> void:
	var pressed := in_jump and not _jump_prev
	_jump_prev = in_jump
	if pressed and on_ground and (state == S.IDLE or state == S.BLOCK):
		vel_y = jump_v
		on_ground = false
		if state == S.BLOCK: _set_state(S.IDLE)

func _read_skill(dt: float) -> void:
	if kit == "sickle" and veyr_festival_t > 0.0:
		in_skill = ""
		_queued_skill = ""
		_queued_skill_t = 0.0
		return

	# FRG19S: pressing the assigned Powder Keg key again requests its explosion.
	# This bypasses its cooldown only while a placed keg exists; otherwise normal rules apply.
	if kit == "bomb" and bob_barrel_active and in_skill != "" and in_skill == bob_barrel_skill_key:
		bob_barrel_request = true
		in_skill = ""
		_queued_skill = ""
		_queued_skill_t = 0.0
		return
	if kit == "bomb" and in_skill != "" and attacks.has(in_skill):
		if String(attacks[in_skill].get("type", "")) == "mine" and bob_mine_charges <= 0:
			in_skill = ""
			return
	# FRG19C: X recast reels a previously bound enemy to Kaizen (even during X cooldown).
	if kit == "chainblade" and in_skill == "x" and kaizen_bind_seconds > 0.0 and is_instance_valid(kaizen_bound_target):
		var victim: Fighter = kaizen_bound_target
		kaizen_bound_target = null
		kaizen_bind_seconds = 0.0
		if not victim.is_down():
			var pull_to: Vector3 = global_position + forward() * 1.25
			pull_to.y = victim.position.y
			victim.teleport(pull_to)
			victim.remove_status("root")
			victim.stagger(0.40)
		in_skill = ""
		return
	# A press during the wind-up or active phase is buffered briefly rather
	# than silently lost. A cooldown begins ONLY when the ability actually starts.
	if state in [S.HITSTUN, S.STAGGER, S.KO, S.WIN]:
		_queued_skill = ""
		_queued_skill_t = 0.0
		return
	if in_skill != "":
		var key: String = in_skill
		if attacks.has(key) and float(cooldowns.get(key, 1.0)) <= 0.0:
			_queued_skill = key
			_queued_skill_t = SKILL_BUFFER_SECONDS
	elif _queued_skill_t > 0.0:
		_queued_skill_t = maxf(_queued_skill_t - dt, 0.0)
		if _queued_skill_t <= 0.0:
			_queued_skill = ""
	_try_queued_skill()

func _try_queued_skill() -> void:
	if _queued_skill == "" or _queued_skill_t <= 0.0:
		return
	var key: String = _queued_skill
	if not attacks.has(key) or float(cooldowns.get(key, 1.0)) > 0.0:
		_queued_skill = ""
		_queued_skill_t = 0.0
		return
	var free: bool = state in [S.IDLE, S.BLOCK, S.CHARGE] or (state == S.ATTACK and atk_phase == 2)
	if not free:
		return
	_queued_skill = ""
	_queued_skill_t = 0.0
	_holding = false
	_buffered = false
	_combo_next = "l1"
	_combo_timer = 0.0
	cooldowns[key] = float(attacks[key].cd) * cd_mult
	_start_attack(key)

func _try_queued_light(dt: float) -> void:
	if _queued_light_t <= 0.0:
		return
	_queued_light_t = maxf(_queued_light_t - dt, 0.0)
	if _queued_light_t <= 0.0:
		return
	if state == S.IDLE and atk_lock <= 0.0 and not in_block and _queued_skill == "":
		_queued_light_t = 0.0
		if kit == "kicks" and not on_ground:
			if kira_air_strikes < 3: _start_attack("air_l%d" % (kira_air_strikes + 1))
		elif kit == "assassin" and not on_ground:
			if nyx_air_strikes < 2: _start_attack("air_l%d" % (nyx_air_strikes + 1))
		else:
			_start_attack(_combo_next if _combo_timer > 0.0 else "l1")

func _request_light() -> void:
	# FRG19R — Kira: three real airborne kick contacts, not an unlimited loop.
	if kit == "kicks" and not on_ground:
		if kira_air_strikes >= 3: return
		if state in [S.IDLE, S.BLOCK]:
			if atk_lock <= 0.0: _start_attack("air_l%d" % (kira_air_strikes + 1))
			else: _queued_light_t = LIGHT_BUFFER_SECONDS
		elif state == S.ATTACK and atk_id in ["air_l1", "air_l2"]:
			_buffered = true
		return
	# FRG19Q — two independently damaging air dagger hits per jump.
	if kit == "assassin" and not on_ground:
		if nyx_air_strikes >= 2: return
		if state in [S.IDLE, S.BLOCK]:
			if atk_lock <= 0.0:
				_start_attack("air_l%d" % (nyx_air_strikes + 1))
			else: _queued_light_t = LIGHT_BUFFER_SECONDS
		elif state == S.ATTACK and atk_id == "air_l1":
			_buffered = true
		return
	if state == S.IDLE or state == S.BLOCK:
		if atk_lock > 0.0:
			_queued_light_t = LIGHT_BUFFER_SECONDS
		else:
			_start_attack(_combo_next if _combo_timer > 0.0 else "l1")
	elif state == S.ATTACK and not atk.is_empty() and atk.next != "":
		# One buffered follow-up per swing; cannot multiply damage or skip frames.
		_buffered = true

func _start_attack(aid: String) -> void:
	# FRG19Q — never allow queued air strikes when back on the ground.
	if kit == "kicks" and aid in ["air_l1", "air_l2", "air_l3"] and on_ground: return # FRG19R
	if kit == "assassin" and aid in ["air_l1", "air_l2"] and on_ground: return
	atk_power = 1.0
	if aid == "heavy" and state == S.CHARGE: atk_power = 1.0 + 0.5 * minf(state_t / CHARGE_MAX, 1.0)
	atk_power *= dmg_mult * (RAGE_MULT if rage_t > 0.0 else 1.0) * status_runtime.outgoing_multiplier()
	atk_id = aid
	atk = attacks[aid].duplicate(true)
	# FRG19R — each Kira air kick advances once, including buffered chains.
	if kit == "kicks" and aid in ["air_l1", "air_l2", "air_l3"]:
		kira_air_strikes = int(aid.right(1))
	# FRG19Q — count at swing START, so every subsequent air cut is separate.
	if kit == "assassin" and aid in ["air_l1", "air_l2"]:
		nyx_air_strikes = 1 if aid == "air_l1" else 2
	# FRG19O — 1% extra power per best consecutive real hit this round.
	if kit == "knuckles" and String(look.get("vrm", "")) == "rook":
		atk_power *= 1.0 + 0.01 * float(rook_best_hits)
	# FRG19M — Kaede begins 20% weaker and regains 5% per confirmed Z counter.
	if kit == "katana":
		atk_power *= 0.80 + 0.05 * float(kaede_counter_bloom)
		if aid == "c":
			# Prevent residual dash/steering from sliding her during Thousand Cuts.
			_steer_vel = Vector3.ZERO
			_dash_t = 0.0
			_dodge_t = 0.0
	# FRG19K: the sword, not the shield bash, gains Judgment power.
	if kit == "knight" and String(look.get("element", "")) == "light" and aster_judgment_t > 0.0:
		if aid.begins_with("l") or aid in ["heavy", "x", "c"]:
			var missing: float = clampf(1.0 - hp / maxf(max_hp, 1.0), 0.0, 1.0)
			atk_power *= 1.20 + missing * 0.30
			if aid.begins_with("l") or aid == "heavy":
				atk["apply_status"] = "weaken"
				atk["status_duration"] = 50.0
				atk["status_stacks"] = 1

	# FRG19J: festival empowers LIGHTS only; no free Frenzy on cast.
	if kit == "sickle" and aid.begins_with("l"):
		if veyr_festival_t > 0.0:
			atk_power *= 1.35
			atk["guard"] = float(atk.get("guard", 0.0)) * 3.0
		if veyr_frenzy_t > 0.0:
			atk_power *= 1.15

	# FRG19I: the third confirmed Read upgrades the next Eightfold finisher.
	if kit == "tonfa" and aid == "v" and renji_reads >= 3:
		atk["multi_hit"] = int(atk.get("multi_hit", 8)) + 1
		atk_power *= 1.20
		renji_reads = 0
		renji_read_timer = 0.0
	if kit == "scythe" and String(atk.get("type", "melee")) == "melee":
		if nythera_mode == 1: atk_power *= 1.15
		if not on_ground: atk_power *= 3.0
	if kit == "tristaff" and String(atk.get("type", "melee")) == "melee":
		match zephyr_mode:
			1: atk["reach"] = float(atk.reach) * 1.07
			2: atk["reach"] = float(atk.reach) * 1.20
			3: atk["reach"] = float(atk.reach) * 0.75
	atk_phase = 0
	_buffered = false
	_queued_light_t = 0.0
	swing_serial += 1
	if float(atk.self_jump) > 0.0 and atk.mode != "leap":
		vel_y = float(atk.self_jump); on_ground = false
	_set_state(S.ATTACK)
	notify_passive_event("attack_started", opponent)
	if aid in ["z", "x", "c", "v"]:
		notify_passive_event("skill_started", opponent)

func _attack_step() -> void:
	var w: float = float(atk.wind) * attack_time_multiplier()
	var ac: float = float(atk.active) * attack_time_multiplier()
	var r: float = float(atk.recover) * attack_time_multiplier()
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
		# FRG12A - explicit AI movement takes precedence over legacy auto-approach
		if state == S.IDLE and auto_approach and brain != null and o and not o.is_down() and dist > ENGAGE and in_move.length_squared() < 0.0001:
			v = walk_speed * status_runtime.movement_multiplier()
			if kit == "greatsword" and garrick_resolve >= 2: v *= 1.20
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

		var steer := 1.0 if state == S.IDLE else 0.5 if state == S.BLOCK else 0.4 if state == S.CHARGE else 0.65 if kit == "kicks" and not on_ground and state == S.ATTACK and atk_id in ["air_l1", "air_l2", "air_l3"] else 0.63 if kit == "assassin" and not on_ground and state == S.ATTACK and atk_id in ["air_l1", "air_l2"] else 0.35 if kit == "chainblade" and state == S.ATTACK and atk_id in ["z", "c"] else 0.0
		# Don't let direct input instantly erase a strong knockback reaction.
		if _knock > 0.2: steer *= 0.35
		var requested := Vector3.ZERO
		if steer > 0.0 and in_move.length_squared() > 0.0001:
			var sprint_now := in_sprint and state == S.IDLE and on_ground
			var speed := move_speed * (SPRINT_MULT if sprint_now else 1.0) * status_runtime.movement_multiplier()
			# FRG19L: approaching with 2+ Resolve grants +20% speed, not sideways retreat speed.
			if kit == "greatsword" and garrick_resolve >= 2 and o != null and not o.is_down() and in_move.normalized().dot(dir) > 0.25:
				speed *= 1.20
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
	# FRG19O — Meteor Fist continues even when struck; HP still decreases.
	if _rook_meteor_armor(): return
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
	# Stuns, clashes, and guard breaks cancel EVERY queued action.
	_holding = false
	_buffered = false
	_queued_skill = ""
	_queued_skill_t = 0.0
	_queued_light_t = 0.0
	_combo_next = "l1"
	_combo_timer = 0.0

func push_back(speed: float) -> void:
	_apply_knock(opponent, speed)

# --- getting hit -------------------------------------------------------------------------

## Returns "none", "miss", "warded", "counter", "parry", "blocked", "guard_break", "hit", "crit" or "ko".
func receive_hit(attacker, a: Dictionary, power: float) -> String:
	if state == S.KO: return "none"
	if invuln_t > 0.0: return "miss"

	# FRG19E - each genuine incoming hit consumes exactly one snowglass crystal.
	if String(look.get("element", "")) == "frost" and roxy_aegis_t > 0.0 and roxy_aegis_charges > 0:
		roxy_aegis_charges -= 1
		model.flash(Color("#baf3ff"), 0.17)
		return "warded"
	if ward_t > 0.0: return "warded"
	if counter_t > 0.0:
		counter_t = 0.0
		# FRG19M — award only after an actual incoming hit triggers Z stance.
		if kit == "katana": kaede_counter_bloom = mini(4, kaede_counter_bloom + 1)
		return "counter"

	# FRG19J Death Feint counters only parryable hits; it never prevents
	# genuinely unblockable attacks or invulnerable misses.
	if kit == "sickle" and veyr_feint_t > 0.0 and not bool(a.get("no_parry", false)):
		veyr_feint_t = 0.0
		veyr_feint_counter = true
		return "counter"

	# FRG19I: Iron Reflection replaces held guard with automatic genuine parries.
	# Unparryable moves still hit normally; normal parry hooks grant the Read.
	if kit == "tonfa" and renji_reflection_t > 0.0 and not bool(a.get("no_parry", false)):
		guard = minf(guard + max_guard * 0.10, max_guard)
		if model != null: model.flash(Color("#d4b0ff"), 0.14)
		return "parry"
	var dmg: float = float(a.dmg) * power * status_runtime.incoming_multiplier()
	# FRG19P: halve HP damage before guard-break chip calculation, not guard loss.
	if kit == "mage" and String(look.get("element", "")) == "water" and marina_bubble_t > 0.0:
		dmg *= 0.5
	# FRG19L: 25% less projectile HP damage when advancing with 2+ Resolve.
	# The metadata is set by Match only for real projectile hits; guard cost remains unchanged.
	if kit == "greatsword" and bool(a.get("_garrick_resolve_defense", false)):
		dmg *= 0.75
	# Staff mastery reduces normal damage; SPLIT grip trades guard for speed.
	if kit == "tristaff": dmg *= 1.08 if zephyr_mode == 1 else 0.90
	if state == S.BLOCK and not (kit == "tristaff" and zephyr_mode == 1):
		if state_t <= parry_window and not bool(a.get("no_parry", false)):
			guard = minf(guard + max_guard * 0.10, max_guard)
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
	# FRG19O — damage taken, but no stun or attack interruption while casting C.
	if _rook_meteor_armor(): return "crit" if last_crit else "hit"

	# Blood Festival grants stun immunity, NOT damage or knockback immunity.
	if kit == "sickle" and veyr_festival_t > 0.0:
		return "crit" if last_crit else "hit"
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
	if _rook_meteor_armor(): return
	_stun = d; _stun_pose = "stagger"; _interrupt_attack(); _set_state(S.STAGGER)

func clash_recoil() -> void:
	if _rook_meteor_armor(): return
	_stun = 0.38; _stun_pose = "clash"; _interrupt_attack(); _apply_knock(opponent, 4.0); _set_state(S.HITSTUN)

func win() -> void:
	if state != S.KO: _set_state(S.WIN)

func heal(amount: float) -> void: hp = minf(hp + amount, max_hp)

func _ko() -> void:
	_set_state(S.KO)
	knocked_out.emit(self)

# --- posing ------------------------------------------------------------------------------

# FRG16B - combat choreography
# Sync combat state to additive skeleton motion; combat stats are unchanged.
func _frg16b_update_choreography() -> void:
	if model == null:
		return
	var action := "idle"
	if state == S.KO:
		action = "hit"
	elif state == S.WIN:
		action = "win"
	elif state == S.HITSTUN:
		action = "hit"
	elif state == S.STAGGER:
		action = "stagger"
	elif state == S.ATTACK:
		action = "attack"
	elif state == S.CHARGE:
		action = "charge"
	elif state == S.BLOCK:
		action = "block"
	elif _dodge_t > 0.0 or _dash_t > 0.0:
		action = "dodge"
	elif not on_ground:
		action = "jump"
	model.choreo_state = action
	model.choreo_weight = 0.0 if action == "idle" else 1.0
	if action == "attack" and not atk.is_empty():
		var total: float = maxf(0.01, (float(atk.get("wind", 0.0)) + float(atk.get("active", 0.0)) + float(atk.get("recover", 0.0))) * attack_time_multiplier())
		model.choreo_progress = clampf(state_t / total, 0.0, 1.0)
	elif action == "dodge":
		model.choreo_progress = 0.5
	elif action == "win":
		model.choreo_progress = 0.5
	else:
		model.choreo_progress = clampf(state_t / 0.45, 0.0, 1.0)

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
