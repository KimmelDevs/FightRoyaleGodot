#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot - Update 12C: whiff punishment, baiting & anti-stalling.

Run from your Godot project folder:
    python install_12c_whiff_punish.py

Options:
    python install_12c_whiff_punish.py --dry-run
    python install_12c_whiff_punish.py --check-godot
    python install_12c_whiff_punish.py --restore FULL_BACKUP_PATH

Requires AI updates 12A/12B. Never edits character VRM/SFX/assets.
Inspects all patch anchors BEFORE writing; creates restorable SHA256 backups.
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

VERSION = "12C.1"
AI_FILE = "scripts/ai_brain.gd"
FIGHTER_FILE = "scripts/fighter.gd"
MATCH_FILE = "scripts/match.gd"
REPORT = "reports/ai_whiff_punish_12c.txt"
AI_MARKER = "# FRG12C - grounded whiff punishment, short bait and anti-stalling"
FIGHTER_MARKER = "# FRG12C - actual melee contact serial for truthful whiff checks"
MATCH_MARKER = "# FRG12C - record confirmed melee contact for AI recovery reads"

AI_FIELDS = '''# FRG12C - grounded whiff punishment, short bait and anti-stalling
var _seen_recovery_serial := -1
var _last_self_attack_serial := -1
var _last_enemy_attack_serial := -1
var _punish_t := 0.0
var _bait_t := 0.0
var _bait_cd := 2.4
var _idle_standoff_t := 0.0
var _engage_t := 0.0
'''

AI_FUNC = '''func _analyze_openings(f: Fighter, o: Fighter, dt: float) -> void:
	# Timers are real seconds, not frame counts, and never grant an instant hit.
	_punish_t = maxf(_punish_t - dt, 0.0)
	_bait_t = maxf(_bait_t - dt, 0.0)
	_bait_cd = maxf(_bait_cd - dt, 0.0)
	_engage_t = maxf(_engage_t - dt, 0.0)
	var offset: Vector3 = o.position - f.position
	offset.y = 0.0
	var distance: float = offset.length()
	# Read an attack ONCE, after its actual active window. A blocked/parried
	# hit or melee clash is a contact, NOT a whiff. Missing the opponent must
	# leave the attacker in recovery for the CPU to capitalize.
	if o.state == Fighter.S.ATTACK and o.atk_phase == 2 and String(o.atk.get("type", "")) == "melee":
		if o.swing_serial != _seen_recovery_serial:
			_seen_recovery_serial = o.swing_serial
			if o.last_melee_contact_serial != o.swing_serial and distance < 4.4:
				# Hard/Master see openings more consistently; lower CPUs are less
				# likely to notice a miss in time. Recovery still must be reachable.
				var read_chance: float = 0.86 if float(p.think) <= 0.75 else 0.60 if float(p.think) <= 1.0 else 0.26 if float(p.think) < 1.5 else 0.10
				if randf() < read_chance:
					_punish_t = 0.78 if float(p.think) <= 0.75 else 0.58
					_bait_t = 0.0
					_think_cd = minf(_think_cd, 0.035)
	# Never enter prolonged circling when neither fighter has committed.
	var acted: bool = f.swing_serial != _last_self_attack_serial or o.swing_serial != _last_enemy_attack_serial
	_last_self_attack_serial = f.swing_serial
	_last_enemy_attack_serial = o.swing_serial
	if acted or f.state != Fighter.S.IDLE or o.state != Fighter.S.IDLE:
		_idle_standoff_t = 0.0
	else:
		_idle_standoff_t += dt
	var standoff_limit: float = 3.2 if float(p.think) <= 1.0 else 4.7
	if _idle_standoff_t > standoff_limit:
		_engage_t = 1.6
		_idle_standoff_t = 0.0
		_bait_t = 0.0
	# Bait is a short footwork hesitation, never a fake damaging attack.
	# Keep it rare and disabled for Easy/Normal to avoid passive AI duels.
	if float(p.think) <= 1.0 and _bait_cd <= 0.0:
		_bait_cd = _r(3.2, 5.2)
		var reach: float = _preferred_range(f)
		var can_bait: bool = not (f.kit in RANGED) and not (o.kit in RANGED) and f.state == Fighter.S.IDLE and o.state == Fighter.S.IDLE and distance >= reach and distance < reach + 1.25 and _engage_t <= 0.0 and _punish_t <= 0.0
		if can_bait and randf() < 0.36:
			_bait_t = _r(0.28, 0.48)
	if o.state != Fighter.S.IDLE or f.state != Fighter.S.IDLE:
		_bait_t = 0.0

'''

