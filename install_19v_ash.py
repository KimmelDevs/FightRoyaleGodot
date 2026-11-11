#!/usr/bin/env python3
"""Fight Royale Godot — Update 19V: Ash / Crimson Hunter.

Run from the Godot project folder:
    python install_19v_ash.py

Options:
    --dry-run          Validate expected sources without touching files
    --restore PATH     Restore a backup created by this installer

Requires Update 19U. Only refines the existing Ash fighter; no roster removals.
The published Fight Royale browser kit (2026-11-11) specifies nerfed bow
basics, a 30-guard heavy, bleed on Arrow Rain/Hunter's Snare, and a pinning
Hunter's Snare. The Godot root implementation is a conservative translation.
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

VERSION = '19V.1'
SENTINEL = 'data/browser_ash_19v.json'
SOURCE = 'https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts'


def load_json(root: Path, rel: str):
    try:
        return json.loads((root / rel).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f'Cannot read {rel}: {exc}') from exc


def json_blob(value) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def swap_once(content: str, old: str, new: str, rel: str) -> str:
    n = content.count(old)
    if n != 1:
        raise RuntimeError(f'{rel}: expected exactly one anchor, found {n}: {old[:90]!r}. Nothing changed.')
    return content.replace(old, new, 1)


def build(root: Path) -> dict[str, bytes]:
    if not (root / 'project.godot').is_file():
        raise RuntimeError('Run from the Godot project folder containing project.godot.')
    if not (root / 'data/browser_raven_19u.json').is_file():
        raise RuntimeError('Install Update 19U first.')
    roster = load_json(root, 'data/roster.json')
    ash = [r for r in roster if r.get('id') == 'ash']
    if len(ash) != 1 or ash[0].get('look', {}).get('kit') != 'bow':
        raise RuntimeError('Expected one existing Ash fighter with kit=bow; roster not modified.')
    if not (root / 'animations/bow.tres').is_file():
        raise RuntimeError('Missing animations/bow.tres; do not install over an incomplete project.')
    attacks = load_json(root, 'data/attacks.json')
    table = attacks.get('ash')
    keys = ('l1', 'l2', 'l3', 'heavy', 'z', 'x', 'c', 'v')
    if not isinstance(table, dict) or any(key not in table or not isinstance(table[key], dict) for key in keys):
        raise RuntimeError('Ash needs eight existing bow attacks in data/attacks.json.')
    expected = {'z': 'Leap Back', 'x': 'Arrow Rain', 'c': "Hunter's Snare", 'v': 'Piercing Volley'}
    for key, name in expected.items():
        if table[key].get('name') != name:
            raise RuntimeError(f'Ash {key.upper()} expected {name!r}, got {table[key].get("name")!r}.')

    # Match the verified browser bow kit's numbers; do not modify legacy Sylva.
    table['l1'].update(dmg=48, guard=14, wind=0.16, recover=0.22, speed=28,
                       count=1, style='arrow', next='l2')
    table['l2'].update(dmg=50, guard=14, wind=0.16, recover=0.22, speed=28,
                       count=1, style='arrow', next='l3')
    table['l3'].update(dmg=37, guard=12, wind=0.22, recover=0.38, speed=28,
                       count=3, spread=0.12, style='arrow', next='')
    table['heavy'].update(dmg=195, guard=30, wind=0.10, recover=0.50,
                          speed=42, size=1.7, count=1, pierce=True,
                          style='arrow', heavy=True)
    table['z'].update(type='blink', mode='back', cd=4.0,
                      desc='Spring away to open distance.')
    table['x'].update(type='strike', cd=8.0, dmg=80, guard=20,
                      wind=0.22, recover=0.40, delay=0.70,
                      radius=1.8, repeat=3, interval=0.25, style='arrows',
                      apply_status='bleed', status_duration=4.0,
                      status_stacks=1, status_chance=1.0,
                      desc='Three marked volleys. Confirmed HP hits cause bleeding.')
    table['c'].update(type='projectile', cd=10.0, dmg=100, guard=30,
                      wind=0.20, recover=0.40, speed=32, size=1.3,
                      stun=1.6, stagger=True, style='arrow',
                      apply_status='bleed', status_duration=4.0,
                      status_stacks=1, status_chance=1.0,
                      ash_root_on_hit=True, ash_root_duration=1.6,
                      desc='A barbed arrow that pins a struck opponent and applies bleed.')
    table['v'].update(type='projectile', cd=9.0, dmg=55, guard=14,
                      wind=0.20, recover=0.40, speed=32,
                      count=5, spread=0.25, pierce=True, style='arrow',
                      desc='Five piercing arrows fired in a spread.')
    changes: dict[str, bytes] = {'data/attacks.json': json_blob(attacks)}

    rel = 'scripts/match.gd'
    src = (root / rel).read_text(encoding='utf-8')
    # Contact-gated root: does not activate on blocks, parries or invulnerability.
    anchor = '\t# FRG19T: only confirmed Gale dive-smash HP hits refund cooldowns.\n'
    injection = (
        '\t# FRG19V — Ash Hunter\'s Snare pins only after a confirmed damaging contact.\n'
        '\t# This is independent from bleed and never triggers on block/parry/clash.\n'
        '\tif attacker is Fighter and attacker.kit == "bow" and String(attacker.look.get("vrm", "")) == "ash" and bool(a.get("ash_root_on_hit", false)) and result in ["hit", "crit"] and not d.is_down():\n'
        '\t\tif d.add_status("root", 1, float(a.get("ash_root_duration", 1.6))):\n'
        '\t\t\tfx.ring(hit_pos, Color("#f04d67"), 1.0, 0.22, 0.70)\n'
        '\t\t\tfx.number(d.chest() + Vector3(0, 0.6, 0), "SNARED", Color("#ff9fae"), 0.75)\n'
    )
    src = swap_once(src, anchor, injection + anchor, rel)
    # Tell players where Ash's AoE arrows fall; visual change only.
    anchor = '\t\t"lightning":\n\t\t\tfx.flash(g + Vector3(0, 0.4, 0), Color("#fff2b0"), radius * 0.6, 0.15, 0.9)\n'
    visual = (
        '\t\t"arrows": # FRG19V — a burst of arrows, not magical blade slashes.\n'
        '\t\t\tfx.sparks(g + Vector3(0, 0.75, 0), Color("#ff697c"), 14, 3.7, Vector3.UP)\n'
        '\t\t\tfx.ring(g, Color("#d54a60"), radius * 0.88, 0.20, 0.65)\n'
    )
    src = swap_once(src, anchor, visual + anchor, rel)
    changes[rel] = src.encode('utf-8')

    changes[SENTINEL] = json_blob({
        'version': VERSION, 'id': 'ash', 'character': 'Ash — Crimson Hunter',
        'kind': 'EXISTING FIGHTER REFINEMENT', 'browser_reference': SOURCE,
        'browser_reference_checked': '2026-11-11',
        'implemented': [
            'Bow basic light 48/50/37 HP damage; third basic shoots 3 arrows',
            'Charged heavy 195 HP damage, guard 30, piercing projectile',
            'Leap Back retains 4-second cooldown',
            'Arrow Rain: 3 area impacts; confirmed HP hits apply 4-second bleed',
            'Hunters Snare: confirmed HP hits apply 4-second bleed and 1.6-second root',
            'Piercing Volley: 5 piercing arrows',
            'Ash-specific bow visuals for Arrow Rain',
        ],
        'unchanged': ['VRM and model assets', 'other fighter kits', 'two existing game modes',
                      'shop disabled and player progression scope'],
        'limitations': [
            'Godot engine compile and in-game animation alignment not verified',
            'Godot status bleed amount follows the existing status rule, not browser absolute 22 DPS',
        ]
    })
    changes['reports/ash_19v.txt'] = (
        'Fight Royale Godot — Update 19V / Ash Crimson Hunter\n'
        'Updated the existing Ash bow kit; no new roster entry.\n'
        'Basic damage: 48, 50, 37 each x 3; heavy damage 195 / guard damage 30.\n'
        'Arrow Rain applies bleeding on confirmed HP damage, up to three area hits.\n'
        'Hunter\'s Snare roots for 1.6 seconds and bleeds only on confirmed HP hits.\n'
        'Piercing Volley fires five piercing arrows; Leap Back stays on a 4s cooldown.\n'
        'Status bleed intensity is inherited from data/status_rules_15a.json.\n'
        'Godot compilation and actual gameplay remain unverified.\n'
    ).encode('utf-8')
    return changes


def sha(data: bytes | None):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def atomic_write(path: Path, payload: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.frg19v-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def install(root: Path, dry_run: bool):
    if (root / SENTINEL).is_file():
        print('19V already installed; no changes.')
        return
    changes = build(root)
    changed = {rel: value for rel, value in changes.items()
               if not (root / rel).is_file() or (root / rel).read_bytes() != value}
    for rel in changed:
        print('Update:', rel)
    if dry_run:
        print('19V dry-run passed; project unchanged.')
        return
    if not changed:
        print('19V: no files changed.')
        return
    backup = root.parent / (root.name + '_backups') / (
        'ash_19v_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {'version': VERSION, 'project': str(root), 'files': {}}
    for rel, value in changed.items():
        before = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest['files'][rel] = {'before': sha(before), 'after': sha(value)}
        if before is not None:
            dest = backup / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(before)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    written: list[str] = []
    try:
        for rel, value in changed.items():
            atomic_write(root / rel, value)
            written.append(rel)
    except BaseException:
        for rel in reversed(written):
            previous = backup / rel
            if previous.is_file():
                atomic_write(root / rel, previous.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print('19V installed. Backup:', backup)


def restore(root: Path, backup: Path):
    manifest = load_json(backup, 'manifest.json')
    if manifest.get('project') != str(root):
        raise RuntimeError('Backup does not belong to this project')
    for rel, hashes in manifest['files'].items():
        current = (root / rel).read_bytes() if (root / rel).is_file() else None
        if sha(current) != hashes['after']:
            raise RuntimeError('Restore refused; modified since install: ' + rel)
    for rel, hashes in manifest['files'].items():
        previous = backup / rel
        if hashes['before'] is None:
            (root / rel).unlink(missing_ok=True)
        else:
            atomic_write(root / rel, previous.read_bytes())
    print('Restored:', backup)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--restore', type=Path)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    try:
        if args.restore:
            restore(root, args.restore.expanduser().resolve())
        else:
            install(root, args.dry_run)
    except Exception as e:
        print('ERROR:', e, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
