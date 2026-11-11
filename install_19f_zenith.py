#!/usr/bin/env python3
"""Fight Royale Godot 19F — Zenith / Iron Sovereign (first playable port).

Run in your Godot folder: python install_19f_zenith.py
Options: --dry-run, --restore BACKUP_DIRECTORY

Adds Zenith's five-hit metal spear combo, magnetic lance charge, Rail Spear,
Phantom Spear Barrage, Spearstep, and Sovereign Arsenal (17 spear bloom + 12
launched spears + 2 directed finishers), with +0.01 action speed per confirmed
hit up to 14 stacks for 5s. Rail Spear manual recast, complete polarity and
exact browser cinematics remain for subsequent refinement.

Browser reference checked 2026-11-10:
https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

VERSION = '19F.1'
CHARACTER = 'zenith'
LOOK = dict(
    name='Zenith', body='f', vrm='zenith', kit='glaive', element='metal',
    outfit='knight', style='long', hat='none', hair='#b8dfca',
    hair_shade='#79bba1', iris_top='#2a9b7b', iris_bottom='#a2fae6',
    eye_dark='#103d38', tunic='#26383c', band='#a7cebf', pants='#1a2932',
    boots='#22333b', metal='#d5f0e8', trim='#84e0c2', cape='#34565b',
    cape_bottom='#96d6bd', glow='#b5ffdf', shield='#2a5953', emblem='#c8fbe6'
)
# Browser values; the special 5-hit l5 splits its TOTAL 51 damage across
# 5 real hit windows to avoid multiplying the source damage fivefold.
MOVES = {
    'l1': dict(name='Steel Fang 1',wind=.085,active=.075,recover=.14,dmg=32.25,guard=13,reach=2.14,lunge=2.35,knock=.65,stun=.16,next='l2',style='zenith_basic'),
    'l2': dict(name='Steel Fang 2',wind=.099,active=.075,recover=.14,dmg=34.5,guard=15,reach=2.14,lunge=2.35,knock=.65,stun=.16,next='l3',style='zenith_basic'),
    'l3': dict(name='Steel Fang 3',wind=.113,active=.075,recover=.15,dmg=36.75,guard=17,reach=2.14,lunge=2.35,knock=.65,stun=.16,next='l4',style='zenith_basic'),
    'l4': dict(name='Steel Fang 4',wind=.127,active=.075,recover=.16,dmg=38.25,guard=19,reach=2.14,lunge=2.35,knock=.65,stun=.16,next='l5',style='zenith_basic'),
    'l5': dict(name='Phantom Fang',wind=.141,active=.40,recover=.12,dmg=10.2,guard=4.2,reach=2.14,lunge=2.35,knock=3.,stun=.32,style='zenith_phantom',multi_hit=5),
    'heavy': dict(name='Magnetic Lance',type='projectile',wind=.44,active=.05,recover=.47,dmg=100,guard=35,knock=3,stun=.35,heavy=True,speed=23,size=.88,pierce=True,style='zenith_heavy'),
    'z': dict(name='Rail Spear',desc='Piercing thrown metal spear. Magnetic recall refinement follows in a later update.',type='projectile',cd=12,wind=.19,active=.05,recover=.29,dmg=92,guard=25,knock=2.5,stun=.40,speed=24,size=1.06,pierce=True,style='zenith_rail'),
    'x': dict(name='Phantom Spear Barrage',desc='Five rapid thrusts followed by three separately launched spectral spears.',cd=10,type='melee',wind=.12,active=.75,recover=.33,dmg=25,guard=9,reach=2.35,lunge=0.5,knock=.35,stun=.13,style='zenith_barrage',multi_hit=5),
    'c': dict(name='Spearstep',desc='A rapid forward spear dash strike; real hit adds magnetic attack speed.',cd=11,type='melee',wind=.16,active=.22,recover=.38,dmg=110,guard=34,reach=2.63,lunge=16,knock=4.2,stun=.45,style='zenith_dash'),
    'v': dict(name='Sovereign Arsenal',desc='17-spear metal bloom, followed by twelve flying spears and two finishing rails.',cd=53,type='projectile',wind=.55,active=1.35,recover=.7,dmg=43,guard=15,knock=1.4,stun=.18,speed=17,size=1.2,pierce=False,style='zenith_arsenal'),
}
ALIASES = {'l1':'l1','l2':'l2','l3':'l3','l4':'l4','l5':'l5','heavy':'heavy','z':'z','x':'x','c':'v','v':'c'}

# The existing glaive match branch is shared with Zarek. Distinguish the weapon
# by element so we do NOT turn Zarek's double-ended glaive into Zenith's spear.
MODEL_GLAIVE = '''\t\t"glaive": # FRG19B/19F - element-specific polearm designs
\t\t\tif String(L.get("element", "")) == "metal":
\t\t\t\t# FRG19F Zenith: SINGLE-TIPPED thrusting spear, not Zarek's double glaive.
\t\t\t\tvar spear := _pivot(r, Vector3(0, -0.14, 0))
\t\t\t\t_part(spear, _cyl(0.017, 0.017, 1.92, 14), _mat(L.metal, true), Vector3(0, 0.66, 0))
\t\t\t\t_part(spear, _cyl(0.031, 0.031, 0.22, 12), _mat(L.band), Vector3(0, -0.12, 0))
\t\t\t\t_part(spear, _box(0.20, 0.045, 0.085), trim, Vector3(0, 1.55, 0))
\t\t\t\t_part(spear, _box(0.14, 0.47, 0.065), steel, Vector3(0, 1.80, 0))
\t\t\t\t_part(spear, _box(0.038, 0.38, 0.078), glow, Vector3(0, 1.81, -0.032))
\t\t\t\t_part(spear, _cyl(0.0, 0.062, 0.26, 12), steel, Vector3(0, 2.12, 0))
\t\t\t\tblade_base = _pivot(spear, Vector3(0, 1.20, 0))
\t\t\t\tblade_tip = _pivot(spear, Vector3(0, 2.25, 0))
\t\t\t\tcast_point = blade_tip
\t\t\t\tshield_node = l
\t\t\telse:
\t\t\t\t# FRG19B Zarek original double-ended Storm Glaive.
\t\t\t\tvar shaft := _pivot(r)
\t\t\t\t_part(shaft, _cyl(0.018, 0.018, 1.38, 16), _mat(L.metal, true), Vector3(0, 0, 0))
\t\t\t\t_part(shaft, _cyl(0.027, 0.027, 0.24, 12), _mat(L.band), Vector3(0, 0.03, 0))
\t\t\t\tfor sign in [-1.0, 1.0]:
\t\t\t\t\t_part(shaft, _box(0.09, 0.37, 0.021), steel, Vector3(0, sign * 0.86, 0))
\t\t\t\t\t_part(shaft, _box(0.025, 0.28, 0.025), glow, Vector3(0, sign * 0.86, 0))
\t\t\t\t\t_part(shaft, _cyl(0.0 if sign > 0.0 else 0.045, 0.045 if sign > 0.0 else 0.0, 0.22, 12), steel, Vector3(0, sign * 1.13, 0))
\t\t\t\tblade_base = _pivot(shaft, Vector3(0, 0.55, 0))
\t\t\t\tblade_tip = _pivot(shaft, Vector3(0, 1.27, 0))
\t\t\t\tcast_point = blade_tip
\t\t\t\tshield_node = l
'''

FIGHTER_FIELDS = '''# FRG19F Zenith - +0.01 action speed per real damage event, 14-stack cap.
var zenith_magnetic_stacks := 0
var zenith_magnetic_timer := 0.0
'''
FIGHTER_TICK = '''\t# FRG19F Zenith: consecutive landed hits refresh the 5s charge duration.
\tif zenith_magnetic_timer > 0.0:
\t\tzenith_magnetic_timer = maxf(0.0, zenith_magnetic_timer - dt)
\t\tif zenith_magnetic_timer <= 0.0:
\t\t\tzenith_magnetic_stacks = 0
'''
FIGHTER_PASSIVE = '''\t# FRG19F: ONLY landed damaging hits grant the iron sovereign momentum.
\tif kit == "glaive" and String(look.get("element", "")) == "metal" and event_id == "landed_hit":
\t\tzenith_magnetic_stacks = mini(zenith_magnetic_stacks + 1, 14)
\t\tzenith_magnetic_timer = 5.0
'''
MATCH_BLOOM = '''\n# FRG19F — 17 visual spear sentinels; 12 outward shots and 2 final rails.
# Kept distinct from Zarek's glaive V; all delayed events are tied to the round.
func _zenith_spear_projectile(f: Fighter, attack: Dictionary, offset: float, speed: float) -> void:
\tif not is_instance_valid(f) or f.is_down() or round_over:
\t\treturn
\tvar origin: Vector3 = f.model.cast_point.global_position
\tvar opponent = f.opponent
\tvar aim: Vector3 = opponent.chest() - origin if is_instance_valid(opponent) and not opponent.is_down() else f.forward()
\tvar direction := aim.normalized().rotated(Vector3.UP, offset)
\t_spawn_projectile(f, attack, f.atk_power, origin, direction * speed, Color(f.look.glow), opponent)

func _zenith_barrage(f: Fighter, a: Dictionary) -> void:
\tvar rnd: int = _round
\tfor i in range(3):
\t\tvar shot: Dictionary = a.duplicate(true)
\t\tshot["type"] = "projectile"
\t\tshot["style"] = "zenith_spear"
\t\tshot["dmg"] = 24.0
\t\tshot["guard"] = 9.0
\t\tshot["pierce"] = false
\t\tshot["size"] = 0.8
\t\tshot["speed"] = 22.0
\t\tvar angle: float = (float(i) - 1.0) * 0.13
\t\tlater(0.23 + float(i) * 0.14, func():
\t\t\tif rnd == _round and is_instance_valid(f) and not f.is_down():
\t\t\t\t_zenith_spear_projectile(f, shot, angle, 22.0))

func _zenith_arsenal(f: Fighter, a: Dictionary) -> void:
\tvar rnd: int = _round
\tvar bloom := Node3D.new()
\tbloom.name = "ZenithMetalBloom19F"
\tf.add_child(bloom)
\tbloom.position = Vector3(0.0, 1.15, 0.0)
\tvar material := Fx.unlit(Color("#c5fff1"), 0.95, true)
\tfor i in range(17):
\t\tvar spear := MeshInstance3D.new()
\t\tvar blade := BoxMesh.new()
\t\tblade.size = Vector3(0.055, 0.055, 0.85)
\t\tspear.mesh = blade
\t\tspear.material_override = material
\t\tvar a_rad: float = TAU * float(i) / 17.0
\t\tspear.position = Vector3(cos(a_rad) * 1.4, sin(a_rad * 2.0) * 0.22, sin(a_rad) * 1.4)
\t\tspear.rotation.y = -a_rad
\t\tbloom.add_child(spear)
\tfx_placeholder
\tlater(1.25, func():
\t\tif is_instance_valid(bloom): bloom.queue_free())
\tfor i in range(12):
\t\tvar shot: Dictionary = a.duplicate(true)
\t\tshot["style"] = "zenith_spear"
\t\tshot["dmg"] = 21.5
\t\tshot["guard"] = 8.0
\t\tshot["size"] = 0.8
\t\tshot["pierce"] = false
\t\tvar angle: float = (float(i) - 5.5) * 0.072
\t\tlater(0.07 + float(i) * 0.085, func():
\t\t\tif rnd == _round and is_instance_valid(f) and not f.is_down():
\t\t\t\t_zenith_spear_projectile(f, shot, angle, 17.0))
\tfor i in range(2):
\t\tvar finisher: Dictionary = a.duplicate(true)
\t\tfinisher["style"] = "zenith_finisher"
\t\tfinisher["dmg"] = 43.0
\t\tfinisher["size"] = 1.15
\t\tfinisher["pierce"] = true
\t\tvar angle: float = -0.055 if i == 0 else 0.055
\t\tlater(1.06 + float(i) * 0.13, func():
\t\t\tif rnd == _round and is_instance_valid(f) and not f.is_down():
\t\t\t\t_zenith_spear_projectile(f, finisher, angle, 23.0))
'''.replace('\tfx_placeholder', '	fx.ring(f.position, Color("#bbffe8"), 2.1, 0.32, 0.84)')


def jbytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def jsonfile(root:Path, rel:str):
    try: return json.loads((root/rel).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as err: raise RuntimeError(f'Cannot read {rel}: {err}') from err


def swap_once(source:str, needle:str, replacement:str, rel:str):
    n=source.count(needle)
    if n!=1: raise RuntimeError(f'{rel}: expected 1 code anchor, found {n}; project unchanged')
    return source.replace(needle,replacement,1)


def build(root:Path):
    if not (root/'project.godot').is_file(): raise RuntimeError('Run from Godot project containing project.godot')
    if not (root/'data/browser_roxy_19e.json').is_file(): raise RuntimeError('Install Update 19E (Roxy) before 19F')
    roster=jsonfile(root,'data/roster.json')
    attacks=jsonfile(root,'data/attacks.json')
    poses=jsonfile(root,'data/poses.json')
    stats=jsonfile(root,'data/stats.json')
    if not isinstance(roster,list) or any(not isinstance(o,dict) for o in (attacks,poses,stats)):
        raise RuntimeError('Unexpected fighter data format')
    ids=[x.get('id') for x in roster]
    if len(ids)!=len(set(ids)): raise RuntimeError('Duplicate fighter IDs; refusing to modify')
    if CHARACTER in ids or CHARACTER in attacks: raise RuntimeError('Zenith is already present; refusing to replace existing fighter')
    if 'zarek' not in attacks or 'glaive' not in poses or 'glaive' not in stats:
        raise RuntimeError('Missing earlier Zarek glaive port required as template')
    src=(root/'animations/glaive.tres')
    if not src.is_file(): raise RuntimeError('Missing glaive animation library')
    entry={'id':CHARACTER,'title':'Iron Sovereign','role':'Magnetic Spear Duelist',
           'desc':'Metal spear specialist with rapid thrusts, magnetic charge, spearstep and sovereign arsenal.',
           'stats':{'power':4,'speed':4,'range':4,'defense':3},'look':deepcopy(LOOK)}
    roster.append(entry)
    out={}
    moves={}
    for name, attrs in MOVES.items():
        source=deepcopy(attacks['zarek'].get(name,attacks['zarek']['l1']))
        source.update(deepcopy(attrs))
        source['id']=name
        source['element']='metal'
        source['next']=attrs.get('next','')
        source['type']=attrs.get('type','melee')
        source['heavy']=bool(attrs.get('heavy',False))
        source['cd']=float(attrs.get('cd',0))
        source['multi_hit']=int(attrs.get('multi_hit',1))
        source['count']=int(attrs.get('count',1))
        source['spread']=float(attrs.get('spread',0.0))
        source['pierce']=bool(attrs.get('pierce',False))
        alias=ALIASES[name]
        source['pose_w']=attacks['zarek'][alias]['pose_w']
        source['pose_s']=attacks['zarek'][alias]['pose_s']
        source['browser_pose_w']=('zn'+name+'_w')
        source['browser_pose_s']=('zn'+name+'_s')
        for k in ('pose_w','pose_s'):
            if source[k] not in poses['glaive']:
                raise RuntimeError(f'Zenith {name} references unknown {k}: {source[k]}')
        moves[name]=source
    attacks[CHARACTER]=moves
    out['data/roster.json']=jbytes(roster)
    out['data/attacks.json']=jbytes(attacks)
    # Keep model/weapon offsets configured per ID so Zarek remains unchanged.
    p='scripts/fighter_model.gd'
    code=(root/p).read_text(encoding='utf-8')
    start=code.find('\t\t"glaive": # FRG19B')
    end=code.find('\t\t"knight":', start)
    if start<0 or end<start or 'for sign in [-1.0, 1.0]' not in code[start:end]:
        raise RuntimeError(f'{p}: glaive code differs from expected 19B implementation')
    code=code[:start]+MODEL_GLAIVE+code[end:]
    out[p]=code.encode('utf-8')
    p='scripts/fighter.gd'
    code=(root/p).read_text(encoding='utf-8')
    code=swap_once(code,'var zarek_momentum := 0  # FRG19B projectile-destroy Clash Momentum\n',
        FIGHTER_FIELDS+'var zarek_momentum := 0  # FRG19B projectile-destroy Clash Momentum\n',p)
    code=swap_once(code,'\troxy_freeze_cd = maxf(0.0, roxy_freeze_cd - dt)\n',
        '\troxy_freeze_cd = maxf(0.0, roxy_freeze_cd - dt)\n'+FIGHTER_TICK,p)
    code=swap_once(code,'func notify_passive_event(event_id: String, other: Node = null) -> void:\n',
        'func notify_passive_event(event_id: String, other: Node = null) -> void:\n'+FIGHTER_PASSIVE,p)
    code=swap_once(code,'\treturn (1.0 / maxf(1.0 - 0.02 * float(guard_fatigue), 0.5)) * status_runtime.attack_time_multiplier() / factor\n',
        '\tvar metal_factor: float = 1.0 + 0.01 * float(zenith_magnetic_stacks) if kit == "glaive" and String(look.get("element", "")) == "metal" else 1.0\n\treturn (1.0 / maxf(1.0 - 0.02 * float(guard_fatigue), 0.5)) * status_runtime.attack_time_multiplier() / (factor * metal_factor)\n',p)
    code=swap_once(code,'\treturn summary\n\n# FRG15D - status HUD and countdown indicators\n',
        '\tif kit == "glaive" and String(look.get("element", "")) == "metal" and zenith_magnetic_stacks > 0:\n\t\treturn "Magnetic x%d" % zenith_magnetic_stacks if summary.is_empty() else "Magnetic x%d, %s" % [zenith_magnetic_stacks, summary]\n\treturn summary\n\n# FRG15D - status HUD and countdown indicators\n',p)
    out[p]=code.encode('utf-8')
    p='scripts/match.gd'
    code=(root/p).read_text(encoding='utf-8')
    code=swap_once(code,'\tmatch a.type:\n\t\t"projectile": _fire(f, a)\n',
        '\tif f.kit == "glaive" and String(f.look.get("element", "")) == "metal":\n'
        '\t\tmatch String(a.get("style", "")):\n'
        '\t\t\t"zenith_barrage": _zenith_barrage(f, a)\n'
        '\t\t\t"zenith_arsenal": _zenith_arsenal(f, a); return\n'
        '\tmatch a.type:\n\t\t"projectile": _fire(f, a)\n',p)
    code=swap_once(code,'func _active_melee_contact(f: Fighter) -> void:\n',
        MATCH_BLOOM+'\nfunc _active_melee_contact(f: Fighter) -> void:\n',p)
    # Distinct projectile silhouettes rather than generic magic balls.
    code=swap_once(code,'\tmatch style:\n\t\t"arrow":\n',
        '\tmatch style:\n\t\t"zenith_rail", "zenith_heavy", "zenith_spear", "zenith_finisher":\n'
        '\t\t\tvar spear := BoxMesh.new()\n\t\t\tspear.size = Vector3(0.08, 0.09, 0.78) * size\n\t\t\treturn spear\n\t\t"arrow":\n',p)
    out[p]=code.encode('utf-8')
    ai_rel='data/ai_personalities.json'
    if (root/ai_rel).is_file():
        ai=jsonfile(root,ai_rel)
        if not isinstance(ai,dict) or not isinstance(ai.get('fighters',{}),dict):
            raise RuntimeError('Unrecognized AI personality JSON')
        ai['fighters'].setdefault(CHARACTER, {'archetype':'katana','attack_pace':1.20,'skill_pace':1.04,
                    'approach_scale':1.02,'orbit_scale':1.10,'parry_scale':1.04})
        out[ai_rel]=jbytes(ai)
    out['data/browser_zenith_19f.json']=jbytes({
        'version':VERSION,'fighter':CHARACTER,
        'browser_reference':'https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts',
        'status':'FIRST PLAYABLE PASS, NOT FULL SOURCE PARITY',
        'implemented':['single-tip metal spear visual','five-hit light combo','five-contact Phantom Fang with total 51 damage',
                       'Magnetic Lance charged projectile','piercing Rail Spear throw','five-thrust barrage and three independently timed spears',
                       'Spearstep dash strike','Sovereign Arsenal 17 visual spears, 12 live shots and 2 finisher projectiles',
                       'Magnetic Charge +0.01 action speed per damaging hit up to 14 stacks (5 second reset)'],
        'refinements_pending':['manual spear recall and physical throw/return path',
          'Positive/Negative polarity pull and repel mechanics', 'correct source-authored Zenith-specific bone poses',
          'V protective CC immunity and spear intercept behavior','V camera choreography','spear vs twin-blade speed modes',
          'character AI behavior verification and runtime balance testing']})
    out['reports/zenith_19f.txt']=(
        'Fight Royale Update 19F — Zenith Iron Sovereign\n'
        'Requires 19E. Adds fully selectable Zenith without touching Zarek.\n'
        'Run Godot editor once to import models/zenith.vrm after adding it.\n'
        'First playable pass: real timed contact, 5 spear basics, Z/X/C/V and magnetic charge.\n'
        'Uses glaive pose aliases until unique Zenith animations are baked in.\n'
        'Manual recall, magnetic polarities and source-accurate V protective bloom need refinement.\n'
        'No shop, online, survival or team-mode updates.\n').encode('utf-8')
    return out


def sha(value):
    return hashlib.sha256(value).hexdigest() if value is not None else None


def atomic(path:Path, payload:bytes):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.frg19f-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(payload);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def execute(root:Path, dry:bool):
    if (root/'data/browser_zenith_19f.json').exists():
        print('Update 19F already installed. No changes.');return
    payload=build(root)
    changes={key:value for key,value in payload.items() if not (root/key).is_file() or (root/key).read_bytes()!=value}
    for rel in changes: print('Update:',rel)
    if dry:
        print('DRY RUN: no project changes.');return
    backup=root.parent/(root.name+'_backups')/('zenith_19f_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
    backup.mkdir(parents=True,exist_ok=False)
    manifest={'version':VERSION,'project':str(root),'files':{}}
    for rel,data in changes.items():
        old=(root/rel).read_bytes() if (root/rel).is_file() else None
        manifest['files'][rel]={'before':sha(old),'after':sha(data)}
        if old is not None:
            saved=backup/rel;saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(old)
    (backup/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    done=[]
    try:
        for rel,data in changes.items():
            atomic(root/rel,data);done.append(rel)
    except BaseException:
        for rel in reversed(done):
            old=backup/rel
            if old.is_file(): atomic(root/rel,old.read_bytes())
            else: (root/rel).unlink(missing_ok=True)
        raise
    print('Installed Zenith 19F. Backup:',backup)


def restore(root:Path, backup:Path):
    data=jsonfile(backup,'manifest.json')
    if data.get('project') != str(root): raise RuntimeError('Wrong project backup')
    for rel,info in data['files'].items():
        actual=(root/rel).read_bytes() if (root/rel).is_file() else None
        if sha(actual) != info['after']: raise RuntimeError(f'Rollback prevented: {rel} changed after install')
    for rel,info in data['files'].items():
        old=backup/rel
        if info['before'] is None: (root/rel).unlink(missing_ok=True)
        else: atomic(root/rel,old.read_bytes())
    print('Restored:',backup)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run',action='store_true')
    ap.add_argument('--restore',type=Path)
    args=ap.parse_args()
    root=Path.cwd().resolve()
    try:
        if args.restore: restore(root,args.restore.expanduser().resolve())
        else: execute(root,args.dry_run)
    except Exception as err:
        print('ERROR:',err,file=sys.stderr);return 1
    return 0

if __name__=='__main__': raise SystemExit(main())