REPORT_TEXT = '''FIGHT ROYALE GODOT — UPDATE 12C — WHIFF PUNISH, BAITING, ANTI-STALLING

Requires Updates 12A and 12B; designed for Duel vs CPU and CPU vs CPU.

CHANGES
- Match melee resolver now records a confirmed contact serial when an attack
  collides with another fighter, whether it hits, is blocked/parried or clashes.
- AI checks the opponent once during melee recovery. If the preceding swing
  never made contact, harder CPUs may approach and punish the opening.
- Brief baiting footwork is available on Hard/Master, rather than fake attacks.
- Anti-stalling encourages re-engagement after prolonged neutral circling.
- Existing damage, move reach, cooldowns, guard and projectile defense unchanged.

HOW TO TEST IN GODOT
1. CPU vs CPU: set A=Master and B=Hard. Test two melee fighters.
2. Observe miss -> forward approach -> quick attack when in range.
3. Observe that blocked or clashed swings do NOT count as whiffs.
4. Watch both fighters approach again after a prolonged neutral standoff.
5. Retest Easy, then duel vs CPU; check Debugger for script errors.

Python validation is NOT a substitute for compiling and playing the Godot game.
'''


def replace_once(s: str, old: str, new: str, where: str) -> str:
    count = s.count(old)
    if count != 1:
        raise ValueError(f"{where}: expected one anchor, found {count}; source differs from expected Update 12B")
    return s.replace(old, new, 1)


def function_span(s: str, name: str) -> tuple[int, int, str]:
    hits = list(re.finditer(rf"(?m)^func {re.escape(name)}\(", s))
    if len(hits) != 1:
        raise ValueError(f"{name}: expected one function, found {len(hits)}")
    start = hits[0].start()
    nxt = re.search(r"(?m)^func [A-Za-z_][A-Za-z_0-9]*\(", s[hits[0].end():])
    end = hits[0].end() + nxt.start() if nxt else len(s)
    return start, end, s[start:end]


def patch_function(s: str, name: str, old: str, new: str) -> str:
    start, end, body = function_span(s, name)
    if old not in body:
        raise ValueError(f"{name}: expected original segment missing; aborting safely")
    body = replace_once(body, old, new, name)
    return s[:start] + body + s[end:]


