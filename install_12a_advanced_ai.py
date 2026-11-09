#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot - Update 12A: intelligent neutral AI and spacing.

Run from the Godot project folder:
    python install_12a_advanced_ai.py

Optional:
    python install_12a_advanced_ai.py --dry-run
    python install_12a_advanced_ai.py --check-godot
    python install_12a_advanced_ai.py --restore PATH_TO_BACKUP

This is an installer, not a Godot engine replacement. Existing scripts are
patched only after validating the expected code anchors. A hash-checked backup
is created outside the project for safe rollback. No assets or VRMs are moved.
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

VERSION = '12A.1'
MARKER = '# FRG12A - deliberate spacing and cooldown-aware neutral AI'
FIGHTER_MARKER = '# FRG12A - explicit AI movement takes precedence over legacy auto-approach'
REPORT = 'reports/ai_neutral_12a.txt'

FIELD_INSERT = '''var _seen := {}
# FRG12A - deliberate spacing and cooldown-aware neutral AI
var _orbit_sign := 1.0
var _orbit_timer := 0.0
var _close_pressure_timer := 0.0
'''

POSITION = '''func _position(f: Fighter, o, dt: float) -> void:
	# Every CPU issues explicit movement intents; Fighter._move handles the
	# acceleration, footwork and arena clamp. Keep behavior independent of FPS.
	var to_enemy: Vector3 = o.position - f.position
	to_enemy.y = 0.0
	var dist: float = to_enemy.length()
	if dist <= 0.01:
		return
	var toward: Vector3 = to_enemy / dist
	var sideways := Vector3(-toward.z, 0.0, toward.x)
	_orbit_timer -= dt
	if _orbit_timer <= 0.0:
		_orbit_timer = _r(0.65, 1.6)
		_orbit_sign = -1.0 if randf() < 0.5 else 1.0
	# Ground-targeted strike evasions take priority over normal spacing.
	if _side_t > 0.0:
		_side_t = maxf(_side_t - dt, 0.0)
		f.in_move = sideways * _side_sign
		return
	var desired := Vector3.ZERO
	var ranged: bool = f.kit in RANGED
	var preferred: float = _preferred_range(f)
	if ranged:
		# Ranged fighters kite only when threatened at close range; otherwise
		# they actively re-enter their usable firing zone instead of fleeing forever.
		if dist < preferred - 0.9:
			desired = -toward * 0.85 + sideways * _orbit_sign * 0.5
		elif dist > preferred + 1.0:
			desired = toward * 0.95 + sideways * _orbit_sign * 0.2
		else:
			desired = sideways * _orbit_sign * 0.48
	else:
		# Melee fighters approach to actual light-attack reach rather than
		# stopping at a global distance that can be wrong for their weapon.
		if dist > preferred + 0.18:
			desired = toward
		elif dist < 1.08:
			desired = sideways * _orbit_sign * 0.75 - toward * 0.12
		else:
			desired = sideways * _orbit_sign * 0.32
		# Run to a distant opponent, especially a ranged fighter.
		f.in_sprint = dist > 4.2 and f.state == Fighter.S.IDLE
	# Do not retreat forever along the ring. Both classes must steer inward
	# at the boundary, even when the enemy is pushing from the center.
	var from_center := Vector3(f.position.x, 0.0, f.position.z)
	var edge_dist: float = from_center.length()
	var limit: float = maxf(f.arena_radius - 1.15, 0.5)
	if edge_dist > limit:
		var outward: Vector3 = from_center / maxf(edge_dist, 0.001)
		var edge_pressure: float = clampf((edge_dist - limit) / 0.85, 0.0, 1.0)
		if desired.dot(outward) > 0.0:
			desired -= outward * desired.dot(outward)
		desired -= outward * (0.25 + 0.9 * edge_pressure)
	if desired.length_squared() > 0.0001:
		f.in_move = desired.normalized()

func _preferred_range(f: Fighter) -> float:
	if f.kit in RANGED:
		return 5.0 if f.kit == "mage" else 5.5
	var light: Dictionary = f.attacks.get("l1", {})
	return clampf(float(light.get("reach", 1.8)) - 0.15, 1.2, 2.4)

func _usable_skill(f: Fighter, o: Fighter, key: String, dist: float) -> bool:
	if float(f.cooldowns.get(key, 999.0)) > 0.0:
		return false
	var a: Dictionary = f.attacks.get(key, {})
	if a.is_empty():
		return false
	match String(a.get("type", "")):
		"melee":
			return dist <= float(a.get("reach", 2.0)) + 0.65
		"projectile":
			return dist >= 1.1 and dist < 10.5
		"strike":
			if String(a.get("at", "target")) == "self":
				return dist <= float(a.get("radius", 1.5)) + 0.6
			return dist <= 10.5
		"blink":
			var mode: String = String(a.get("mode", ""))
			return (dist > 1.6 and dist < 6.0) if mode == "behind" else dist < 2.6
		"buff":
			var mode: String = String(a.get("mode", ""))
			if mode == "counter":
				return dist < 3.0 and o.state in [Fighter.S.ATTACK, Fighter.S.CHARGE]
			# Defensive ward: do not waste when already protected or healthy.
			return f.ward_t <= 0.0 and (f.hp < f.max_hp * 0.72 or f.guard < f.max_guard * 0.45)
	return false

'''

