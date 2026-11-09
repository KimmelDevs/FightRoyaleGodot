extends Node
## FRG15A - status and passive runtime
# FRG15C - damage/healing/cleanse status support
## Generic status effects and event-triggered passives, with *no* default character passives.
## Character installers can add triggers to data/passive_profiles_15a.json.

const RULES_FILE := "res://data/status_rules_15a.json"
const PROFILES_FILE := "res://data/passive_profiles_15a.json"

var _host = null
var _char_id := ""
var _rules: Dictionary = {}
var _triggers: Dictionary = {}
var _effects: Dictionary = {} # name -> {stacks:int, left:float}
var _event_ready: Dictionary = {} # per-event cooldown deadlines
# FRG15B - control status protections
var _control_ready: Dictionary = {} # next legal application time for control statuses
var _clock := 0.0
var _dot_bank := 0.0

func bind_host(host: Node, fighter_id: String) -> void:
	_host = host
	_char_id = fighter_id
	var rules_data: Variant = _read_json(RULES_FILE)
	if rules_data is Dictionary:
		_rules = rules_data.get("effects", {})
	var profiles_data: Variant = _read_json(PROFILES_FILE)
	if profiles_data is Dictionary:
		var profiles: Dictionary = profiles_data.get("profiles", {})
		var entry: Variant = profiles.get(_char_id, {})
		if entry is Dictionary:
			_triggers = entry.get("triggers", {})

func _read_json(path: String) -> Variant:
	if not FileAccess.file_exists(path):
		push_warning("Fight Royale: missing status configuration " + path)
		return {}
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not (value is Dictionary):
		push_warning("Fight Royale: invalid status configuration " + path)
		return {}
	return value

func apply_effect(effect_id: String, stacks: int = 1, seconds: float = -1.0) -> bool:
	if _host == null or not _rules.has(effect_id) or stacks <= 0:
		return false
	if _host.is_down():
		return false
	var rule: Dictionary = _rules[effect_id]
	var cap: int = maxi(int(rule.get("max_stacks", 1)), 1)
	var duration: float = seconds if seconds > 0.0 else float(rule.get("duration", 3.0))
	if duration <= 0.0:
		return false
	var control_id: String = String(rule.get("control", ""))
	if control_id != "" and _clock < float(_control_ready.get(effect_id, -1.0)):
		return false
	var previous: Dictionary = _effects.get(effect_id, {})
	_effects[effect_id] = {
		"stacks": mini(int(previous.get("stacks", 0)) + stacks, cap),
		"left": maxf(float(previous.get("left", 0.0)), duration)
	}
	if control_id != "":
		# Cooldown begins after the *applied* effect has elapsed.
		_control_ready[effect_id] = _clock + duration + maxf(float(rule.get("immunity_after", 0.0)), 0.0)
	return true

func clear_effect(effect_id: String) -> void:
	_effects.erase(effect_id)

func cleanse_negative(max_count: int = -1) -> int:
	# -1 clears every debuff; positive values remove at most that many kinds.
	# Return the number of distinct effects removed; immunity timers stay intact.
	var removed := 0
	if max_count == 0:
		return 0
	for effect_id in _effects.keys():
		var rule: Dictionary = _rules.get(effect_id, {})
		if String(rule.get("category", "")) != "debuff":
			continue
		_effects.erase(effect_id)
		removed += 1
		if max_count > 0 and removed >= max_count:
			break
	return removed

func clear_all() -> void:
	_effects.clear()
	_event_ready.clear()
	_control_ready.clear()
	_dot_bank = 0.0

func has_effect(effect_id: String) -> bool:
	return _effects.has(effect_id) and int(_effects[effect_id].get("stacks", 0)) > 0

func control_blocks(action: String) -> bool:
	# Called after brain input is set but before actions are processed.
	for effect_id in _effects:
		var rule: Dictionary = _rules.get(effect_id, {})
		var kind: String = String(rule.get("control", ""))
		if kind == "freeze":
			return true
		if kind == "root" and action == "movement":
			return true
		if kind == "silence" and action == "skill":
			return true
	return false