def patch_ai(s: str) -> str:
    if AI_MARKER in s:
        required = ('func _analyze_openings(', '_analyze_openings(f, o, dt)', '_punish_t > 0.0', '_engage_t > 0.0')
        if all(x in s for x in required):
            return s
        raise ValueError('AI has incomplete Update 12C markers')
    for need in ('# FRG12B - predicted projectile defense', '# FRG12A - deliberate spacing', 'func _position(', 'func _offense(', 'func _try_projectile_clash('):
        if need not in s:
            raise ValueError('Update 12A/12B AI required; missing ' + need)
    s = replace_once(s, 'var _close_pressure_timer := 0.0\n',
                     'var _close_pressure_timer := 0.0\n' + AI_FIELDS, 'AI field registration')
    s = patch_function(s, 'think', '\t_position(f, o, dt)\n',
                       '\t_analyze_openings(f, o, dt)\n\t_position(f, o, dt)\n')
    # Insert a standalone read-only opening analysis function before positioning.
    start, _, _ = function_span(s, '_position')
    s = s[:start] + AI_FUNC + s[start:]
    position_before = '''	# Do not retreat forever along the ring. Both classes must steer inward
'''
    position_after = '''	# FRG12C - short proactive adjustments, always subject to edge steering.
	if _punish_t > 0.0 and not ranged and dist > preferred - 0.12:
		desired = toward * 1.0 + sideways * _orbit_sign * 0.10
		f.in_sprint = dist > 3.0
	elif _engage_t > 0.0 and dist > (2.8 if ranged else preferred - 0.1):
		desired = toward * 1.0 + sideways * _orbit_sign * 0.10
		f.in_sprint = not ranged and dist > 3.0
	elif _bait_t > 0.0 and not ranged:
		desired = -toward * 0.32 + sideways * _orbit_sign * 0.62
	# Do not retreat forever along the ring. Both classes must steer inward
'''
    s = patch_function(s, '_position', position_before, position_after)
    offense_before = '''	# Try an off-cooldown skill only if the position and its action type fit.
'''
    offense_after = '''	# A bait delays offense briefly, but an actual missed attack cancels it.
	if _bait_t > 0.0 and _punish_t <= 0.0:
		return
	# Punish a genuine miss with a prompt, usually light, melee response.
	if _punish_t > 0.0 and not ranged and dist <= reach:
		_think_cd = minf(_think_cd, 0.035)
	# Try an off-cooldown skill only if the position and its action type fit.
'''
    s = patch_function(s, '_offense', offense_before, offense_after)
    # Real whiff punishes prioritize fast normals over random skill casts.
    s = patch_function(s, '_offense', '\tif _skill_cd <= 0.0:\n',
                       '\tif _skill_cd <= 0.0 and _punish_t <= 0.0:\n')
    old_heavy = '''	# Heavy swings are poor choices against a distant or mobile target.
'''
    new_heavy = '''	if _punish_t > 0.0 and not ranged:
		heavy_chance = 0.04  # Fast light punishes are safer than charging.
	# Heavy swings are poor choices against a distant or mobile target.
'''
    s = patch_function(s, '_offense', old_heavy, new_heavy)
    old_attack = '''	if randf() < heavy_chance:
		_queue.append([0.0, Fighter.HOLD_T + _r(0.26, 0.55)])
	else:
'''
    new_attack = '''	var spending_punish: bool = _punish_t > 0.0 and not ranged
	if randf() < heavy_chance:
		_queue.append([0.0, Fighter.HOLD_T + _r(0.26, 0.55)])
	else:
'''
    s = patch_function(s, '_offense', old_attack, new_attack)
    # The last appended input is from this decision; consume the temporary
    # punish state only after a legal action has been queued.
    old_tail = '''		for i in hits:
			_queue.append([0.0 if i == 0 else 0.13, 0.06])
'''
    new_tail = '''		for i in hits:
			_queue.append([0.0 if i == 0 else 0.13, 0.06])
	if spending_punish:
		_punish_t = 0.0
'''
    s = patch_function(s, '_offense', old_tail, new_tail)
    return s


def patch_fighter(s: str) -> str:
    if FIGHTER_MARKER in s:
        if 'var last_melee_contact_serial := -1' in s:
            return s
        raise ValueError('Fighter has incomplete Update 12C markers')
    if '# FRG09' not in s or 'var swing_serial := 0' not in s:
        raise ValueError('Unexpected fighter.gd (requires earlier combat/skills updates)')
    return replace_once(s, 'var swing_serial := 0\n',
                        'var swing_serial := 0\n' + FIGHTER_MARKER + '\nvar last_melee_contact_serial := -1\n',
                        'Fighter swing serial')


def patch_match(s: str) -> str:
    if MATCH_MARKER in s:
        if s.count('last_melee_contact_serial =') >= 3:
            return s
        raise ValueError('Match has incomplete Update 12C markers')
    if 'func _melee(f: Fighter, a: Dictionary)' not in s or 'other_landed[f.id] = true' not in s:
        raise ValueError('Unexpected match.gd melee resolver; install Updates 07/12B first')
    # Patch ONLY _melee; do not interfere with other hit paths (projectiles, area spells).
    a, b, part = function_span(s, '_melee')
    part = replace_once(part, '''			landed[d.id] = true
			_melee_hits[contact_key] = landed
			var other_key''',
                    '''			landed[d.id] = true
			# FRG12C - record confirmed melee contact for AI recovery reads
			f.last_melee_contact_serial = f.swing_serial
			d.last_melee_contact_serial = d.swing_serial
			_melee_hits[contact_key] = landed
			var other_key''', 'clash contact')
    part = replace_once(part, '''		landed[d.id] = true
		_melee_hits[contact_key] = landed
		apply_hit''',
                    '''		landed[d.id] = true
		f.last_melee_contact_serial = f.swing_serial
		_melee_hits[contact_key] = landed
		apply_hit''', 'normal melee contact')
    return s[:a] + part + s[b:]


def sha(b: bytes | None) -> str | None:
    return hashlib.sha256(b).hexdigest() if b is not None else None


