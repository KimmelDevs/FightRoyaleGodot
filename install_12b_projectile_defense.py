#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot — Update 12B: predicted projectile defense.

Run from the Godot project folder:
    python install_12b_projectile_defense.py

Optional:
    python install_12b_projectile_defense.py --dry-run
    python install_12b_projectile_defense.py --check-godot
    python install_12b_projectile_defense.py --restore BACKUP_DIRECTORY

Requires Update 12A. Does not overwrite VRMs or SFX. All patch anchors are
validated before changes, then backed up with SHA256-verified restoration.
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

VERSION = "12B.1"
MARKER = "# FRG12B - predicted projectile defense and melee interception"
AI_FILE = "scripts/ai_brain.gd"
MATCH_FILE = "scripts/match.gd"
REPORT = "reports/projectile_defense_12b.txt"

AI_DODGE = '''func _dodge(f: Fighter) -> void:
	# FRG12B - predict the closest approach to the fighter, NOT simply the
	# projectile's distance from the fighter at the current frame.  React only
	# when a projectile is actually on a collision course.
	for pr in threats.projectile_threats():
		if pr.target != f or _seen.has(pr.id):
			continue
		var velocity: Vector3 = pr.vel
		var speed_squared: float = velocity.length_squared()
		if speed_squared < 0.01:
			continue
		var toward: Vector3 = f.chest() - pr.pos
		var eta: float = toward.dot(velocity) / speed_squared
		if eta <= 0.0 or eta > 1.25:
			continue
		var closest: Vector3 = pr.pos + velocity * eta
		var danger_radius: float = f.radius + 0.30 * float(pr.get("size", 1.0)) + 0.12
		if closest.distance_to(f.chest()) > danger_radius:
			continue
		# Wait for a safe opening: hitstun, attacks, and recovery have priority
		# over newly planned reactions. Never cancel a scheduled defense with
		# an unrelated second projectile.
		if f.state != Fighter.S.IDLE and f.state != Fighter.S.BLOCK:
			continue
		if _block_wait >= 0.0 or _block_hold > 0.0 or _projectile_dodge_wait >= 0.0:
			continue
		var reaction: float = _r(float(p.react[0]), float(p.react[1]))
		if eta <= reaction + 0.02:
			_seen[pr.id] = true
			continue  # Too late for this CPU's reaction time.
		var incoming_horizontal := Vector3(-velocity.x, 0.0, -velocity.z)
		var facing_ok: bool = incoming_horizontal.length_squared() <= 0.01 or f.forward().dot(incoming_horizontal.normalized()) >= 0.20
		# Skilled melee AI can intentionally time a LIGHT attack to intercept a
		# non-explosive projectile. The match validates the actual active-frame
		# collision. This is not a guaranteed or instantly triggered defense.
		if facing_ok and _try_projectile_clash(f, pr, eta, reaction):
			_seen[pr.id] = true
			continue
		var can_guard: bool = facing_ok and f.on_ground and f.guard > 8.0 and f.state == Fighter.S.IDLE
		var can_dodge: bool = f.on_ground and f._dodge_cd <= 0.0 and f.state == Fighter.S.IDLE
		if can_guard and eta > reaction + 0.06 and randf() < float(p.parry):
			var start: float = maxf(reaction, eta - minf(f.parry_window * 0.60, 0.095))
			if start < eta - 0.02:
				_schedule(start, maxf(0.19, eta - start + 0.10))
				_seen[pr.id] = true
				continue
		if can_dodge and randf() < float(p.jump):
			var sideways := Vector3(-velocity.z, 0.0, velocity.x).normalized()
			if sideways.length_squared() < 0.01:
				sideways = Vector3(-f.forward().z, 0.0, f.forward().x)
			# Dodge inward when near the edge instead of rolling out of bounds.
			var plus: Vector3 = f.position + sideways * 1.8
			var minus: Vector3 = f.position - sideways * 1.8
			_projectile_dodge_dir = sideways if plus.length_squared() < minus.length_squared() else -sideways
			_projectile_dodge_wait = maxf(reaction, eta - 0.18)
			_seen[pr.id] = true
			continue
		if can_guard and randf() < float(p.block):
			_schedule(reaction, eta - reaction + 0.25)
			_seen[pr.id] = true
			continue
		if f.on_ground and eta > reaction + 0.24 and randf() < float(p.jump):
			_jump_wait = maxf(reaction, eta - 0.34)
		_seen[pr.id] = true
	# Keep the existing warning-marker/area-strike evasions.
	for m in threats.strike_threats():
		if m.target != f or _seen.has(m.id):
			continue
		_seen[m.id] = true
		var eta: float = m.land - threats.now()
		if randf() < 0.3 + float(p.jump):
			_side_t = clampf(eta, 0.3, 0.8)
			_side_sign = 1.0 if randf() < 0.5 else -1.0
		elif randf() < 0.5:
			_jump_wait = maxf(eta - 0.3, 0.0)
	if _seen.size() > 300:
		_seen.clear()

func _try_projectile_clash(f: Fighter, pr: Dictionary, eta: float, reaction: float) -> bool:
	if f.kit in RANGED or f.state != Fighter.S.IDLE or not f.on_ground:
		return false
	if f.atk_lock > 0.0 or _hold > 0.0 or not _queue.is_empty():
		return false
	if bool(pr.get("pierce", false)):
		return false
	var style: String = String(pr.get("style", ""))
	if style in ["explosion", "bomb", "meteor", "grenade", "rocket"]:
		return false
	var light: Dictionary = f.attacks.get("l1", {})
	if String(light.get("type", "")) != "melee":
		return false
	var wind: float = float(light.get("wind", 0.20)) * f.attack_time_multiplier()
	if eta < reaction + wind + 0.12:
		return false
	# More accurate and frequent interception on Hard/Master than on Easy.
	var chance: float = 0.36 if float(p.think) < 0.8 else 0.20 if float(p.think) <= 1.0 else 0.08 if float(p.think) < 1.5 else 0.0
	if randf() >= chance:
		return false
	var wait_time: float = maxf(reaction, eta - wind - 0.095)
	_queue.append([wait_time, 0.06])
	return true

'''

