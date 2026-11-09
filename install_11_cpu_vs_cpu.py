#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot — Update 11: CPU vs CPU spectator mode.

Run from inside your Godot project:
    python install_11_cpu_vs_cpu.py

Optional:
    python install_11_cpu_vs_cpu.py --dry-run
    python install_11_cpu_vs_cpu.py --check-godot
    python install_11_cpu_vs_cpu.py --restore PATH_PRINTED_BY_INSTALLER

Requires the two-mode menu (Update 02) and the duel completion (Update 10).
Compatible with optional Update 09b third-person camera. All changes are
preflighted in memory before files are touched. Backs up originals and refuses
unknown/partially modified projects rather than guessing how to patch them.
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

VERSION = '11.0'
MARKER = '# FRG11 - independent CPU versus CPU spectator controls'
FILES = ('scripts/main.gd', 'scripts/match.gd', 'scripts/hud.gd')
REPORT = 'reports/cpu_vs_cpu_11.txt'


def one(source: str, old: str, new: str, what: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f'{what}: expected 1 exact anchor, found {count}. No changes made. '
                         'Provide the current scripts/main.gd, match.gd and hud.gd to prepare a compatible fix.')
    return source.replace(old, new, 1)


def function(source: str, name: str, patch, required=()) -> str:
    start_re = re.compile(rf'(?m)^func {re.escape(name)}\([^\n]*\)(?:\s*->\s*[A-Za-z0-9_\[\]]+)?\s*:\n')
    found = list(start_re.finditer(source))
    if len(found) != 1:
        raise ValueError(f'{name}: expected exactly one function, found {len(found)}')
    a = found[0].start()
    next_fn = re.search(r'(?m)^func [A-Za-z_][A-Za-z_0-9]*\(', source[found[0].end():])
    b = found[0].end() + next_fn.start() if next_fn else len(source)
    original = source[a:b]
    for expectation in required:
        if expectation not in original:
            raise ValueError(f'{name}: expected code not found: {expectation!r}')
    return source[:a] + patch(original) + source[b:]


def patch_main(s: str) -> str:
    if MARKER in s:
        if all(x in s for x in ('func _choose_cpu_difficulty(', '"cpu_levels":', '_cpu_level_a', '_cpu_level_b')):
            return s
        raise ValueError('Partially installed Update 11 found in scripts/main.gd')
    if 'FIGHT_ROYALE_MODES_V02' not in s or '# FRG10' not in s:
        raise ValueError('Update 11 requires Updates 02 and 10 in main.gd')
    s = one(s, 'var _difficulty := 1\n',
            'var _difficulty := 1\n' + MARKER + '\n'
            'var _cpu_level_a := 2\nvar _cpu_level_b := 2\n', 'CPU configuration')

    def setup(fn: str) -> str:
        old = '''\t_title(v, "AI Difficulty", 23)
\tvar row := HBoxContainer.new()
\tv.add_child(row)
\tfor i in 3:
\t\tvar b := _btn(row, ["Easy", "Normal", "Hard"][i], _choose_difficulty.bind(i), 145)
\t\tif i == _difficulty:
\t\t\tb.modulate = Color("#ffe08a")
'''
        new = '''\tif _mode == "cpu_vs_cpu":
\t\t_text(v, "Each fighter has its own AI difficulty.", 15)
\t\tfor side in 2:
\t\t\t_title(v, "CPU A Difficulty" if side == 0 else "CPU B Difficulty", 21)
\t\t\tvar row := HBoxContainer.new()
\t\t\tv.add_child(row)
\t\t\tfor i in 4:
\t\t\t\tvar b := _btn(row, ["Easy", "Normal", "Hard", "Master"][i], _choose_cpu_difficulty.bind(side, i), 137)
\t\t\t\tif i == (_cpu_level_a if side == 0 else _cpu_level_b):
\t\t\t\t\tb.modulate = Color("#ffe08a")
\telse:
\t\t_title(v, "Opponent AI Difficulty", 23)
\t\tvar row := HBoxContainer.new()
\t\tv.add_child(row)
\t\tfor i in 3:
\t\t\tvar b := _btn(row, ["Easy", "Normal", "Hard"][i], _choose_difficulty.bind(i), 145)
\t\t\tif i == _difficulty:
\t\t\t\tb.modulate = Color("#ffe08a")
'''
        if fn.count(old) != 1:
            raise ValueError('Expected AI difficulty controls in show_prepare not found')
        fn = fn.replace(old, new, 1)
        return fn.replace('Spectator mode: both fighters are CPU-controlled. Esc pauses; R rematches.',
                          'Spectator: C camera | 1-4 camera views | MMB orbit | wheel zoom | [ ] speed | Esc pause | R rematch')

    s = function(s, 'show_prepare', setup, ('_title(v, "AI Difficulty", 23)',))
    s = one(s, 'func _choose_difficulty(index: int) -> void:\n',
            'func _choose_cpu_difficulty(side: int, index: int) -> void:\n'
            '\tif side == 0:\n\t\t_cpu_level_a = clampi(index, 0, 3)\n'
            '\telse:\n\t\t_cpu_level_b = clampi(index, 0, 3)\n'
            '\tshow_prepare()\n\n'
            'func _choose_difficulty(index: int) -> void:\n', 'CPU difficulty callback')
    s = one(s, '"difficulty": _difficulty, "spectator": spectator, "round_seconds": _duel_seconds}',
            '"difficulty": _difficulty, "cpu_levels": [_cpu_level_a, _cpu_level_b], '
            '"spectator": spectator, "round_seconds": _duel_seconds}', 'separate AI difficulty config')
    return s


