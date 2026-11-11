#!/usr/bin/env python3
"""Fight Royale Godot Update 19J — Veyr / Venom Reaper, first playable port.

Run from Godot project: python install_19j_veyr.py
Options: --dry-run, --restore PATH
Requires Update 19I. Makes external backups and supports safe re-runs.

Browser source checked 2026-11-10: web/src/game/kits.ts and roster.ts.
First playable: dual sickles, four-hit lights, charged sickle, three-blade
Crimson Execution, Death Feint, Blood Festival, Carrion Sweep, poison,
Bloodlust/Frenzy. Festival's full cinematic scythe choreography, exact
blood-rim behavior and final balance remain for later refinements.
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

VERSION = "19J.1"
ID = "veyr"
LOOK = {
 'name':'Veyr','body':'m','vrm':'veyr','kit':'sickle','element':'venom',
 'outfit':'assassin','style':'short','hat':'none',
 'hair':'#2b2429','hair_shade':'#6c454d','iris_top':'#ab283d',
 'iris_bottom':'#f27366','eye_dark':'#28121e',
 'tunic':'#372b38','band':'#7b2a40','pants':'#211d27',
 'boots':'#28202a','metal':'#b9b2bc','trim':'#c34b56',
 'cape':'#38252f','cape_bottom':'#8d2e47','glow':'#ff465d',
 'shield':'#572735','emblem':'#ff465d'
}
# Source: 2026-11-10 browser main kits.ts, sickle() and bonusSkill(sickle).
# V's exact contact count in the Godot port is 5, independently defendable.
MOVES = {
 'l1':dict(name='Sickle Flick',wind=.085,active=.065,recover=.17,dmg=46,guard=11,reach=1.65,lunge=3.2,knock=.9,stun=.20,next='l2',style='veyr_sickle'),
 'l2':dict(name='Crosscut',wind=.085,active=.065,recover=.17,dmg=50,guard=11,reach=1.65,lunge=3.2,knock=1.1,stun=.21,next='l3',style='veyr_sickle'),
 'l3':dict(name='Rising Carve',wind=.12,active=.07,recover=.22,dmg=57,guard=14,reach=1.70,lunge=3.8,knock=1.4,stun=.23,next='l4',style='veyr_sickle'),
 'l4':dict(name='Crescent Crosscut',wind=.18,active=.09,recover=.38,dmg=72,guard=20,reach=1.80,lunge=3.2,knock=3.0,stun=.36,style='veyr_sickle'),
 'heavy':dict(name='Sickle Execution',wind=.42,active=.10,recover=.54,dmg=100,guard=30,reach=2.05,lunge=4.3,knock=3.0,stun=.40,heavy=True,style='veyr_sickle'),
 'z':dict(name='Crimson Execution',desc='Three curved blood blades. Poison stacks from successful hits.',cd=12.0,type='projectile',wind=.30,active=.05,recover=.54,dmg=45,guard=14,knock=1.8,stun=.22,speed=14,count=3,spread=.58,size=1.2,style='bloodcrescent'),
 'x':dict(name='Death Feint',desc='Brief 0.30s counter. Successful counter crosses behind the attacker.',cd=10.0,type='buff',mode='blood_feint',duration=.30,wind=.08,active=.04,recover=.55,dmg=0,guard=0,style='veyr_feint'),
 'c':dict(name='Blood Festival',desc='8s scythe ring, minor inward rim pressure, stun immunity, +35% light damage and x3 light guard damage; skills locked during festival.',cd=29.0,type='buff',mode='blood_festival',duration=8.0,radius=3.5,wind=.26,active=.05,recover=.24,dmg=0,guard=0,style='veyr_festival'),
 'v':dict(name='Carrion Sweep',desc='Five independent, defendable sickle strikes.',cd=12.0,type='melee',wind=.16,active=.72,recover=.30,dmg=18,guard=5,reach=1.94,lunge=2.2,knock=.25,stun=.10,style='sickle_carrion',multi_hit=5)
}
POSE_MAP = {'l1':'l1','l2':'l2','l3':'l3','l4':'l4','heavy':'heavy','z':'z','x':'x','c':'c','v':'v'}

MODEL = r'''
		"sickle": # FRG19J — one curved short sickle in EACH hand
			for grip in [r, l]:
				var weapon := _pivot(grip, Vector3(0.0, -0.07, 0.02))
				_part(weapon, _cyl(0.024, 0.026, 0.45, 12), _mat(L.band), Vector3(0, 0.12, 0))
				_part(weapon, _box(0.14, 0.045, 0.055), trim, Vector3(0, 0.33, 0))
				var curve := _pivot(weapon, Vector3(0, 0.38, 0))
				_part(curve, _box(0.24, 0.07, 0.035), steel, Vector3(0.10, 0.05, 0), Vector3(0, 0, 0.28))
				_part(curve, _box(0.23, 0.065, 0.031), steel, Vector3(0.29, 0.09, 0), Vector3(0, 0, 0.63))
				_part(curve, _box(0.16, 0.045, 0.027), glow, Vector3(0.42, 0.02, 0), Vector3(0, 0, 1.10))
				_part(curve, _cyl(0.0, 0.036, 0.13, 10), steel, Vector3(0.48, -0.05, 0), Vector3(0, 0, 1.25))
			blade_base = _pivot(r, Vector3(0, 0.29, 0))
			blade_tip = _pivot(r, Vector3(0.48, 0.47, 0))
			cast_point = blade_tip
			shield_node = l
'''
FIELD = r'''
# FRG19J — Veyr's resources are per-fighter and reset when a new Fighter is created.
var veyr_bloodlust := 0.0
var veyr_frenzy_t := 0.0
var veyr_festival_t := 0.0
var veyr_festival_tick := 0.0
var veyr_feint_t := 0.0
var veyr_feint_counter := false
'''
TICK = r'''
	# FRG19J: real simulation time; no buffs continue while spectators pause.
	if kit == "sickle":
		veyr_festival_t = maxf(0.0, veyr_festival_t - dt)
		veyr_feint_t = maxf(0.0, veyr_feint_t - dt)
		veyr_frenzy_t = maxf(0.0, veyr_frenzy_t - dt)
		if veyr_frenzy_t <= 0.0:
			veyr_bloodlust = maxf(0.0, veyr_bloodlust - dt * 1.0)
		if veyr_bloodlust >= 100.0:
			veyr_bloodlust = 0.0
			veyr_frenzy_t = 5.0
		lifesteal = 0.12 if veyr_festival_t > 0.0 else (0.08 if veyr_frenzy_t > 0.0 else 0.0)
'''
EVENT = r'''
	# FRG19J: bloodlust is only earned on landed damaging attacks, never on cast.
	if kit == "sickle" and event_id == "landed_hit":
		veyr_bloodlust = minf(100.0, veyr_bloodlust + 9.0)
'''
SUMMARY = r'''
	if kit == "sickle":
		var label: String = "BLOODLUST %d%%" % int(veyr_bloodlust)
		if veyr_frenzy_t > 0.0: label += " · FRENZY %.1fs" % veyr_frenzy_t
		if veyr_festival_t > 0.0: label += " · FESTIVAL %.1fs" % veyr_festival_t
		return label if summary.is_empty() else label + ", " + summary
'''
ATTACK_BOOST = r'''
	# FRG19J: festival empowers LIGHTS only; no free Frenzy on cast.
	if kit == "sickle" and aid.begins_with("l"):
		if veyr_festival_t > 0.0:
			atk_power *= 1.35
			atk["guard"] = float(atk.get("guard", 0.0)) * 3.0
		if veyr_frenzy_t > 0.0:
			atk_power *= 1.15
'''
COUNTER = r'''
	# FRG19J Death Feint counters only parryable hits; it never prevents
	# genuinely unblockable attacks or invulnerable misses.
	if kit == "sickle" and veyr_feint_t > 0.0 and not bool(a.get("no_parry", false)):
		veyr_feint_t = 0.0
		veyr_feint_counter = true
		return "counter"
'''
NO_STAGGER = r'''
	# Blood Festival grants stun immunity, NOT damage or knockback immunity.
	if kit == "sickle" and veyr_festival_t > 0.0:
		return "crit" if last_crit else "hit"
'''
MATCH_BEATS = r'''
# FRG19J Carrion Sweep: five distinct contact frames; ordinary blocks/parries/clashes.
func _veyr_schedule_beats(f: Fighter, a: Dictionary) -> void:
	var count: int = int(a.get("multi_hit", 1))
	if count <= 1 or not f.active_melee(): return
	var serial: int = f.swing_serial
	var round_id: int = _round
	var span: float = float(a.get("active", 0.0)) * f.attack_time_multiplier()
	for beat in range(1, count):
		var wait_time: float = span * float(beat) / float(count)
		later(wait_time, func(): _veyr_beat(f, a, serial, round_id, beat))

func _veyr_beat(f: Fighter, a: Dictionary, serial: int, round_id: int, beat: int) -> void:
	if round_over or _round != round_id or not is_instance_valid(f) or f.is_down(): return
	if f.swing_serial != serial or not f.active_melee(): return
	_melee(f, a, beat)

# A lightweight, dodgeable scythe perimeter around Veyr. First-port visual
# approximation, not the browser's final cinematic scythe ring choreography.
func _veyr_step_festivals(dt: float) -> void:
	if dt <= 0.0 or round_over: return
	for f in fighters:
		if not is_instance_valid(f) or f.is_down() or f.kit != "sickle" or f.veyr_festival_t <= 0.0:
			continue
		f.veyr_festival_tick -= dt
		if f.veyr_festival_tick > 0.0: continue
		f.veyr_festival_tick = 0.65
		fx.ring(f.position, Color("#e94468"), 3.5, 0.35, 0.55)
		for d in enemies_of(f):
			var delta: Vector3 = d.position - f.position
			delta.y = 0.0
			var distance: float = delta.length()
			if distance < 2.65 or distance > 3.85: continue
			var rim: Dictionary = f.attacks.l1.duplicate(true)
			rim["id"] = "festival_rim"
			rim["dmg"] = 16.0
			rim["guard"] = 10.0
			rim["knock"] = 0.0
			rim["stun"] = 0.12
			rim["apply_status"] = ""
			apply_hit(f, d, rim, f.dmg_mult, d.chest(), delta.normalized(), false)
			if not d.is_down():
				var pull: Vector3 = -delta.normalized() * 0.25
				d.position += pull
'''
BUFF = r'''
		"blood_feint":
			f.veyr_feint_t = float(a.get("duration", 0.30))
			f.veyr_feint_counter = false
			fx.flash(f.chest(), Color("#ff5577"), 0.45, 0.18, 0.8)
		"blood_festival":
			f.veyr_festival_t = float(a.get("duration", 8.0))
			f.veyr_festival_tick = 0.38
			if f.opponent != null and not f.opponent.is_down():
				var away: Vector3 = f.position - f.opponent.position
				away.y = 0.0
				if away.length_squared() < 0.001: away = Vector3.RIGHT
				f.teleport(f.opponent.position + away.normalized() * 1.75)
			fx.ring(f.position, Color("#f34669"), 3.5, 0.4, 0.85)
			fx.number(f.chest() + Vector3(0, 0.8, 0), "BLOOD FESTIVAL", Color("#ff9daf"), 1.2)
'''
COUNTER_RESOLVE = r'''
			if d.kit == "sickle" and d.veyr_feint_counter:
				d.veyr_feint_counter = false
				fx.number(d.chest() + Vector3(0, 0.5, 0), "DEATH FEINT!", Color("#ff849d"), 0.9)
				if attacker is Fighter and not attacker.is_down():
					d.teleport(attacker.position - attacker.forward() * 1.3)
					var riposte: Dictionary = d.attacks.heavy.duplicate(true)
					riposte["dmg"] = 145.0
					riposte["knock"] = 2.2
					riposte["stun"] = 0.40
					apply_hit(d, attacker, riposte, d.dmg_mult, attacker.chest(), d.forward(), false)
			elif d.kit == "hammer" and d.nesa_counter_pending:
'''
SHAPE = r'''
		"bloodcrescent":
			var crescent := BoxMesh.new()
			crescent.size = Vector3(0.46, 0.11, 0.25) * size
			return crescent
'''

def load_json(root:Path,relative:str):
    try:return json.loads((root/relative).read_text('utf-8-sig'))
    except (OSError,ValueError) as e:raise RuntimeError(f'Cannot read {relative}: {e}') from e

def json_bytes(d):return (json.dumps(d,indent=2,ensure_ascii=False)+'\n').encode('utf-8')

def replace_once(source:str,anchor:str,replacement:str,path:str):
    count=source.count(anchor)
    if count != 1: raise RuntimeError(f'{path}: expected exactly one anchor {anchor[:70]!r}; found {count}. No files changed.')
    return source.replace(anchor,replacement,1)

def build(root:Path)->dict[str,bytes]:
    if not (root/'project.godot').is_file(): raise RuntimeError('Run in the folder containing project.godot')
    if not (root/'data/browser_renji_19i.json').is_file(): raise RuntimeError('Install Update 19I first')
    roster=load_json(root,'data/roster.json')
    attacks=load_json(root,'data/attacks.json')
    stats=load_json(root,'data/stats.json')
    poses=load_json(root,'data/poses.json')
    if not isinstance(roster,list) or not all(isinstance(x,dict) for x in (attacks,stats,poses)):
        raise RuntimeError('Unexpected character database layout')
    if ID in [x.get('id') for x in roster] or ID in attacks or 'sickle' in stats:
        raise RuntimeError('Veyr or sickle kit already exists; refusing to replace existing content')
    if len({x.get('id') for x in roster}) != len(roster):
        raise RuntimeError('Duplicate roster IDs')
    if not all(x in attacks for x in ('nyx','renji')) or 'assassin' not in poses or 'assassin' not in stats:
        raise RuntimeError('Required fighter/pose templates missing')
    ani=root/'animations/assassin.tres'
    if not ani.is_file(): raise RuntimeError('Missing animations/assassin.tres')
    roster.append({'id':ID,'title':'Venom Reaper','role':'Assassin - Dual Sickles',
       'desc':'Twin sickle rushdown. Bloodlust fills only on damaging hits. Blood Festival summons an orbiting perimeter, blocks special skills, boosts lights and ignores stuns.',
       'stats':{'power':4,'speed':5,'range':2,'defense':1},'look':deepcopy(LOOK)})
    stats['sickle']={'hp':1950,'guard':62,'move':4.5,'walk':3.55,'parry':0.20,'jump':8.2}
    poses['sickle']=deepcopy(poses['assassin'])
    # Extend only existing pose names; exact browser keyframes will be migrated later.
    new={}
    for key, data in MOVES.items():
        refkey=key if key in attacks['nyx'] else 'l4'
        base=attacks['nyx'].get(refkey)
        if not isinstance(base,dict):raise RuntimeError(f'Nyx template missing: {refkey}')
        atk=deepcopy(base)
        atk.update(deepcopy(data));atk['id']=key;atk['element']='venom'
        atk['next']=data.get('next','');atk['type']=data.get('type','melee')
        atk['heavy']=bool(data.get('heavy',False));atk['cd']=float(data.get('cd',0.0))
        atk['mode']=data.get('mode','');atk['duration']=float(data.get('duration',0.0))
        atk['multi_hit']=int(data.get('multi_hit',1))
        atk['self_jump']=0.0;atk['at']='self' if atk['type']=='buff' else 'target'
        atk['apply_status']='poison' if key in ['l1','l2','l3','l4','heavy','z','v'] else ''
        atk['status_duration']=5.0
        atk['status_stacks']=1
        atk['status_chance']=1.0
        if key == 'z':
            atk['radius']=0.0; atk['pierce']=False
        # Match keys to an existing animation pose; be explicit about approximations.
        for pose_key in ('pose_w','pose_s'):
            if atk[pose_key] not in poses['sickle']:
                raise RuntimeError(f'Missing Veyr pose {atk[pose_key]} in assassin animation')
        new[key]=atk
    attacks[ID]=new
    result={
       'data/roster.json':json_bytes(roster),'data/attacks.json':json_bytes(attacks),
       'data/stats.json':json_bytes(stats),'data/poses.json':json_bytes(poses),
       'animations/sickle.tres':ani.read_bytes(),
    }
    path='scripts/fighter_model.gd';src=(root/path).read_text('utf-8')
    # Asset resolution: use veyr.vrm when available; else Gale (browser placeholder), then Vesper.
    anchor='\tvar standin: String = str(FALLBACK.get(look.get("body", "f"), "ember"))'
    src=replace_once(src,anchor,
        '\tif requested == "veyr":\n\t\tfor alternate in ["gale", "vesper"]:\n\t\t\tif not candidate_ids.has(alternate): candidate_ids.append(alternate)\n'+anchor,path)
    src=replace_once(src,'\t\t"tonfa":',MODEL+'\t\t"tonfa":',path)
    result[path]=src.encode('utf-8')
    path='scripts/fighter.gd';src=(root/path).read_text('utf-8')
    src=replace_once(src,'var renji_reflection_t := 0.0',FIELD+'var renji_reflection_t := 0.0',path)
    src=replace_once(src,'\t# FRG19I reflection decays in match-time;',TICK+'\t# FRG19I reflection decays in match-time;',path)
    src=replace_once(src,'\tif kit == "tonfa" and event_id == "parried":',EVENT+'\tif kit == "tonfa" and event_id == "parried":',path)
    src=replace_once(src,'\tif kit == "tonfa":\n\t\tvar tag:',SUMMARY+'\tif kit == "tonfa":\n\t\tvar tag:',path)
    # Clear queued skills even while festival is active; no accidental cast on expiration.
    src=replace_once(src,'func _read_skill(dt: float) -> void:\n',
        'func _read_skill(dt: float) -> void:\n'
        '\tif kit == "sickle" and veyr_festival_t > 0.0:\n'
        '\t\tin_skill = ""\n\t\t_queued_skill = ""\n\t\t_queued_skill_t = 0.0\n\t\treturn\n',path)
    src=replace_once(src,'\tatk = attacks[aid].duplicate(true)\n','\tatk = attacks[aid].duplicate(true)\n'+ATTACK_BOOST,path)
    src=replace_once(src,'\tif kit == "tristaff": dmg *= 1.08',
        '\tif kit == "tristaff": dmg *= 1.08',path) # intentional preflight anchor
    src=replace_once(src,'\tif counter_t > 0.0: counter_t = 0.0; return "counter"\n',
        '\tif counter_t > 0.0: counter_t = 0.0; return "counter"\n'+COUNTER,path)
    src=replace_once(src,'\tif hp <= 0.0: _ko(); return "ko"\n\t# One stun per skill use;',
        '\tif hp <= 0.0: _ko(); return "ko"\n'+NO_STAGGER+'\t# One stun per skill use;',path)
    # Guard fatigue + frenzy attack speed both affect actual state durations.
    src=replace_once(src,'\treturn (1.0 / maxf(1.0 - 0.02 * float(guard_fatigue), 0.5)) * status_runtime.attack_time_multiplier()',
        '\tvar veyr_frenzy_speed: float = 1.25 if kit == "sickle" and veyr_frenzy_t > 0.0 else 1.0\n'
        '\treturn (1.0 / maxf(1.0 - 0.02 * float(guard_fatigue), 0.5)) * status_runtime.attack_time_multiplier() / veyr_frenzy_speed',path)
    result[path]=src.encode('utf-8')
    path='scripts/match.gd';src=(root/path).read_text('utf-8')
    src=replace_once(src,'\tif f.kit == "tonfa" and String(a.get("type", "")) == "melee":',
       '\tif f.kit == "sickle" and String(a.get("type", "")) == "melee": _veyr_schedule_beats(f, a)\n'
       '\tif f.kit == "tonfa" and String(a.get("type", "")) == "melee":',path)
    src=replace_once(src,'func _renji_schedule_beats(f: Fighter, a: Dictionary) -> void:\n',
       MATCH_BEATS+'\nfunc _renji_schedule_beats(f: Fighter, a: Dictionary) -> void:\n',path)
    src=replace_once(src,'\t_nythera_step_wells(dt)\n',
       '\t_nythera_step_wells(dt)\n\t_veyr_step_festivals(dt)\n',path)
    src=replace_once(src,'\t\t"renji_reflection":',BUFF+'\t\t"renji_reflection":',path)
    src=replace_once(src,'\t\t\tif d.kit == "hammer" and d.nesa_counter_pending:',COUNTER_RESOLVE[:-1],path)
    src=replace_once(src,'\t\t"arrow":\n',SHAPE+'\t\t"arrow":\n',path)
    result[path]=src.encode('utf-8')
    ai_path='data/ai_personalities.json'
    if (root/ai_path).is_file():
        personalities=load_json(root,ai_path)
        if not isinstance(personalities,dict) or not isinstance(personalities.get('fighters'),dict):
            raise RuntimeError('Unexpected AI profile format')
        personalities['fighters'][ID]={'archetype':'assassin','attack_pace':1.22,
            'skill_pace':1.15,'approach_scale':1.19,'orbit_scale':1.29,'parry_scale':1.05}
        result[ai_path]=json_bytes(personalities)
    result['data/browser_veyr_19j.json']=json_bytes({
       'version':VERSION,'character':ID,
       'browser_sources':['https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts',
                           'https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/roster.ts'],
       'status':'FIRST PLAYABLE PORT — FULL BROWSER VFX, BLOODLUST BALANCE, AND CHOREOGRAPHY STILL PENDING',
       'implemented':['dual procedural sickles','four basic lights and heavy','three projectile Crimson Execution',
                      'short Death Feint counter','eight-second Blood Festival perimeter',
                      'stun immunity but normal damage during Festival','Festival light-damage and guard buffs',
                      'five-hit defendable Carrion Sweep','landed-hit Bloodlust accumulation, decay and Frenzy',
                      'poison through existing status runtime'],
       'pending':['exact browser sickle choreography','final cinematic orbiting sickle geometry',
                  'perimeter timing and Bloodlust/Frenzy balance parity','Godot engine runtime validation']})
    result['reports/veyr_19j.txt']=(
       '19J — Veyr / Venom Reaper\n'
       'Dual sickles (kit: sickle). Dedicated models/veyr.vrm preferred, then Gale/Vesper stand-ins.\n'
       'Z Crimson Execution: 3 blood projectiles. X Death Feint: 0.30s counter.\n'
       'C Blood Festival: 8s +35% light dmg, x3 light guard dmg, stun immunity, skill lock.\n'
       'V Carrion Sweep: five separate melee collision checks.\n'
       'Bloodlust fills on confirmed hits, decays slowly; poison status uses existing rules.\n'
       'Full choreography and exact browser balance are refinement work.\n').encode('utf-8')
    return result

def digest(data:bytes|None)->str|None:
    return hashlib.sha256(data).hexdigest() if data is not None else None

def atomic(path:Path,blob:bytes)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.frg19j-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:out.write(blob);out.flush();os.fsync(out.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def install(root:Path,dry_run:bool)->None:
    if (root/'data/browser_veyr_19j.json').is_file():
        print('Update 19J already installed; no changes');return
    planned=build(root)
    changed={rel:b for rel,b in planned.items() if not (root/rel).is_file() or (root/rel).read_bytes()!=b}
    for rel in changed:print('Update:',rel)
    if dry_run:print('Dry run OK; no files changed');return
    folder=root.parent/(root.name+'_backups')/('veyr_19j_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
    folder.mkdir(parents=True,exist_ok=False)
    manifest={'version':VERSION,'project':str(root),'files':{}}
    for rel,new in changed.items():
        old=(root/rel).read_bytes() if (root/rel).is_file() else None
        manifest['files'][rel]={'before':digest(old),'after':digest(new)}
        if old is not None:
            target=folder/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(old)
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    done=[]
    try:
        for rel,blob in changed.items():atomic(root/rel,blob);done.append(rel)
    except BaseException:
        for rel in reversed(done):
            old=folder/rel
            if old.is_file():atomic(root/rel,old.read_bytes())
            else:(root/rel).unlink(missing_ok=True)
        raise
    print('Installed Update 19J (Veyr). Backup:',folder)

def restore(root:Path,folder:Path)->None:
    manifest=load_json(folder,'manifest.json')
    if manifest.get('project')!=str(root):raise RuntimeError('Backup belongs to another project')
    for rel,meta in manifest.get('files',{}).items():
        current=(root/rel).read_bytes() if (root/rel).is_file() else None
        if digest(current)!=meta.get('after'):raise RuntimeError('File changed since installation: '+rel)
    for rel,meta in manifest['files'].items():
        old=folder/rel
        if meta['before'] is None:(root/rel).unlink(missing_ok=True)
        else:atomic(root/rel,old.read_bytes())
    print('Restored:',folder)

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--restore',type=Path)
    args=p.parse_args();root=Path.cwd().resolve()
    try:
        if args.restore:restore(root,args.restore.expanduser().resolve())
        else:install(root,args.dry_run)
    except Exception as error:
        print('ERROR:',error,file=sys.stderr);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