func stacks_of(effect_id: String) -> int:
	return int(_effects.get(effect_id, {}).get("stacks", 0))

func modify(stat_id: String) -> float:
	var total := 0.0
	for effect_id in _effects:
		var rule: Dictionary = _rules.get(effect_id, {})
		var mods: Dictionary = rule.get("modifiers", {})
		total += float(mods.get(stat_id, 0.0)) * stacks_of(effect_id)
	return clampf(total, -0.75, 1.5)

func movement_multiplier() -> float:
	return clampf(1.0 + modify("movement"), 0.25, 2.5)

func attack_time_multiplier() -> float:
	return 1.0 / clampf(1.0 + modify("attack_speed"), 0.3, 2.5)

func guard_regen_multiplier() -> float:
	return clampf(1.0 + modify("guard_regen"), 0.0, 3.0)

func outgoing_multiplier() -> float:
	return clampf(1.0 + modify("outgoing_damage"), 0.25, 2.5)

func incoming_multiplier() -> float:
	return clampf(1.0 + modify("incoming_damage"), 0.25, 2.5)

func short_label() -> String:
	var labels: Array[String] = []
	for effect_id in _effects:
		var rule: Dictionary = _rules.get(effect_id, {})
		var stack_count := stacks_of(effect_id)
		var label: String = String(rule.get("label", effect_id))
		labels.append(label + ("x%d" % stack_count if stack_count > 1 else ""))
		if labels.size() == 2:
			break
	return ", ".join(PackedStringArray(labels))

func step(dt: float) -> void:
	if dt <= 0.0 or _host == null:
		return
	_clock += dt
	if _host.is_down():
		clear_all()
		return
	for effect_id in _effects.keys():
		var info: Dictionary = _effects[effect_id]
		info["left"] = float(info.get("left", 0.0)) - dt
		if float(info["left"]) <= 0.0:
			_effects.erase(effect_id)
		else:
			_effects[effect_id] = info
	_dot_bank += dt
	while _dot_bank >= 0.25:
		_dot_bank -= 0.25
		var damage := 0.0
		var healing := 0.0
		for effect_id in _effects:
			var rule: Dictionary = _rules.get(effect_id, {})
			var stack_count: int = stacks_of(effect_id)
			damage += maxf(float(rule.get("dot_hp_fraction_per_second", 0.0)), 0.0) * stack_count * 0.25 * float(_host.max_hp)
			healing += maxf(float(rule.get("hot_hp_fraction_per_second", 0.0)), 0.0) * stack_count * 0.25 * float(_host.max_hp)
		if damage > 0.0:
			_host.receive_status_damage(damage)
			if _host.is_down():
				clear_all()
				break
		if healing > 0.0 and _host.has_method("heal"):
			_host.heal(healing)

func on_event(event_id: String, other: Node = null) -> void:
	if _host == null or _host.is_down():
		return
	var entries: Variant = _triggers.get(event_id, [])
	if not (entries is Array):
		return
	for idx in range(entries.size()):
		var item: Variant = entries[idx]
		if not (item is Dictionary):
			continue
		var effect_id: String = String(item.get("effect", ""))
		if not _rules.has(effect_id):
			continue
		var token := event_id + ":" + str(idx)
		if _clock < float(_event_ready.get(token, -1.0)):
			continue
		if randf() > clampf(float(item.get("chance", 1.0)), 0.0, 1.0):
			continue
		var target: Node = other if String(item.get("target", "self")) == "opponent" else _host
		if not is_instance_valid(target) or not target.has_method("add_status"):
			continue
		var count: int = maxi(int(item.get("stacks", 1)), 1)
		var duration: float = float(item.get("duration", -1.0))
		if bool(target.call("add_status", effect_id, count, duration)):
			_event_ready[token] = _clock + maxf(float(item.get("cooldown", 0.0)), 0.0)