# Apply both queued-dodge resolution and the existing block/attack processing.
THINK_BEFORE = '\t_dodge(f)\n\t_position(f, o, dt)\n'
THINK_AFTER = '''\t_dodge(f)
	# Resolve projectile dodge at the predicted interception time.
	if _projectile_dodge_wait >= 0.0:
		_projectile_dodge_wait -= dt
		if _projectile_dodge_wait < 0.0:
			f.in_dodge = _projectile_dodge_dir
	_position(f, o, dt)
'''

THREATS_BEFORE = 'return _projectiles.map(func(p): return {"target": p.target, "pos": p.node.global_position, "vel": p.vel, "id": p.id})'
THREATS_AFTER = ('return _projectiles.map(func(p): return {"target": p.target, '
                 '"pos": p.node.global_position, "vel": p.vel, "id": p.id, '
                 '"size": p.size, "style": String(p.atk.get("style", "")), '
                 '"pierce": bool(p.pierce)})')

UPDATE_BEFORE = '''		var done := false
		for e in fighters:
			if e.team == p.team or e.is_down() or p.hit.has(e.id): continue
'''
UPDATE_AFTER = '''		var done := false
		# FRG12B - melee-vs-projectile clash. No free block: only an actual
		# active melee swing facing the incoming bolt can destroy it. Explosive
		# and piercing projectiles retain their original collision behavior.
		var style: String = String(p.atk.get("style", ""))
		if not bool(p.pierce) and not (style in ["explosion", "bomb", "meteor", "grenade", "rocket"]):
			for defender in fighters:
				if defender.team == p.team or defender.is_down() or not defender.active_melee():
					continue
				var cut: Vector3 = _swept_projectile_point(defender.chest(), old_pos, node.global_position)
				var local_cut: Vector3 = cut - defender.global_position
				if local_cut.y < 0.55 or local_cut.y > 2.2:
					continue
				local_cut.y = 0.0
				var reach: float = clampf(float(defender.atk.get("reach", 1.8)) * 0.65, 0.8, 1.45)
				if local_cut.length() > reach:
					continue
				if local_cut.length() > 0.1 and local_cut.normalized().dot(defender.forward()) < 0.25:
					continue
				fx.sparks(cut, Color(defender.look.glow), 18, 5.0, -p.vel.normalized())
				fx.ring(cut, Color("#ffe6a4"), 0.85, 0.2, 0.65)
				fx.number(cut + Vector3(0, 0.22, 0), "CLASH!", Color("#ffe6a4"), 0.65)
				done = true
				break
		if done:
			node.queue_free()
			_projectiles.erase(p)
			continue
		for e in fighters:
			if e.team == p.team or e.is_down() or p.hit.has(e.id): continue
'''


