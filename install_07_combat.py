#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot | Update 07 — Combat contact, damage/knockback and hit feel.

Run from the Godot project folder:
    python install_07_combat.py

Optional:
    python install_07_combat.py --dry-run
    python install_07_combat.py --check-godot
    python install_07_combat.py --restore "<backup directory printed at install>"

Requires Updates 01–06. Uses only Python's standard library. Does not alter VRMs,
SFX or existing character damage tables. Rolls back partial writes on errors.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

VERSION = '07.0'
MARKER = '# FRG07 - persistent melee contact and directional knockback'
FILES = ('scripts/fighter.gd', 'scripts/match.gd')


def once(src: str, old: str, new: str, label: str) -> str:
    n = src.count(old)
    if n != 1:
        raise RuntimeError(f'{label}: expected 1 matching anchor, found {n}: {old[:90]!r}. '
                           'No files were changed; upload the current scripts for a tailored patch.')
    return src.replace(old, new, 1)


def patch_fighter(src: str) -> str:
    if MARKER in src:
        required = ('func active_melee()', 'func _apply_knock(', '_knock_dir',
                    'func _interrupt_attack()', 'pos += _knock_dir * _knock * dt')
        if all(v in src for v in required):
            return src
        raise RuntimeError('Partially installed Update 07 detected in fighter.gd')
    if not all(x in src for x in ('DODGE_SPEED', '_steer_vel', 'model.run', 'func _read_dodge()')):
        raise RuntimeError('Movement Update 06 missing from fighter.gd. Install Update 06 first.')

    src = once(src, 'const STUN_DR := 0.6',
        'const STUN_DR := 0.6\n' + MARKER + '\nconst KNOCK_DAMPING := 14.0',
        'fighter.gd constants')
    src = once(src, 'var _knock := 0.0',
        'var _knock := 0.0\nvar _knock_dir := Vector3.ZERO',
        'fighter.gd knock direction')
    src = once(src,
        '## Melee trail should show (wind-up end, active, just after).',
        '''## True throughout the *entire* damaging window, not just on the first active frame.
func active_melee() -> bool:
	return state == S.ATTACK and not atk.is_empty() and String(atk.get("type", "")) == "melee" \\
		and atk_phase == 1 and state_t <= float(atk.wind) + float(atk.active) + 0.0001

## Melee trail should show (wind-up end, active, just after).''',
        'fighter.gd active melee predicate')
    src = once(src,
        '\t\t_knock = maxf(_knock - 14.0 * dt, 0.0)\n\t\tv -= _knock\n'
        '\t\tif dist < MIN_DIST and v > 0.0:\n\t\t\tv = 0.0\n\t\tpos += dir * v * dt',
        '''		# Knockback uses the ORIGINAL impact direction, independent of facing changes.
		_knock = maxf(_knock - KNOCK_DAMPING * dt, 0.0)
		if dist < MIN_DIST and v > 0.0:
			v = 0.0
		pos += dir * v * dt
		if _knock > 0.0:
			pos += _knock_dir * _knock * dt''',
        'fighter.gd directional knock movement')
    src = once(src,
        '\t\tvar steer := 1.0 if state == S.IDLE else 0.5 if state == S.BLOCK else 0.4 if state == S.CHARGE else 0.0',
        '''		var steer := 1.0 if state == S.IDLE else 0.5 if state == S.BLOCK else 0.4 if state == S.CHARGE else 0.0
		# Don't let direct input instantly erase a strong knockback reaction.
		if _knock > 0.2: steer *= 0.35''',
        'fighter.gd impact steering penalty')
    src = once(src, 'func push_back(speed: float) -> void: _knock = maxf(_knock, speed)',
        '''func _apply_knock(attacker, speed: float) -> void:
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
	# A hit or clash cancels pending combo inputs; the next tap starts from l1.
	_holding = false
	_buffered = false
	_combo_next = "l1"
	_combo_timer = 0.0

func push_back(speed: float) -> void:
	_apply_knock(opponent, speed)''',
        'fighter.gd knock / combo interruption helpers')
    src = once(src, '\t\t\t_knock = 3.5', '\t\t\t_apply_knock(attacker, 3.5)',
               'fighter.gd guard break knock')
    src = once(src, '\t\t_knock = float(a.knock) * 0.5',
               '\t\t_apply_knock(attacker, float(a.knock) * 0.5)',
               'fighter.gd blocked knock')
    src = once(src, '\t_knock = float(a.knock)',
               '\t_apply_knock(attacker, float(a.knock))',
               'fighter.gd hit knock')
    src = once(src,
        '\telse: _stun = stun; _stun_pose = "hit"; _holding = false; _set_state(S.HITSTUN)',
        '\telse: _stun = stun; _stun_pose = "hit"; _interrupt_attack(); _set_state(S.HITSTUN)',
        'fighter.gd hit interrupt')
    src = once(src,
        '\t_stun = d; _stun_pose = "stagger"; _holding = false; _set_state(S.STAGGER)',
        '\t_stun = d; _stun_pose = "stagger"; _interrupt_attack(); _set_state(S.STAGGER)',
        'fighter.gd stagger interrupt')
    src = once(src,
        '\t_stun = 0.38; _stun_pose = "clash"; _holding = false; _knock = 4.0; _set_state(S.HITSTUN)',
        '\t_stun = 0.38; _stun_pose = "clash"; _interrupt_attack(); _apply_knock(opponent, 4.0); _set_state(S.HITSTUN)',
        'fighter.gd clash recoil')
    return src


