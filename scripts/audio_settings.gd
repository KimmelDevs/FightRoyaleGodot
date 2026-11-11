# FRG18B - UI sounds and persistent audio levels
extends Node
## Audio buses and volumes persist in user://, not inside the project assets.
## CombatAudio sends sounds to FRG_SFX / FRG_CLASH; UI cues use FRG_UI.

const SAVE_PATH := "user://fight_royale_audio.cfg"
const SOUND_ROOT := "res://sfx/"
const BUS_NAMES := {"combat": "FRG_SFX", "clashes": "FRG_CLASH", "ui": "FRG_UI", "music": "FRG_MUSIC"}
const UI_FILES := {
    "ui_select": ["ui/interface_option_select.mp3", "ui/select_click.mp3", "ui/classic_click.mp3"],
    "ui_back": ["ui/software_interface_back.mp3", "ui/mouse_click_close.mp3"],
    "ui_start": ["ui/software_interface_start.mp3", "ui/sci_fi_confirmation.mp3"],
    "ui_confirm": ["ui/confirmation_tone.mp3", "ui/modern_technology_select.mp3"],
}

var levels: Dictionary = {"master": 0.85, "combat": 0.85, "clashes": 0.85, "ui": 0.60, "music": 0.65}
var _sounds: Dictionary = {}
var _voices: Array[AudioStreamPlayer] = []

func _ready() -> void:
    for bus_name in BUS_NAMES.values():
        _ensure_bus(String(bus_name))
    _load_settings()
    for key in levels.keys():
        _apply_level(String(key))

func _ensure_bus(bus_name: String) -> void:
    if AudioServer.get_bus_index(bus_name) != -1:
        return
    AudioServer.add_bus()
    var index: int = AudioServer.get_bus_count() - 1
    AudioServer.set_bus_name(index, bus_name)
    AudioServer.set_bus_send(index, "Master")

func _load_settings() -> void:
    var settings := ConfigFile.new()
    if settings.load(SAVE_PATH) != OK:
        return
    for key in levels.keys():
        levels[key] = clampf(float(settings.get_value("audio", key, levels[key])), 0.0, 1.0)

func get_level(channel: String) -> float:
    return float(levels.get(channel, 1.0))

func set_level(channel: String, level: float) -> void:
    if not levels.has(channel):
        return
    levels[channel] = clampf(level, 0.0, 1.0)
    _apply_level(channel)
    var settings := ConfigFile.new()
    for key in levels.keys():
        settings.set_value("audio", String(key), levels[key])
    var error: Error = settings.save(SAVE_PATH)
    if error != OK:
        push_warning("Fight Royale: audio preferences could not be saved: %s" % error)

func _apply_level(channel: String) -> void:
    var bus_name := "Master" if channel == "master" else String(BUS_NAMES.get(channel, ""))
    if bus_name.is_empty():
        return
    var index: int = AudioServer.get_bus_index(bus_name)
    if index == -1:
        return
    var level: float = float(levels.get(channel, 1.0))
    AudioServer.set_bus_mute(index, level < 0.001)
    AudioServer.set_bus_volume_db(index, linear_to_db(maxf(level, 0.001)))

func _find_sound(event_name: String) -> AudioStream:
    if _sounds.has(event_name):
        return _sounds[event_name] as AudioStream
    var candidates: Array = UI_FILES.get(event_name, [])
    for relative in candidates:
        var full_path: String = SOUND_ROOT + String(relative)
        if not ResourceLoader.exists(full_path):
            continue
        var audio: AudioStream = load(full_path) as AudioStream
        if audio != null:
            _sounds[event_name] = audio
            return audio
    return null

func play_ui(event_name: String) -> void:
    var stream: AudioStream = _find_sound(event_name)
    if stream == null:
        return # Missing / not yet imported sounds are safe.
    var live: Array[AudioStreamPlayer] = []
    for voice in _voices:
        if is_instance_valid(voice) and not voice.is_queued_for_deletion():
            live.append(voice)
    _voices = live
    if _voices.size() >= 5:
        var oldest: AudioStreamPlayer = _voices.pop_front()
        if is_instance_valid(oldest):
            oldest.queue_free()
    var player := AudioStreamPlayer.new()
    add_child(player)
    player.bus = "FRG_UI"
    player.stream = stream
    player.volume_db = -7.0
    player.finished.connect(player.queue_free)
    _voices.append(player)
    player.play()