OFFENSE = '''func _offense(f: Fighter, o, dt: float) -> void:
	if f.state != Fighter.S.IDLE or not _queue.is_empty() or _hold > 0.0 or _block_hold > 0.0 or _block_wait >= 0.0:
		return
	var horizontal: Vector3 = o.position - f.position
	horizontal.y = 0.0
	var dist: float = horizontal.length()
	var ranged: bool = f.kit in RANGED
	var light: Dictionary = f.attacks.get("l1", {})
	var reach: float = 10.0 if ranged else float(light.get("reach", 1.8)) + 0.35
	# Try an off-cooldown skill only if the position and its action type fit.
	_skill_cd -= dt
	if _skill_cd <= 0.0:
		_skill_cd = _r(float(p.skill[0]), float(p.skill[1]))
		var keys := ["c", "x", "z"]
		keys.shuffle()
		if randf() < (0.65 if p.think <= 0.75 else 0.5):
			for key in keys:
				if _usable_skill(f, o, key, dist) and _try_skill(f, key, true):
					_queue.clear()
					return
	# Don't throw away attacks outside their actual reach.
	if dist > reach:
		return
	var vulnerable := o.state in [Fighter.S.HITSTUN, Fighter.S.STAGGER]
	if vulnerable:
		_think_cd = minf(_think_cd, 0.12)
	_think_cd -= dt
	if _think_cd > 0.0:
		return
	_think_cd = (_r(0.48, 0.95) if f.kit in ["assassin", "knuckles", "kicks"] else _r(0.65, 1.3)) * float(p.think)
	var heavy_chance := 0.17 if ranged else 0.23
	if o.state == Fighter.S.BLOCK:
		heavy_chance = 0.52
	elif vulnerable:
		heavy_chance = 0.41
	# Heavy swings are poor choices against a distant or mobile target.
	if not ranged and dist > float(light.get("reach", 1.8)) - 0.1:
		heavy_chance *= 0.6
	if randf() < heavy_chance:
		_queue.append([0.0, Fighter.HOLD_T + _r(0.26, 0.55)])
	else:
		var chain_count := 0
		for name in f.attacks:
			if String(name).begins_with("l") and String(name).length() == 2:
				chain_count += 1
		var max_hits := maxi(1, mini(int(p.combo), chain_count))
		var hits := randi_range(1, max_hits)
		for i in hits:
			_queue.append([0.0 if i == 0 else 0.13, 0.06])
'''


def function_span(source: str, name: str) -> tuple[int, int, str]:
    starts = list(re.finditer(rf'(?m)^func {re.escape(name)}\(', source))
    if len(starts) != 1:
        raise ValueError(f'{name}: expected exactly 1 function, found {len(starts)}')
    start = starts[0].start()
    m = re.search(r'(?m)^func [A-Za-z_][A-Za-z_0-9]*\(', source[starts[0].end():])
    end = starts[0].end() + m.start() if m else len(source)
    return start, end, source[start:end]


