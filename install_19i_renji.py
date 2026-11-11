#!/usr/bin/env python3
"""Fight Royale Godot 19I — Renji, The Counter Fist (first playable port).

Run: python install_19i_renji.py
Options: --dry-run, --restore BACKUP_DIRECTORY
Requires 19H. Safe to rerun; preserves unrelated VRMs, audio and player poses.

Renji: close-range five-hit combo, heavy, seven-contact Z, 15-second
Iron Reflection automatic perfect parry, two-contact C, eight-contact V,
Read stacks on true parries and a three-Read ultimate bonus. All strikes go
through the existing melee pipeline; none are fake ranged slashes.

Pending refinement: individual directional counter choreography, exact unique
VRM tonfa poses, extendable/hook transformations and final browser balance.
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

VERSION = '19I.1'
CHARACTER = 'renji'
LOOK = {
    'name':'Renji','body':'m','vrm':'aster','kit':'tonfa','element':'dark',
    'outfit':'martial','style':'short','hat':'none','hair':'#FFD438','hair_shade':'#BB850E',
    'iris_top':'#EDAE2F','iris_bottom':'#FFE27F','eye_dark':'#51350A',
    'tunic':'#19252E','band':'#F6BF40','pants':'#17212C','boots':'#1B242D',
    'metal':'#9BA6B1','trim':'#EFC755','cape':'#171123','cape_bottom':'#34204E',
    'glow':'#9452D8','shield':'#1B1530','emblem':'#C49BFF'
}
# Browser values from kits.ts tonfaMoves and bonusSkill. Timings are first-port,
# multi-hit contacts are separately defended using the existing melee system.
MOVES = {
 'l1':dict(name='Guard-Line Jab',wind=.095,active=.075,recover=.13,dmg=41,guard=12,reach=1.76,lunge=2.1,knock=.32,stun=.14,style='renji_tonfa',next='l2'),
 'l2':dict(name='Reverse-Grip Snap',wind=.105,active=.075,recover=.14,dmg=45,guard=13,reach=1.79,lunge=2.,knock=.42,stun=.15,style='renji_tonfa',next='l3'),
 'l3':dict(name='Shoulder Elbow',wind=.12,active=.075,recover=.15,dmg=49,guard=14,reach=1.70,lunge=1.7,knock=.55,stun=.18,style='renji_elbow',next='l4'),
 'l4':dict(name='Intercepting Knee',wind=.14,active=.085,recover=.17,dmg=54,guard=16,reach=1.73,lunge=1.6,knock=.72,stun=.19,style='renji_knee',next='l5'),
 'l5':dict(name='Cross-Tonfa Verdict',wind=.17,active=.095,recover=.31,dmg=89,guard=26,reach=1.89,lunge=1.7,knock=3.1,stun=.32,style='renji_tonfa'),
 'heavy':dict(name='Guard-Crushing Backfist',wind=.31,active=.12,recover=.52,dmg=152,guard=47,reach=1.91,lunge=1.2,knock=4.6,stun=.43,heavy=True,style='renji_tonfa'),
 'z':dict(name='Hundred Fangs: Hollow Impact',desc='Seven individually defendable blunt tonfa, elbow and knee impacts.',cd=9.,wind=.18,active=1.02,recover=.45,dmg=25,guard=9,reach=1.98,lunge=2.5,knock=.4,stun=.11,style='renji_hundred',multi_hit=7),
 'x':dict(name='Iron Reflection: Eclipse Guard',desc='For 15s, normal guard is disabled and incoming parryable hits are automatically perfect-parried.',cd=30.,type='buff',mode='renji_reflection',duration=15.,wind=.08,active=.05,recover=.19,dmg=0,guard=0,reach=0,lunge=0,knock=0,stun=0,style='renji_reflection'),
 'c':dict(name='Blindside Step: Breaker Pivot',desc='Two timed grounded tonfa/elbow contacts; no ranged phantom hit.',cd=12.,wind=.18,active=.46,recover=.35,dmg=52,guard=18,reach=2.03,lunge=3.65,knock=1.3,stun=.19,style='renji_blindside',multi_hit=2),
 'v':dict(name='Final Verdict: Eightfold',desc='Eight separate blunt melee contacts. With three Reads, unleash a ninth impact.',cd=43.,wind=.34,active=1.72,recover=.68,dmg=35,guard=12,reach=2.08,lunge=1.8,knock=.50,stun=.15,style='renji_eightfold',multi_hit=8)
}
# First-port poses use the installed knuckles animation library, not a fake
# claim that the exact browser procedural tonfa choreography is reproduced.
POSE_FROM = {'l1':'l1','l2':'l2','l3':'l3','l4':'l4','l5':'l5',
             'heavy':'heavy','z':'z','x':'x','c':'c','v':'v'}

TONFA_MODEL = r'''
		"tonfa": # FRG19I — one blunt offset-grip tonfa on each forearm (no blades)
			for grip in [r, l]:
				var staff := _pivot(grip, Vector3(0.0, -0.11, -0.06))
				# Main shaft projects along forearm; the short perpendicular handle stays in palm.
				_part(staff, _cyl(0.035, 0.041, 0.55, 12), _mat(L.metal, true), Vector3(0.0, 0.23, 0.0))
				_part(staff, _cyl(0.041, 0.041, 0.12, 12), trim, Vector3(0.0, 0.47, 0.0))
				_part(staff, _cyl(0.032, 0.032, 0.24, 12), _mat(L.band), Vector3(0.0, 0.10, -0.10), Vector3(PI * 0.5, 0.0, 0.0))
				_part(staff, _box(0.075, 0.035, 0.075), glow, Vector3(0.0, 0.52, 0.0))
			blade_base = _pivot(r, Vector3(0.0, 0.02, 0.0))
			blade_tip = _pivot(r, Vector3(0.0, 0.40, 0.0))
			cast_point = blade_tip
			shield_node = l
'''
FIGHTER_FIELDS = r'''
# FRG19I — Renji: Reads only from confirmed parries; reflection only auto-parries
# attacks the ordinary parry system would allow.
var renji_reflection_t := 0.0
var renji_reads := 0
var renji_read_timer := 0.0
'''
FIGHTER_TICK = r'''
	# FRG19I reflection decays in match-time; cannot block manually while active.
	if kit == "tonfa":
		renji_reflection_t = maxf(0.0, renji_reflection_t - dt)
		if renji_reflection_t > 0.0:
			in_block = false
		if renji_read_timer > 0.0:
			renji_read_timer = maxf(0.0, renji_read_timer - dt)
			if renji_read_timer <= 0.0: renji_reads = 0
'''
FIGHTER_READ = r'''
	if kit == "tonfa" and event_id == "parried":
		renji_reads = mini(3, renji_reads + 1)
		renji_read_timer = 30.0
'''
FIGHTER_AUTO = r'''
	# FRG19I: Iron Reflection replaces held guard with automatic genuine parries.
	# Unparryable moves still hit normally; normal parry hooks grant the Read.
	if kit == "tonfa" and renji_reflection_t > 0.0 and not bool(a.get("no_parry", false)):
		guard = minf(guard + max_guard * 0.10, max_guard)
		if model != null: model.flash(Color("#d4b0ff"), 0.14)
		return "parry"
'''
FIGHTER_READ_V = r'''
	# FRG19I: the third confirmed Read upgrades the next Eightfold finisher.
	if kit == "tonfa" and aid == "v" and renji_reads >= 3:
		atk["multi_hit"] = int(atk.get("multi_hit", 8)) + 1
		atk_power *= 1.20
		renji_reads = 0
		renji_read_timer = 0.0
'''
MATCH_MULTI = r'''
# FRG19I — each tonfa beat is separately blockable, parryable, clashable and dodgeable.
# Never invoke a magical slash; all contacts share ordinary melee collision.
func _renji_schedule_beats(f: Fighter, a: Dictionary) -> void:
	var count: int = int(a.get("multi_hit", 1))
	if count <= 1 or not f.active_melee(): return
	var serial: int = f.swing_serial
	var round_id: int = _round
	var span: float = float(a.get("active", 0.0)) * f.attack_time_multiplier()
	for beat in range(1, count):
		var wait_time: float = span * float(beat) / float(count)
		later(wait_time, func():
			_renji_beat(f, a, serial, round_id, beat))

func _renji_beat(f: Fighter, a: Dictionary, serial: int, round_id: int, beat: int) -> void:
	if round_over or _round != round_id or not is_instance_valid(f) or f.is_down(): return
	if f.swing_serial != serial or not f.active_melee(): return
	_melee(f, a, beat)
'''
BUFF = r'''
		"renji_reflection": # FRG19I — no invulnerability to truly unparryable hits
			f.renji_reflection_t = float(a.get("duration", 15.0))
			fx.ring(f.position, Color("#bc8cff"), 1.4, 0.3, 0.8)
			fx.number(f.chest() + Vector3(0, 0.7, 0), "IRON REFLECTION", Color("#e4c8ff"), 0.8)
'''


def json_file(root: Path, rel: str):
    try: return json.loads((root/rel).read_text(encoding='utf-8-sig'))
    except (OSError,ValueError) as e: raise RuntimeError(f'Cannot read {rel}: {e}') from e

def jbytes(obj): return (json.dumps(obj,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
def once(src:str, anchor:str, replacement:str, path:str)->str:
    n=src.count(anchor)
    if n!=1: raise RuntimeError(f'{path}: expected 1 occurrence of {anchor[:75]!r}, found {n}; no files changed')
    return src.replace(anchor,replacement,1)

def build(root:Path)->dict[str,bytes]:
    if not (root/'project.godot').is_file():
        raise RuntimeError('Run in the Godot project folder containing project.godot')
    if not (root/'data/browser_nythera_19h.json').is_file():
        raise RuntimeError('Install Update 19H first')
    roster=json_file(root,'data/roster.json')
    attacks=json_file(root,'data/attacks.json')
    stats=json_file(root,'data/stats.json')
    poses=json_file(root,'data/poses.json')
    if not isinstance(roster,list) or not all(isinstance(d,dict) for d in (attacks,stats,poses)):
        raise RuntimeError('Unexpected fighter database structure')
    ids=[d.get('id') for d in roster]
    if len(ids)!=len(set(ids)) or CHARACTER in ids or CHARACTER in attacks or 'tonfa' in stats:
        raise RuntimeError('Renji already present or tonfa kit occupied; refusing to overwrite')
    if not all(x in attacks for x in ('rook','nythera')) or 'knuckles' not in poses or 'knuckles' not in stats:
        raise RuntimeError('Missing prior fighter and animation templates')
    anim=root/'animations/knuckles.tres'
    if not anim.is_file(): raise RuntimeError('Missing animations/knuckles.tres')
    roster.append({
        'id':CHARACTER,'title':'The Counter Fist','role':'Martial Artist - Twin Tonfas',
        'desc':'Close-range blunt counter fighter. Iron Reflection perfect-parries incoming parryable attacks. Three Reads empower Eightfold.',
        'stats':{'power':4,'speed':5,'range':1,'defense':3},'look':deepcopy(LOOK)})
    stats['tonfa']={'hp':2100,'guard':78,'move':4.30,'walk':3.45,'parry':.21,'jump':8.1}
    poses['tonfa']=deepcopy(poses['knuckles'])
    new={}
    for key, data in MOVES.items():
        reference=attacks['rook'].get(POSE_FROM[key])
        if not isinstance(reference,dict): raise RuntimeError(f'Rook move {key} unavailable')
        atk=deepcopy(reference)
        atk.update(deepcopy(data))
        atk['id']=key
        atk['element']='dark'
        atk['next']=data.get('next','')
        atk['type']=data.get('type','melee')
        atk['heavy']=bool(data.get('heavy',False))
        atk['cd']=float(data.get('cd',0.0))
        atk['multi_hit']=int(data.get('multi_hit',1))
        atk['mode']=data.get('mode','')
        atk['duration']=float(data.get('duration',0.0))
        # Explicitly eliminate inherited projectile / jumping behavior from Rook.
        atk['self_jump']=0.0
        atk['at']='self'
        atk['pose_w']=reference['pose_w']
        atk['pose_s']=reference['pose_s']
        for which in ('pose_w','pose_s'):
            if atk[which] not in poses['tonfa']:
                raise RuntimeError('Missing inherited tonfa pose: '+atk[which])
        new[key]=atk
    attacks[CHARACTER]=new
    result={
        'data/roster.json':jbytes(roster),'data/attacks.json':jbytes(attacks),
        'data/stats.json':jbytes(stats),'data/poses.json':jbytes(poses),
        'animations/tonfa.tres':anim.read_bytes(),
    }
    path='scripts/fighter_model.gd'; src=(root/path).read_text('utf-8')
    src=once(src,'\t\t"knuckles":',TONFA_MODEL+'\t\t"knuckles":',path)
    result[path]=src.encode()

    path='scripts/fighter.gd'; src=(root/path).read_text('utf-8')
    src=once(src,'var in_mode_switch := false',FIGHTER_FIELDS+'var in_mode_switch := false',path)
    src=once(src,'\tif kit == "tristaff":\n\t\tzephyr_mode_cooldown', FIGHTER_TICK+'\tif kit == "tristaff":\n\t\tzephyr_mode_cooldown',path)
    src=once(src,'\tif status_runtime != null:\n\t\tstatus_runtime.on_event(event_id, other)',FIGHTER_READ+'\tif status_runtime != null:\n\t\tstatus_runtime.on_event(event_id, other)',path)
    src=once(src,'\tif kit == "tristaff":\n\t\tvar tag:',
        '\tif kit == "tonfa":\n\t\tvar tag: String = "READ x%d" % renji_reads\n'
        '\t\tif renji_reflection_t > 0.0: tag += " · REFLECT %.1fs" % renji_reflection_t\n'
        '\t\treturn tag if summary.is_empty() else tag + ", " + summary\n'
        '\tif kit == "tristaff":\n\t\tvar tag:',path)
    src=once(src,'\tatk = attacks[aid].duplicate(true)\n',
             '\tatk = attacks[aid].duplicate(true)\n'+FIGHTER_READ_V,path)
    src=once(src,'\tif counter_t > 0.0: counter_t = 0.0; return "counter"\n',
             '\tif counter_t > 0.0: counter_t = 0.0; return "counter"\n'+FIGHTER_AUTO,path)
    result[path]=src.encode()

    path='scripts/match.gd'; src=(root/path).read_text('utf-8')
    src=once(src,'\tif f.kit == "tristaff" and String(a.get("type", "")) == "melee":\n',
             '\tif f.kit == "tonfa" and String(a.get("type", "")) == "melee": _renji_schedule_beats(f, a)\n'
             '\tif f.kit == "tristaff" and String(a.get("type", "")) == "melee":\n',path)
    src=once(src,'func _zephyr_schedule_beats(f: Fighter, a: Dictionary) -> void:\n',
             MATCH_MULTI+'\nfunc _zephyr_schedule_beats(f: Fighter, a: Dictionary) -> void:\n',path)
    src=once(src,'\t\t"frost_aegis":\n',BUFF+'\t\t"frost_aegis":\n',path)
    # Tonfa is a blunt weapon: suppress blade ribbons even though the shaft has
    # two geometric reference points for impact positions.
    src=once(src,'\tif f.model.blade_base and f.model.blade_tip:\n',
             '\tif f.kit != "tonfa" and f.model.blade_base and f.model.blade_tip:\n',path)
    result[path]=src.encode()

    apath='data/ai_personalities.json'
    if (root/apath).is_file():
        ai=json_file(root,apath)
        if not isinstance(ai,dict) or not isinstance(ai.get('fighters'),dict):
            raise RuntimeError('Unexpected AI personalities JSON')
        ai['fighters']['renji']={'archetype':'knuckles','attack_pace':1.19,
            'skill_pace':1.11,'approach_scale':1.17,'orbit_scale':1.22,'parry_scale':1.29}
        result[apath]=jbytes(ai)
    result['data/browser_renji_19i.json']=jbytes({
        'version':VERSION,'character':CHARACTER,'browser_reference':'https://github.com/KimmelDevs/Fight-Royale/blob/main/web/src/game/kits.ts',
        'status':'FIRST PLAYABLE PORT — DIRECTIONAL COUNTER AND CHOREOGRAPHY REFINEMENT PENDING',
        'implemented':['five blunt-hit lights and heavy','7-contact Hundred Fangs','Iron Reflection 15s automatic parry on parryable hits',
        'two-contact Blindside Step','eightfold V plus ninth hit at 3 Reads','Read stacks only on confirmed parries',
        'procedural twin tonfas with no blade trail'],
        'pending':['true directional parry-counter choreography','three-Read finisher animation variations',
                   'separate elbow and knee VRM poses','tonfa extension, guard-ring and hook transformations',
                   'Godot engine and gameplay validation']})
    result['reports/renji_19i.txt']=(
        'Update 19I - Renji: The Counter Fist (first playable port)\n'
        'Model uses models/aster.vrm until a dedicated renji.vrm is provided; preserve any existing assets.\n'
        'Z: Hundred Fangs (7 real contact checks); X: Iron Reflection (15s auto parries);\n'
        'C: Blindside Step (2 real contacts); V: Final Verdict: Eightfold (+1 beat at 3 Reads).\n'
        'Read x3 bonus is consumed by V. No sword slash VFX.\n'
        'Custom directional counters, tonfa transformations, dedicated VRM poses and full parity remain for refinement.\n').encode('utf-8')
    return result

def digest(b:bytes|None)->str|None:
    return hashlib.sha256(b).hexdigest() if b is not None else None

def atomic(path:Path,payload:bytes):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.frg19i-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(payload);out.flush();os.fsync(out.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def install(root:Path,dry:bool):
    if (root/'data/browser_renji_19i.json').is_file():
        print('Update 19I already installed; no changes');return
    planned=build(root)
    changed={rel:data for rel,data in planned.items() if not (root/rel).is_file() or (root/rel).read_bytes()!=data}
    for rel in changed:print('Update:',rel)
    if dry:
        print('Dry run OK; no files changed');return
    folder=root.parent/(root.name+'_backups')/('renji_19i_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
    folder.mkdir(parents=True,exist_ok=False)
    manifest={'version':VERSION,'project':str(root),'files':{}}
    for rel,new in changed.items():
        prev=(root/rel).read_bytes() if (root/rel).is_file() else None
        manifest['files'][rel]={'before':digest(prev),'after':digest(new)}
        if prev is not None:
            saved=folder/rel;saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(prev)
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    done=[]
    try:
        for rel,new in changed.items():atomic(root/rel,new);done.append(rel)
    except BaseException:
        for rel in reversed(done):
            old=folder/rel
            if old.is_file():atomic(root/rel,old.read_bytes())
            else:(root/rel).unlink(missing_ok=True)
        raise
    print('Installed Update 19I (Renji). Backup:',folder)

def restore(root:Path,folder:Path):
    manifest=json_file(folder,'manifest.json')
    if manifest.get('project')!=str(root):raise RuntimeError('Backup belongs to another project')
    for rel,meta in manifest.get('files',{}).items():
        current=(root/rel).read_bytes() if (root/rel).is_file() else None
        if digest(current)!=meta['after']:
            raise RuntimeError('File changed since installation: '+rel)
    for rel,meta in manifest['files'].items():
        old=folder/rel
        if meta['before'] is None:(root/rel).unlink(missing_ok=True)
        else:atomic(root/rel,old.read_bytes())
    print('Restored:',folder)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--restore',type=Path)
    args=p.parse_args();root=Path.cwd().resolve()
    try:
        if args.restore:restore(root,args.restore.expanduser().resolve())
        else:install(root,args.dry_run)
    except Exception as e:
        print('ERROR:',e,file=sys.stderr);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
