#!/usr/bin/env python3
"""Fight Royale Godot Update 19E: Roxy — Snow Puppet Master (first playable port).

Run inside the Godot project: python install_19e_roxy.py
Options: --dry-run, --restore <backup-folder>

Uses Roxy's three skills from the browser's public kits.ts on 2026-11-10:
Z Snowglass Aegis, X Frost Marionette, C Glacier Meteor.
Adds basic frost-shard combo/charged attack, four-shard shield absorption,
4-hit frost freeze trigger, a moving freezing marionette, and a slowing meteor.
Uses mage animation poses and approximate visuals until a refinement pass.
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

VERSION = '19E.1'
LOOK = {
    'name':'Roxy','body':'f','vrm':'roxy','kit':'mage','element':'frost',
    'outfit':'mage','style':'long','hat':'witch','hair':'#e6f5ff',
    'hair_shade':'#8abfe2','iris_top':'#3276af','iris_bottom':'#b4efff',
    'eye_dark':'#163c6a','tunic':'#244b86','band':'#e6f8ff',
    'pants':'#d8eefa','boots':'#25365d','metal':'#bedce7','trim':'#e4faff',
    'cape':'#85bce1','cape_bottom':'#e9fcff','glow':'#9cddff',
    'shield':'#9cddff','emblem':'#e8f8ff'
}
# Numeric values are based on the current public mage(frost) definition.
MOVES = {
    'l1':dict(name='Frost Shard I',type='projectile',wind=.16,active=.05,recover=.26,dmg=43.05,guard=15,knock=1.6,stun=.28,speed=15,size=.82,count=1,spread=0.0,style='frost_shard',pierce=False,next='l2',pose_w='m1_w',pose_s='m1_s'),
    'l2':dict(name='Frost Shard II',type='projectile',wind=.16,active=.05,recover=.28,dmg=47.25,guard=15,knock=1.8,stun=.30,speed=15,size=.82,count=1,spread=0.0,style='frost_shard',pierce=False,next='l3',pose_w='m2_w',pose_s='m2_s'),
    'l3':dict(name='Frost Shard Fan',type='projectile',wind=.24,active=.05,recover=.42,dmg=33.60,guard=14,knock=3.0,stun=.40,speed=15,size=.82,count=3,spread=.22,style='frost_shard',pierce=False,pose_w='m3_w',pose_s='m3_s'),
    'heavy':dict(name='Seeking Frost',type='projectile',wind=.24,active=.05,recover=.55,dmg=42,guard=16,knock=1.2,stun=.16,speed=13.0,size=.85,count=4,spread=.33,style='frost_shard',pierce=False,pose_w='mh_w',pose_s='mh_s'),
    'z':dict(name='Snowglass Aegis',desc='Four ice crystals absorb one damaging hit each, for up to seven seconds.',cd=13,type='buff',mode='frost_aegis',duration=7,wind=.13,active=.05,recover=.25,pose_w='mh_w',pose_s='m3_s'),
    'x':dict(name='Frost Marionette',desc='Summon a snow puppet that rushes its target and freezes on contact.',cd=10,type='snow_puppet',style='freeze',wind=.26,active=.05,recover=.42,dmg=46,guard=20,knock=.7,stun=.08,count=1,speed=4.5,radius=.9,duration=8.5,apply_status='freeze',status_duration=2.0,pose_w='m2_w',pose_s='m2_s'),
    'c':dict(name='Glacier Meteor',desc='Call down an icy meteor on the marked position, slowing on a successful hit.',cd=15,type='strike',style='meteor',wind=.36,active=.05,recover=.65,dmg=160,guard=65,knock=5.5,stun=.65,heavy=True,delay=.85,radius=2.1,apply_status='slow',status_duration=2.0,pose_w='mh_w',pose_s='mh_s')
}

FIGHTER_FIELDS = '''
# FRG19E — Roxy's four shield charges and frost-shard freeze buildup.
var roxy_aegis_charges := 0
var roxy_aegis_t := 0.0
var roxy_frost_stacks := 0
var roxy_freeze_cd := 0.0
'''
FIGHTER_TICK = '''
	# FRG19E - only in-game simulation time advances these timers.
	if roxy_aegis_t > 0.0:
		roxy_aegis_t = maxf(0.0, roxy_aegis_t - dt)
		if roxy_aegis_t <= 0.0:
			roxy_aegis_charges = 0
	roxy_freeze_cd = maxf(0.0, roxy_freeze_cd - dt)
'''
FIGHTER_DEFENSE = '''
	# FRG19E - each genuine incoming hit consumes exactly one snowglass crystal.
	if String(look.get("element", "")) == "frost" and roxy_aegis_t > 0.0 and roxy_aegis_charges > 0:
		roxy_aegis_charges -= 1
		model.flash(Color("#baf3ff"), 0.17)
		return "warded"
'''
# This is confined to Roxy's element, so Ember/Marina/Raven retain their staffs.
MAGE_WEAPON = '''
		"mage":
			if String(L.get("element", "")) == "frost":
				# FRG19E — Roxy's compact floating spellbook instead of a staff.
				var book := _pivot(l, Vector3(-0.16, 0.13, -0.18))
				_part(book, _box(0.30, 0.06, 0.23), _mat(L.metal), Vector3(0, 0, 0))
				_part(book, _box(0.27, 0.065, 0.20), _mat(L.tunic), Vector3(0, 0.032, 0))
				_part(book, _box(0.024, 0.069, 0.23), trim, Vector3(0, 0.03, 0))
				_part(book, _sph(0.04), glow, Vector3(-0.09, 0.09, 0.025))
				var crystal := _pivot(r, Vector3(0.0, 0.17, 0.0))
				_part(crystal, _sph(0.075), glow, Vector3(0, 0.07, 0))
				blade_base = crystal
				blade_tip = _pivot(crystal, Vector3(0, 0.22, 0))
				cast_point = blade_tip
				shield_node = _pivot(l)
			else:
				var s := _pivot(r, Vector3(0, -0.25, 0))
				_part(s, _cyl(0.016, 0.016, 1.5), _mat(L.tunic), Vector3(0, 0.45, 0))
				_part(s, _cyl(0.034, 0.016, 0.08), trim, Vector3(0, 1.22, 0))
				var orb := _pivot(s, Vector3(0, 1.32, 0))
				_part(orb, _sph(0.07), _glow(L.glow))
				_part(orb, TorusMesh.new(), trim, Vector3.ZERO, Vector3(PI / 2, 0, 0), Vector3.ONE * 0.11)
				blade_base = _pivot(s, Vector3(0, 0.9, 0)); blade_tip = orb; cast_point = orb
				shield_node = _pivot(l)
'''
MATCH_FIELDS = '''
# FRG19E — snow puppets live only for their current round.
var _roxy_puppets: Array[Dictionary] = []
'''
MATCH_PUPPETS = '''
# FRG19E — real moving snow-puppet summon, not a fake projectile or a strike.
func _roxy_spawn_puppet(f: Fighter, a: Dictionary) -> void:
	if f.is_down() or f.opponent == null or f.opponent.is_down():
		return
	var puppet := Node3D.new()
	puppet.name = "RoxyFrostMarionette19E"
	add_child(puppet)
	puppet.global_position = f.global_position + f.forward() * 0.85 + Vector3(0.0, 0.28, 0.0)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color("#bbebff")
	mat.roughness = 0.35
	var body := MeshInstance3D.new()
	var body_mesh := SphereMesh.new()
	body_mesh.radius = 0.30
	body_mesh.height = 0.60
	body.mesh = body_mesh
	body.material_override = mat
	puppet.add_child(body)
	var head := MeshInstance3D.new()
	var head_mesh := SphereMesh.new()
	head_mesh.radius = 0.21
	head_mesh.height = 0.42
	head.mesh = head_mesh
	head.material_override = mat
	head.position = Vector3(0.0, 0.38, 0.0)
	puppet.add_child(head)
	var orb := MeshInstance3D.new()
	var orb_mesh := SphereMesh.new()
	orb_mesh.radius = 0.07
	orb_mesh.height = 0.14
	orb.mesh = orb_mesh
	orb.material_override = Fx.unlit(Color("#ecffff"))
	orb.position = Vector3(0.0, 0.67, 0.0)
	puppet.add_child(orb)
	_roxy_puppets.append({"node": puppet, "caster": f, "target": f.opponent, "atk": a.duplicate(true), "power": f.atk_power, "life": float(a.get("duration", 8.5)), "speed": float(a.get("speed", 4.5))})
	fx.flash(puppet.global_position, Color("#a6edff"), 0.4, 0.20, 0.75)

func _roxy_step_puppets(dt: float) -> void:
	if dt <= 0.0 or round_over:
		return
	for record in _roxy_puppets.duplicate():
		var puppet: Node3D = record["node"]
		var caster: Fighter = record["caster"]
		var target: Fighter = record["target"]
		record["life"] = float(record["life"]) - dt
		if not is_instance_valid(puppet) or not is_instance_valid(caster) or not is_instance_valid(target) or caster.is_down() or target.is_down() or float(record["life"]) <= 0.0:
			if is_instance_valid(puppet):
				puppet.queue_free()
			_roxy_puppets.erase(record)
			continue
		var delta_to: Vector3 = target.position - puppet.global_position
		delta_to.y = 0.0
		var distance := delta_to.length()
		if distance > 0.01:
			puppet.global_position += delta_to.normalized() * minf(float(record["speed"]) * dt, distance)
		puppet.rotation.y += dt * 2.3
		if distance <= float(record["atk"].get("radius", 0.9)) + target.radius:
			var hit: Dictionary = record["atk"]
			var direction := delta_to.normalized() if distance > 0.01 else caster.forward()
			apply_hit(caster, target, hit, float(record["power"]), target.chest(), direction, true)
			fx.ring(puppet.global_position, Color("#b7f2ff"), 1.0, 0.32, 0.85)
			puppet.queue_free()
			_roxy_puppets.erase(record)
'''
MATCH_BUFF = '''
		"frost_aegis":
			# FRG19E: four charges for a maximum of seven seconds (no stacking).
			f.roxy_aegis_charges = 4
			f.roxy_aegis_t = float(a.get("duration", 7.0))
			fx.ring(f.position, Color("#a7efff"), 1.5, 0.38, 0.85)
			fx.number(f.chest() + Vector3(0, 0.8, 0), "SNOWGLASS x4", Color("#e1faff"), 1.0)
'''
MATCH_FREEZE = '''
	# FRG19E: four landed frost shards freeze, with a brief re-freeze cooldown.
	if attacker is Fighter and String(attacker.look.get("element", "")) == "frost" and String(a.get("style", "")) == "frost_shard" and result in ["hit", "crit", "ko"]:
		attacker.roxy_frost_stacks = mini(attacker.roxy_frost_stacks + 1, 4)
		if attacker.roxy_frost_stacks >= 4 and attacker.roxy_freeze_cd <= 0.0 and not d.is_down():
			if d.add_status("freeze", 1, 2.0):
				fx.number(d.chest() + Vector3(0, 0.65, 0), "FROZEN!", Color("#a8eeff"), 1.1)
				attacker.roxy_frost_stacks = 0
				attacker.roxy_freeze_cd = 4.0
'''


def read_json(root:Path,name:str):
    try: return json.loads((root/name).read_text(encoding='utf-8-sig'))
    except (OSError,ValueError) as exc: raise RuntimeError(f'Cannot read {name}: {exc}') from exc


def stable_replace(text:str, anchor:str, replacement:str, filename:str)->str:
    count=text.count(anchor)
    if count != 1: raise RuntimeError(f'{filename}: expected one exact patch anchor; found {count}. No files installed.')
    return text.replace(anchor,replacement,1)


def jbytes(data)->bytes:
    return (json.dumps(data,indent=2,ensure_ascii=False)+'\n').encode('utf-8')


def payload_for(root:Path)->dict[str,bytes]:
    if not (root/'project.godot').is_file(): raise RuntimeError('Run from Godot project folder (project.godot must be present).')
    if not (root/'data/browser_nesa_19d.json').is_file(): raise RuntimeError('Install Update 19D (Nesa) before 19E.')
    roster = read_json(root,'data/roster.json')
    stats = read_json(root,'data/stats.json')
    poses = read_json(root,'data/poses.json')
    attacks = read_json(root,'data/attacks.json')
    if not isinstance(roster,list) or not all(isinstance(x,dict) for x in [stats,poses,attacks]):
        raise RuntimeError('Unexpected roster, poses, stats or attacks schema.')
    ids=[x.get('id') for x in roster]
    if len(ids)!=len(set(ids)): raise RuntimeError('Duplicate fighter IDs; cannot safely add Roxy.')
    if 'roxy' in ids or 'roxy' in attacks: raise RuntimeError('Roxy already exists; refusing to overwrite your fighter data.')
    if 'mage' not in poses or 'mage' not in stats or 'raven' not in attacks:
        raise RuntimeError('Missing original mage base poses/stats/Raven attacks.')
    roster.append({'id':'roxy','title':'Snow Puppet Master','role':'Mage - Ice Puppeteer',
        'desc':'Ice shield, freezing snow marionette, frost shards, and an icy meteor.',
        'stats':{'power':4,'speed':3,'range':5,'defense':3}, 'look':deepcopy(LOOK)})
    # Roxy shares the browser mage kit; no duplicate mage stats or animation library.
    base=attacks['raven']['l1']
    mapped={}
    for key,raw in MOVES.items():
        m=deepcopy(base)
        m.update(deepcopy(raw))
        m['id']=key
        m['element']='frost'
        m['next']=raw.get('next','')
        m['type']=raw.get('type','projectile')
        m['heavy']=bool(raw.get('heavy',False))
        m['cd']=float(raw.get('cd',0.0))
        m['apply_status']=str(raw.get('apply_status',''))
        m['status_duration']=float(raw.get('status_duration',-1.0))
        m['status_chance']=1.0
        m['mode']=str(raw.get('mode',''))
        m['no_parry']=False
        if m['pose_w'] not in poses['mage'] or m['pose_s'] not in poses['mage']:
            raise RuntimeError(f'Roxy missing mage pose for {key}')
        mapped[key]=m
    # The current public kit gives Roxy exactly Z / X / C, not V. The internal
    # V entry satisfies existing Fighter.setup's four-key assumption, while
    # Roxy's skill picker hides it. It is NEVER selected for Roxy in normal UI.
    mapped['v']=deepcopy(mapped['c'])
    mapped['v']['id']='v'
    mapped['v']['name']='Unused (Roxy has three skills)'
    attacks['roxy']=mapped
    result={'data/roster.json':jbytes(roster),'data/attacks.json':jbytes(attacks)}
    p='scripts/fighter.gd'; f=(root/p).read_text(encoding='utf-8')
    f=stable_replace(f, 'var nesa_counter_pending := false\n', FIGHTER_FIELDS+'var nesa_counter_pending := false\n',p)
    f=stable_replace(f, '\tward_t = maxf(ward_t - dt, 0.0)\n', '\tward_t = maxf(ward_t - dt, 0.0)\n'+FIGHTER_TICK,p)
    f=stable_replace(f, '\tif ward_t > 0.0: return "warded"\n', FIGHTER_DEFENSE+'\tif ward_t > 0.0: return "warded"\n',p)
    result[p]=f.encode('utf-8')
    p='scripts/fighter_model.gd'; model=(root/p).read_text(encoding='utf-8')
    mage_start='\t\t"mage":\n'
    start=model.find(mage_start)
    end=model.find('\t\t"bow":\n',start)
    if start < 0 or end < start: raise RuntimeError('Missing stable mage/bow weapon branch boundaries.')
    existing=model[start:end]
    if 'var s := _pivot(r, Vector3(0, -0.25, 0))' not in existing or 'var orb := _pivot(s' not in existing:
        raise RuntimeError('Original mage staff has changed: refusing to replace it.')
    model=model[:start]+MAGE_WEAPON+model[end:]
    result[p]=model.encode('utf-8')
    p='scripts/match.gd'; match=(root/p).read_text(encoding='utf-8')
    match=stable_replace(match, 'var _strike_marks: Array = []   # {target, land, id}\n',
                         'var _strike_marks: Array = []   # {target, land, id}\n'+MATCH_FIELDS,p)
    match=stable_replace(match,'\tfighters.clear(); _trails.clear(); _melee_hits.clear(); _frg19b_multi_phase.clear(); _projectiles.clear(); _strike_marks.clear(); _timers.clear()\n',
       '\tfor puppet in _roxy_puppets:\n\t\tif is_instance_valid(puppet["node"]):\n\t\t\tpuppet["node"].queue_free()\n\t_roxy_puppets.clear()\n\tfighters.clear(); _trails.clear(); _melee_hits.clear(); _frg19b_multi_phase.clear(); _projectiles.clear(); _strike_marks.clear(); _timers.clear()\n',p)
    match=stable_replace(match,'\t_update_projectiles(dt)\n\t_blade_light(dt)\n','\t_update_projectiles(dt)\n\t_roxy_step_puppets(dt)\n\t_blade_light(dt)\n',p)
    match=stable_replace(match,'\t\t"buff": _buff(f, a)\n', '\t\t"buff": _buff(f, a)\n\t\t"snow_puppet": _roxy_spawn_puppet(f, a)\n',p)
    match=stable_replace(match,'func _active_melee_contact(f: Fighter) -> void:\n', MATCH_PUPPETS+'\nfunc _active_melee_contact(f: Fighter) -> void:\n',p)
    match=stable_replace(match, '\t\t"ward":\n',MATCH_BUFF+'\t\t"ward":\n',p)
    match=stable_replace(match, '\tvar result := d.receive_hit(attacker, a, power)\n',
                       '\tvar result := d.receive_hit(attacker, a, power)\n'+MATCH_FREEZE,p)
    result[p]=match.encode('utf-8')
    # Roxy's skill picker must not invent a fourth skill that the browser lacks.
    p='scripts/main.gd'; menu=(root/p).read_text(encoding='utf-8')
    menu=stable_replace(menu,'\tfor key in ["z", "x", "c", "v"]:\n\t\t\toptions.add_item("%s: %s" % [key.to_upper(), attacks[key].name])\n',
           '\tvar roxy_keys := ["z", "x", "c"] if fighter.id == "roxy" else ["z", "x", "c", "v"]\n\tfor key in roxy_keys:\n\t\toptions.add_item("%s: %s" % [key.to_upper(), attacks[key].name])\n',p) if False else menu
    # Patch the whole picker block using the actual 3-level indentation.
    needle='''\t\tfor key in ["z", "x", "c", "v"]:
\t\t\toptions.add_item("%s: %s" % [key.to_upper(), attacks[key].name])
\t\toptions.select(["z", "x", "c", "v"].find(arr[slot]))
'''
    replacement='''\t\tvar possible_keys: Array = ["z", "x", "c"] if fighter.id == "roxy" else ["z", "x", "c", "v"]
\t\tfor key in possible_keys:
\t\t\toptions.add_item("%s: %s" % [key.to_upper(), attacks[key].name])
\t\toptions.select(maxi(0, possible_keys.find(arr[slot])))
'''
    menu=stable_replace(menu,needle,replacement,p)
    menu=stable_replace(menu, '\treturn out\n\nfunc show_menu() -> void:\n',
          '\tif Data.character(index).id == "roxy" and out.has("v"):\n\t\treturn ["z", "x", "c"]\n\treturn out\n\nfunc show_menu() -> void:\n',p)
    menu=stable_replace(menu,'Pick three skills per fighter. The fourth skill is freely available to equip.',
       'Pick three skills per fighter. Some fighters offer a fourth skill.',p)
    result[p]=menu.encode('utf-8')
    p='data/weapon_profiles.json'
    if (root/p).is_file():
        profile=read_json(root,p)
        # Shared mage kit means original mage grip profile remains unchanged.
        if not isinstance(profile,dict): raise RuntimeError('Invalid weapon profile data.')
    p='data/ai_personalities.json'
    if (root/p).is_file():
        ai=read_json(root,p)
        if not isinstance(ai.get('fighters',{}),dict): raise RuntimeError('Unexpected AI personality schema.')
        ai['fighters'].setdefault('roxy',{'archetype':'mage','attack_pace':0.94,
                   'approach_scale':0.82,'skill_pace':0.92,'orbit_scale':1.2,
                   'heavy_scale':0.85})
        result[p]=jbytes(ai)
    result['data/browser_roxy_19e.json']=jbytes({
       'update':VERSION,'fighter':'roxy','browser_source':'https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts',
       'status':'FIRST PLAYABLE PASS, not full browser parity',
       'browser_skills':['Snowglass Aegis','Frost Marionette','Glacier Meteor'],
       'implemented':['3-step frost-shard basic combo','4-way charged shards','Aegis 4-hit absorb / 7s',
                      'moving freezing snow puppet','Glacier Meteor with slow','4 frost shard hits freeze with cooldown','floating spellbook'],
       'refinements_remaining':['bespoke puppet locomotion / collision', 'four visible orbiting Aegis crystals',
                      '2-second post-thaw slow', 'unique full-body snow summoning choreography', 'battle-tested AI and effects']
    })
    result['reports/roxy_19e.txt']=(
      'Update 19E — Roxy Snow Puppet Master\nRequires 19D.\n'
      'Godot imports models/roxy.vrm automatically when opening the project in editor mode.\n'
      'Frost basic / charged; Z Snowglass Aegis; X moving freezing snow puppet; C Glacier Meteor.\n'
      'Three browser skills: no fictitious V slot in Roxy character picker.\n'
      'Aegis absorbs up to four damaging hits for seven seconds, no accumulating charges.\n'
      'Freeze trigger: four successful frost-shard hits (not blocks); cooldown four seconds.\n'
      'First playable port. Bespoke puppet animation and visible orbiting crystals will follow.\n'
      'No shop/survival/online/mode changes.\n').encode('utf-8')
    return result


def sha(data:bytes|None):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def write_atomic(path:Path,data:bytes):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.frg19e-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(data);out.flush();os.fsync(out.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def install(root:Path,dry:bool):
    if (root/'data/browser_roxy_19e.json').is_file():
        print('Update 19E is already installed; nothing changed.')
        return
    payload=payload_for(root) # all anchors validated before modifying any file
    changes={rel:new for rel,new in payload.items() if not (root/rel).is_file() or (root/rel).read_bytes()!=new}
    for rel in changes: print('Update:',rel)
    if dry:
        print('DRY RUN: no files changed')
        return
    backup=root.parent/(root.name+'_backups')/('roxy_19e_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
    backup.mkdir(parents=True,exist_ok=False)
    manifest={'version':VERSION,'project':str(root),'files':{}}
    for rel,new in changes.items():
        old=(root/rel).read_bytes() if (root/rel).is_file() else None
        manifest['files'][rel]={'before':sha(old),'after':sha(new)}
        if old is not None:
            dest=backup/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(old)
    (backup/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    completed=[]
    try:
        for rel,new in changes.items():
            write_atomic(root/rel,new);completed.append(rel)
    except BaseException:
        for rel in reversed(completed):
            saved=backup/rel
            if saved.is_file():write_atomic(root/rel,saved.read_bytes())
            else:(root/rel).unlink(missing_ok=True)
        raise
    print('Update 19E installed. Roxy is selectable. Backup:',backup)


def restore(root:Path,backup:Path):
    data=read_json(backup,'manifest.json')
    if data.get('project') != str(root): raise RuntimeError('Wrong project backup.')
    for rel,state in data['files'].items():
        present=(root/rel).read_bytes() if (root/rel).is_file() else None
        if sha(present) != state['after']: raise RuntimeError(f'Rollback aborted: {rel} was changed after install.')
    for rel,state in data['files'].items():
        if state['before'] is None:(root/rel).unlink(missing_ok=True)
        else:write_atomic(root/rel,(backup/rel).read_bytes())
    print('Restored:',backup)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run',action='store_true')
    ap.add_argument('--restore',type=Path)
    args=ap.parse_args()
    root=Path.cwd().resolve()
    try:
        if args.restore:restore(root,args.restore.expanduser().resolve())
        else:install(root,args.dry_run)
    except Exception as exc:
        print('ERROR:',exc,file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
