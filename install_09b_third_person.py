#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot — Update 09b: third-person combat camera preview.

Run from your Godot project directory:
    python install_09b_third_person.py

Optional:
    python install_09b_third_person.py --dry-run
    python install_09b_third_person.py --check-godot
    python install_09b_third_person.py --godot "C:/path/to/Godot.exe" --check-godot
    python install_09b_third_person.py --restore "BACKUP_FOLDER_SHOWN_AFTER_INSTALL"

Duel vs CPU: third-person by default; F6 toggles existing side-view camera,
Tab toggles lock-on, middle-mouse drag orbits in free camera, wheel zooms.
CPU vs CPU: existing spectator camera unchanged. No combat/rig/asset changes.

The script checks exact anchor text before writing, backs up changed files, and
refuses to overwrite unsupported versions. Requires Python 3.9+; stdlib only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

VERSION = "09b.1"
MARKER = "# FRG09B - third-person duel camera"
MATCH = "scripts/match.gd"
REPORT = "reports/third_person_camera_09b.txt"

STATE = r'''# FRG09B - third-person duel camera
# The browser game's original side-view stays available with F6.
# All camera settings are runtime-only and do not touch fighter rigs/skills.
var _third_person := true
var _lock_on := true
var _camera_dragging := false
var _camera_initialized := false
var _orbit_yaw := 0.0
var _orbit_pitch := deg_to_rad(22.0)
var _follow_distance := 5.4
var _camera_hint: Label
'''

INPUT = r'''func _unhandled_input(e: InputEvent) -> void:
	if paused:
		return
	if not bool(cfg.get("spectator", false)):
		if e is InputEventKey and e.pressed and not e.echo:
			if e.keycode == KEY_F6 or e.physical_keycode == KEY_F6:
				_third_person = not _third_person
				_camera_dragging = false
				_camera_initialized = false
				_update_camera_hint()
				get_viewport().set_input_as_handled()
				return
			if e.keycode == KEY_TAB or e.physical_keycode == KEY_TAB:
				if _third_person:
					_lock_on = not _lock_on
					_update_camera_hint()
					get_viewport().set_input_as_handled()
					return
		if e is InputEventMouseButton and _third_person:
			if e.button_index == MOUSE_BUTTON_MIDDLE:
				_camera_dragging = e.pressed
				get_viewport().set_input_as_handled()
				return
			if e.pressed and e.button_index == MOUSE_BUTTON_WHEEL_UP:
				_follow_distance = clampf(_follow_distance - 0.55, 3.2, 9.0)
				get_viewport().set_input_as_handled()
				return
			if e.pressed and e.button_index == MOUSE_BUTTON_WHEEL_DOWN:
				_follow_distance = clampf(_follow_distance + 0.55, 3.2, 9.0)
				get_viewport().set_input_as_handled()
				return
		if e is InputEventMouseMotion and _third_person and _camera_dragging:
			_lock_on = false
			_orbit_yaw -= e.relative.x * 0.006
			_orbit_pitch = clampf(_orbit_pitch + e.relative.y * 0.005, deg_to_rad(9.0), deg_to_rad(60.0))
			_update_camera_hint()
			get_viewport().set_input_as_handled()
			return
		_player_brain.on_event(e)
'''

