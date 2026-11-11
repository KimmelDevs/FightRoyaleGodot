#!/usr/bin/env python3
"""Fight Royale Godot — Update 19O: Rook, Iron Fist (first playable refinement).

Run in your project directory: python install_19o_rook.py
Options: --dry-run or --restore PATH_TO_19O_BACKUP

Requires 19N. Preserves Rook's existing VRM, poses, character ID and
Rush/Shockwave Punch/Meteor Fist/Iron Body abilities. Adds browser light-attack
balance, Beatdown passive, and real Meteor Fist super armor. Does not touch
other knuckle fighters. Does not require third-party Python packages.
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

VERSION = '19O.1'
MARKER = 'FRG19O'


def load_json(root: Path, rel: str):
    try:
        return json.loads((root / rel).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f'{rel}: {exc}') from exc


def dump_json(obj) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def replace_one(src: str, old: str, new: str, path: str) -> str:
    found = src.count(old)
    if found != 1:
        raise RuntimeError(f'{path}: expected one anchor {old[:90]!r}, found {found}. Nothing changed.')
    return src.replace(old, new, 1)


def build(root: Path) -> dict[str, bytes]:
    if not (root / 'project.godot').is_file():
        raise RuntimeError('Run inside the Godot project (project.godot missing).')
    if not (root / 'data/browser_ember_19n.json').is_file():
        raise RuntimeError('Install Update 19N before Update 19O.')
    roster = load_json(root, 'data/roster.json')
    matching = [c for c in roster if c.get('id') == 'rook']
    if len(matching) != 1 or matching[0].get('look', {}).get('vrm') != 'rook' or matching[0].get('look', {}).get('kit') != 'knuckles':
        raise RuntimeError('Expected exactly one original Rook (knuckles/rook VRM).')
    attacks = load_json(root, 'data/attacks.json')
    moves = attacks.get('rook')
    if not isinstance(moves, dict) or not all(k in moves for k in ['l1', 'l2', 'l3', 'l4', 'l5', 'heavy', 'z', 'x', 'c', 'v']):
        raise RuntimeError('Rook kit is incomplete. Aborting without changes.')
    if (moves['c'].get('name'), moves['c'].get('mode'), moves['v'].get('name')) != ('Meteor Fist', 'leap', 'Iron Body'):
        raise RuntimeError('Unexpected Rook kit version. Aborting without changes.')
    if not (root / 'animations/knuckles.tres').is_file():
        raise RuntimeError('Missing knuckles animation library.')
    # Source: current browser kits.ts knuckles() and +25% light attacks in attacks().
    for key, dmg in {'l1':50.0, 'l2':50.0, 'l3':68.75, 'l4':75.0, 'l5':118.75}.items():
        moves[key]['dmg'] = dmg
    moves['c']['desc'] = ('Leap and smash the ground. Super armor through wind-up, flight, landing and recovery: '
                          'immune to stun, stagger, paralysis, slow, root, and knockback; still takes HP damage.')
    moves['c']['rook_super_armor'] = True
    changes = {'data/attacks.json': dump_json(attacks)}

    rel = 'scripts/fighter.gd'
    src = (root / rel).read_text(encoding='utf-8')
    src = replace_one(src, 'var garrick_resolve := 0\n',
        '# FRG19O — Rook: consecutive genuine hits build round-local Beatdown.\n'
        'var rook_combo_hits := 0\n'
        'var rook_best_hits := 0\n'
        'var rook_last_hit_at := -99.0\n'
        'var garrick_resolve := 0\n', rel)
    src = replace_one(src, 'func add_status(effect_id: String, stacks: int = 1, seconds: float = -1.0) -> bool:\n',
        'func _rook_meteor_armor() -> bool:\n'
        '\treturn kit == "knuckles" and String(look.get("vrm", "")) == "rook" and state == S.ATTACK and atk_id == "c" and String(atk.get("name", "")) == "Meteor Fist"\n\n'
        'func add_status(effect_id: String, stacks: int = 1, seconds: float = -1.0) -> bool:\n'
        '\t# FRG19O — super armor resists control application, never damage-over-time.\n'
        '\tif _rook_meteor_armor() and effect_id in ["freeze", "paralyze", "root", "slow", "stun"]:\n'
        '\t\treturn false\n', rel)
    src = replace_one(src, 'func notify_passive_event(event_id: String, other: Node = null) -> void:\n',
        'func notify_passive_event(event_id: String, other: Node = null) -> void:\n'
        '\t# FRG19O — Beatdown only counts confirmed HP-damaging contacts.\n'
        '\tif kit == "knuckles" and String(look.get("vrm", "")) == "rook":\n'
        '\t\tif event_id == "landed_hit":\n'
        '\t\t\tif _clock - rook_last_hit_at > 2.8: rook_combo_hits = 0\n'
        '\t\t\trook_last_hit_at = _clock\n'
        '\t\t\trook_combo_hits += 1\n'
        '\t\t\trook_best_hits = maxi(rook_best_hits, rook_combo_hits)\n'
        '\t\telif event_id in ["blocked_attack", "was_parried", "guard_break_attack", "countered_attack"]:\n'
        '\t\t\trook_combo_hits = 0\n', rel)
    src = replace_one(src, 'func status_summary() -> String:\n\tvar summary: String = status_runtime.short_label() if status_runtime != null else ""\n',
        'func status_summary() -> String:\n\tvar summary: String = status_runtime.short_label() if status_runtime != null else ""\n'
        '\t# FRG19O — permanent best-of-round bonus, temporary active hit chain.\n'
        '\tif kit == "knuckles" and String(look.get("vrm", "")) == "rook":\n'
        '\t\tvar label: String = "BEATDOWN %d | BEST %d (+%d%%)" % [rook_combo_hits, rook_best_hits, rook_best_hits]\n'
        '\t\treturn label if summary.is_empty() else label + ", " + summary\n', rel)
    src = replace_one(src, '\t_clock += dt\n\tif status_runtime != null:\n',
        '\t_clock += dt\n'
        '\tif kit == "knuckles" and String(look.get("vrm", "")) == "rook" and rook_combo_hits > 0 and _clock - rook_last_hit_at > 2.8:\n'
        '\t\trook_combo_hits = 0\n'
        '\tif status_runtime != null:\n', rel)
    for kind in ('movement','attack','skill','defense'):
        src = replace_one(src, f'if status_runtime.control_blocks("{kind}"):',
                          f'if not _rook_meteor_armor() and status_runtime.control_blocks("{kind}"):', rel)
    src = replace_one(src, '\tatk = attacks[aid].duplicate(true)\n',
        '\tatk = attacks[aid].duplicate(true)\n'
        '\t# FRG19O — 1% extra power per best consecutive real hit this round.\n'
        '\tif kit == "knuckles" and String(look.get("vrm", "")) == "rook":\n'
        '\t\tatk_power *= 1.0 + 0.01 * float(rook_best_hits)\n', rel)
    src = replace_one(src, 'func _apply_knock(attacker, speed: float) -> void:\n',
        'func _apply_knock(attacker, speed: float) -> void:\n'
        '\t# FRG19O — Meteor Fist continues even when struck; HP still decreases.\n'
        '\tif _rook_meteor_armor(): return\n', rel)
    src = replace_one(src, '\tif hp <= 0.0: _ko(); return "ko"\n\n\t# Blood Festival grants stun immunity, NOT damage or knockback immunity.\n',
        '\tif hp <= 0.0: _ko(); return "ko"\n'
        '\t# FRG19O — damage taken, but no stun or attack interruption while casting C.\n'
        '\tif _rook_meteor_armor(): return "crit" if last_crit else "hit"\n\n'
        '\t# Blood Festival grants stun immunity, NOT damage or knockback immunity.\n', rel)
    src = replace_one(src, 'func stagger(d: float) -> void:\n',
        'func stagger(d: float) -> void:\n\tif _rook_meteor_armor(): return\n', rel)
    src = replace_one(src, 'func clash_recoil() -> void:\n',
        'func clash_recoil() -> void:\n\tif _rook_meteor_armor(): return\n', rel)
    changes[rel] = src.encode('utf-8')

    rel = 'scripts/match.gd'
    src = (root / rel).read_text(encoding='utf-8')
    src = replace_one(src,
        '\telif result == "guard_break":\n\t\td.notify_passive_event("guard_broken", attacker if attacker is Fighter else null)\n',
        '\telif result == "guard_break":\n'
        '\t\td.notify_passive_event("guard_broken", attacker if attacker is Fighter else null)\n'
        '\t\tif attacker is Fighter and attacker.kit == "knuckles" and String(attacker.look.get("vrm", "")) == "rook":\n'
        '\t\t\tattacker.notify_passive_event("guard_break_attack", d) # FRG19O\n', rel)
    src = replace_one(src,
        '\t\t"counter":\n\n\t\t\tif d.kit == "sickle" and d.veyr_feint_counter:',
        '\t\t"counter":\n'
        '\t\t\t# FRG19O — a counter breaks Rook\'s active hit chain.\n'
        '\t\t\tif attacker is Fighter and attacker.kit == "knuckles" and String(attacker.look.get("vrm", "")) == "rook":\n'
        '\t\t\t\tattacker.notify_passive_event("countered_attack", d)\n\n\t\t\tif d.kit == "sickle" and d.veyr_feint_counter:', rel)
    changes[rel] = src.encode('utf-8')

    changes['data/browser_rook_19o.json'] = dump_json({
        'version': VERSION, 'character': 'rook', 'state': 'FIRST PLAYABLE REFINEMENT',
        'source': 'https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts',
        'completed': [
            'Five light attacks gain browser 25% damage bonus (50/50/68.75/75/118.75)',
            'Beatdown: uninterrupted real HP hits build a best-of-round count; +1% attack power per best hit',
            'Blocked, parried, guard-broken and countered swings break the active chain',
            'Current chain resets after 2.8 seconds without a real hit; best remains for the round',
            'Meteor Fist C has super armor during wind-up, leap, landing and recovery',
            'Super armor ignores control and knockback, but not HP damage or KO',
            'Preserves Rook skill identities and animation library and leaves legacy knuckle fighters unchanged',
        ],
        'pending': ['custom Meteor Fist landing crater choreography', 'Godot engine playtest'],
        'notes': 'Rook is an existing fighter. No shop and no new modes.'
    })
    changes['reports/rook_19o.txt'] = (
        '19O — Rook / Iron Fist\n'
        'Five light punches: 50 / 50 / 68.75 / 75 / 118.75 base damage.\n'
        'BEATDOWN: each real hit boosts best hit chain; +1% damage per best hit.\n'
        'Chain resets after 2.8s without contact and on guarded/parried/countered attacks.\n'
        'Meteor Fist: all cast phases have super armor. Damage and KO remain possible.\n'
        'Existing Rook VRM, Rush, Shockwave Punch, Meteor Fist and Iron Body remain.\n'
        'Godot engine gameplay validation pending.\n'
    ).encode('utf-8')
    return changes


def sha(blob: bytes | None):
    return hashlib.sha256(blob).hexdigest() if blob is not None else None


def atomic_write(path: Path, blob: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix='.frg19o-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(blob)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def install(root: Path, dry_run: bool):
    if (root / 'data/browser_rook_19o.json').is_file():
        print('Update 19O is already installed. No changes.')
        return
    changes = build(root)  # validate all anchors before writing a single file
    changed = {rel: blob for rel, blob in changes.items()
               if not (root / rel).is_file() or (root / rel).read_bytes() != blob}
    for rel in changed:
        print('Update:', rel)
    if dry_run:
        print('19O dry run passed. No files changed.')
        return
    backup = root.parent / (root.name + '_backups') / ('rook_19o_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {'version': VERSION, 'project': str(root), 'files': {}}
    for rel, blob in changed.items():
        previous = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest['files'][rel] = {'before': sha(previous), 'after': sha(blob)}
        if previous is not None:
            saved = backup / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(previous)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    completed = []
    try:
        for rel, blob in changed.items():
            atomic_write(root / rel, blob)
            completed.append(rel)
    except BaseException:
        for rel in reversed(completed):
            previous = backup / rel
            if previous.is_file(): atomic_write(root / rel, previous.read_bytes())
            else: (root / rel).unlink(missing_ok=True)
        raise
    print('19O installed. Backup:', backup)


def restore(root: Path, backup: Path):
    manifest = load_json(backup, 'manifest.json')
    if manifest.get('project') != str(root):
        raise RuntimeError('Backup was created for another project.')
    for rel, metadata in manifest['files'].items():
        current = (root / rel).read_bytes() if (root / rel).is_file() else None
        if sha(current) != metadata['after']:
            raise RuntimeError('File changed since installation; restore stopped: ' + rel)
    for rel, metadata in manifest['files'].items():
        saved = backup / rel
        if metadata['before'] is None: (root / rel).unlink(missing_ok=True)
        else: atomic_write(root / rel, saved.read_bytes())
    print('Restored:', backup)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--restore', type=Path)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    try:
        if args.restore: restore(root, args.restore.expanduser().resolve())
        else: install(root, args.dry_run)
    except Exception as exc:
        print('ERROR:', exc, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
