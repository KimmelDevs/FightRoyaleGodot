#!/usr/bin/env python3
"""Fight Royale Godot — Update 18A: Combat Audio Integration.

Run inside your Godot folder:
    python install_18a_combat_audio.py
    python install_18a_combat_audio.py --dry-run

Needs Update 17D. The provided SFX filenames are matched under res://sfx/.
Sound files may remain missing: the game will simply stay silent for those events.
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

TAG = "# FRG18A - combat sound integration"
VERSION = "18A.1"
MATCH = "scripts/match.gd"
AUDIO = "scripts/combat_audio.gd"
CONFIG = "data/audio_events_18a.json"
REPORT = "reports/audio_integration_18a.txt"

EVENTS = {'swing_light': (['fight/fast_sword_whoosh.mp3', 'fight/sword_blade_swish.mp3', 'fight/swift_sword_strike.mp3'], -8, 75), 'swing_heavy': (['fight/metal_hit_woosh.mp3', 'fight/cinematic_whoosh_deep_impact.mp3'], -5, 125), 'swing_fist': (['fight/punch_through_air.mp3', 'fight/quick_hit_through_air.mp3'], -8, 85), 'cast_magic': (['misc/fast_magic_game_spell.mp3', 'misc/arcane_chain_spell.mp3', 'bunker/magic_spell_mystery_whoosh.mp3'], -8, 180), 'arrow': (['fight/arrow_shot_through_air.mp3', 'fight/arrow_whizz_in_battle.mp3'], -8, 95), 'hit_light': (['fight/impact_of_a_blow.mp3', 'fight/body_punch_quick_hit.mp3', 'fight/weak_hit_impact.mp3'], -6, 65), 'hit_heavy': (['fight/heavy_sword_hit.mp3', 'fight/impact_big.mp3', 'fight/hard_and_quick_punch.mp3'], -4, 105), 'block': (['fight/hitting_metal_armor.mp3', 'fight/metal_hammer_hit.mp3'], -7, 120), 'parry': (['fight/sword_metal_strike.mp3', 'fight/metallic_sword_scrape.mp3'], -2, 160), 'clash': (['fight/heavy_sword_smashes_metal.mp3', 'fight/samurai_sword_impact.mp3'], -3, 130), 'guard_break': (['fight/dramatic_metal_explosion_impact.mp3', 'fight/metal_hammer_hit.mp3'], -3, 230), 'dash': (['fight/fast_air_transition_sweep.mp3', 'fight/quick_zoom_impact.mp3'], -12, 170), 'land': (['fight/boot_stomp_on_mud_surface.mp3', 'fight/body_impact_falling_into_the_sand.mp3'], -11, 160), 'explosion': (['fight/explosion_hit.mp3', 'fight/fire_explosion.mp3'], -5, 240), 'lightning': (['fight/fast_thunder_impact.mp3', 'fight/heavy_electric_shockwave_impact.mp3'], -6, 190), 'water': (['fight/water_drop_splashes_in_cave.mp3', 'misc/fairy_water_spell.mp3'], -8, 200), 'ice': (['misc/icicles_spell_whoosh.mp3', 'bunker/dropping_ice_into_a_glass.mp3'], -7, 170), 'fire': (['fight/fire_explosion.mp3', 'misc/explosion_spell.mp3'], -7, 170), 'skill_impact': (['fight/impact_big.mp3', 'fight/strong_close_thunder_explosion.mp3'], -8, 180), 'projectile_clash': (['fight/metallic_impact_with_whip.mp3', 'fight/exciting_fast_hit.mp3'], -6, 140), 'ko': (['fight/falling_hit.mp3', 'fight/impact_heartbeat_deep.mp3'], -5, 700), 'fight_start': (['game_sports/start_match_countdown.mp3', 'fight/introduction_bell_sound.mp3'], -14, 1000), 'victory': (['game_sports/instant_win.mp3', 'game_sports/video_game_win.mp3'], -11, 1000)}
AUDIO_GD = '# FRG18A - Combat sound engine. Safe if SFX are not yet imported.\nclass_name CombatAudio\nextends Node3D\n\nconst CONFIG_PATH := "res://data/audio_events_18a.json"\nconst SOUND_ROOT := "res://sfx/"\nconst MAX_VOICES := 20\n\nvar _events: Dictionary = {}\nvar _streams: Dictionary = {}\nvar _last_ms: Dictionary = {}\nvar _active: Array[Node] = []\n\nfunc _ready() -> void:\n\tif FileAccess.file_exists(CONFIG_PATH):\n\t\tvar parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(CONFIG_PATH))\n\t\tif parsed is Dictionary:\n\t\t\t_events = parsed.get("events", {})\n\nfunc _load_sound(relative: String) -> AudioStream:\n\tif _streams.has(relative):\n\t\treturn _streams[relative] as AudioStream\n\tvar full: String = SOUND_ROOT + relative\n\tif not ResourceLoader.exists(full):\n\t\treturn null\n\tvar sound: AudioStream = load(full) as AudioStream\n\tif sound != null:\n\t\t_streams[relative] = sound\n\treturn sound\n\nfunc play_event(event_name: String, world_position: Vector3 = Vector3.ZERO, spatial: bool = true) -> void:\n\tvar spec: Dictionary = _events.get(event_name, {})\n\tif spec.is_empty():\n\t\treturn\n\tvar now_ms: int = Time.get_ticks_msec()\n\tvar cooldown: int = int(spec.get("cooldown_ms", 0))\n\tif now_ms - int(_last_ms.get(event_name, -1000000)) < cooldown:\n\t\treturn\n\tvar loaded: Array[AudioStream] = []\n\tfor candidate in spec.get("files", []):\n\t\tvar s: AudioStream = _load_sound(String(candidate))\n\t\tif s != null:\n\t\t\tloaded.append(s)\n\tif loaded.is_empty():\n\t\treturn # Files may still be importing; silence is safer than a runtime error.\n\t_last_ms[event_name] = now_ms\n\t# Clean up stale references before enforcing a voice budget.\n\tvar alive: Array[Node] = []\n\tfor previous in _active:\n\t\tif is_instance_valid(previous) and not previous.is_queued_for_deletion():\n\t\t\talive.append(previous)\n\t_active = alive\n\tif _active.size() >= MAX_VOICES:\n\t\tvar oldest: Node = _active.pop_front()\n\t\tif is_instance_valid(oldest):\n\t\t\toldest.queue_free()\n\tvar stream: AudioStream = loaded[randi_range(0, loaded.size() - 1)]\n\tvar volume: float = float(spec.get("volume_db", -8.0))\n\tif spatial:\n\t\tvar player := AudioStreamPlayer3D.new()\n\t\tadd_child(player)\n\t\tplayer.global_position = world_position\n\t\tplayer.stream = stream\n\t\tplayer.volume_db = volume\n\t\tplayer.unit_size = 5.0\n\t\tplayer.max_distance = 34.0\n\t\tplayer.pitch_scale = randf_range(0.97, 1.03)\n\t\tplayer.finished.connect(player.queue_free)\n\t\t_active.append(player)\n\t\tplayer.play()\n\telse:\n\t\tvar player := AudioStreamPlayer.new()\n\t\tadd_child(player)\n\t\tplayer.stream = stream\n\t\tplayer.volume_db = volume\n\t\tplayer.finished.connect(player.queue_free)\n\t\t_active.append(player)\n\t\tplayer.play()\n'


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}; no changes applied")
    return source.replace(old, new, 1)


def patch_match(src: str) -> str:
    if TAG in src:
        return src
    if "# FRG17C - elemental hit and skill VFX" not in src:
        raise RuntimeError("Update 17C is required before 18A.")
    # Keep all insertion anchors from the last checked project revision.
    src = replace_once(src, "extends Node3D\n", "extends Node3D\n" + TAG + "\nconst COMBAT_AUDIO_SCRIPT = preload(\"res://scripts/combat_audio.gd\")\n", "Class header")
    src = replace_once(src, "var fx: Fx\n", "var fx: Fx\nvar audio\n", "Audio field")
    src = replace_once(src, "\tadd_child(fx)\n\tcamera = Camera3D.new()", "\tadd_child(fx)\n\taudio = COMBAT_AUDIO_SCRIPT.new()\n\tadd_child(audio)\n\tcamera = Camera3D.new()", "Audio node creation")
    src = replace_once(src, '\t\tbanner("FIGHT!", Color.WHITE)\n', '\t\tbanner("FIGHT!", Color.WHITE)\n\t\taudio.play_event("fight_start", Vector3.ZERO, false)\n', "Fight start sound")
    src = replace_once(src, '\tf.landed.connect(func(x: Fighter): fx.ring(x.global_position, Color.WHITE, 0.8, 0.25, 0.5))\n', '\tf.landed.connect(func(x: Fighter): fx.ring(x.global_position, Color.WHITE, 0.8, 0.25, 0.5))\n\tf.landed.connect(func(x: Fighter): audio.play_event("land", x.global_position))\n\tf.dashed.connect(func(x: Fighter): audio.play_event("dash", x.global_position))\n', "Landing and dash sounds")
    src = replace_once(src, 'func _on_swing(f: Fighter) -> void:\n\tvar a := f.atk\n', """func _on_swing(f: Fighter) -> void:
\tvar a := f.atk
\tvar audio_type := String(a.get("type", "melee"))
\tvar cue := "swing_light"
\tif audio_type == "projectile":
\t\tcue = "arrow" if f.kit == "bow" else "cast_magic"
\telif audio_type in ["strike", "buff", "blink"]:
\t\tcue = "cast_magic"
\telif f.kit in ["knuckles", "kicks"]:
\t\tcue = "swing_fist"
\telif f.atk_id in ["heavy", "l3", "v"]:
\t\tcue = "swing_heavy"
\taudio.play_event(cue, f.chest())
""", "Swing sounds")
    src = replace_once(src, '\t# FRG17C: visual-only elemental accent for skill impact events.\n', """\t# FRG18A: small selection of per-element and skill-impact sounds.
\tvar style_sound := String(a.get("style", ""))
\tvar element_sound := String(a.get("element", ""))
\tvar cue := "skill_impact"
\tif style_sound in ["explosion", "meteor"]:
\t\tcue = "explosion"
\telif style_sound == "lightning" or element_sound == "lightning":
\t\tcue = "lightning"
\telif element_sound in ["water", "ice", "fire"]:
\t\tcue = element_sound
\taudio.play_event(cue, g)
\t# FRG17C: visual-only elemental accent for skill impact events.
""", "Skill-impact sounds")
    # Use event-specific hooks; do not play a hit for misses or warded damage.
    section_at = src.index('func apply_hit(')
    before, section = src[:section_at], src[section_at:]
    section = replace_once(section, '\t\t"hit", "crit", "ko":\n\t\t\tvar crit := d.last_crit\n', '\t\t"hit", "crit", "ko":\n\t\t\taudio.play_event("hit_heavy" if heavy else "hit_light", hit_pos)\n\t\t\tvar crit := d.last_crit\n', "Hit audio")
    section = replace_once(section, '\t\t"blocked":\n\t\t\tif attacker is Fighter:', '\t\t"blocked":\n\t\t\taudio.play_event("block", shield_pos)\n\t\t\tif attacker is Fighter:', "Block audio")
    section = replace_once(section, '\t\t"parry":\n\t\t\tif attacker is Fighter:', '\t\t"parry":\n\t\t\taudio.play_event("parry", shield_pos)\n\t\t\tif attacker is Fighter:', "Parry audio")
    section = replace_once(section, '\t\t"guard_break":\n\t\t\tfx.combat_guard_break(hit_pos)\n', '\t\t"guard_break":\n\t\t\taudio.play_event("guard_break", hit_pos)\n\t\t\tfx.combat_guard_break(hit_pos)\n', "Guard-break audio")
    section = replace_once(section, '\tfx.combat_clash(pos)\n', '\taudio.play_event("clash", pos)\n\tfx.combat_clash(pos)\n', "Weapon clash audio")
    section = replace_once(section, 'func _on_ko(f: Fighter) -> void:\n', 'func _on_ko(f: Fighter) -> void:\n\taudio.play_event("ko", f.chest())\n', "KO audio")
    section = replace_once(section, '\t\tui_event.emit({"type": "over", "text": result_text, "sub": detail + "  |  R to rematch", "color": result_color})\n', '\t\tui_event.emit({"type": "over", "text": result_text, "sub": detail + "  |  R to rematch", "color": result_color})\n\t\taudio.play_event("victory", Vector3.ZERO, false)\n', "Victory audio")
    src = before + section
    # Intercept 12B projectile cuts and 14A projectile-v-projectile clashes.
    src = replace_once(src, '\t\t\tfx.number(impact + Vector3(0.0, 0.3, 0.0), "CLASH!", Color("#ffe6a0"), 0.65)\n', '\t\t\tfx.number(impact + Vector3(0.0, 0.3, 0.0), "CLASH!", Color("#ffe6a0"), 0.65)\n\t\t\taudio.play_event("projectile_clash", impact)\n', "Projectile clash audio")
    src = replace_once(src, '\t\t\t\tfx.number(cut + Vector3(0, 0.22, 0), "CLASH!", Color("#ffe6a4"), 0.65)\n', '\t\t\t\tfx.number(cut + Vector3(0, 0.22, 0), "CLASH!", Color("#ffe6a4"), 0.65)\n\t\t\t\taudio.play_event("projectile_clash", cut)\n', "Projectile intercept audio")
    return src


def sha(b: bytes | None) -> str | None:
    return hashlib.sha256(b).hexdigest() if b is not None else None


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".frg18a-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def get_changes(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise RuntimeError("Run inside your Godot project directory (project.godot missing).")
    match_path = root / MATCH
    if not match_path.is_file():
        raise RuntimeError("Can't find scripts/match.gd")
    original = match_path.read_text(encoding="utf-8-sig")
    patched = patch_match(original)
    existing_audio = root / AUDIO
    if existing_audio.is_file() and existing_audio.read_text(encoding="utf-8-sig") != AUDIO_GD:
        raise RuntimeError("An existing scripts/combat_audio.gd differs from this update. No files changed.")
    config_file = root / CONFIG
    config = {"version": VERSION, "sfx_root": "res://sfx", "events": {key: {"files": info[0], "volume_db": info[1], "cooldown_ms": info[2]} for key, info in EVENTS.items()}}
    config_bytes = (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode()
    if config_file.is_file():
        # Preserve user-adjusted volumes and sound mappings.
        config_bytes = config_file.read_bytes()
        try:
            d = json.loads(config_bytes)
            if not isinstance(d, dict) or not isinstance(d.get("events"), dict):
                raise ValueError("Unexpected audio config structure")
        except Exception as e:
            raise RuntimeError(f"Existing {CONFIG} is malformed: {e}") from e
    actual_sfx = root / "sfx"
    available = sum(1 for path in actual_sfx.rglob("*.mp3") if path.is_file()) if actual_sfx.is_dir() else 0
    event_files = {f for info in EVENTS.values() for f in info[0]}
    resolved = sum(1 for filename in event_files if (actual_sfx / filename).is_file())
    report = (f"Fight Royale - Update 18A Combat Audio\nSFX folder: {actual_sfx}\n"
              f"MP3 files present: {available}\nEvent-mapped sounds on disk: {resolved}/{len(event_files)}\n"
              f"Event groups: {len(EVENTS)}\n"
              "Sounds are loaded at runtime after Godot imports the MP3 files.\n"
              "Missing sounds are skipped without gameplay failures.\n"
              "Use audio_events_18a.json to adjust event filenames and levels.\n"
              "A future 18B update can add menu UI sounds and audio sliders.\n")
    wanted = {MATCH: patched.encode(), AUDIO: AUDIO_GD.encode(), CONFIG: config_bytes, REPORT: report.encode()}
    return {name: value for name, value in wanted.items() if not (root / name).is_file() or (root / name).read_bytes() != value}


def install(root: Path, updates: dict[str, bytes], dry_run: bool) -> None:
    if not updates:
        print("Update 18A already installed; nothing changed.")
        return
    for relative in updates:
        print("Update:", relative)
    if dry_run:
        print("DRY RUN: no changes applied.")
        return
    backup_dir = root.parent / (root.name + "_backups") / (
        "combat_audio_18a_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    backup_dir.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for rel, contents in updates.items():
        target = root / rel
        original = target.read_bytes() if target.is_file() else None
        manifest["files"][rel] = {"before": sha(original), "after": sha(contents)}
        if original is not None:
            save = backup_dir / "originals" / rel
            save.parent.mkdir(parents=True, exist_ok=True)
            save.write_bytes(original)
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    finished = []
    try:
        for rel, contents in updates.items():
            atomic_write(root / rel, contents)
            finished.append(rel)
    except Exception:
        for rel in reversed(finished):
            saved = backup_dir / "originals" / rel
            if saved.is_file():
                atomic_write(root / rel, saved.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print("Update 18A installed. Backup:", backup_dir)


def restore(root: Path, folder: str) -> None:
    backup_dir = Path(folder).expanduser().resolve()
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest.get("project", "")).resolve() != root:
        raise RuntimeError("Backup isn't from Update 18A for this project.")
    for rel, entry in manifest["files"].items():
        now = (root / rel).read_bytes() if (root / rel).is_file() else None
        if sha(now) != entry["after"]:
            raise RuntimeError("Changed since installation, refusing to restore: " + rel)
        old = backup_dir / "originals" / rel
        if entry["before"] is not None and (not old.is_file() or sha(old.read_bytes()) != entry["before"]):
            raise RuntimeError("Original backup missing or corrupt: " + rel)
    for rel in manifest["files"]:
        original = backup_dir / "originals" / rel
        if original.is_file():
            atomic_write(root / rel, original.read_bytes())
        else:
            (root / rel).unlink(missing_ok=True)
    print("Update 18A restored.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fight Royale Godot — Update 18A: Combat Audio")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", metavar="BACKUP_FOLDER")
    args = parser.parse_args()
    root = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(root, args.restore)
        else:
            install(root, get_changes(root), args.dry_run)
        return 0
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