CAMERA = r'''func _make_camera_hint() -> void:
	# Lightweight, non-interactive label. HUD and pause UI remain on top.
	var layer := CanvasLayer.new()
	layer.layer = 0
	add_child(layer)
	_camera_hint = Label.new()
	_camera_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_camera_hint.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_camera_hint.add_theme_font_size_override("font_size", 14)
	_camera_hint.add_theme_color_override("font_color", Color("#fff3dc"))
	_camera_hint.add_theme_color_override("font_outline_color", Color.BLACK)
	_camera_hint.add_theme_constant_override("outline_size", 5)
	layer.add_child(_camera_hint)
	_camera_hint.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_camera_hint.position = Vector2(-240, 6)
	_camera_hint.size = Vector2(480, 24)
	_update_camera_hint()

func _update_camera_hint() -> void:
	if _camera_hint == null:
		return
	if _third_person:
		_camera_hint.text = "THIRD PERSON  |  F6 side view  |  Tab lock: %s  |  MMB orbit  |  Wheel zoom" % ("ON" if _lock_on else "OFF")
	else:
		_camera_hint.text = "SIDE VIEW  |  F6 third person"

func _update_third_person_camera(dt: float) -> void:
	if local == null or not is_instance_valid(local):
		return
	var me: Fighter = local
	if not _camera_initialized:
		var facing: Vector3 = me.forward()
		_orbit_yaw = atan2(facing.x, facing.z)
		_camera_initialized = true
	var focus: Vector3 = me.chest()
	var distance: float = _follow_distance
	var enemy: Fighter = me.opponent
	if _lock_on and is_instance_valid(enemy) and not enemy.is_down():
		var delta: Vector3 = enemy.global_position - me.global_position
		delta.y = 0.0
		if delta.length_squared() > 0.02:
			var desired_yaw: float = atan2(delta.x, delta.z)
			_orbit_yaw = lerp_angle(_orbit_yaw, desired_yaw, 1.0 - exp(-7.0 * dt))
		# In lock-on, a little of the opponent is framed beside the player.
		# Pull backward as they separate so both remain in view.
		focus = me.chest().lerp(enemy.chest(), 0.27)
		distance = maxf(distance, delta.length() * 0.54 + 2.7)
	var back := Vector3(
		-sin(_orbit_yaw) * cos(_orbit_pitch),
		sin(_orbit_pitch),
		-cos(_orbit_yaw) * cos(_orbit_pitch)
	)
	var desired: Vector3 = focus + back * distance
	# Future-proof for levels with walls/obstacles; does not require a hand-made camera rig.
	var query := PhysicsRayQueryParameters3D.create(focus, desired)
	query.collide_with_areas = false
	var hit: Dictionary = get_world_3d().direct_space_state.intersect_ray(query)
	if not hit.is_empty():
		desired = focus.lerp(hit.position, 0.86)
	camera.fov = lerpf(camera.fov, 64.0, 1.0 - exp(-7.0 * dt))
	camera.global_position = camera.global_position.lerp(desired, 1.0 - exp(-9.0 * dt))
	camera.look_at(focus, Vector3.UP)
	# Preserve the pre-existing impact shake instead of losing hit feel.
	_trauma = maxf(_trauma - 1.4 * dt, 0.0)
	var shake: float = _trauma * _trauma
	_shake_t += dt * 32.0
	camera.global_position += Vector3(
		0.22 * shake * sin(_shake_t * 1.7),
		0.16 * shake * sin(_shake_t * 2.3),
		0.0
	)

'''


