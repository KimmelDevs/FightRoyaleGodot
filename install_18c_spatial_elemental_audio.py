#!/usr/bin/env python3
"""Fight Royale Godot — Update 18C: per-fighter and elemental combat audio.

Run in the Godot project folder:
    python install_18c_spatial_elemental_audio.py
    python install_18c_spatial_elemental_audio.py --dry-run
    python install_18c_spatial_elemental_audio.py --restore PATH_TO_BACKUP

Requires Update 18B (and the combat audio engine from 18A).
Adds independent sound cooldowns for both fighters, weapon-style swing cues,
and quiet elemental accents on successful special-attack hits. Combat stats,
animation, physics and VRM models are untouched.
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

VERSION = "18C.1"
TAG = "# FRG18C - per-fighter and elemental combat audio"
MATCH_MARKER = "# FRG18C: independent per-fighter swing audio, with kit-aware cues."
AUDIO = "scripts/combat_audio.gd"
MATCH = "scripts/match.gd"
PROFILE = "data/audio_profiles_18c.json"
REPORT = "reports/spatial_elemental_audio_18c.txt"

EXTRA_EVENTS = {
    "element_fire":      {"files": ["fight/fire_explosion.mp3", "misc/explosion_spell.mp3"], "volume_db": -17, "cooldown_ms": 175},
    "element_lightning": {"files": ["bunker/futuristic_electricity_sparks.mp3", "fight/fast_thunder_impact.mp3"], "volume_db": -17, "cooldown_ms": 175},
    "element_ice":       {"files": ["misc/icicles_spell_whoosh.mp3", "bunker/dropping_ice_into_a_glass.mp3"], "volume_db": -17, "cooldown_ms": 175},
    "element_water":     {"files": ["misc/fairy_water_spell.mp3", "fight/water_drop_splashes_in_cave.mp3"], "volume_db": -17, "cooldown_ms": 175},
    "element_wind":      {"files": ["fight/fast_air_transition_sweep.mp3", "fight/quick_zoom_impact.mp3"], "volume_db": -18, "cooldown_ms": 175},
    "element_earth":     {"files": ["fight/apocalyptic_stomp_impact.mp3", "fight/underground_explosion_impact_echo.mp3"], "volume_db": -19, "cooldown_ms": 200},
    "element_light":     {"files": ["fight/shot_light_energy_flowing.mp3", "game_sports/sword_magic_drag.mp3"], "volume_db": -18, "cooldown_ms": 175},
    "element_dark":      {"files": ["misc/arcane_chain_spell.mp3", "fight/magic_whip_swell.mp3"], "volume_db": -18, "cooldown_ms": 175},
}

PROFILES = {
    "version": VERSION,
    "elemental_special_hits": True,
    "new_events": EXTRA_EVENTS,
    "swing_kits": {
        "knuckles": "swing_fist", "kicks": "swing_fist",
        "greatsword": "swing_heavy", "hammer": "swing_heavy",
        "bow": "arrow", "staff": "swing_light",
        "katana": "swing_light", "daggers": "swing_light",
        "scythe": "swing_heavy", "glaive": "swing_heavy",
    },
}

# Insert only in known releases. Unknown or locally edited script versions fail
# safely with a descriptive error instead of corrupting the project.
def once(source: str, old: str, new: str, label: str) -> str:
    n = source.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor; found {n}. No files modified.")
    return source.replace(old, new, 1)


NEW_METHODS = r'''# FRG18C - per-fighter and elemental combat audio
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

'''


def patch_audio(src: str) -> str:
    if TAG in src:
        return src
    if "# FRG18B - UI sounds and persistent audio levels" not in src or "# FRG18A - Combat sound engine" not in src:
        raise RuntimeError("Install 18A and 18B before 18C (combat audio engine markers not found).")
    src = once(src,
        'const SOUND_ROOT := "res://sfx/"\n',
        'const SOUND_ROOT := "res://sfx/"\nconst PROFILES_18C_PATH := "res://data/audio_profiles_18c.json"\n',
        "18C config path")
    src = once(src,
        'var _active: Array[Node] = []\n',
        'var _active: Array[Node] = []\nvar _swing_kits: Dictionary = {}\nvar _elemental_special_hits: bool = true\n',
        "18C profile fields")
    src = once(src,
        '\t\t\t_events = parsed.get("events", {})\n',
        '''\t\t\t_events = parsed.get("events", {})
\tif FileAccess.file_exists(PROFILES_18C_PATH):
\t\tvar extra: Variant = JSON.parse_string(FileAccess.get_file_as_string(PROFILES_18C_PATH))
\t\tif extra is Dictionary:
\t\t\t_swing_kits = extra.get("swing_kits", {})
\t\t\t_elemental_special_hits = bool(extra.get("elemental_special_hits", true))
\t\t\tvar new_events: Variant = extra.get("new_events", {})
\t\t\tif new_events is Dictionary:
\t\t\t\t# Keep existing 18A sound mappings and their chosen volumes.
\t\t\t\t_events.merge(new_events, false)
''',
        "18C config loading")
    src = once(src,
        'func play_event(event_name: String, world_position: Vector3 = Vector3.ZERO, spatial: bool = true) -> void:\n',
        'func play_event(event_name: String, world_position: Vector3 = Vector3.ZERO, spatial: bool = true, source_id: int = 0) -> void:\n',
        "18C optional source argument")
    src = once(src,
        '\tvar cooldown: int = int(spec.get("cooldown_ms", 0))\n\tif now_ms - int(_last_ms.get(event_name, -1000000)) < cooldown:\n',
        '\tvar cooldown: int = int(spec.get("cooldown_ms", 0))\n\tvar throttle_key: String = "%s|%d" % [event_name, source_id]\n\tif now_ms - int(_last_ms.get(throttle_key, -1000000)) < cooldown:\n',
        "18C per-actor sound throttle")
    src = once(src,
        '\t_last_ms[event_name] = now_ms\n',
        '\t_last_ms[throttle_key] = now_ms\n',
        "18C last sound timestamp")
    src = once(src,
        'func _load_sound(relative: String) -> AudioStream:\n',
        NEW_METHODS + 'func _load_sound(relative: String) -> AudioStream:\n',
        "18C audio methods")
    return src


def patch_match(src: str) -> str:
    if MATCH_MARKER in src:
        return src
    if "# FRG18A - combat sound integration" not in src:
        raise RuntimeError("Missing 18A match audio hooks; install 18A first.")
    old_swing = '''\tvar audio_type := String(a.get("type", "melee"))
\tvar cue := "swing_light"
\tif audio_type == "projectile":
\t\tcue = "arrow" if f.kit == "bow" else "cast_magic"
\telif audio_type in ["strike", "buff", "blink"]:
\t\tcue = "cast_magic"
\telif f.kit in ["knuckles", "kicks"]:
\t\tcue = "swing_fist"
\telif f.atk_id in ["heavy", "l3", "v"]:
\t\tcue = "swing_heavy"
\taudio.play_event(cue, f.chest())'''
    new_swing = '''\t# FRG18C: independent per-fighter swing audio, with kit-aware cues.
\taudio.play_attack_swing(String(f.kit), String(f.atk_id), a, f.chest(), f.get_instance_id())'''
    src = once(src, old_swing, new_swing, "18C skill and attack audio routing")
    src = once(src,
        '\t\t\taudio.play_event("hit_heavy" if heavy else "hit_light", hit_pos)\n',
        '''\t\t\taudio.play_event("hit_heavy" if heavy else "hit_light", hit_pos, true, d.get_instance_id())
\t\t\tif attacker is Fighter:
\t\t\t\tvar special_audio: bool = heavy or String(attacker.atk_id) in ["z", "x", "c", "v", "l3"]
\t\t\t\taudio.play_special_elemental_hit(String(attacker.look.element), hit_pos, attacker.get_instance_id(), special_audio)
''',
        "18C hit and elemental accents")
    src = once(src,
        '\t\t\taudio.play_event("block", shield_pos)\n',
        '\t\t\taudio.play_event("block", shield_pos, true, d.get_instance_id())\n',
        "18C block source")
    src = once(src,
        '\t\t\taudio.play_event("parry", shield_pos)\n',
        '\t\t\taudio.play_event("parry", shield_pos, true, d.get_instance_id())\n',
        "18C parry source")
    src = once(src,
        '\t\t\taudio.play_event("guard_break", hit_pos)\n',
        '\t\t\taudio.play_event("guard_break", hit_pos, true, d.get_instance_id())\n',
        "18C guard-break source")
    # Match marker is on the newly inserted method call, not an extra header.
    return src


def sha(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".frg18c-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def changes_for(root: Path) -> dict[str, bytes]:
    if not (root / 'project.godot').is_file():
        raise RuntimeError('Run from your Godot folder containing project.godot.')
    if not (root / AUDIO).is_file() or not (root / MATCH).is_file():
        raise RuntimeError('Missing match.gd or combat_audio.gd; install earlier updates first.')
    current_audio = (root / AUDIO).read_text(encoding='utf-8-sig')
    current_match = (root / MATCH).read_text(encoding='utf-8-sig')
    if (TAG in current_audio) != (MATCH_MARKER in current_match):
        raise RuntimeError('Partial Update 18C detected. Restore the affected files before retrying.')
    audio_text = patch_audio(current_audio)
    match_text = patch_match(current_match)
    profile_bytes = (json.dumps(PROFILES, indent=2) + '\n').encode('utf-8')
    existing_profile = root / PROFILE
    if existing_profile.is_file() and existing_profile.read_bytes() != profile_bytes:
        # Never overwrite user-customized audio settings/profiles.
        if TAG not in current_audio:
            raise RuntimeError('Existing data/audio_profiles_18c.json differs from 18C defaults; refusing overwrite.')
        profile_bytes = existing_profile.read_bytes()
    root_sfx = root / 'sfx'
    count_found = sum((root_sfx / filename).is_file() for event in EXTRA_EVENTS.values() for filename in event['files'])
    report = (f'Fight Royale Godot Update 18C ({VERSION})\n'
              'Independent audio cooldowns per fighter in CPU vs CPU and duels.\n'
              'Kit-aware attack-swing cues and quiet elemental special-hit accents.\n'
              'No gameplay, character stats, attack timing or model changes.\n'
              'SFX root: res://sfx/ (no files moved or copied)\n'
              f'Additional sound candidate files present: {count_found}/16\n'
              'Absent audio remains nonfatal until imported into Godot.\n'
              'Edit data/audio_profiles_18c.json to disable elemental_special_hits or adjust mappings.\n')
    files = {AUDIO: audio_text.encode(), MATCH: match_text.encode(),
             PROFILE: profile_bytes, REPORT: report.encode()}
    return {path: content for path, content in files.items()
            if not (root / path).is_file() or (root / path).read_bytes() != content}


def install(root: Path, changes: dict[str, bytes], dry_run: bool) -> Path | None:
    if not changes:
        print('18C already installed; no changes.')
        return None
    for file in changes:
        print('Update:', file)
    if dry_run:
        print('DRY RUN: no changes made.')
        return None
    backup = root.parent / (root.name + '_backups') / (
        'spatial_elemental_audio_18c_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {'version': VERSION, 'project': str(root), 'files': {}}
    for rel, content in changes.items():
        old = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest['files'][rel] = {'before': sha(old), 'after': sha(content)}
        if old is not None:
            saved = backup / 'originals' / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(old)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    written: list[str] = []
    try:
        for rel, content in changes.items():
            atomic_write(root / rel, content)
            written.append(rel)
    except Exception:
        for rel in reversed(written):
            original = backup / 'originals' / rel
            if original.is_file():
                atomic_write(root / rel, original.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print('18C installed. Backup:', backup)
    return backup


def restore(root: Path, backup_name: str) -> None:
    backup = Path(backup_name).expanduser().resolve()
    manifest = json.loads((backup / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('version') != VERSION or Path(manifest.get('project', '')).resolve() != root:
        raise RuntimeError('Not an 18C backup for this exact project.')
    for rel, info in manifest['files'].items():
        now = (root / rel).read_bytes() if (root / rel).is_file() else None
        if sha(now) != info['after']:
            raise RuntimeError('File changed since install; refusing restore: ' + rel)
        old = backup / 'originals' / rel
        if info['before'] is not None and (not old.is_file() or sha(old.read_bytes()) != info['before']):
            raise RuntimeError('Missing or damaged original backup: ' + rel)
    for rel in manifest['files']:
        old = backup / 'originals' / rel
        if old.is_file():
            atomic_write(root / rel, old.read_bytes())
        else:
            (root / rel).unlink(missing_ok=True)
    print('18C restored.')


def main() -> int:
    parser = argparse.ArgumentParser(description='Fight Royale Godot Update 18C: per-fighter combat audio')
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--restore', metavar='BACKUP_FOLDER')
    args = parser.parse_args()
    root = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(root, args.restore)
        else:
            install(root, changes_for(root), args.dry_run)
        return 0
    except Exception as exc:
        print('ERROR:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