def patch_match(s: str) -> str:
    if MARKER in s:
        if all(x in s for x in ('func _spectator_input(', 'func _update_spectator_camera(',
                                '"spectator_speed":', '_spectator_speed_index')):
            return s
        raise ValueError('Partially installed Update 11 found in scripts/match.gd')
    if '# FRG10' not in s or 'func _finish_duel(' not in s:
        raise ValueError('Update 11 requires Update 10 match.gd')
    s = one(s, 'var _sun: DirectionalLight3D\n',
            'var _sun: DirectionalLight3D\n\n' + MARKER + '\n'
            'const SPECTATOR_SPEEDS := [0.5, 1.0, 1.5, 2.0]\n'
            'const SPECTATOR_VIEWS := ["Cinematic", "Orbit", "Follow CPU A", "Follow CPU B"]\n'
            'var _spectator_speed_index := 1\n'
            'var _spectator_view := 0\n'
            'var _spectator_dragging := false\n'
            'var _spectator_yaw := 0.8\n'
            'var _spectator_pitch := 0.36\n'
            'var _spectator_distance := 9.0\n', 'spectator state')
    # Independent AI brains: both brains are already independent instances. This
    # makes their difficulty presets truly independent too.
    def brain(fn: str) -> str:
        old = '\tif String(f.owner_peer).begins_with("cpu"): return AiBrain.new(self, cfg.get("difficulty", 1))'
        new = '''\tif String(f.owner_peer).begins_with("cpu"):
\t\tvar preset := int(cfg.get("difficulty", 1))
\t\tif bool(cfg.get("spectator", false)):
\t\t\tvar levels: Array = cfg.get("cpu_levels", [2, 2])
\t\t\tvar idx := 0 if String(f.owner_peer) == "cpu_a" else 1
\t\t\tif levels.size() > idx:
\t\t\t\tpreset = int(levels[idx])
\t\treturn AiBrain.new(self, clampi(preset, 0, 3))'''
        if fn.count(old) != 1:
            raise ValueError('Existing AiBrain mapping not found')
        return fn.replace(old, new, 1)
    s = function(s, '_brain_for', brain, ('AiBrain.new(self, cfg.get("difficulty", 1))',))
    s = one(s, 'func _unhandled_input(e: InputEvent) -> void:\n',
            'func _unhandled_input(e: InputEvent) -> void:\n'
            '\tif bool(cfg.get("spectator", false)):\n'
            '\t\t_spectator_input(e)\n\t\treturn\n', 'spectator input routing')
    spectator_input = '''# --- FRG11: spectator controls ------------------------------------------------------------

func _spectator_input(e: InputEvent) -> void:
\t# Esc and R remain handled by Hud. No input is sent to PlayerBrain.
\tif e is InputEventKey and e.pressed and not e.echo:
\t\tvar k: int = e.keycode if e.keycode != 0 else e.physical_keycode
\t\tif k == KEY_C:
\t\t\t_spectator_view = (_spectator_view + 1) % SPECTATOR_VIEWS.size()
\t\telif k >= KEY_1 and k <= KEY_4:
\t\t\t_spectator_view = k - KEY_1
\t\telif k == KEY_BRACKETLEFT:
\t\t\t_spectator_speed_index = maxi(0, _spectator_speed_index - 1)
\t\telif k == KEY_BRACKETRIGHT:
\t\t\t_spectator_speed_index = mini(SPECTATOR_SPEEDS.size() - 1, _spectator_speed_index + 1)
\t\telse:
\t\t\treturn
\t\tget_viewport().set_input_as_handled()
\t\treturn
\tif e is InputEventMouseButton:
\t\tif e.button_index == MOUSE_BUTTON_MIDDLE:
\t\t\t_spectator_dragging = e.pressed
\t\t\tif e.pressed:
\t\t\t\t_spectator_view = 1
\t\t\tget_viewport().set_input_as_handled()
\t\t\treturn
\t\tif e.pressed and e.button_index == MOUSE_BUTTON_WHEEL_UP:
\t\t\t_spectator_distance = clampf(_spectator_distance - 0.6, 4.0, 18.0)
\t\t\t_spectator_view = 1
\t\t\tget_viewport().set_input_as_handled()
\t\t\treturn
\t\tif e.pressed and e.button_index == MOUSE_BUTTON_WHEEL_DOWN:
\t\t\t_spectator_distance = clampf(_spectator_distance + 0.6, 4.0, 18.0)
\t\t\t_spectator_view = 1
\t\t\tget_viewport().set_input_as_handled()
\t\t\treturn
\tif e is InputEventMouseMotion and _spectator_dragging:
\t\t_spectator_yaw -= e.relative.x * 0.007
\t\t_spectator_pitch = clampf(_spectator_pitch + e.relative.y * 0.005, 0.13, 1.12)
\t\tget_viewport().set_input_as_handled()

'''
    s = one(s, 'func _process(real_dt: float) -> void:\n',
            spectator_input + 'func _process(real_dt: float) -> void:\n', 'spectator input function')
    s = one(s, '\tvar dt := 0.0 if paused else real_dt * scale\n',
            '\tvar speed := float(SPECTATOR_SPEEDS[_spectator_speed_index]) if bool(cfg.get("spectator", false)) else 1.0\n'
            '\tvar dt := 0.0 if paused else real_dt * scale * speed\n', 'spectator speed simulation')
    s = one(s, '\tfor f in fighters:\n\t\tf.tick(dt)\n',
            '\tfor f in fighters:\n\t\t# Zero-delta brain calls can still schedule attacks; pause must freeze AI.\n'
            '\t\tif dt > 0.0:\n\t\t\tf.tick(dt)\n', 'true spectator pause')
    s = one(s, 'func _update_camera(dt: float) -> void:\n',
            'func _update_camera(dt: float) -> void:\n'
            '\tif bool(cfg.get("spectator", false)) and _spectator_view != 0:\n'
            '\t\t_update_spectator_camera(dt)\n\t\treturn\n', 'spectator camera dispatch')
    spectator_camera = '''func _update_spectator_camera(dt: float) -> void:
\tif fighters.size() < 2:
\t\treturn
\tvar a: Fighter = fighters[0]
\tvar b: Fighter = fighters[1]
\tvar mid: Vector3 = (a.chest() + b.chest()) * 0.5
\tvar target: Vector3 = mid
\tif _spectator_view == 2:
\t\ttarget = a.chest().lerp(b.chest(), 0.15)
\telif _spectator_view == 3:
\t\ttarget = b.chest().lerp(a.chest(), 0.15)
\tvar dist := _spectator_distance
\tif _spectator_view == 2 or _spectator_view == 3:
\t\tdist = maxf(5.0, _spectator_distance * 0.72)
\telse:
\t\tdist = maxf(dist, a.position.distance_to(b.position) * 0.85 + 3.0)
\tvar dir := Vector3(sin(_spectator_yaw) * cos(_spectator_pitch),
\t\tsin(_spectator_pitch), cos(_spectator_yaw) * cos(_spectator_pitch))
\tvar desired := target + dir * dist
\tvar alpha := 1.0 - exp(-6.0 * dt)
\tcamera.fov = lerpf(camera.fov, 56.0, alpha)
\tcamera.global_position = camera.global_position.lerp(desired, alpha)
\tcamera.look_at(target, Vector3.UP)
\t_trauma = maxf(_trauma - 1.4 * dt, 0.0)

'''
    s = one(s, 'func _make_camera_hint() -> void:\n',
            spectator_camera + 'func _make_camera_hint() -> void:\n', 'spectator camera function') if 'func _make_camera_hint() -> void:\n' in s else one(s,
            'func hud() -> Dictionary:\n', spectator_camera + 'func hud() -> Dictionary:\n', 'spectator camera function')
    s = one(s, '\t\t"spectator": bool(cfg.get("spectator", false)),\n',
            '\t\t"spectator": bool(cfg.get("spectator", false)),\n'
            '\t\t"spectator_speed": float(SPECTATOR_SPEEDS[_spectator_speed_index]),\n'
            '\t\t"spectator_view": SPECTATOR_VIEWS[_spectator_view],\n'
            '\t\t"paused": paused,\n', 'HUD spectator telemetry')
    return s