def replace_function(source: str, name: str, replacement: str, must_contain: str) -> str:
    a, b, old = function_span(source, name)
    if must_contain not in old:
        raise ValueError(f'{name} appears modified; refusing to overwrite unrecognized AI logic')
    return source[:a] + replacement.rstrip() + '\n\n' + source[b:].lstrip('\n')


def patch_ai(source: str) -> str:
    if MARKER in source:
        if all(s in source for s in ('func _preferred_range(', 'func _usable_skill(', 'func _position(', 'func _offense(')):
            return source
        raise ValueError('Partially installed Update 12A in ai_brain.gd; refusing to guess')
    for needed in ('class_name AiBrain', 'func _position(', 'func _offense(', 'func _try_skill(', 'var _seen := {}'):
        if needed not in source:
            raise ValueError(f'ai_brain.gd lacks required existing construct: {needed}')
    if source.count('var _seen := {}') != 1:
        raise ValueError('AI state anchor not unique')
    source = source.replace('var _seen := {}\n', FIELD_INSERT, 1)
    source = replace_function(source, '_position', POSITION, 'if f.kit in RANGED:')
    source = replace_function(source, '_offense', OFFENSE, 'if dist > reach: return')
    return source


def patch_fighter(source: str) -> str:
    if FIGHTER_MARKER in source:
        if 'and in_move.length_squared() < 0.0001' in source:
            return source
        raise ValueError('Partially installed Update 12A in fighter.gd')
    line = 'if state == S.IDLE and auto_approach and brain != null and o and not o.is_down() and dist > ENGAGE:'
    if source.count(line) != 1:
        raise ValueError('Expected legacy auto-approach line exactly once; fighter.gd may have been changed')
    replacement = (FIGHTER_MARKER + '\n\t\t' + line[:-1] + ' and in_move.length_squared() < 0.0001:')
    # Keep original indentation. The comment lives at the same indent level.
    source = source.replace('\t\t' + line, '\t\t' + replacement, 1)
    return source


