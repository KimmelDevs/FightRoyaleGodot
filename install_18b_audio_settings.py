#!/usr/bin/env python3
"""Fight Royale Godot — 18B: UI sounds and saved audio sliders.

Run from your Godot project directory:
    python install_18b_audio_settings.py
    python install_18b_audio_settings.py --dry-run
    python install_18b_audio_settings.py --restore BACKUP_DIR

Requires 18A. Creates audio settings, separate Combat/Clash/UI/Music buses,
menu sound cues and audio sliders. Does not touch VRMs, imported audio or combat stats.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

VERSION = "18B.1"
TAG = "# FRG18B - UI sounds and persistent audio levels"
PROJECT = "project.godot"
MAIN = "scripts/main.gd"
COMBAT_AUDIO = "scripts/combat_audio.gd"
SETTINGS = "scripts/audio_settings.gd"
REPORT = "reports/audio_settings_18b.txt"

UI_SOUNDS = {
    "ui_select": ["ui/interface_option_select.mp3", "ui/select_click.mp3", "ui/classic_click.mp3"],
    "ui_back": ["ui/software_interface_back.mp3", "ui/mouse_click_close.mp3"],
    "ui_start": ["ui/software_interface_start.mp3", "ui/sci_fi_confirmation.mp3"],
    "ui_confirm": ["ui/confirmation_tone.mp3", "ui/modern_technology_select.mp3"],
}

AUDIO_SETTINGS_GD = r'''# FRG18B - UI sounds and persistent audio levels
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
'''


def once(source: str, before: str, after: str, context: str) -> str:
    found = source.count(before)
    if found != 1:
        raise RuntimeError(f"{context}: expected exactly one anchor; found {found}. No project files changed.")
    return source.replace(before, after, 1)


def patch_project(src: str) -> str:
    if 'AudioSettings="*res://scripts/audio_settings.gd"' in src:
        return src
    return once(src, 'Profile="*res://scripts/profile.gd"',
                'Profile="*res://scripts/profile.gd"\nAudioSettings="*res://scripts/audio_settings.gd"',
                "AudioSettings autoload")


def patch_combat_audio(src: str) -> str:
    if TAG in src:
        return src
    if "# FRG18A - Combat sound engine" not in src:
        raise RuntimeError("Install Update 18A before 18B (scripts/combat_audio.gd missing marker).")
    src = once(src, 'class_name CombatAudio\n', 'class_name CombatAudio\n' + TAG + '\n', "CombatAudio header")
    src = once(src,
        '\t\tplayer.stream = stream\n\t\tplayer.volume_db = volume\n\t\tplayer.unit_size = 5.0',
        '\t\tplayer.stream = stream\n\t\tplayer.bus = "FRG_CLASH" if event_name in ["clash", "parry", "guard_break", "projectile_clash"] else "FRG_SFX"\n\t\tplayer.volume_db = volume\n\t\tplayer.unit_size = 5.0',
        "Spatial combat audio bus")
    src = once(src,
        '\t\tplayer.stream = stream\n\t\tplayer.volume_db = volume\n\t\tplayer.finished.connect(player.queue_free)',
        '\t\tplayer.stream = stream\n\t\tplayer.bus = "FRG_SFX"\n\t\tplayer.volume_db = volume\n\t\tplayer.finished.connect(player.queue_free)',
        "Nonspatial combat audio bus")
    return src


AUDIO_SECTION = '''# FRG18B - UI sounds and persistent audio levels
func _set_audio_level(percent: float, channel: String) -> void:
    AudioSettings.set_level(channel, percent / 100.0)

func _audio_settings_section(parent: VBoxContainer) -> void:
    _title(parent, "Audio", 24)
    var audio_grid := GridContainer.new()
    audio_grid.columns = 2
    audio_grid.add_theme_constant_override("h_separation", 20)
    audio_grid.add_theme_constant_override("v_separation", 5)
    parent.add_child(audio_grid)
    for item in [["master", "Master"], ["combat", "Combat SFX"], ["clashes", "Parries / Clashes"], ["ui", "Menu Sounds"], ["music", "Music (future)"]]:
        var channel: String = String(item[0])
        _text(audio_grid, String(item[1]), 16)
        var slider := HSlider.new()
        slider.custom_minimum_size = Vector2(360, 23)
        slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        slider.min_value = 0.0
        slider.max_value = 100.0
        slider.step = 1.0
        slider.value = AudioSettings.get_level(channel) * 100.0
        slider.value_changed.connect(_set_audio_level.bind(channel))
        audio_grid.add_child(slider)
    _text(parent, "Changes apply instantly and are saved automatically.", 13)

'''


def patch_main(src: str) -> str:
    if TAG in src:
        return src
    if '## FIGHT_ROYALE_MODES_V02' not in src:
        raise RuntimeError("Expected Update 02+ main menu not found.")
    # Make sure references are created only after the AudioSettings autoload exists.
    src = once(src,
        '\tif action.is_valid():\n\t\tbutton.pressed.connect(action)\n\tparent.add_child(button)',
        '''\t# FRG18B: audio persists even as this menu is replaced.
\tbutton.pressed.connect(func():
\t\tvar cue := "ui_select"
\t\tif value.begins_with("Back"):
\t\t\tcue = "ui_back"
\t\telif value == "START FIGHT":
\t\t\tcue = "ui_start"
\t\tAudioSettings.play_ui(cue))
\tif action.is_valid():
\t\tbutton.pressed.connect(action)
\tparent.add_child(button)''',
        "Menu click sounds")
    src = once(src,
        'func show_settings() -> void:\n\tvar v := _screen()\n\t_title(v, "Settings — Controls")',
        'func show_settings() -> void:\n\tvar v := _screen()\n\t_title(v, "Settings — Controls & Audio")\n\t_audio_settings_section(v)',
        "Settings audio sliders")
    src = once(src, 'func _begin_rebind(action: String, slot: int, button: Button) -> void:',
               AUDIO_SECTION + 'func _begin_rebind(action: String, slot: int, button: Button) -> void:',
               "Audio slider implementation")
    return src


def hash_bytes(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".frg18b-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def changes_for(root: Path) -> dict[str, bytes]:
    if not (root / PROJECT).is_file():
        raise RuntimeError("Run from the Godot project directory containing project.godot.")
    if not (root / COMBAT_AUDIO).is_file() or not (root / MAIN).is_file():
        raise RuntimeError("Missing scripts/combat_audio.gd or scripts/main.gd; install Update 18A first.")
    project = patch_project((root / PROJECT).read_text(encoding="utf-8-sig"))
    combat = patch_combat_audio((root / COMBAT_AUDIO).read_text(encoding="utf-8-sig"))
    menu = patch_main((root / MAIN).read_text(encoding="utf-8-sig"))
    settings_file = root / SETTINGS
    if settings_file.is_file() and settings_file.read_text(encoding="utf-8-sig") != AUDIO_SETTINGS_GD:
        raise RuntimeError("Existing scripts/audio_settings.gd differs from 18B installer; refusing to overwrite custom code.")
    sound_folder = root / "sfx"
    matches = {event: sum((sound_folder / filename).is_file() for filename in files)
               for event, files in UI_SOUNDS.items()}
    report = ("Fight Royale — Update 18B UI Audio and Volume Settings\n"
              "Master / Combat / Parries & Clashes / UI / Music (future) sliders appear in Settings.\n"
              "Audio volume persists in user://fight_royale_audio.cfg.\n"
              "Separate FRG_SFX, FRG_CLASH, FRG_UI, FRG_MUSIC buses are created at runtime.\n"
              "Menu buttons play UI cues; missing files are silently skipped.\n"
              "Music bus is ready, but no music playback is added in this release.\n"
              f"UI SFX files present: {sum(matches.values())}/{sum(map(len, UI_SOUNDS.values()))}\n"
              + "\n".join(f"  {event}: {count} candidate file(s)" for event, count in matches.items()) + "\n")
    target = {
        PROJECT: project.encode(),
        COMBAT_AUDIO: combat.encode(),
        MAIN: menu.encode(),
        SETTINGS: AUDIO_SETTINGS_GD.encode(),
        REPORT: report.encode(),
    }
    return {name: data for name, data in target.items()
            if not (root / name).is_file() or (root / name).read_bytes() != data}


def install(root: Path, desired: dict[str, bytes], dry_run: bool) -> None:
    if not desired:
        print("18B already installed. No changes.")
        return
    for name in desired:
        print("Update:", name)
    if dry_run:
        print("DRY RUN: no files changed.")
        return
    backup_dir = root.parent / (root.name + "_backups") / (
        "audio_settings_18b_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    backup_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict = {"version": VERSION, "project": str(root), "files": {}}
    for name, contents in desired.items():
        before = (root / name).read_bytes() if (root / name).is_file() else None
        manifest["files"][name] = {"before": hash_bytes(before), "after": hash_bytes(contents)}
        if before is not None:
            original = backup_dir / "originals" / name
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(before)
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    written = []
    try:
        for name, contents in desired.items():
            atomic_write(root / name, contents)
            written.append(name)
    except Exception:
        for name in reversed(written):
            old = backup_dir / "originals" / name
            if old.is_file():
                atomic_write(root / name, old.read_bytes())
            else:
                (root / name).unlink(missing_ok=True)
        raise
    print("Update 18B installed. Backup:", backup_dir)


def restore(root: Path, folder: str) -> None:
    backup_dir = Path(folder).expanduser().resolve()
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest.get("project", "")).resolve() != root:
        raise RuntimeError("This is not an 18B backup of the current project.")
    for name, entry in manifest["files"].items():
        now = (root / name).read_bytes() if (root / name).is_file() else None
        if hash_bytes(now) != entry["after"]:
            raise RuntimeError("Cannot restore file changed since installation: " + name)
        old = backup_dir / "originals" / name
        if entry["before"] is not None and (not old.is_file() or hash_bytes(old.read_bytes()) != entry["before"]):
            raise RuntimeError("Backup is missing or damaged: " + name)
    for name in manifest["files"]:
        old = backup_dir / "originals" / name
        if old.is_file():
            atomic_write(root / name, old.read_bytes())
        else:
            (root / name).unlink(missing_ok=True)
    print("Restored Update 18B backup.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fight Royale Godot — 18B: UI sounds and audio settings")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", metavar="BACKUP_FOLDER")
    args = parser.parse_args()
    root = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(root, args.restore)
        else:
            install(root, changes_for(root), args.dry_run)
        return 0
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