def patch_hud(s: str) -> str:
    if MARKER in s:
        if all(x in s for x in ('spectator_speed', 'spectator_view', '_controls_hint.text')):
            return s
        raise ValueError('Partially installed Update 11 found in scripts/hud.gd')
    if 'class_name Hud' not in s or '# FRG10' not in s:
        raise ValueError('Update 11 requires Update 10 hud.gd')
    s = one(s, '# FRG10 - complete Duel vs CPU match flow\n',
            '# FRG10 - complete Duel vs CPU match flow\n' + MARKER + '\n', 'spectator HUD marker')
    s = one(s, '\t_controls_hint.visible = not bool(match_node.cfg.get("spectator", false))\n',
            '\t_controls_hint.visible = true\n', 'spectator controls guide')
    # The optional third-person patch changed the HUD's clock formatting.
    clock_re = re.compile(r'(?m)^\t\t_clock_label\.text = [^\n]+\n\t\t_clock_label\.visible = [^\n]+\n')
    if len(list(clock_re.finditer(s))) != 1:
        raise ValueError('Expected one duel clock display block')
    new_clock = '\t\tvar mode_text := "CPU VS CPU" if bool(h.get("spectator", false)) else "DUEL"\n\t\t_clock_label.text = "%s  |  --:--" % mode_text if unlimited else ("%s  |  %02d:%02d" % [mode_text, int(seconds / 60), seconds % 60])\n\t\t_clock_label.visible = true\n\tif bool(h.get("spectator", false)):\n\t\t_controls_hint.text = "C / 1-4 camera  |  MMB orbit  |  Wheel zoom  |  [ ] speed  |  Esc pause  |  R rematch   •   %s   %.1fx%s" % [str(h.get("spectator_view", "Cinematic")), float(h.get("spectator_speed", 1.0)), "  PAUSED" if bool(h.get("paused", false)) else ""]\n'
    s = clock_re.sub(lambda _: new_clock, s, count=1)
    return s