def sha(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.frg12a_' + uuid.uuid4().hex[:10] + '.tmp')
    try:
        tmp.write_bytes(data)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def changes_for(root: Path) -> dict[str, bytes]:
    if not (root / 'project.godot').is_file():
        raise ValueError('Run this script from the Godot project folder (where project.godot is).')
    files = {'scripts/ai_brain.gd': patch_ai, 'scripts/fighter.gd': patch_fighter}
    updates: dict[str, bytes] = {}
    for rel, fn in files.items():
        path = root / rel
        if not path.is_file():
            raise ValueError(f'Missing {rel}; aborting before any changes')
        before = path.read_text(encoding='utf-8-sig')
        if rel.endswith('fighter.gd') and 'FRG09' not in before:
            raise ValueError('Update 09 is missing from fighter.gd; install earlier updates first')
        after = fn(before)
        for required in ('class_name ', 'extends ', 'func '):
            if required not in after:
                raise ValueError(f'Unexpected malformed GDScript in {rel}: missing {required}')
        if after != before:
            updates[rel] = after.encode('utf-8')
    report = '''FIGHT ROYALE GODOT - UPDATE 12A (ADVANCED AI: SPACING & ATTACK CHOICES)

Implemented:
- Every AI controls its own movement toward or around the opponent.
- Melee target spacing uses actual light-attack reach, rather than one global threshold.
- Ranged AI approaches firing distance, strafes and retreats when pressured.
- Both AI classes return toward arena center to avoid edge camping.
- Melee approach can sprint when the target is far away.
- Skill choices evaluate attack type, range, cooldown and defensive context.
- More opportunistic attack decisions against staggered or blocking opponents.
- The old automatic melee approach only activates when no explicit AI movement is requested.

Preserved:
- Duel vs CPU and CPU vs CPU, per-fighter difficulty from Update 11.
- Existing damage values, parry timing, guard fatigue and skill cooldown lengths.
- Spectator cameras, third-person camera, player controls, weapons, VRMs, SFX.

Next suggested 12B: intelligent projectile parry/dodge and heavy attack defense.
Next suggested 12C: whiff punish, baiting and anti-stalling refinements.

This update does not verify Godot runtime or VRM rendering. Open the project in
Godot Editor first for automatic imports, then test both game modes.
'''.encode('utf-8')
    if not (root / REPORT).is_file() or (root / REPORT).read_bytes() != report:
        updates[REPORT] = report
    return updates


def install(root: Path, updates: dict[str, bytes], dry: bool) -> Path | None:
    if not updates:
        print('Update 12A already installed. No changes necessary.')
        return None
    print('Changes:')
    for rel in updates:
        print('  -', rel)
    if dry:
        print('Dry run passed; no files changed.')
        return None
    backup = root.parent / (root.name + '_backups') / ('advanced_ai_12a_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {'version': VERSION, 'project': str(root), 'files': {}}
    for rel, new in updates.items():
        p = root / rel
        old = p.read_bytes() if p.is_file() else None
        manifest['files'][rel] = {'old': sha(old), 'new': sha(new)}
        if old is not None:
            dest = backup / 'originals' / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(old)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    touched = []
    try:
        for rel, new in updates.items():
            write_atomic(root / rel, new)
            touched.append(rel)
    except Exception:
        for rel in reversed(touched):
            backup_file = backup / 'originals' / rel
            if backup_file.is_file():
                write_atomic(root / rel, backup_file.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print('Backup:', backup)
    return backup


def restore(root: Path, backup_text: str) -> None:
    backup = Path(backup_text).expanduser().resolve()
    meta = json.loads((backup / 'manifest.json').read_text(encoding='utf-8'))
    if meta.get('version') != VERSION or Path(meta.get('project', '')).resolve() != root:
        raise ValueError('This backup does not belong to Update 12A or this project.')
    for rel, hashes in meta['files'].items():
        p = root / rel
        current = p.read_bytes() if p.is_file() else None
        if sha(current) != hashes['new']:
            raise ValueError(f'{rel} changed after installation; refusing destructive restore.')
        if hashes['old'] is not None and not (backup / 'originals' / rel).is_file():
            raise ValueError(f'Backup missing original file: {rel}')
    for rel in meta['files']:
        origin = backup / 'originals' / rel
        if origin.is_file():
            write_atomic(root / rel, origin.read_bytes())
        else:
            (root / rel).unlink(missing_ok=True)
    print('Restored backup:', backup)


def check_godot(root: Path) -> None:
    engine = shutil.which('godot') or shutil.which('godot4') or shutil.which('Godot')
    if not engine:
        print('Godot executable not on PATH; open the project in the Godot editor to validate scripts.')
        return
    print('Checking Godot scripts with:', engine)
    cmd = [engine, '--headless', '--path', str(root), '--editor', '--quit']
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        print((result.stdout + '\n' + result.stderr)[-9000:])
        if result.returncode != 0:
            print('Godot reported errors (exit code', result.returncode, '). Review the messages above.')
        else:
            print('Godot editor check completed with exit code 0.')
    except (OSError, subprocess.TimeoutExpired) as ex:
        print('Godot check could not complete:', ex)


def main() -> int:
    argp = argparse.ArgumentParser(description='Fight Royale Godot Update 12A: Advanced AI')
    argp.add_argument('--dry-run', action='store_true', help='Validate patches without modifying files')
    argp.add_argument('--check-godot', action='store_true', help='Run Godot headless editor check after installing (if executable is on PATH)')
    argp.add_argument('--restore', metavar='BACKUP_DIRECTORY', help='Restore a backup created by this installer')
    argp.add_argument('--project', type=Path, default=Path.cwd(), help='Godot project directory (default: current folder)')
    args = argp.parse_args()
    root = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(root, args.restore)
        else:
            edits = changes_for(root)
            install(root, edits, args.dry_run)
            if args.check_godot and not args.dry_run:
                check_godot(root)
        return 0
    except Exception as ex:
        print('ERROR —', ex, file=sys.stderr)
        print('No unvalidated files will be patched. Send this error if you need a compatibility fix.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