def one(s: str, old: str, new: str, what: str) -> str:
    count = s.count(old)
    if count != 1:
        raise ValueError(f"{what}: expected one anchor, found {count}; refusing to overwrite unrecognized code")
    return s.replace(old, new, 1)


def function_span(s: str, name: str) -> tuple[int, int, str]:
    pattern = rf'(?m)^func {re.escape(name)}\('
    occurrences = list(re.finditer(pattern, s))
    if len(occurrences) != 1:
        raise ValueError(f"{name}: expected exactly one function, found {len(occurrences)}")
    a = occurrences[0].start()
    nxt = re.search(r'(?m)^func [a-zA-Z_][A-Za-z_0-9]*\(', s[occurrences[0].end():])
    b = occurrences[0].end() + nxt.start() if nxt else len(s)
    return a, b, s[a:b]


def patch_ai(s: str) -> str:
    if MARKER in s:
        if 'func _try_projectile_clash(' in s and '_projectile_dodge_wait' in s and 'closest.distance_to' in s:
            return s
        raise ValueError('Partial Update 12B found in ai_brain.gd')
    if 'FRG12A' not in s or 'func _preferred_range(' not in s:
        raise ValueError('Update 12A is required. Run install_12a_advanced_ai.py first.')
    s = one(s, 'var _seen := {}\n',
            'var _seen := {}\n' + MARKER +
            '\nvar _projectile_dodge_wait := -1.0\nvar _projectile_dodge_dir := Vector3.ZERO\n',
            'AI defense state')
    s = one(s, THINK_BEFORE, THINK_AFTER, 'AI think loop')
    a, b, old = function_span(s, '_dodge')
    if 'threats.projectile_threats()' not in old or 'threats.strike_threats()' not in old:
        raise ValueError('Unexpected _dodge implementation. No files changed.')
    s = s[:a] + AI_DODGE + s[b:].lstrip('\n')
    return s


def patch_match(s: str) -> str:
    if MARKER in s:
        if 'var local_cut: Vector3' in s and '"style": String(p.atk.get(' in s:
            return s
        raise ValueError('Partial Update 12B found in match.gd')
    if 'func projectile_threats() -> Array:' not in s or 'func _update_projectiles(dt: float)' not in s:
        raise ValueError('Expected projectile methods missing from match.gd')
    s = one(s, THREATS_BEFORE, THREATS_AFTER, 'Projectile threat data')
    s = one(s, UPDATE_BEFORE, UPDATE_AFTER.replace('FRG12B -', MARKER[2:]+' -'), 'Projectile collision loop')
    return s


def sha(x: bytes | None) -> str | None:
    return hashlib.sha256(x).hexdigest() if x is not None else None