def changes_for(root: Path) -> dict[str, bytes]:
    if not (root / 'project.godot').is_file():
        raise ValueError('Run this from inside the Godot project directory (containing project.godot).')
    changes = {}
    for rel, parser in zip(FILES, (patch_main, patch_match, patch_hud)):
        path = root / rel
        if not path.is_file():
            raise ValueError(f'Missing {rel}; cannot safely patch the current game.')
        before = path.read_text(encoding='utf-8-sig')
        after = parser(before)
        if after != before:
            changes[rel] = after.encode('utf-8')
    report = '''FIGHT ROYALE GODOT — UPDATE 11 — CPU VS CPU

Completes the existing two-fighter spectator mode:
- Independent AI difficulty for CPU A and CPU B (Easy/Normal/Hard/Master).
- Both fighters receive separate AiBrain instances; no player input in spectator mode.
- C cycles cinematic, orbit, follow CPU A, follow CPU B camera views.
- Number keys 1-4 pick a camera view directly.
- Hold middle mouse and drag to orbit; mouse wheel changes camera distance.
- Left/right brackets [ ] set playback simulation speed to 0.5x / 1.0x / 1.5x / 2.0x.
- Esc opens pause; paused matches do not tick fighter brains.
- CPU health/guard bars, running match clock, camera and speed hints.
- Knockout, time-limit decision, rematch and fighter reselect remain from Update 10.
- Duel vs CPU, skills, VRMs, render options and SFX are preserved.
- No shop, economy, survival, team fights or multiplayer added.

If the VRMs do not appear immediately, open the Godot editor once to import assets.
Godot runtime gameplay and model rendering must still be tested on your computer.
'''.encode('utf-8')
    if not (root / REPORT).is_file() or (root / REPORT).read_bytes() != report:
        changes[REPORT] = report
    return changes


def digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.frg11_' + uuid.uuid4().hex[:10] + '.tmp')
    try:
        temp.write_bytes(content)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def install(root: Path, changes: dict[str, bytes], dry: bool = False) -> Path | None:
    if not changes:
        print('Already installed — no changes needed.')
        return None
    print('Files to update:')
    for rel in changes:
        print(' -', rel)
    if dry:
        print('Dry run OK; nothing written.')
        return None
    backup = root.parent / (root.name + '_backups') / ('cpu_vs_cpu_11_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    records = {'version': VERSION, 'project': str(root), 'files': {}}
    for rel, after in changes.items():
        path = root / rel
        before = path.read_bytes() if path.is_file() else None
        records['files'][rel] = {'old': digest(before), 'new': digest(after)}
        if before is not None:
            dest = backup / 'originals' / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(before)
    (backup / 'manifest.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')
    applied = []
    try:
        for rel, data in changes.items():
            atomic_write(root / rel, data)
            applied.append(rel)
    except Exception:
        for rel in reversed(applied):
            original = backup / 'originals' / rel
            if original.is_file():
                atomic_write(root / rel, original.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print('Backup:', backup)
    return backup


def restore(root: Path, backup_arg: str) -> None:
    backup = Path(backup_arg).expanduser().resolve()
    meta = json.loads((backup / 'manifest.json').read_text(encoding='utf-8'))
    if meta.get('version') != VERSION or Path(meta.get('project', '')).resolve() != root:
        raise ValueError('Backup belongs to another version or project directory')
    for rel, hashes in meta['files'].items():
        p = Path(rel)
        if p.is_absolute() or '..' in p.parts:
            raise ValueError('Unsafe filename in backup manifest')
        current = root / p
        if not current.is_file() or digest(current.read_bytes()) != hashes['new']:
            raise ValueError('Cannot restore a file modified after Update 11: ' + rel)
        original = backup / 'originals' / rel
        if hashes['old'] is not None and (not original.is_file() or digest(original.read_bytes()) != hashes['old']):
            raise ValueError('Backup original missing/corrupt: ' + rel)
    for rel, hashes in meta['files'].items():
        path = root / rel
        if hashes['old'] is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write(path, (backup / 'originals' / rel).read_bytes())
        print('Restored:', rel)


def check_godot(root: Path, executable: str | None) -> int:
    exe = None
    if executable:
        exe = str(Path(executable).resolve()) if Path(executable).is_file() else shutil.which(executable)
    if not exe:
        exe = next((p for n in ('godot', 'godot4', 'godot.exe') if (p := shutil.which(n))), None)
    if not exe:
        print('Godot not found on PATH; open the project in Godot to import/validate.')
        return 0
    try:
        result = subprocess.run([exe, '--headless', '--editor', '--path', str(root), '--quit'],
                                capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as error:
        print('Could not complete Godot validation:', error)
        return 2
    output = (result.stdout + '\n' + result.stderr)[-16000:]
    print(output)
    if result.returncode or re.search(r'SCRIPT ERROR|Parse Error|Failed to load script', output, re.I):
        return 2
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description='Fight Royale Godot — Update 11 CPU vs CPU')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--restore', metavar='BACKUP_FOLDER')
    p.add_argument('--check-godot', action='store_true')
    p.add_argument('--godot', metavar='PATH', help='Godot executable for --check-godot')
    args = p.parse_args()
    root = Path.cwd().resolve()
    print('FIGHT ROYALE GODOT | UPDATE 11 — CPU VS CPU\nProject:', root)
    try:
        if args.restore:
            restore(root, args.restore)
            return 0
        changes = changes_for(root)
        install(root, changes, dry=args.dry_run)
        if args.check_godot and not args.dry_run:
            return check_godot(root, args.godot)
        if not args.dry_run:
            print('\nOpen Godot > CPU vs CPU > select fighters > choose AI levels > START FIGHT.')
            print('Camera: C or 1-4; MMB drag; wheel. Speed: [ and ]. Esc pause, R rematch.')
            print('Report:', REPORT)
        return 0
    except Exception as error:
        print('\nERROR:', error, file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