def patch_match(src: str) -> str:
    if MARKER in src:
        required = ('_melee_hits', 'func _active_melee_contact(',
                    'func _swept_projectile_point(', 'f.active_melee()', 'contact_key')
        if all(v in src for v in required):
            return src
        raise RuntimeError('Partially installed Update 07 detected in match.gd')
    if not all(x in src for x in ('cfg.get("spectator"', 'func _melee(', 'func _update_projectiles(')):
        raise RuntimeError('Game Modes Update 02 missing from match.gd. Install Update 02 first.')

    src = once(src, 'var _trails: Dictionary = {}    # Fighter -> Trail',
        'var _trails: Dictionary = {}    # Fighter -> Trail\n'
        'var _melee_hits: Dictionary = {}  ' + MARKER + '\n'
        'const MELEE_FRONT_DOT := 0.15\nconst MELEE_HEIGHT_TOLERANCE := 1.3',
        'match.gd hit registry')
    src = once(src, 'fighters.clear(); _trails.clear(); _projectiles.clear(); _strike_marks.clear(); _timers.clear()',
        'fighters.clear(); _trails.clear(); _melee_hits.clear(); _projectiles.clear(); _strike_marks.clear(); _timers.clear()',
        'match.gd round reset')
    src = once(src,
        '\tfor f in fighters:\n\t\tf.tick(dt)\n\t\tif _trails.has(f):',
        '''	for f in fighters:
		f.tick(dt)
		# A sword remains dangerous for the entire active window. One contact per
		# defender/swing is enforced in _melee, so framerate cannot multiply damage.
		if dt > 0.0 and not round_over and f.active_melee():
			_active_melee_contact(f)
		if _trails.has(f):''',
        'match.gd active contact sampling')

    start = src.index('func _melee(f: Fighter, a: Dictionary) -> void:')
    end = src.index('\nfunc _fire(f: Fighter, a: Dictionary) -> void:', start)
    old = src[start:end]
    if not all(x in old for x in ('_clash(', 'apply_hit(', 'enemies_of(', 'a.reach')):
        raise RuntimeError('Unknown melee collision implementation; refusing to overwrite it')
    new = '''func _active_melee_contact(f: Fighter) -> void:
	_melee(f, f.atk)

func _melee(f: Fighter, a: Dictionary) -> void:
	if not f.active_melee():
		return
	var contact_key := "%d:%d" % [f.id, f.swing_serial]
	var landed: Dictionary = _melee_hits.get(contact_key, {})
	var fwd := f.forward()
	for d in enemies_of(f):
		if landed.has(d.id):
			continue
		var to: Vector3 = d.position - f.position
		var dy := absf(to.y)
		to.y = 0.0
		var dist := to.length()
		var dir := to / maxf(dist, 0.001)
		var front_ok := dist <= 0.6 or dir.dot(fwd) >= MELEE_FRONT_DOT
		if not front_ok:
			continue
		# Two overlapping melee active windows can clash. Check BOTH fighters'
		# facings, so a hit from behind doesn't produce a fake frontal clash.
		if d is Fighter and d.active_melee() and dy < 0.8 \\
			and dist <= minf(float(a.reach), float(d.atk.reach)) + 0.3 \\
			and (dist <= 0.6 or (-dir).dot(d.forward()) >= MELEE_FRONT_DOT):
			landed[d.id] = true
			_melee_hits[contact_key] = landed
			var other_key := "%d:%d" % [d.id, d.swing_serial]
			var other_landed: Dictionary = _melee_hits.get(other_key, {})
			other_landed[f.id] = true
			_melee_hits[other_key] = other_landed
			_clash(f, d, f.position + dir * minf(dist * 0.5, 0.8) + Vector3(0, 1.15, 0))
			return
		if dist - d.radius + 0.35 > float(a.reach) or dy > MELEE_HEIGHT_TOLERANCE:
			continue
		# Record contact BEFORE hit handling (which can trigger counters/KO).
		landed[d.id] = true
		_melee_hits[contact_key] = landed
		apply_hit(f, d, a, f.atk_power, d.chest() - dir * 0.15, dir, false)
'''
    src = src[:start] + new + src[end:]

    # High-speed projectiles use swept tests to avoid tunneling through fighters.
    src = once(src, '\t\tvar node: MeshInstance3D = p.node\n\t\tnode.global_position += p.vel * dt',
        '\t\tvar node: MeshInstance3D = p.node\n'
        '\t\tvar old_pos: Vector3 = node.global_position\n'
        '\t\tnode.global_position += p.vel * dt',
        'match.gd old projectile position')
    src = once(src,
        '''			if node.global_position.distance_to(e.chest()) < 0.3 * p.size + e.radius:
				p.hit[e.id] = true
				var dir: Vector3 = p.vel; dir.y = 0; dir = dir.normalized()
				_impact(p.atk, node.global_position, p.color, 0.7)
				apply_hit(p.shooter, e, p.atk, p.power, node.global_position, dir, true)''',
        '''			var contact: Vector3 = _swept_projectile_point(e.chest(), old_pos, node.global_position)
			if contact.distance_to(e.chest()) < 0.3 * p.size + e.radius:
				p.hit[e.id] = true
				var dir: Vector3 = p.vel
				dir.y = 0.0
				dir = dir.normalized()
				_impact(p.atk, contact, p.color, 0.7)
				apply_hit(p.shooter, e, p.atk, p.power, contact, dir, true)''',
        'match.gd swept projectile hit')
    src = once(src, '\nfunc _update_projectiles(dt: float) -> void:',
        '''
## Closest point on projectile travel segment, including both end points.
func _swept_projectile_point(target: Vector3, a: Vector3, b: Vector3) -> Vector3:
	var travel := b - a
	var length_sq := travel.length_squared()
	if length_sq < 0.000001:
		return a
	var along := clampf((target - a).dot(travel) / length_sq, 0.0, 1.0)
	return a + travel * along

func _update_projectiles(dt: float) -> void:''',
        'match.gd projectile segment helper')
    # Preserve existing visual effects and hit-stop; tighten heavy/crit display on KO.
    src = once(src, '\tvar heavy: bool = a.heavy or a.id == "l3"',
        '\tvar heavy: bool = bool(a.get("heavy", false)) or String(a.get("id", "")) == "l3"',
        'match.gd resilient heavy-hit classification')
    return src


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def safe_write(p: Path, contents: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_name(p.name + '.tmp-' + uuid.uuid4().hex[:8])
    try:
        temp.write_bytes(contents)
        os.replace(temp, p)
    finally:
        if temp.exists():
            temp.unlink()


def json_bytes(data: dict) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')


def resolve_root(path: str | None) -> Path:
    root = Path(path or '.').expanduser().resolve()
    for rel in ('project.godot', *FILES):
        if not (root / rel).is_file():
            raise RuntimeError(f'Missing {rel}. Run this installer inside your Godot project folder.')
    return root


def build_changes(root: Path) -> dict[str, bytes]:
    changes: dict[str, bytes] = {}
    changes[FILES[0]] = patch_fighter((root / FILES[0]).read_text(encoding='utf-8-sig')).encode('utf-8')
    changes[FILES[1]] = patch_match((root / FILES[1]).read_text(encoding='utf-8-sig')).encode('utf-8')
    report = '''FIGHT ROYALE GODOT — COMBAT UPDATE 07

CHANGES
- Samples melee collision throughout each attack's active window; prior code
  tested only the first active frame and could miss moving opponents.
- Keeps one contact (hit/parry/block/clash) per target per swing, even when
  running above 60 FPS or during hit-stop.
- Uses facing checks for melee and clashes, avoiding clashes from behind.
- Improves knockback: defender moves away from the actual source of impact,
  instead of using whichever direction the character later faces.
- Hitstun, stagger and clashes clear buffered combo inputs.
- Uses swept (segment) hit detection on fast projectiles to reduce tunneling.
- Keeps the existing attacks.json damage, skill cooldowns, guard/parry rules,
  SFX, VRM assets, VFX and two game modes unchanged.

TESTING
Run Duel vs CPU and CPU vs CPU. Check a light combo, heavy hit, projectile,
block, guard break, and clash. Confirm each swing deals damage only once.

The installer was verified by Python static checks and idempotence testing.
Actual Godot parsing/rendering still needs confirmation on your machine.
Use --check-godot when you have the Godot executable on PATH.
'''
    changes['reports/combat_audit_07.txt'] = report.encode('utf-8')
    return changes


def install(root: Path, changes: dict[str, bytes], dry_run: bool) -> Path | None:
    pending = {rel: data for rel, data in changes.items()
               if not (root / rel).is_file() or (root / rel).read_bytes() != data}
    for rel in changes:
        print('  %-10s %s' % ('UPDATE' if rel in pending else 'unchanged', rel))
    print('Files to change:', len(pending))
    if dry_run:
        print('Dry run: no files written.')
        return None
    if not pending:
        print('Already installed. No changes made.')
        return None
    folder = (root.parent / (root.name + '_backups') /
              ('combat_07_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
               + '_' + uuid.uuid4().hex[:6]))
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {'version': VERSION, 'project': str(root), 'files': []}
    for rel, contents in pending.items():
        target = root / rel
        orig = target.read_bytes() if target.is_file() else None
        if orig is not None:
            saved = folder / 'originals' / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(orig)
        manifest['files'].append({'path': rel, 'existed': orig is not None,
                                  'before': sha(orig) if orig is not None else None,
                                  'after': sha(contents)})
    (folder / 'manifest.json').write_bytes(json_bytes(manifest))
    completed = []
    try:
        for rel, contents in pending.items():
            safe_write(root / rel, contents)
            completed.append(rel)
    except Exception:
        for rel in reversed(completed):
            saved = folder / 'originals' / rel
            if saved.is_file():
                safe_write(root / rel, saved.read_bytes())
            elif (root / rel).is_file():
                (root / rel).unlink()
        raise
    print('Backup:', folder)
    return folder


def restore(root: Path, backup: str) -> None:
    folder = Path(backup).expanduser().resolve()
    meta = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if meta.get('version') != VERSION or Path(meta.get('project', '')).resolve() != root:
        raise RuntimeError('The selected backup was not created by Update 07 for this project')
    for entry in meta['files']:
        rel = Path(entry['path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise RuntimeError('Unsafe restore path')
        target = root / rel
        if target.is_file() and sha(target.read_bytes()) != entry['after']:
            raise RuntimeError(f'{rel} changed after Update 07; refusing to overwrite edits')
        if entry['existed']:
            saved = (folder / 'originals' / rel).read_bytes()
            if sha(saved) != entry['before']:
                raise RuntimeError(f'Backup corrupted: {rel}')
    for entry in meta['files']:
        rel = Path(entry['path'])
        target = root / rel
        if entry['existed']:
            safe_write(target, (folder / 'originals' / rel).read_bytes())
        elif target.is_file():
            target.unlink()
        print('  restored', rel)
    print('Backup restored successfully.')


def check_godot(root: Path, selected: str | None) -> int:
    exe = None
    if selected:
        exe = str(Path(selected).resolve()) if Path(selected).is_file() else shutil.which(selected)
    if not exe:
        exe = next((p for name in ('godot', 'godot4', 'godot.exe')
                    if (p := shutil.which(name))), None)
    if not exe:
        print('Godot not found. Open the project in the editor, or pass --godot PATH.')
        return 0
    for args in (['--headless', '--editor', '--path', str(root), '--quit'],
                 ['--headless', '--path', str(root), '--quit-after', '3']):
        try:
            proc = subprocess.run([exe, *args], capture_output=True, text=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print('Godot validation error:', exc)
            return 2
        print((proc.stdout + proc.stderr)[-5000:])
        if proc.returncode != 0:
            print('Godot failed with exit code', proc.returncode)
            return 2
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Fight Royale Godot Update 07 — Combat')
    p.add_argument('--project', help='Godot project path (default: current working directory)')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--restore', metavar='BACKUP_FOLDER')
    p.add_argument('--check-godot', action='store_true')
    p.add_argument('--godot', metavar='EXECUTABLE')
    args = p.parse_args(argv)
    root = resolve_root(args.project)
    print('FIGHT ROYALE GODOT | UPDATE 07 — COMBAT\nProject:', root)
    if args.restore:
        restore(root, args.restore)
        return 0
    changes = build_changes(root)
    install(root, changes, args.dry_run)
    if not args.dry_run:
        print('Done. Review: reports/combat_audit_07.txt')
    if args.check_godot and not args.dry_run:
        return check_godot(root, args.godot)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, KeyError, UnicodeError) as exc:
        print('ERROR:', exc, file=sys.stderr)
        sys.exit(1)
