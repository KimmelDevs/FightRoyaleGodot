#!/usr/bin/env python3
"""Fight Royale Godot 19B: first playable browser fighter port (Zarek).

Run from the project folder:
    python install_19b_zarek.py

This ports Zarek's roster data, five-light combo, charge and Z/X/C/V skill
numbers/names from the published browser source. A procedural double-ended
glaive, temporary pose aliases and multi-hit contacts provide a playable first
pass. Cinematic choreography, aerial-specific combos and skill-specific
cancels remain for follow-up installers; they are NOT claimed to be exact.

Source checked 2026-11-10:
https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/roster.ts
https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts
https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/fighter.ts
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

VERSION = '19B.1'
CHECKED = '2026-11-10'
ID = 'zarek'
SOURCE = 'https://github.com/KimmelDevs/Fight-Royale/blob/main/web/src/game/kits.ts'

# Raw values are from the published browser kit. The browser applies a later
# hit-reach * .82 and lunge * .80 balance pass to grounded glaive attacks.
MOVES = {
 'l1': dict(name='Cyclone Fang 1', wind=.11, active=.09, recover=.19, dmg=58, guard=16, reach=2.05,lunge=2.7,knock=1,stun=.22,next='l2',pose_w='gl1_w',pose_s='gl1_s'),
 'l2': dict(name='Cyclone Fang 2', wind=.12, active=.09, recover=.18, dmg=64, guard=17, reach=2.10,lunge=2.8,knock=1,stun=.23,next='l3',pose_w='gl2_w',pose_s='gl2_s'),
 'l3': dict(name='Cyclone Fang 3', wind=.10, active=.10, recover=.20, dmg=69, guard=18, reach=2.08,lunge=2.7,knock=1.2,stun=.24,next='l4',pose_w='gl3_w',pose_s='gl3_s'),
 'l4': dict(name='Cyclone Fang 4', wind=.17, active=.11, recover=.23, dmg=74, guard=20, reach=2.12,lunge=2.4,knock=1.6,stun=.27,next='l5',pose_w='gl4_w',pose_s='gl4_s'),
 'l5': dict(name='Cyclone Fang Finisher', wind=.17,active=.56,recover=.33,dmg=104,guard=29,reach=2.18,lunge=1.7,knock=3.5,stun=.38,style='glaive_cyclone',multi_hit=4,pose_w='gl5_w',pose_s='gl5_s'),
 'heavy': dict(name='Split Current', wind=.35,active=.14,recover=.55,dmg=165,guard=48,reach=2.34,lunge=2.5,knock=5,stun=.52,heavy=True,pose_w='glh_w',pose_s='glh_s'),
 'z':dict(name='Serpent Wheel', desc='Five revolving blade passes while stepping forward. Blockable and clashable, not parryable.',cd=8,wind=.14,active=1.08,recover=.40,dmg=33,guard=11,reach=2.06,lunge=3.1,knock=.5,stun=.12,style='glaive_serpent',multi_hit=5,no_parry=True,pose_w='glz_w',pose_s='glz_s'),
 'x':dict(name='Phantom Spiral',desc='Reverse-strike sliding double cut.',cd=9,wind=.13,active=.43,recover=.39,dmg=85,guard=24,reach=2.18,lunge=1.4,knock=2,stun=.27,style='glaive_phantom',multi_hit=2,pose_w='glx_w',pose_s='glx_turn'),
 'c':dict(name='Infinite Crescent',desc='Seven accelerating crescent cuts and a launcher finish. Blockable and clashable, not parryable.',cd=20,wind=.30,active=1.78,recover=.70,dmg=44,guard=15,reach=2.18,lunge=1.2,knock=.6,stun=.21,style='glaive_infinite',multi_hit=7,no_parry=True,pose_w='glc_w',pose_s='glc_s'),
 'v':dict(name='Arc Flash',desc='Fast linear glaive dash ending in a heavy cut.',cd=12,wind=.13,active=.21,recover=.48,dmg=190,guard=49,reach=2.35,lunge=38,knock=5.2,stun=.60,heavy=True,style='glaive_thunderflash',pose_w='glx_w',pose_s='glx_turn'),
}

ROSTER_FIELDS = dict(id='zarek', title='Storm Glaive', role='Duelist - Double-Ended Glaive',
    desc='A lightning duelist who builds Clash Momentum by destroying incoming projectiles with her glaive.',
    stats=dict(power=4,speed=4,range=4,defense=3))
LOOK = dict(name='Zarek',body='f',vrm='zarek',kit='glaive',element='storm',outfit='assassin',style='ponytail',hat='none',
    hair='#c8d7eb',hair_shade='#6f93c5',iris_top='#2d74d8',iris_bottom='#a5f0ff',eye_dark='#11284c',
    tunic='#17273f',band='#326ba4',pants='#10192c',boots='#17253a',metal='#cbdcec',trim='#8bdfff',
    cape='#192c4d',cape_bottom='#356dc1',glow='#62cfff',shield='#183a5a',emblem='#c7faff')
STAT = dict(hp=2250,guard=88,move=4.0,walk=3.15,parry=.19,jump=7.7)

# The browser's custom glaive poses need dedicated baking in 19B follow-ups;
# interim paths use the existing katana library so actions have a visible pose.
POSE_ALIAS = dict(l1=('l1_w','l1_s'),l2=('l2_w','l2_s'),l3=('l3_w','l3_s'),
                  l4=('l2_w','l2_s'),l5=('charge','heavy_s'),heavy=('charge','heavy_s'),
                  z=('l1_w','l1_s'),x=('l2_w','l2_s'),c=('charge','heavy_s'),v=('charge','heavy_s'))

MODEL_INSERT = '''
		"glaive": # FRG19B — original double-ended Storm Glaive (right hand)
			var shaft := _pivot(r)
			_part(shaft, _cyl(0.018, 0.018, 1.38, 16), _mat(L.metal, true), Vector3(0, 0, 0))
			_part(shaft, _cyl(0.027, 0.027, 0.24, 12), _mat(L.band), Vector3(0, 0.03, 0))
			for sign in [-1.0, 1.0]:
				_part(shaft, _box(0.09, 0.37, 0.021), steel, Vector3(0, sign * 0.86, 0))
				_part(shaft, _box(0.025, 0.28, 0.025), glow, Vector3(0, sign * 0.86, 0))
				_part(shaft, _cyl(0.0 if sign > 0.0 else 0.045, 0.045 if sign > 0.0 else 0.0, 0.22, 12), steel, Vector3(0, sign * 1.13, 0))
			blade_base = _pivot(shaft, Vector3(0, 0.55, 0))
			blade_tip = _pivot(shaft, Vector3(0, 1.27, 0))
			cast_point = blade_tip
			shield_node = l
'''

MOMENTUM_PATCH = '''
	# FRG19B: only real projectile destroys earn Zarek's Clash Momentum.
	if kit == "glaive" and String(look.get("element", "")) == "storm" and event_id == "projectile_destroyed":
		zarek_momentum += 1
'''

# Simple timed real contact windows: each phase has its own serial and can
# collide once per target. No cosmetic-only damage, no same-frame hit spam.
MULTI_HELPER = '''
# FRG19B: multi-pass moves use real melee checks, once per target each beat.
func _frg19b_multi_contact(f: Fighter) -> void:
	if not f.active_melee():
		_frg19b_multi_phase.erase(f.id)
		return
	var hits: int = clampi(int(f.atk.get("multi_hit", 1)), 1, 12)
	if hits <= 1:
		return
	var attack_t: float = (f.state_t - float(f.atk.wind) * f.attack_time_multiplier())
	var length: float = maxf(float(f.atk.active) * f.attack_time_multiplier(), 0.025)
	var phase: int = clampi(int(floor(maxf(attack_t, 0.0) * hits / length)), 0, hits - 1)
	var key: String = str(f.id)
	var saved: Dictionary = _frg19b_multi_phase.get(key, {})
	var original: int = f.swing_serial
	if saved.get("move", "") != f.atk_id or int(saved.get("serial", -1)) != original:
		saved = {"move": f.atk_id, "phase": 0, "serial": original}
	if phase > int(saved.get("phase", 0)):
		f.swing_serial += phase - int(saved.get("phase", 0))
		saved["phase"] = phase
		saved["serial"] = f.swing_serial
	_frg19b_multi_phase[key] = saved
'''


def read_json(root: Path, rel: str):
    path=root/rel
    try:return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError,ValueError) as e:raise RuntimeError(f'Cannot read {rel}: {e}') from e


def replace_once(txt:str, before:str, after:str, path:str)->str:
    count=txt.count(before)
    if count != 1:raise RuntimeError(f'{path}: expected one matching code anchor, found {count}. No files changed.')
    return txt.replace(before,after,1)


def jsonbytes(obj):return (json.dumps(obj,indent=2,ensure_ascii=False)+'\n').encode('utf-8')

def make_payload(root:Path):
    if not (root/'project.godot').is_file():raise RuntimeError('Open PowerShell in your Godot project directory containing project.godot.')
    if not (root/'data/browser_migration_plan_19a.json').is_file():raise RuntimeError('Install Update 19A first.')
    data={n:read_json(root,f'data/{n}.json') for n in ['roster','stats','attacks','poses']}
    roster,stats,attacks,poses = [data[n] for n in ['roster','stats','attacks','poses']]
    if not isinstance(roster,list) or not all(isinstance(data[n],dict) for n in ['stats','attacks','poses']):raise RuntimeError('Unexpected data JSON format.')
    ids=[str(x.get('id')) for x in roster]
    if len(ids)!=len(set(ids)):raise RuntimeError('Duplicate fighter IDs in roster. Aborting.')
    if ID in ids or 'glaive' in stats or 'glaive' in poses or ID in attacks:
        raise RuntimeError('Zarek or glaive kit already exists. Refusing to overwrite user content. If 19B was installed already, no new installation is needed.')
    if not all(k in attacks for k in ['kaede']) or 'katana' not in stats or 'katana' not in poses:
        raise RuntimeError('Missing original katana/Kaede data needed to initialize a playable Zarek.')
    clone=deepcopy(ROSTER_FIELDS);clone['look']=deepcopy(LOOK)
    roster.append(clone)
    stats['glaive']=deepcopy(STAT)
    poses['glaive']=deepcopy(poses['katana'])
    moves={}
    for aid,attrs in MOVES.items():
        item=deepcopy(attacks['kaede']['l1']);item.update(deepcopy(attrs))
        bw=item['pose_w'];bs=item['pose_s']
        item['browser_pose_w']=bw;item['browser_pose_s']=bs
        item['pose_w'],item['pose_s']=POSE_ALIAS[aid]
        item['reach']=round(float(item['reach'])*.82,2)
        item['lunge']=round(float(item['lunge'])*.8,2)
        item['id']=aid;item['element']='storm'
        # Ensure the selected template's unrelated flags never leak.
        item['heavy']=bool(attrs.get('heavy',False))
        item['next']=attrs.get('next','')
        item['cd']=float(attrs.get('cd',0))
        item['type']='melee'
        moves[aid]=item
    attacks[ID]=moves
    outputs={f'data/{n}.json':jsonbytes(data[n]) for n in data}
    src=root/'animations/katana.tres'
    if not src.is_file():raise RuntimeError('Missing animations/katana.tres; prior animation update is required.')
    outputs['animations/glaive.tres']=src.read_bytes()
    outputs['data/browser_zarek_19b.json']=jsonbytes({'version':VERSION,'source':SOURCE,'source_checked':CHECKED,
        'fighter':'zarek','kit':'glaive','status':'first playable pass; NOT full browser gameplay parity',
        'mechanics_implemented':['five-step combo','charged attack','Z/X/C/V','real timed multi-hit contact','projectile-destroy Clash Momentum','double-ended polearm'],
        'still_to_refine':['individual source-accurate VRM poses','Z spinning / dash cancel','X slide-through movement','C launcher cinematic','V movement track','aerial special choreography'],
        'model_requirement':'models/zarek.vrm if available; existing VRM fallback otherwise','attack_reference':MOVES})
    report='''Fight Royale Godot — 19B Zarek first playable import
Source: browser roster.ts, kits.ts, fighter.ts (checked 2026-11-10)
Zarek: added to selection, using zarek.vrm if present (Godot must import VRMs first).
Combat: 5 light attacks + charged + Z/X/C/V, projectile-destroy momentum, actual multi-hit contact checks.
Weapons: procedural dual-ended storm glaive attached to right hand.
Animation: katana pose aliases for this initial pass. Dedicated source-accurate poses still pending.
Not yet browser-equivalent: dash-cancels, special movement/cinematics and custom Zarek animation timings.
Kaizen and Nesa are NOT added by this installer. They will get individual updates instead of unfinished kits.
No shop, survival or online changes. Original models and SFX are preserved.
'''
    outputs['reports/zarek_19b.txt']=report.encode('utf-8')
    modpath='scripts/fighter_model.gd'
    model=(root/modpath).read_text(encoding='utf-8')
    if '# FRG19B — original double-ended Storm Glaive' not in model:
        model=replace_once(model,'\tmatch kit:\n','\tmatch kit:\n'+MODEL_INSERT,modpath)
    outputs[modpath]=model.encode('utf-8')
    fpath='scripts/fighter.gd'
    fighter=(root/fpath).read_text(encoding='utf-8')
    if 'var zarek_momentum' not in fighter:
        fighter=replace_once(fighter,'var guard_fatigue := 0\n','var guard_fatigue := 0\nvar zarek_momentum := 0  # FRG19B projectile-destroy Clash Momentum\n',fpath)
        fighter=replace_once(fighter,'func notify_passive_event(event_id: String, other: Node = null) -> void:\n','func notify_passive_event(event_id: String, other: Node = null) -> void:\n'+MOMENTUM_PATCH,fpath)
        fighter=replace_once(fighter,'\treturn (1.0 / maxf(1.0 - 0.02 * float(guard_fatigue), 0.5)) * status_runtime.attack_time_multiplier()',
            '\tvar factor: float = 1.0 + 0.20 * float(mini(zarek_momentum, 5)) if kit == "glaive" and atk_id.begins_with("l") else 1.0\n\treturn (1.0 / maxf(1.0 - 0.02 * float(guard_fatigue), 0.5)) * status_runtime.attack_time_multiplier() / factor', fpath)
        fighter=replace_once(fighter,'if state_t <= parry_window:\n','if state_t <= parry_window and not bool(a.get("no_parry", false)):\n', fpath)
        fighter=replace_once(fighter,'func status_summary() -> String:\n\treturn status_runtime.short_label() if status_runtime != null else ""',
            'func status_summary() -> String:\n\tvar summary: String = status_runtime.short_label() if status_runtime != null else ""\n\tif kit == "glaive" and zarek_momentum > 0:\n\t\treturn "Momentum x%d" % zarek_momentum if summary.is_empty() else "Momentum x%d, %s" % [zarek_momentum, summary]\n\treturn summary', fpath)
    outputs[fpath]=fighter.encode('utf-8')
    mpath='scripts/match.gd'
    match=(root/mpath).read_text(encoding='utf-8')
    if '# FRG19B: multi-pass moves' not in match:
        match=replace_once(match,'var _melee_hits: Dictionary = {}', 'var _frg19b_multi_phase: Dictionary = {}\nvar _melee_hits: Dictionary = {}',mpath)
        match=replace_once(match,'_melee_hits.clear(); _projectiles.clear()', '_melee_hits.clear(); _frg19b_multi_phase.clear(); _projectiles.clear()',mpath)
        match=replace_once(match,'\t\tif dt > 0.0 and not round_over and f.active_melee():\n\t\t\t_active_melee_contact(f)',
            '\t\tif dt > 0.0 and not round_over and f.active_melee():\n\t\t\t_frg19b_multi_contact(f)\n\t\t\t_active_melee_contact(f)',mpath)
        match += '\n'+MULTI_HELPER
    outputs[mpath]=match.encode('utf-8')
    # Modify existing AI personality config only if new character is absent.
    a_path=root/'data/ai_personalities.json'
    if a_path.is_file():
        ai=read_json(root,'data/ai_personalities.json')
        if not isinstance(ai,dict) or not isinstance(ai.get('fighters',{}),dict):raise RuntimeError('Unexpected AI personality config.')
        ai['fighters'].setdefault('zarek',{'archetype':'katana','attack_pace':1.22,'parry_scale':1.16,'orbit_scale':1.22,'skill_pace':1.10})
        outputs['data/ai_personalities.json']=jsonbytes(ai)
    wp=root/'data/weapon_profiles.json'
    if wp.is_file():
        prof=read_json(root,'data/weapon_profiles.json')
        if not isinstance(prof,dict) or not isinstance(prof.get('kits',{}),dict):raise RuntimeError('Unexpected weapon profile config.')
        prof['kits'].setdefault('glaive',deepcopy(prof['kits']['katana']))
        outputs['data/weapon_profiles.json']=jsonbytes(prof)
    # Sanity check all in-memory assets are in sync before writing anything.
    for move in moves.values():
        assert move['pose_w'] in poses['glaive'] and move['pose_s'] in poses['glaive']
    assert all(k in moves for k in ['l1','l2','l3','l4','l5','heavy','z','x','c','v'])
    return outputs


def sha(data:bytes|None)->str|None:return hashlib.sha256(data).hexdigest() if data is not None else None

def atomic_write(path:Path,payload:bytes):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.frg19b-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as handle:
            handle.write(payload);handle.flush();os.fsync(handle.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def execute(root:Path,dry:bool):
    if (root/'data/browser_zarek_19b.json').is_file():
        # An existing 19B may have customized data; refuse re-porting that would overwrite it.
        print('Update 19B already installed. Existing Zarek content preserved.')
        return
    desired=make_payload(root)
    changes={rel:payload for rel,payload in desired.items() if not (root/rel).is_file() or (root/rel).read_bytes()!=payload}
    for name in changes:print('Update:',name)
    if dry:print('DRY RUN — no changes.');return
    backup=root.parent/(root.name+'_backups')/('roster_19b_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
    backup.mkdir(parents=True,exist_ok=False)
    manifest={'version':VERSION,'project':str(root),'files':{}}
    for rel,payload in changes.items():
        old=(root/rel).read_bytes() if (root/rel).is_file() else None
        manifest['files'][rel]={'before':sha(old),'after':sha(payload)}
        if old is not None:
            dest=backup/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(old)
    (backup/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    completed=[]
    try:
        for rel,payload in changes.items():
            atomic_write(root/rel,payload);completed.append(rel)
    except Exception:
        for rel in reversed(completed):
            archived=backup/rel
            if archived.is_file():atomic_write(root/rel,archived.read_bytes())
            else:(root/rel).unlink(missing_ok=True)
        raise
    print('Update 19B installed — Zarek appears in roster. Open Godot editor to import VRMs before playing.')
    print('Backup:',backup)


def restore(root:Path,backup:Path):
    meta=read_json(backup,'manifest.json')
    if meta.get('project')!=str(root):raise RuntimeError('Backup is not for this project.')
    for rel,state in meta['files'].items():
        current=(root/rel).read_bytes() if (root/rel).is_file() else None
        if sha(current)!=state['after']:raise RuntimeError(f'Cannot restore, file changed: {rel}')
    for rel,state in meta['files'].items():
        path=root/rel;old=backup/rel
        if state['before'] is None:path.unlink(missing_ok=True)
        else:atomic_write(path,old.read_bytes())
    print('Restored from',backup)


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--restore',type=Path)
    args=parser.parse_args()
    root=Path.cwd().resolve()
    try:
        if args.restore:restore(root,args.restore.expanduser().resolve())
        else:execute(root,args.dry_run)
    except Exception as error:
        print('ERROR:',error,file=sys.stderr);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