def atomic_write(p: Path, content: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_name(p.name + '.frg12c_' + uuid.uuid4().hex[:10] + '.tmp')
    try:
        temp.write_bytes(content)
        temp.replace(p)
    finally:
        temp.unlink(missing_ok=True)


def plan(root: Path) -> dict[str, bytes]:
    if not (root / 'project.godot').is_file():
        raise ValueError('Run the installer from your Godot project folder (containing project.godot).')
    edits: dict[str, bytes] = {}
    for rel, patch in [(AI_FILE, patch_ai), (FIGHTER_FILE, patch_fighter), (MATCH_FILE, patch_match)]:
        p = root / rel
        if not p.is_file():
            raise ValueError('Missing file: ' + rel)
        old = p.read_text(encoding='utf-8-sig')
        new = patch(old)
        if not new.startswith('class_name ') or 'extends ' not in new:
            raise ValueError('Unexpected GDScript structure in ' + rel)
        if old != new:
            edits[rel] = new.encode('utf-8')
    note = REPORT_TEXT.encode('utf-8')
    if not (root / REPORT).is_file() or (root / REPORT).read_bytes() != note:
        edits[REPORT] = note
    return edits


def install(root: Path, edits: dict[str, bytes], dry: bool) -> None:
    if not edits:
        print('Update 12C already installed — no changes needed.')
        return
    print('Update 12C planned changes:')
    for rel in edits:
        print(' - ' + rel)
    if dry:
        print('Dry run successful. No files changed.')
        return
    backup = (root.parent / (root.name + '_backups') /
              ('ai_12c_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:7]))
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {'version': VERSION, 'project': str(root), 'files': {}}
    for rel, content in edits.items():
        orig = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest['files'][rel] = {'old': sha(orig), 'new': sha(content)}
        if orig is not None:
            target = backup / 'originals' / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(orig)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    touched: list[str] = []
    try:
        for rel, content in edits.items():
            atomic_write(root / rel, content)
            touched.append(rel)
    except Exception:
        for rel in reversed(touched):
            orig = backup / 'originals' / rel
            if orig.is_file():
                atomic_write(root / rel, orig.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print('Installation completed. Backup saved to: ' + str(backup))
    print('Next: open Godot and test CPU vs CPU (Hard vs Master recommended).')


def restore(root: Path, folder: str) -> None:
    backup = Path(folder).expanduser().resolve()
    data = json.loads((backup / 'manifest.json').read_text(encoding='utf-8'))
    if data.get('version') != VERSION or Path(data['project']).resolve() != root:
        raise ValueError('Backup belongs to another project or update.')
    for rel, h in data['files'].items():
        now = (root / rel).read_bytes() if (root / rel).is_file() else None
        if sha(now) != h['new']:
            raise ValueError(f'Refusing to overwrite {rel}: it changed since Update 12C.')
        if h['old'] is not None and not (backup / 'originals' / rel).is_file():
            raise ValueError('Backup missing original: ' + rel)
    for rel in data['files']:
        orig = backup / 'originals' / rel
        if orig.is_file():
            atomic_write(root / rel, orig.read_bytes())
        else:
            (root / rel).unlink(missing_ok=True)
    print('Restored files from ' + str(backup))


def godot_check(root: Path) -> None:
    cmd = shutil.which('godot') or shutil.which('godot4') or shutil.which('Godot')
    if cmd is None:
        print('Godot was not found on PATH; open the Godot editor to validate GDScript.')
        return
    r = subprocess.run([cmd, '--headless', '--editor', '--path', str(root), '--quit'],
                       capture_output=True, text=True, timeout=120)
    print((r.stdout + '\n' + r.stderr)[-12000:])
    if r.returncode != 0:
        raise RuntimeError(f'Godot returned exit code {r.returncode}')


def main() -> int:
    parser = argparse.ArgumentParser(description='Fight Royale Godot Update 12C — Whiff punish, baiting, anti-stalling')
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--restore', metavar='BACKUP_FOLDER')
    parser.add_argument('--check-godot', action='store_true')
    args = parser.parse_args()
    root = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(root, args.restore)
        else:
            install(root, plan(root), args.dry_run)
            if args.check_godot and not args.dry_run:
                godot_check(root)
        return 0
    except Exception as ex:
        print('ERROR — ' + str(ex), file=sys.stderr)
        print('No unvalidated source patch was installed. Send this message if you need a compatibility fix.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