def write_atomic(p: Path, data: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_name(p.name + '.frg12b_' + uuid.uuid4().hex[:8] + '.tmp')
    try:
        temp.write_bytes(data)
        temp.replace(p)
    finally:
        temp.unlink(missing_ok=True)


def plan(root: Path) -> dict[str, bytes]:
    if not (root/'project.godot').is_file():
        raise ValueError('Run this command from the Godot project folder (containing project.godot).')
    edits = {}
    for rel, fn in [(AI_FILE, patch_ai), (MATCH_FILE, patch_match)]:
        p = root / rel
        if not p.is_file():
            raise ValueError(f'Missing {rel}; no files changed')
        before = p.read_text(encoding='utf-8-sig')
        after = fn(before)
        if not after.startswith('class_name '):
            raise ValueError(f'Unexpected first line in {rel}')
        if after != before:
            edits[rel] = after.encode('utf-8')
    report = """FIGHT ROYALE GODOT — UPDATE 12B: PREDICTIVE PROJECTILE DEFENSE

Requires Update 12A. Compatible with Duel vs CPU and CPU vs CPU.

WHAT CHANGED
- Projectile AI checks direction and closest point of approach; near misses are ignored.
- Difficulty reaction delays are respected before choosing a defensive action.
- AI may time its parry, hold a block, dodge sideways, or jump.
- Melee AI on Hard/Master can time a light swing to collide with an incoming shot.
- A projectile can be destroyed only by a REAL active melee swing facing it.
- Piercing and explosion-style shots cannot be removed by this clash mechanism.
- Neither damage nor cooldown values have been modified.

TESTS IN GODOT
1. Place a melee CPU opposite a ranged CPU (try Master on the melee side).
2. Watch for deliberate sword-vs-projectile clashes as well as parries/dodges.
3. Try Easy: noticeably slower reactions than Master.
4. Test Duel vs CPU, spectator pause and rematch.
5. Check Godot's Debugger/Output for errors or import warnings.

This report is a static installer result. Engine compilation and gameplay must
still be verified locally with Godot; Python tests do not prove that Godot runs.
""".encode('utf-8')
    if not (root/REPORT).is_file() or (root/REPORT).read_bytes() != report:
        edits[REPORT] = report
    return edits


def install(root: Path, edits: dict[str, bytes], dry: bool) -> None:
    if not edits:
        print('Update 12B already installed: no changes necessary.')
        return
    print('Update 12B changes:')
    for f in edits:
        print(' -', f)
    if dry:
        print('Dry run passed; nothing written.')
        return
    bdir = (root.parent / (root.name + '_backups') /
            ('projectile_12b_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
             + '_' + uuid.uuid4().hex[:6]))
    bdir.mkdir(parents=True, exist_ok=False)
    manifest = {'version': VERSION, 'project': str(root), 'files': {}}
    for rel, data in edits.items():
        p = root/rel
        old = p.read_bytes() if p.is_file() else None
        manifest['files'][rel] = {'old': sha(old), 'new': sha(data)}
        if old is not None:
            backup = bdir/'originals'/rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(old)
    (bdir/'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    touched = []
    try:
        for rel, data in edits.items():
            write_atomic(root/rel, data)
            touched.append(rel)
    except Exception:
        for rel in reversed(touched):
            original = bdir/'originals'/rel
            if original.is_file():
                write_atomic(root/rel, original.read_bytes())
            else:
                (root/rel).unlink(missing_ok=True)
        raise
    print('Backup:', bdir)
    print('Install complete. Open Godot Editor, allow imports, then test CPU vs CPU.')


def restore(root: Path, backup_dir: str) -> None:
    bdir = Path(backup_dir).expanduser().resolve()
    data = json.loads((bdir/'manifest.json').read_text(encoding='utf-8'))
    if data['version'] != VERSION or Path(data['project']).resolve() != root:
        raise ValueError('Backup belongs to a different update or project.')
    for rel, hashes in data['files'].items():
        existing = (root/rel).read_bytes() if (root/rel).is_file() else None
        if sha(existing) != hashes['new']:
            raise ValueError(f'{rel} was modified after installation; refusing to overwrite changes.')
        if hashes['old'] and not (bdir/'originals'/rel).is_file():
            raise ValueError(f'Original backup is missing: {rel}')
    for rel in data['files']:
        old = bdir/'originals'/rel
        if old.is_file():
            write_atomic(root/rel, old.read_bytes())
        else:
            (root/rel).unlink(missing_ok=True)
    print('Restored:', bdir)


def check_godot(root: Path) -> None:
    binary = shutil.which('godot') or shutil.which('godot4') or shutil.which('Godot')
    if not binary:
        print('Godot executable not found on PATH. Use Godot Editor to validate.')
        return
    result = subprocess.run([binary, '--headless', '--editor', '--path', str(root), '--quit'],
                            capture_output=True, text=True, timeout=120)
    print((result.stdout + '\n' + result.stderr)[-10000:])
    if result.returncode != 0:
        raise RuntimeError(f'Godot engine returned error code {result.returncode}')


def main() -> int:
    parser = argparse.ArgumentParser(description='Fight Royale Godot Update 12B - Projectile Defense')
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--check-godot', action='store_true')
    parser.add_argument('--restore', metavar='BACKUP_DIR')
    args = parser.parse_args()
    root = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(root, args.restore)
        else:
            install(root, plan(root), args.dry_run)
            if args.check_godot and not args.dry_run:
                check_godot(root)
        return 0
    except Exception as ex:
        print('ERROR —', ex, file=sys.stderr)
        print('No unvalidated patch will be applied. Send this error for a compatibility fix.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
