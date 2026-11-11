#!/usr/bin/env python3
"""Fight Royale Godot — 19U: Raven Electric Witch, real Static Field.

Run in the Godot project folder: python install_19u_raven.py
Optional: --dry-run | --restore PATH_TO_BACKUP
Requires 19T. Preserves Raven's VRM, her existing fighter ID and all other fighters.

Browser source reference (as of Nov 2026):
https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts
Raven uses Blink, Chain Lightning, Thunderstorm and a five-second Static Field.
The field's short slow/paralysis tick durations are a conservative Godot adaptation.
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

VERSION = '19U.1'
SENTINEL = 'data/browser_raven_19u.json'


def load_json(root: Path, rel: str):
    try:
        return json.loads((root / rel).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f'Cannot read {rel}: {exc}') from exc


def json_blob(value) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def replace_once(content: str, old: str, new: str, filename: str) -> str:
    occurrences = content.count(old)
    if occurrences != 1:
        raise RuntimeError(f'{filename}: expected one anchor; found {occurrences}: {old[:90]!r}. No changes written.')
    return content.replace(old, new, 1)


def build(root: Path) -> dict[str, bytes]:
    if not (root / 'project.godot').is_file():
        raise RuntimeError('Run inside the Godot project directory (project.godot missing).')
    if not (root / 'data/browser_gale_19t.json').is_file():
        raise RuntimeError('Install Update 19T first.')
    if (root / SENTINEL).exists():
        raise RuntimeError('19U sentinel already exists; refusing to patch twice.')
    roster = load_json(root, 'data/roster.json')
    raven = [entry for entry in roster if entry.get('id') == 'raven']
    if len(raven) != 1 or raven[0].get('look', {}).get('kit') != 'mage' or raven[0].get('look', {}).get('element') != 'electric':
        raise RuntimeError('Expected exactly one existing Raven with kit=mage, element=electric.')
    attacks = load_json(root, 'data/attacks.json')
    a = attacks.get('raven')
    if not isinstance(a, dict) or not all(k in a for k in ('l1', 'l2', 'l3', 'heavy', 'z', 'x', 'c', 'v')):
        raise RuntimeError('Raven attack table is incomplete.')
    required_names = {'z': 'Blink', 'x': 'Chain Lightning', 'c': 'Thunderstorm', 'v': 'Static Field'}
    for key, name in required_names.items():
        if a[key].get('name') != name:
            raise RuntimeError(f'Unexpected Raven {key.upper()} skill: {a[key].get("name")!r}.')
    if not (root / 'animations/mage.tres').is_file():
        raise RuntimeError('Missing existing mage animation library.')
    a['z'].update(type='blink', mode='back', cd=4.0, desc='Flash backward out of danger.')
    # Only actual damage contacts will apply these via Match.apply_hit().
    for key in ('x', 'c'):
        a[key]['apply_status'] = 'paralyze'
        a[key]['status_duration'] = 2.5
        a[key]['status_chance'] = 1.0
        a[key]['status_stacks'] = 1
    a['x'].update(cd=6.0, dmg=90.0, speed=42.0, size=1.3,
                  desc='A near-instant electric projectile. Confirmed damage paralyzes its victim.')
    a['c'].update(cd=12.0, dmg=110.0, delay=0.45, radius=1.25,
                  repeat=3, interval=0.35, style='lightning',
                  desc='Three delayed lightning strikes; real damage contacts apply paralysis.')
    a['v'].update(name='Static Field', type='buff', mode='raven_static_field',
                  duration=5.0, radius=3.0, cd=13.0, dmg=0.0, guard=0.0,
                  wind=0.22, recover=0.45, pose_w='mh_w', pose_s='m3_s',
                  desc='Place a five-second electric circle. Enemies inside are slowed and periodically paralyzed; allies are unaffected.')
    out: dict[str, bytes] = {'data/attacks.json': json_blob(attacks)}

    file = 'scripts/match.gd'
    source = (root / file).read_text(encoding='utf-8')
    source = replace_once(source,
        'var _marina_pools: Array[Dictionary] = []\n',
        'var _marina_pools: Array[Dictionary] = []\n'
        '# FRG19U — stationary Raven shock zones, destroyed on rematch.\n'
        'var _raven_fields: Array[Dictionary] = []\n', file)
    source = replace_once(source,
        '\t_marina_pools.clear()\n\tfighters.clear();',
        '\t_marina_pools.clear()\n'
        '\tfor field in _raven_fields:\n'
        '\t\tif is_instance_valid(field["node"]): field["node"].queue_free()\n'
        '\t_raven_fields.clear()\n'
        '\tfighters.clear();', file)
    source = replace_once(source,
        '\t_marina_step_pools(dt) # FRG19P: heal only while simulation advances\n',
        '\t_marina_step_pools(dt) # FRG19P: heal only while simulation advances\n'
        '\t_raven_step_fields(dt) # FRG19U: status ticks halt during pause/hitstop\n', file)
    source = replace_once(source,
        '\tmatch a.mode:\n\t\t"marina_bubble":',
        '\tmatch a.mode:\n'
        '\t\t"raven_static_field": # FRG19U: five-second area with actual periodic CC.\n'
        '\t\t\tif f.kit == "mage" and String(f.look.get("element", "")) == "electric":\n'
        '\t\t\t\t_raven_spawn_field(f, a)\n'
        '\t\t"marina_bubble":', file)
    anchor = '# FRG19P — Healing Water is a real area, not an instant self-heal.\n'
    funcs = '''# FRG19U — Raven's Static Field: spatial, team-aware and time-limited.
func _raven_spawn_field(caster: Fighter, attack: Dictionary) -> void:
	if round_over or not is_instance_valid(caster) or caster.is_down(): return
	var radius: float = float(attack.get("radius", 3.0))
	var marker := MeshInstance3D.new()
	var mesh := CylinderMesh.new()
	mesh.top_radius = 1.0
	mesh.bottom_radius = 1.0
	mesh.height = 0.024
	marker.mesh = mesh
	marker.material_override = Fx.unlit(Color("#83f5bc"), 0.37, true)
	marker.scale = Vector3(radius, 1.0, radius)
	add_child(marker)
	var center: Vector3 = Vector3(caster.position.x, 0.0, caster.position.z)
	marker.global_position = center + Vector3(0.0, 0.045, 0.0)
	_raven_fields.append({"node": marker, "owner": caster, "team": caster.team,
		"center": center, "radius": radius, "seconds": float(attack.get("duration", 5.0)),
		"slow_tick": 0.0, "shock_tick": 0.65, "ring_tick": 0.0})
	fx.ring(center, Color("#65f1b1"), radius, 0.35, 0.85)
	fx.number(caster.chest() + Vector3(0.0, 0.75, 0.0), "STATIC FIELD", Color("#b3ffd8"), 0.85)

func _raven_step_fields(dt: float) -> void:
	if dt <= 0.0 or round_over: return
	for field in _raven_fields.duplicate():
		var owner: Fighter = field["owner"]
		field["seconds"] = float(field["seconds"]) - dt
		if not is_instance_valid(owner) or owner.is_down(): field["seconds"] = 0.0
		if float(field["seconds"]) <= 0.0:
			if is_instance_valid(field["node"]): field["node"].queue_free()
			_raven_fields.erase(field)
			continue
		field["slow_tick"] = float(field["slow_tick"]) + dt
		field["shock_tick"] = float(field["shock_tick"]) + dt
		field["ring_tick"] = float(field["ring_tick"]) + dt
		if float(field["ring_tick"]) >= 0.70:
			field["ring_tick"] = 0.0
			fx.ring(field["center"], Color("#74ffa9"), float(field["radius"]), 0.20, 0.50)
		var slow_due: bool = float(field["slow_tick"]) >= 0.38
		var shock_due: bool = float(field["shock_tick"]) >= 1.55
		if not slow_due and not shock_due: continue
		if slow_due: field["slow_tick"] = 0.0
		if shock_due: field["shock_tick"] = 0.0
		for victim in fighters:
			if victim.team == int(field["team"]) or victim.is_down(): continue
			var separation: Vector3 = victim.position - field["center"]
			separation.y = 0.0
			if separation.length() > float(field["radius"]) + victim.radius * 0.25: continue
			if slow_due:
				# Refreshes a short movement debuff; only targets inside the area.
				victim.add_status("slow", 1, 0.55)
			if shock_due and victim.add_status("paralyze", 1, 0.45):
				fx.flash(victim.chest(), Color("#a6ffda"), 0.45, 0.12, 0.82)
				fx.number(victim.chest() + Vector3(0.0, 0.6, 0.0), "SHOCK", Color("#b3ffd8"), 0.65)

'''
    source = replace_once(source, anchor, funcs + anchor, file)
    out[file] = source.encode('utf-8')
    out[SENTINEL] = json_blob({
        'version': VERSION, 'character': 'raven', 'kind': 'EXISTING FIGHTER REFINEMENT',
        'source': 'https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts',
        'abilities': {
            'z': 'Blink backwards, 4s cooldown',
            'x': 'Chain Lightning with confirmed-hit paralysis, 6s cooldown',
            'c': 'Thunderstorm three strikes, 12s cooldown; each confirmed hit can paralyze',
            'v': 'Static Field, 5s duration, radius 3m, 13s cooldown; slows and periodically paralyzes enemies inside'
        },
        'guarantees': ['No changes to VRM files', 'No shop or currency changes', 'No changes to other fighters'],
        'notes': ['Field ends on caster KO, expiry or rematch', 'Periodic field paralysis uses short shocks with existing control-immunity rules', 'Godot gameplay not tested in this environment'],
    })
    out['reports/raven_19u.txt'] = (
        'Update 19U — Raven: Electric Witch\n'
        'Existing Raven and raven.vrm preserved.\n'
        'Blink Z unchanged; Chain Lightning X and Thunderstorm C cause paralysis only on successful HP hits.\n'
        'Static Field V is a real five-second radius-3m zone; slows enemies while inside and periodically shocks them.\n'
        'Zone ignores allies, clears on KO/rematch and does not tick while paused.\n'
        'NOTE: Godot editor compilation and visual gameplay are not verified here.\n'
    ).encode('utf-8')
    return out


def sha(blob: bytes | None) -> str | None:
    return hashlib.sha256(blob).hexdigest() if blob is not None else None


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.frg19u-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def install(root: Path, dry_run: bool) -> None:
    if (root / SENTINEL).is_file():
        print('19U already installed; no changes')
        return
    changes = build(root)  # Full preflight before any writes.
    changed = {rel: data for rel, data in changes.items()
               if not (root / rel).is_file() or (root / rel).read_bytes() != data}
    for rel in changed: print('Update:', rel)
    if dry_run:
        print('19U dry run passed; project untouched')
        return
    backup = root.parent / (root.name + '_backups') / (
        'raven_19u_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {'version': VERSION, 'project': str(root), 'files': {}}
    for rel, data in changed.items():
        previous = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest['files'][rel] = {'before': sha(previous), 'after': sha(data)}
        if previous is not None:
            backup_file = backup / rel
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            backup_file.write_bytes(previous)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    written = []
    try:
        for rel, data in changed.items():
            atomic_write(root / rel, data)
            written.append(rel)
    except BaseException:
        for rel in reversed(written):
            saved = backup / rel
            if saved.is_file(): atomic_write(root / rel, saved.read_bytes())
            else: (root / rel).unlink(missing_ok=True)
        raise
    print('19U installed. Backup:', backup)


def restore(root: Path, backup: Path) -> None:
    manifest = load_json(backup, 'manifest.json')
    if manifest.get('project') != str(root):
        raise RuntimeError('Backup belongs to a different project')
    for rel, hashes in manifest['files'].items():
        current = (root / rel).read_bytes() if (root / rel).is_file() else None
        if sha(current) != hashes['after']:
            raise RuntimeError('Restore refused; file changed since installation: ' + rel)
    for rel, hashes in manifest['files'].items():
        saved = backup / rel
        if hashes['before'] is None: (root / rel).unlink(missing_ok=True)
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
