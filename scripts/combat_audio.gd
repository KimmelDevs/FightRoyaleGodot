# FRG18A - Combat sound engine. Safe if SFX are not yet imported.
class_name CombatAudio
# FRG18B - UI sounds and persistent audio levels
extends Node3D

const CONFIG_PATH := "res://data/audio_events_18a.json"
const SOUND_ROOT := "res://sfx/"
const PROFILES_18C_PATH := "res://data/audio_profiles_18c.json"
const MAX_VOICES := 20

var _events: Dictionary = {}
var _streams: Dictionary = {}
var _last_ms: Dictionary = {}
var _active: Array[Node] = []
var _swing_kits: Dictionary = {}
var _elemental_special_hits: bool = true

func _ready() -> void:
	if FileAccess.file_exists(CONFIG_PATH):
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(CONFIG_PATH))
		if parsed is Dictionary:
			_events = parsed.get("events", {})
	if FileAccess.file_exists(PROFILES_18C_PATH):
		var extra: Variant = JSON.parse_string(FileAccess.get_file_as_string(PROFILES_18C_PATH))
		if extra is Dictionary:
			_swing_kits = extra.get("swing_kits", {})
			_elemental_special_hits = bool(extra.get("elemental_special_hits", true))
			var new_events: Variant = extra.get("new_events", {})
			if new_events is Dictionary:
				# Keep existing 18A sound mappings and their chosen volumes.
				_events.merge(new_events, false)

# FRG18C - per-fighter and elemental combat audio
# Source IDs make CPU A and CPU B independent: their swings no longer mute one another.
func play_attack_swing(kit: String, attack_id: String, attack: Dictionary, world_pos: Vector3, source_id: int) -> void:
    var attack_type: String = String(attack.get("type", "melee"))
    var cue := "swing_light"
    if attack_type == "projectile":
        cue = "arrow" if kit == "bow" else "cast_magic"
    elif attack_type in ["strike", "buff", "blink"]:
        cue = "cast_magic"
    elif kit in ["knuckles", "kicks"]:
        cue = "swing_fist"
    elif attack_id in ["heavy", "l3", "v"]:
        cue = "swing_heavy"
    elif _swing_kits.has(kit):
        cue = String(_swing_kits[kit])
    play_event(cue, world_pos, true, source_id)

func play_special_elemental_hit(element: String, world_pos: Vector3, source_id: int, is_special: bool) -> void:
    if not is_special or not _elemental_special_hits:
        return
    var key := "element_" + element.to_lower()
    if _events.has(key):
        play_event(key, world_pos, true, source_id)

func _load_sound(relative: String) -> AudioStream:
	if _streams.has(relative):
		return _streams[relative] as AudioStream
	var full: String = SOUND_ROOT + relative
	if not ResourceLoader.exists(full):
		return null
	var sound: AudioStream = load(full) as AudioStream
	if sound != null:
		_streams[relative] = sound
	return sound

func play_event(event_name: String, world_position: Vector3 = Vector3.ZERO, spatial: bool = true, source_id: int = 0) -> void:
	var spec: Dictionary = _events.get(event_name, {})
	if spec.is_empty():
		return
	var now_ms: int = Time.get_ticks_msec()
	var cooldown: int = int(spec.get("cooldown_ms", 0))
	var throttle_key: String = "%s|%d" % [event_name, source_id]
	if now_ms - int(_last_ms.get(throttle_key, -1000000)) < cooldown:
		return
	var loaded: Array[AudioStream] = []
	for candidate in spec.get("files", []):
		var s: AudioStream = _load_sound(String(candidate))
		if s != null:
			loaded.append(s)
	if loaded.is_empty():
		return # Files may still be importing; silence is safer than a runtime error.
	_last_ms[throttle_key] = now_ms
	# Clean up stale references before enforcing a voice budget.
	var alive: Array[Node] = []
	for previous in _active:
		if is_instance_valid(previous) and not previous.is_queued_for_deletion():
			alive.append(previous)
	_active = alive
	if _active.size() >= MAX_VOICES:
		var oldest: Node = _active.pop_front()
		if is_instance_valid(oldest):
			oldest.queue_free()
	var stream: AudioStream = loaded[randi_range(0, loaded.size() - 1)]
	var volume: float = float(spec.get("volume_db", -8.0))
	if spatial:
		var player := AudioStreamPlayer3D.new()
		add_child(player)
		player.global_position = world_position
		player.stream = stream
		player.bus = "FRG_CLASH" if event_name in ["clash", "parry", "guard_break", "projectile_clash"] else "FRG_SFX"
		player.volume_db = volume
		player.unit_size = 5.0
		player.max_distance = 34.0
		player.pitch_scale = randf_range(0.97, 1.03)
		player.finished.connect(player.queue_free)
		_active.append(player)
		player.play()
	else:
		var player := AudioStreamPlayer.new()
		add_child(player)
		player.stream = stream
		player.bus = "FRG_SFX"
		player.volume_db = volume
		player.finished.connect(player.queue_free)
		_active.append(player)
		player.play()
