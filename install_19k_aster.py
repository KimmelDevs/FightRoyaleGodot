#!/usr/bin/env python3
"""Fight Royale Godot 19K: Aster / Azure Knight browser-kit refinement.

From your Godot project folder: python install_19k_aster.py
Optional: --dry-run or --restore PATH
Requires the 19J chain. Safe to rerun; creates backups *outside* the repo.

This first refinement ports Aster's low sweep, 50-second Weaken on his X/C,
Judgment's 10-second empowered blade stance, light-sword attack speed buff,
shield-hide/restore visual, missing-HP scaling and HP pressure while blocking.
It does NOT replace shared knight moves or Vesper's skills.
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

VERSION = "19K.1"
MARKER = "FRG19K"

def read_json(root: Path, rel: str):
    try: return json.loads((root/rel).read_text('utf-8-sig'))
    except (OSError, ValueError) as e: raise RuntimeError(f"Cannot read {rel}: {e}") from e

def encoded(obj): return (json.dumps(obj, indent=2, ensure_ascii=False) + '\n').encode('utf-8')

def once(src: str, old: str, new: str, path: str) -> str:
    count=src.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one anchor {old[:92]!r}; found {count}. No files changed.")
    return src.replace(old, new, 1)

def build(root: Path) -> dict[str, bytes]:
    if not (root/'project.godot').is_file():
        raise RuntimeError('Run inside the Godot folder containing project.godot')
    if not (root/'data/browser_veyr_19j.json').is_file():
        raise RuntimeError('Install Update 19J first, then run 19K')
    attacks = read_json(root,'data/attacks.json')
    roster = read_json(root,'data/roster.json')
    rules = read_json(root,'data/status_rules_15a.json')
    if not any(x.get('id')=='aster' for x in roster):
        raise RuntimeError('Aster is missing from the roster')
    if not all(k in attacks.get('aster', {}) for k in ['l1','l2','l3','heavy','z','x','c','v']):
        raise RuntimeError('Aster skill table is incomplete')
    if not (root/'animations/knight.tres').is_file():
        raise RuntimeError('Knight animation library is missing')
    if 'weaken' not in rules.get('effects', {}):
        raise RuntimeError('The Weaken status from Update 15A is missing')

    # Explicitly modify only Aster. Never touch generic knight attacks (Vesper).
    x = attacks['aster']['x']
    x.update(name='Rising Slash — Low Sweep',
             desc='Low forward sword sweep; applies one 50-second Weaken stack on a landed hit.',
             type='melee',wind=.18,active=.12,recover=.40,
             reach=2.25,lunge=4.4,self_jump=0.0,
             pose_w='l2_w',pose_s='l2_s',
             apply_status='weaken',status_duration=50.0,
             status_stacks=1,status_chance=1.0,
             style='aster_sweep')
    c = attacks['aster']['c']
    c.update(apply_status='weaken',status_duration=50.0,
             status_stacks=1,status_chance=1.0,
             desc='A penetrating blade wave that applies a 50-second Weaken stack on a landed hit.')
    v = attacks['aster']['v']
    v.update(name='Judgment',
             desc='10s sword-and-shield transformation: +50% sword swing speed and greater sword damage, scaling with missing HP. Sword hits inflict Weaken. Blocking slowly drains HP.',
             type='buff',mode='aster_judgment',duration=10.0,cd=16.0,
             wind=.62,active=.06,recover=.30,
             dmg=0.0,guard=0.0,heavy=False,
             pose_w='charge',pose_s='heavy_s',
             apply_status='',style='judgment')
    # Latest local balance request caps Weaken at 3; the browser source still
    # records an older x5 version. Keep the Godot cap3 and grant 50s per hit.
    effects = rules['effects']['weaken']
    if int(effects.get('max_stacks', 3)) != 3:
        raise RuntimeError('Existing Weaken cap differs from latest cap 3; refusing global balance edit')

    result = {'data/attacks.json': encoded(attacks)}

    path='scripts/fighter.gd'; src=(root/path).read_text('utf-8')
    src=once(src,
             'var roxy_aegis_charges := 0\n',
             '# FRG19K — Aster-only 10-second Judgment state.\n'
             'var aster_judgment_t := 0.0\n'
             'var roxy_aegis_charges := 0\n',path)
    src=once(src,
             '\t# FRG19I reflection decays in match-time;',
             '\t# FRG19K: Judgment belongs to the light knight only. Its timer\n'
             '\t# advances during the actual match simulation, not during pause.\n'
             '\tif kit == "knight" and String(look.get("element", "")) == "light":\n'
             '\t\tvar was_judging: bool = aster_judgment_t > 0.0\n'
             '\t\taster_judgment_t = maxf(0.0, aster_judgment_t - dt)\n'
             '\t\tif aster_judgment_t > 0.0 and state == S.BLOCK:\n'
             '\t\t\thp = maxf(1.0, hp - max_hp * 0.006 * dt)\n'
             '\t\tif was_judging and aster_judgment_t <= 0.0 and model != null and model.shield_node != null:\n'
             '\t\t\tmodel.shield_node.visible = true\n'
             '\t# FRG19I reflection decays in match-time;',path)
    src=once(src,
             '\tif kit == "tonfa":\n\t\tvar tag: String = "READ x%d" % renji_reads',
             '\t# FRG19K: show the remaining Judgment time in both match HUDs.\n'
             '\tif kit == "knight" and String(look.get("element", "")) == "light" and aster_judgment_t > 0.0:\n'
             '\t\tvar aster_tag: String = "JUDGMENT %.1fs" % aster_judgment_t\n'
             '\t\treturn aster_tag if summary.is_empty() else aster_tag + ", " + summary\n'
             '\tif kit == "tonfa":\n\t\tvar tag: String = "READ x%d" % renji_reads',path)
    src=once(src,
             '\treturn (1.0 / maxf(1.0 - 0.02 * float(guard_fatigue), 0.5)) * status_runtime.attack_time_multiplier() / veyr_frenzy_speed / (factor * metal_factor * dragon_mode_speed * dragon_rhythm_speed) * (1.0 + 0.05 * float(nythera_orbit_marks)) / (1.0 + 0.10 * float(nythera_dread_stacks))',
             '\tvar aster_sword_speed: float = 1.5 if kit == "knight" and String(look.get("element", "")) == "light" and aster_judgment_t > 0.0 and (atk_id.begins_with("l") or atk_id in ["heavy", "x"]) else 1.0\n'
             '\treturn (1.0 / maxf(1.0 - 0.02 * float(guard_fatigue), 0.5)) * status_runtime.attack_time_multiplier() / veyr_frenzy_speed / (factor * metal_factor * dragon_mode_speed * dragon_rhythm_speed * aster_sword_speed) * (1.0 + 0.05 * float(nythera_orbit_marks)) / (1.0 + 0.10 * float(nythera_dread_stacks))',path)
    src=once(src,
             '\tatk = attacks[aid].duplicate(true)\n',
             '\tatk = attacks[aid].duplicate(true)\n'
             '\t# FRG19K: the sword, not the shield bash, gains Judgment power.\n'
             '\tif kit == "knight" and String(look.get("element", "")) == "light" and aster_judgment_t > 0.0:\n'
             '\t\tif aid.begins_with("l") or aid in ["heavy", "x", "c"]:\n'
             '\t\t\tvar missing: float = clampf(1.0 - hp / maxf(max_hp, 1.0), 0.0, 1.0)\n'
             '\t\t\tatk_power *= 1.20 + missing * 0.30\n'
             '\t\t\tif aid.begins_with("l") or aid == "heavy":\n'
             '\t\t\t\tatk["apply_status"] = "weaken"\n'
             '\t\t\t\tatk["status_duration"] = 50.0\n'
             '\t\t\t\tatk["status_stacks"] = 1\n',path)
    result[path]=src.encode('utf-8')

    path='scripts/match.gd'; src=(root/path).read_text('utf-8')
    src=once(src,
             '\tmatch a.mode:\n',
             '\tmatch a.mode:\n'
             '\t\t"aster_judgment": # FRG19K — temporary damage and sword speed transformation\n'
             '\t\t\tif f.kit == "knight" and String(f.look.get("element", "")) == "light":\n'
             '\t\t\t\tf.aster_judgment_t = float(a.get("duration", 10.0))\n'
             '\t\t\t\tif f.model != null and f.model.shield_node != null:\n'
             '\t\t\t\t\tf.model.shield_node.visible = false\n'
             '\t\t\t\tf.model.flash(Color("#fff6bd"), 0.5)\n'
             '\t\t\t\tfx.ring(f.position, Color("#ffe59c"), 2.4, 0.5, 0.8)\n'
             '\t\t\t\tfx.number(f.chest() + Vector3(0, 0.6, 0), "JUDGMENT", Color("#fff0b4"), 1.2)\n',path)
    result[path]=src.encode('utf-8')

    # A report makes first-port limitations explicit; no hidden claims of parity.
    result['data/browser_aster_19k.json']=encoded({
        'version':VERSION,'character':'aster','status':'PLAYABLE REFINEMENT — COMBAT ANIMATION PARITY PENDING',
        'source':'https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts',
        'scope':['light knight only; existing fighter id','X forward low sweep, no jump','X/C hit applies Weaken for 50 seconds, maximum three stacks',
                 'V Judgment, 10 seconds, 16-second cooldown','sword-only 1.5x speed and conditional Weaken','shield hidden during stance and restored afterward',
                 'missing HP power scaling; small health drain while blocking'],
        'pending':['unique Godot animation for low sweep, raise and sword fusion',
                   'precise browser balance and VFX parity','in-engine testing']})
    result['reports/aster_19k.txt']=(
        '19K — Aster, Azure Knight\n'
        'X now performs a grounded low forward sweep rather than launching into the air.\n'
        'X and C apply 50-second Weaken, capped at three stacks per earlier user balance choice.\n'
        'V Judgment is a 10-second transformation, with faster sword attacks and missing-HP damage scaling.\n'
        'Shield geometry is hidden during the stance and restored automatically.\n'
        'Aster shares no modified moves with Vesper. Full choreography is a later refinement.\n'
        'Godot engine runtime validation has not been performed.\n').encode('utf-8')
    return result

def sha(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None

def atomic(path: Path, blob: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd,tmp = tempfile.mkstemp(prefix='.frg19k-', dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f: f.write(blob);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def install(root: Path, dry_run: bool):
    if (root/'data/browser_aster_19k.json').is_file():
        print('19K already installed; no changes');return
    planned = build(root)
    changed = {name: blob for name,blob in planned.items()
               if not (root/name).is_file() or (root/name).read_bytes()!=blob}
    for name in changed: print('Update:',name)
    if dry_run: print('Dry run passed; no files modified');return
    backup = root.parent/(root.name+'_backups')/('aster_19k_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    manifest={'version':VERSION,'project':str(root),'files':{}}
    for rel, new in changed.items():
        old=(root/rel).read_bytes() if (root/rel).is_file() else None
        manifest['files'][rel]={'before':sha(old),'after':sha(new)}
        if old is not None:
            dest=backup/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(old)
    (backup/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    done=[]
    try:
        for rel,blob in changed.items():atomic(root/rel,blob);done.append(rel)
    except BaseException:
        for rel in reversed(done):
            orig=backup/rel
            if orig.is_file():atomic(root/rel,orig.read_bytes())
            else:(root/rel).unlink(missing_ok=True)
        raise
    print('Installed 19K. Backup:',backup)

def restore(root: Path, backup: Path):
    manifest=read_json(backup,'manifest.json')
    if manifest.get('project') != str(root):raise RuntimeError('Backup belongs to another project')
    for rel,meta in manifest.get('files',{}).items():
        cur=(root/rel).read_bytes() if (root/rel).is_file() else None
        if sha(cur)!=meta['after']:raise RuntimeError('File has changed; restore aborted: '+rel)
    for rel,meta in manifest['files'].items():
        original=backup/rel
        if meta['before'] is None:(root/rel).unlink(missing_ok=True)
        else:atomic(root/rel,original.read_bytes())
    print('Restored:',backup)

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--dry-run',action='store_true');a.add_argument('--restore',type=Path)
    args=a.parse_args();root=Path.cwd().resolve()
    try:
        if args.restore:restore(root,args.restore.expanduser().resolve())
        else:install(root,args.dry_run)
    except Exception as exc:
        print('ERROR:',exc,file=sys.stderr);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
