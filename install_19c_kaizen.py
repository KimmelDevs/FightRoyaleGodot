#!/usr/bin/env python3
"""Fight Royale Godot — Update 19C, Kaizen Chainblade Berserker (first playable pass).

Use in project directory: python install_19c_kaizen.py
Supports --dry-run and --restore <backup-directory>.

Ports 5-hit Dancing Fang, charged Chainbreaker, Z Razor Cyclone, X Predator's
Hook, C Death Spiral, V Serpent Bind from the browser source. Z/C use actual
separate multi-hit contact frames through Update 19B, not cosmetic damage.
X and V apply a real short root on successful contact; X recast pulls its bound
target close. Full chained grab cinematics, Z hold-to-extend, directional V
finishers, and bespoke animations are reserved for later refinements.

Browser references (checked 2026-11-10):
https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts
https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/roster.ts
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

VERSION = '19C.1'
CHAR_ID = 'kaizen'
KIT = 'chainblade'

LOOK = {
 'name':'Kaizen','body':'m','vrm':'kaizen','kit':'chainblade','element':'chain','outfit':'knight','style':'short','hat':'none',
 'hair':'#231f29','hair_shade':'#716570','iris_top':'#9d282a','iris_bottom':'#ff895c','eye_dark':'#2c0910',
 'tunic':'#332831','band':'#6e3034','pants':'#221e25','boots':'#352b30','metal':'#adb2bd','trim':'#b88f7b',
 'cape':'#4e242a','cape_bottom':'#8e3039','glow':'#ff5b63','shield':'#3b242b','emblem':'#ffa5a0'
}
STATS = {'hp':2450,'guard':100,'move':3.55,'walk':2.75,'parry':.16,'jump':7.0}
# Values derived from current public kits.ts. Alias poses are temporary; original
# cb_* choreography must be ported in dedicated animation refinements.
MOVES = {
 'l1': {'name':'Dancing Fang 1','wind':.16,'active':.10,'recover':.25,'dmg':69,'guard':20,'reach':2.12,'lunge':2.0,'knock':1.2,'stun':.24,'next':'l2','style':'chain_basic','pose_w':'cb1_w','pose_s':'cb1_s'},
 'l2': {'name':'Dancing Fang 2','wind':.17,'active':.10,'recover':.26,'dmg':73,'guard':21,'reach':2.2,'lunge':2.0,'knock':1.2,'stun':.25,'next':'l3','style':'chain_basic','pose_w':'cb2_w','pose_s':'cb2_s'},
 'l3': {'name':'Dancing Fang 3','wind':.20,'active':.11,'recover':.29,'dmg':77,'guard':23,'reach':2.4,'lunge':1.8,'knock':1.5,'stun':.27,'next':'l4','style':'chain_basic','pose_w':'cb3_w','pose_s':'cb3_s'},
 'l4': {'name':'Dancing Fang 4','wind':.25,'active':.12,'recover':.31,'dmg':90,'guard':28,'reach':2.8,'lunge':1.6,'knock':1.8,'stun':.32,'next':'l5','style':'chain_basic','pose_w':'cb4_w','pose_s':'cb4_s'},
 'l5': {'name':'Dancing Fang Return','wind':.24,'active':.24,'recover':.55,'dmg':112,'guard':36,'reach':3.0,'lunge':1.2,'knock':3.8,'stun':.40,'heavy':True,'style':'chain_return','pose_w':'cb5_w','pose_s':'cb5_s'},
 'heavy':{'name':'Chainbreaker','wind':.35,'active':.17,'recover':.67,'dmg':185,'guard':51,'reach':3.0,'lunge':1.2,'knock':5.6,'stun':.56,'heavy':True,'style':'chain_heavy','pose_w':'cbh_w','pose_s':'cbh_s'},
 'z': {'name':'Razor Cyclone','desc':'Spin the chainblade while walking toward the opponent. Extended hold duration is scheduled for refinement.','cd':8,'wind':.20,'active':1.65,'recover':.38,'dmg':28,'guard':11,'reach':2.2,'stun':.15,'style':'chain_razor_cyclone','multi_hit':6,'pose_w':'cbz_w','pose_s':'cbz_s'},
 'x': {'name':"Predator's Hook",'desc':'Throw a long chain to bind an enemy up to 4 seconds. Recast X to pull them toward Kaizen. Blocking or clashing prevents the bind.','cd':10,'wind':.22,'active':.13,'recover':.45,'dmg':75,'guard':24,'reach':4.8,'stun':.28,'style':'chain_predator_hook','pose_w':'cbh_w','pose_s':'cbh_s'},
 'c': {'name':'Thousand Cuts: Death Spiral','desc':'A moving chain whirlwind with multiple defendable contacts. Contracting circle and overhead finisher will be refined.','cd':22,'wind':.38,'active':1.85,'recover':.68,'dmg':42,'guard':12,'reach':3.1,'radius':4.2,'style':'chain_death_spiral','multi_hit':7,'pose_w':'cbc_w','pose_s':'cbc_s'},
 'v': {'name':'Serpent Bind','desc':'A heavier chain bind that roots the target. Directional swinging finishers are being migrated separately.','cd':13,'wind':.29,'active':.12,'recover':.62,'dmg':85,'guard':29,'reach':2.9,'knock':1.0,'stun':.55,'style':'chain_serpent_bind','pose_w':'cbv_w','pose_s':'cbv_s'}
}
POSE_ALIASES = {
 'l1':('l1_w','l1_s'),'l2':('l2_w','l2_s'),'l3':('l3_w','l3_s'),
 'l4':('l2_w','l2_s'),'l5':('charge','heavy_s'),'heavy':('charge','heavy_s'),
 'z':('charge','l3_s'),'x':('charge','l3_s'),'c':('charge','heavy_s'),'v':('charge','heavy_s')
}

WEAPON_CODE = '''
		"chainblade": # FRG19C segmented chainblade, procedural first pass
			var weapon := _pivot(r)
			_part(weapon, _cyl(0.022, 0.022, 0.35), _mat(L.pants), Vector3(0, -0.05, 0))
			_part(weapon, _box(0.29, 0.045, 0.075), trim, Vector3(0, 0.15, 0))
			for i in range(7):
				var piece := _pivot(weapon, Vector3(0, 0.21 + float(i) * 0.21, 0))
				_part(piece, _box(0.14 - float(i) * 0.008, 0.19, 0.045), steel, Vector3.ZERO)
				_part(piece, _box(0.025, 0.15, 0.048), glow, Vector3.ZERO)
				if i > 0:
					_part(piece, _cyl(0.022, 0.022, 0.08), _mat(L.band), Vector3(0, -0.11, 0))
			blade_base = _pivot(weapon, Vector3(0, 0.34, 0))
			blade_tip = _pivot(weapon, Vector3(0, 1.68, 0))
			cast_point = blade_tip
			shield_node = l
'''

FIGHTER_FIELDS = '''
# FRG19C Kaizen: target captured by a confirmed Predator's Hook contact.
var kaizen_bound_target: Fighter = null
var kaizen_bind_seconds := 0.0
'''

FIGHTER_TICK = '''
	# FRG19C: bind lifetime, no persistence across KO or another match.
	if kaizen_bind_seconds > 0.0:
		kaizen_bind_seconds = maxf(0.0, kaizen_bind_seconds - dt)
		if kaizen_bind_seconds <= 0.0 or not is_instance_valid(kaizen_bound_target) or kaizen_bound_target.is_down():
			kaizen_bound_target = null
'''

FIGHTER_RECAST = '''
	# FRG19C: X recast reels a previously bound enemy to Kaizen (even during X cooldown).
	if kit == "chainblade" and in_skill == "x" and kaizen_bind_seconds > 0.0 and is_instance_valid(kaizen_bound_target):
		var victim: Fighter = kaizen_bound_target
		kaizen_bound_target = null
		kaizen_bind_seconds = 0.0
		if not victim.is_down():
			var pull_to: Vector3 = global_position + forward() * 1.25
			pull_to.y = victim.position.y
			victim.teleport(pull_to)
			victim.remove_status("root")
			victim.stagger(0.40)
		in_skill = ""
		return
'''

MATCH_ON_HIT = '''
	# FRG19C: confirmed contacts only. Blocks, parries, clashes and invulnerable
	# enemies cannot be chain-bound. The victim's existing CC rules do the locking.
	if attacker is Fighter and attacker.kit == "chainblade" and result in ["hit", "crit"]:
		var chain_style: String = String(a.get("style", ""))
		if chain_style == "chain_predator_hook":
			if d.add_status("root", 1, 4.0):
				attacker.kaizen_bound_target = d
				attacker.kaizen_bind_seconds = 4.0
				fx.ring(hit_pos, Color(attacker.look.glow), 1.0, 0.25, 0.7)
		elif chain_style == "chain_serpent_bind":
			d.add_status("root", 1, 1.4)
			fx.ring(hit_pos, Color(attacker.look.glow), 1.6, 0.30, 0.9)
'''


def load_json(root:Path, rel:str):
    try:return json.loads((root/rel).read_text(encoding='utf-8-sig'))
    except (OSError,ValueError) as e:raise RuntimeError(f'Cannot read {rel}: {e}') from e


def one(source:str, anchor:str, replacement:str, name:str):
    count=source.count(anchor)
    if count!=1:raise RuntimeError(f'{name}: expected 1 patch anchor, found {count}; no files modified.')
    return source.replace(anchor,replacement,1)


def json_bytes(value)->bytes:
    return (json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode('utf-8')


def build(root:Path)->dict[str,bytes]:
    if not (root/'project.godot').is_file():raise RuntimeError('Run inside your Godot project folder containing project.godot.')
    if not (root/'data/browser_zarek_19b.json').is_file():raise RuntimeError('Please install Update 19B (Zarek) before 19C.')
    roster=load_json(root,'data/roster.json')
    attacks=load_json(root,'data/attacks.json')
    stats=load_json(root,'data/stats.json')
    poses=load_json(root,'data/poses.json')
    if not isinstance(roster,list) or not all(isinstance(x,dict) for x in (attacks,stats,poses)):
        raise RuntimeError('Unexpected live data format; existing files are untouched.')
    ids=[str(x.get('id','')) for x in roster]
    if len(set(ids))!=len(ids):raise RuntimeError('Duplicate character IDs in the live roster.')
    if CHAR_ID in ids or CHAR_ID in attacks or KIT in stats or KIT in poses:
        raise RuntimeError('Kaizen or chainblade already exists; refusing to overwrite customized content.')
    if 'garrick' not in attacks or 'greatsword' not in stats or 'greatsword' not in poses:
        raise RuntimeError('Existing Garrick/Greatsword base kit is required.')
    lib=root/'animations/greatsword.tres'
    if not lib.is_file():raise RuntimeError('Missing animations/greatsword.tres')
    # Only add a selectable fighter once complete attacks, poses, stats and model branch exist.
    roster.append({'id':CHAR_ID,'title':'Chainblade Berserker','role':'Berserker - Segmented Sword',
      'desc':'A relentless chainblade duelist: five Dancing Fang cuts, spinning chain attacks and a binding hook.',
      'stats':{'power':5,'speed':3,'range':4,'defense':3},'look':deepcopy(LOOK)})
    stats[KIT]=deepcopy(STATS)
    poses[KIT]=deepcopy(poses['greatsword'])
    moves={}
    for key,values in MOVES.items():
        item=deepcopy(attacks['garrick']['l1'])
        item.update(deepcopy(values))
        item['browser_pose_w']=values['pose_w']
        item['browser_pose_s']=values['pose_s']
        item['pose_w'],item['pose_s']=POSE_ALIASES[key]
        item['id']=key
        item['element']='chain'
        item['type']='melee'
        item['heavy']=bool(values.get('heavy',False))
        item['next']=values.get('next','')
        item['cd']=float(values.get('cd',0))
        item['lunge']=float(values.get('lunge',0))
        item['no_parry']=False
        item['stagger']=False
        item['self_jump']=0
        item['mode']=''
        item['multi_hit']=int(values.get('multi_hit',1))
        if key=='c': item['reach']=3.1 # Gameplay approximation of contracting-radius whirlwind.
        moves[key]=item
    for key,item in moves.items():
        if item['pose_w'] not in poses[KIT] or item['pose_s'] not in poses[KIT]:
            raise RuntimeError(f'Missing pose alias on {key}; refusing incomplete migration.')
    attacks[CHAR_ID]=moves
    outputs={f'data/{name}.json':json_bytes(value) for name,value in [
        ('roster',roster),('stats',stats),('attacks',attacks),('poses',poses)]}
    outputs['animations/chainblade.tres']=lib.read_bytes()
    outputs['data/browser_kaizen_19c.json']=json_bytes({
        'update':VERSION,'character':CHAR_ID,'kit':KIT,
        'sources':['https://github.com/KimmelDevs/Fight-Royale/blob/main/web/src/game/kits.ts','https://github.com/KimmelDevs/Fight-Royale/blob/main/web/src/game/roster.ts'],
        'status':'First playable port, not complete browser parity',
        'included':['five-step Dancing Fang combo','Chainbreaker charged attack','Razor Cyclone multi-hit','Predator Hook bind and X recast pull','Death Spiral multi-hit','Serpent Bind initial grab contact','chainblade model'],
        'remaining':['animated physical chain links','X air hook','hold-to-extend Z','Death Spiral contracting circle and finisher','Serpent Bind Z/X cinematic finishers','bespoke bone animation'],
        'moves':MOVES})
    outputs['reports/kaizen_19c.txt']=(
       'Fight Royale Godot 19C — Kaizen Chainblade Berserker first playable import\n'
       'Five light combo, heavy, Z/X/C/V kit available in Duel vs CPU and CPU vs CPU.\n'
       'X successful contact applies root for 4s; press X again while bound to reel enemy.\n'
       'Z/C have actual multi-hit contact phases through Update 19B.\n'
       'V has initial bind hit; cinematic Z/X finishers are not implemented yet.\n'
       'Spinning chainblade movement steers slightly while using Z/C.\n'
       'Uses models/kaizen.vrm if imported; otherwise the existing model fallback applies.\n'
       'Weapon is a procedural static segmented blade, not a physics chain rig.\n'
       'Original browser CB_* poses use interim greatsword aliases in this stage.\n'
       'No shop, online multiplayer, or extra modes added.\n').encode('utf-8')
    p='scripts/fighter_model.gd'; model=(root/p).read_text(encoding='utf-8')
    model=one(model,'\tmatch kit:\n','\tmatch kit:\n'+WEAPON_CODE,p)
    outputs[p]=model.encode('utf-8')
    p='scripts/fighter.gd'; fighter=(root/p).read_text(encoding='utf-8')
    fighter=one(fighter,'var guard_fatigue := 0\n','var guard_fatigue := 0\n'+FIGHTER_FIELDS,p)
    fighter=one(fighter,'\tfor k in cooldowns: cooldowns[k] = maxf(cooldowns[k] - dt, 0.0)',FIGHTER_TICK+'\tfor k in cooldowns: cooldowns[k] = maxf(cooldowns[k] - dt, 0.0)',p)
    fighter=one(fighter,'func _read_skill(dt: float) -> void:\n','func _read_skill(dt: float) -> void:\n'+FIGHTER_RECAST,p)
    steer='var steer := 1.0 if state == S.IDLE else 0.5 if state == S.BLOCK else 0.4 if state == S.CHARGE else 0.0'
    fighter=one(fighter,steer,
        'var steer := 1.0 if state == S.IDLE else 0.5 if state == S.BLOCK else 0.4 if state == S.CHARGE else 0.35 if kit == "chainblade" and state == S.ATTACK and atk_id in ["z", "c"] else 0.0',p)
    outputs[p]=fighter.encode('utf-8')
    p='scripts/match.gd'; match=(root/p).read_text(encoding='utf-8')
    if '# FRG19B: multi-pass moves' not in match:
        raise RuntimeError('Update 19B multi-hit framework not detected in match.gd; reinstall 19B or send your current project.')
    match=one(match,'\tvar result := d.receive_hit(attacker, a, power)\n',
              '\tvar result := d.receive_hit(attacker, a, power)\n'+MATCH_ON_HIT,p)
    outputs[p]=match.encode('utf-8')
    p='data/weapon_profiles.json'
    if (root/p).is_file():
        weapons=load_json(root,p)
        if KIT in weapons.get('kits',{}):raise RuntimeError('Existing chainblade weapon profile; not overwriting.')
        weapons['kits'][KIT]=deepcopy(weapons['kits'].get('greatsword',{}))
        outputs[p]=json_bytes(weapons)
    p='data/ai_personalities.json'
    if (root/p).is_file():
        personalities=load_json(root,p)
        personalities.setdefault('fighters',{}).setdefault(CHAR_ID,{
           'archetype':'greatsword','range_scale':1.25,'approach_scale':1.18,
           'orbit_scale':.96,'attack_pace':1.05,'skill_pace':1.13,'heavy_scale':1.12})
        outputs[p]=json_bytes(personalities)
    return outputs


def sha(data:bytes|None)->str|None:return hashlib.sha256(data).hexdigest() if data is not None else None

def atom(path:Path,data:bytes):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.frg19c-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def install(root:Path,dry:bool):
    if (root/'data/browser_kaizen_19c.json').is_file():
        print('Update 19C already installed. Kaizen content preserved.')
        return
    targets=build(root)  # preflight every anchor and JSON file before writing
    changes={name:value for name,value in targets.items() if not (root/name).is_file() or (root/name).read_bytes()!=value}
    for name in changes:print('Update:',name)
    if dry:
        print('DRY RUN — no files changed.')
        return
    backup=root.parent/(root.name+'_backups')/('roster_19c_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
    backup.mkdir(parents=True,exist_ok=False)
    manifest={'version':VERSION,'project':str(root),'files':{}}
    for rel,data in changes.items():
        old=(root/rel).read_bytes() if (root/rel).is_file() else None
        manifest['files'][rel]={'before':sha(old),'after':sha(data)}
        if old is not None:
            dest=backup/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(old)
    (backup/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    changed=[]
    try:
        for name,data in changes.items():
            atom(root/name,data);changed.append(name)
    except Exception:
        for name in reversed(changed):
            saved=backup/name
            if saved.is_file():atom(root/name,saved.read_bytes())
            else:(root/name).unlink(missing_ok=True)
        raise
    print('Update 19C installed — Kaizen ready for Godot import/testing. Backup:',backup)

def restore(root:Path,folder:Path):
    manifest=load_json(folder,'manifest.json')
    if manifest.get('project')!=str(root):raise RuntimeError('Backup belongs to a different project.')
    files=manifest['files']
    for name,state in files.items():
        actual=(root/name).read_bytes() if (root/name).is_file() else None
        if sha(actual)!=state['after']:raise RuntimeError(f'File changed since installation: {name}; refusing to overwrite.')
    for name,state in files.items():
        saved=folder/name
        if state['before'] is None:(root/name).unlink(missing_ok=True)
        else:atom(root/name,saved.read_bytes())
    print('Restored',folder)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--restore',type=Path)
    opt=parser.parse_args()
    root=Path.cwd().resolve()
    try:
        if opt.restore:restore(root,opt.restore.expanduser().resolve())
        else:install(root,opt.dry_run)
    except Exception as e:
        print('ERROR:',e,file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