def replace_once(text: str, old: str, new: str, what: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{what}: expected exactly 1 match, found {count}. No files changed. Please upload scripts/match.gd for a tailored fix.")
    return text.replace(old, new, 1)


def patch_match(text: str) -> str:
    if MARKER in text:
        expected = [
            'var _third_person := true',
            'func _update_third_person_camera(dt: float) -> void:',
            'func _make_camera_hint() -> void:',
            'KEY_F6', 'KEY_TAB', 'MOUSE_BUTTON_MIDDLE',
            '_update_third_person_camera(dt)',
        ]
        if all(s in text for s in expected):
            return text
        raise RuntimeError("Update 09b marker exists but code looks incomplete. Refusing to overwrite a partial installation.")
    mandatory = [
        'class_name Match',
        'func _unhandled_input(e: InputEvent) -> void:',
        'func _update_camera(dt: float) -> void:',
        'var _sun: DirectionalLight3D',
        'camera = Camera3D.new()',
        'local = null',
        'func hud() -> Dictionary:',
    ]
    missing = [m for m in mandatory if m not in text]
    if missing:
        raise RuntimeError('Current scripts/match.gd is incompatible: ' + ', '.join(missing))
    text = replace_once(
        text,
        'var _sun: DirectionalLight3D\n',
        'var _sun: DirectionalLight3D\n\n' + STATE + '\n',
        'camera state',
    )
    text = replace_once(
        text,
        '\t_player_brain = PlayerBrain.new(camera)\n\tstart_round()',
        '\t_player_brain = PlayerBrain.new(camera)\n\tif not bool(cfg.get("spectator", false)):\n\t\t_make_camera_hint()\n\tstart_round()',
        'camera HUD setup',
    )
    text = replace_once(
        text,
        '\tlocal = null\n\t_round += 1',
        '\tlocal = null\n\t_camera_initialized = false\n\t_round += 1',
        'reset camera on new round',
    )
    start = text.index('func _unhandled_input(e: InputEvent) -> void:')
    end = text.index('\nfunc _process(real_dt: float) -> void:', start)
    old = text[start:end]
    if 'player_brain.on_event(e)' not in old or len(old) > 500:
        raise RuntimeError('Unexpected _unhandled_input implementation; refusing unsafe replacement.')
    text = text[:start] + INPUT.rstrip('\n') + '\n' + text[end:]
    text = replace_once(
        text,
        'func _update_camera(dt: float) -> void:\n',
        'func _update_camera(dt: float) -> void:\n'
        '\tif _third_person and not bool(cfg.get("spectator", false)) and local != null:\n'
        '\t\t_update_third_person_camera(dt)\n'
        '\t\treturn\n'
        '\tcamera.fov = lerpf(camera.fov, 50.0, 1.0 - exp(-7.0 * dt))\n',
        'switchable camera update',
    )
    text = replace_once(
        text,
        '# --- HUD feed ------------------------------------------------------------------------------',
        CAMERA + '# --- HUD feed ------------------------------------------------------------------------------',
        'third-person camera controller',
    )
    return text


def digest(raw: bytes | None) -> str | None:
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def safe_write(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.frg09b_' + uuid.uuid4().hex[:8] + '.tmp')
    try:
        temp.write_bytes(contents)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def changes_for(root: Path) -> dict[str, bytes]:
    if not (root / 'project.godot').is_file():
        raise RuntimeError('Run this command inside your Godot project directory, next to project.godot.')
    src = root / MATCH
    if not src.is_file():
        raise RuntimeError('Missing scripts/match.gd. This installer targets the existing Fight Royale Godot project.')
    old = src.read_text(encoding='utf-8-sig')
    new = patch_match(old)
    changes: dict[str, bytes] = {}
    if old != new:
        changes[MATCH] = new.encode('utf-8')
    report = (
        'FIGHT ROYALE GODOT | UPDATE 09b - THIRD PERSON CAMERA\n'
        '\nDuel vs CPU: third-person camera is ON by default.\n'
        'F6: toggle between third-person and original side-view.\n'
        'Tab: toggle lock-on in third-person (starts ON).\n'
        'Middle mouse hold + drag: free-orbit camera (automatically disables lock-on).\n'
        'Mouse wheel: zoom camera in/out.\n'
        'WASD: camera-relative movement (already supported by PlayerBrain).\n'
        'Left click attack and right click block: unchanged.\n'
        'CPU vs CPU: old cinematic camera preserved.\n'
        '\nThis preview patch changes scripts/match.gd only.\n'
        'It does NOT change damage, AI, abilities, movement code, VRM rigs or SFX.\n'
        'Godot must import any new VRMs in the editor before they can appear in play.\n'
        'Camera is runtime-configurable; F6 allows an immediate A/B comparison.\n'
        '\nTest in Duel vs CPU and verify: rotate with MMB, Tab locks back to opponent,\n'
        'scroll zoom, F6 toggles, paused game accepts no camera inputs, CPU vs CPU unchanged.\n'
        'If a third-person view is blocked by scenery, the camera ray test pulls it inward.\n'
        'Actual game visuals and Godot script parsing require testing in your Godot editor.\n'
    ).encode('utf-8')
    if not (root / REPORT).is_file() or (root / REPORT).read_bytes() != report:
        changes[REPORT] = report
    return changes


def install(root: Path, changes: dict[str, bytes], dry_run: bool) -> Path | None:
    if not changes:
        print('Already installed. No changes needed.')
        return None
    print('Files to update:')
    for rel in changes:
        print(' -', rel)
    if dry_run:
        print('Dry run only; nothing written.')
        return None
    backup = root.parent / (root.name + '_backups') / (
        'camera_09b_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6]
    )
    backup.mkdir(parents=True, exist_ok=False)
    info = {'version': VERSION, 'project': str(root), 'files': {}}
    for rel, new_data in changes.items():
        old_data = (root / rel).read_bytes() if (root / rel).exists() else None
        info['files'][rel] = {'old': digest(old_data), 'new': digest(new_data)}
        if old_data is not None:
            orig = backup / 'originals' / rel
            orig.parent.mkdir(parents=True, exist_ok=True)
            orig.write_bytes(old_data)
    (backup / 'manifest.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    applied: list[str] = []
    try:
        for rel, data in changes.items():
            safe_write(root / rel, data)
            applied.append(rel)
    except Exception:
        for rel in reversed(applied):
            orig = backup / 'originals' / rel
            if orig.exists():
                safe_write(root / rel, orig.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print('Backup:', backup)
    return backup


def restore(root: Path, backup_arg: str) -> None:
    backup = Path(backup_arg).expanduser().resolve()
    meta = json.loads((backup / 'manifest.json').read_text(encoding='utf-8'))
    if meta.get('version') != VERSION or Path(meta.get('project', '')).resolve() != root.resolve():
        raise RuntimeError('That folder is not a 09b backup for this project.')
    entries: dict = meta['files']
    for rel, hashes in entries.items():
        p = Path(rel)
        if p.is_absolute() or '..' in p.parts:
            raise RuntimeError('Unsafe backup entry: ' + rel)
        current = root / rel
        if not current.is_file() or digest(current.read_bytes()) != hashes['new']:
            raise RuntimeError('File changed after installation; refusing to restore over new edits: ' + rel)
        if hashes['old'] is not None:
            orig = backup / 'originals' / rel
            if not orig.is_file() or digest(orig.read_bytes()) != hashes['old']:
                raise RuntimeError('Damaged backup original: ' + rel)
    for rel, hashes in entries.items():
        dest = root / rel
        if hashes['old'] is None:
            dest.unlink(missing_ok=True)
        else:
            safe_write(dest, (backup / 'originals' / rel).read_bytes())
        print('Restored:', rel)


def check_godot(root: Path, specified: str | None) -> int:
    exe = None
    if specified:
        exe = str(Path(specified).expanduser().resolve()) if Path(specified).is_file() else shutil.which(specified)
    if not exe:
        exe = next((p for name in ('godot', 'godot4', 'godot.exe') if (p := shutil.which(name))), None)
    if not exe:
        print('Godot executable not detected; open the Godot editor to import/validate the project.')
        return 0
    try:
        run = subprocess.run([exe, '--headless', '--editor', '--path', str(root), '--quit'],
                             capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print('Godot validation failed:', exc)
        return 2
    out = (run.stdout + '\n' + run.stderr)[-12000:]
    print(out)
    if run.returncode or re.search(r'SCRIPT ERROR|Parse Error|Failed to load script', out, re.I):
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Fight Royale - Update 09b Third Person Camera')
    parser.add_argument('--dry-run', action='store_true', help='Show changes without editing files')
    parser.add_argument('--restore', metavar='BACKUP_FOLDER', help='Safely undo this update')
    parser.add_argument('--check-godot', action='store_true', help='Try to parse project using local Godot executable')
    parser.add_argument('--godot', help='Specific Godot executable for --check-godot')
    args = parser.parse_args()
    root = Path.cwd().resolve()
    print('FIGHT ROYALE GODOT | UPDATE 09b - THIRD-PERSON CAMERA\nProject:', root)
    if args.restore:
        restore(root, args.restore)
        return 0
    changes = changes_for(root)
    install(root, changes, args.dry_run)
    if not args.dry_run:
        print('\nOpen Godot > Duel vs CPU. F6 camera view, Tab lock-on, MMB orbit, wheel zoom.')
        print('Report:', REPORT)
    if args.check_godot and not args.dry_run:
        return check_godot(root, args.godot)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, UnicodeError, KeyError, json.JSONDecodeError) as exc:
        print('ERROR:', exc, file=sys.stderr)
        raise SystemExit(1)
