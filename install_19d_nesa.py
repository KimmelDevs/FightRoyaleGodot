#!/usr/bin/env python3
"""Fight Royale Godot Update 19D — Nesa / Hammer Princess, first playable port.

Run from Godot project directory: python install_19d_nesa.py
Options: --dry-run, --restore <backup-folder>.

The public browser's current 2026-11-10 Nesa kit is the reference, but the
hold-to-spin, growing heart hammer, and full directional choreography need a
later refinement. This installer intentionally leaves existing VRMs/SFX alone.
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

VERSION = "19D.1"
CHARACTER = "nesa"
KIT = "hammer"
LOOK = {
 "name":"Nesa","body":"f","vrm":"nesa","kit":"hammer","element":"force",
 "outfit":"knight","style":"long","hat":"none","hair":"#5a3427",
 "hair_shade":"#b78368","iris_top":"#6f4a39","iris_bottom":"#b69072",
 "eye_dark":"#2c1a15","tunic":"#f1d0da","band":"#c17696",
 "pants":"#6d4956","boots":"#5a3541","metal":"#d9d1dd",
 "trim":"#ffb3d0","cape":"#8e617b","cape_bottom":"#f5c3d7",
 "glow":"#ffd5e5","shield":"#6f5361","emblem":"#ffd5ea"}
STATS = {"hp":2650,"guard":110,"move":3.05,"walk":2.45,"parry":0.15,"jump":7.0}
# Browser values from the hammer() attack table, including the newer non-parryable rules.
MOVES = {
 "l1":dict(name="Heart Hook",wind=.43,active=.095,recover=.21,dmg=97,guard=28,reach=2.43,lunge=1.9,knock=3.1,stun=.29,next="l2",pose_w="l1_w",pose_s="l1_s",style="hammer_hook"),
 "l2":dict(name="Reverse Crush",wind=.45,active=.095,recover=.22,dmg=107,guard=30,reach=2.53,lunge=2.35,knock=3.7,stun=.32,next="l3",pose_w="l2_w",pose_s="l2_s",style="hammer_crush"),
 "l3":dict(name="Overhead Spin",wind=.50,active=.10,recover=.24,dmg=129,guard=35,reach=2.64,lunge=2.65,knock=4.5,stun=.38,next="l4",pose_w="l3_w",pose_s="l3_s",style="hammer_spin"),
 "l4":dict(name="Heartquake",type="strike",at="self",wind=.57,active=.14,recover=.44,dmg=178,guard=47,reach=2.55,lunge=3.25,knock=8.6,stun=.72,heavy=True,delay=.06,radius=2.55,style="nesa_heart_slam",pose_w="charge",pose_s="heavy_s"),
 "heavy":dict(name="Momentum Cyclone",wind=.45,active=.48,recover=.43,dmg=36,guard=15,reach=2.58,lunge=2.10,knock=1.5,stun=.20,style="nesa_spin",multi_hit=3,pose_w="charge",pose_s="l3_s"),
 "z":dict(name="Side Swipe",desc="A huge horizontal hammer hit with powerful knockback. Blocking reduces damage but does not erase knockback.",cd=7,wind=.36,active=.11,recover=.42,dmg=180,guard=72,reach=2.69,lunge=1.75,knock=9.6,stun=.70,heavy=True,style="nesa_side_swipe",pose_w="nx_w",pose_s="nx_s"),
 "x":dict(name="Upsie Daisie",desc="A planted-hammer sideways flying kick with long forward travel.",cd=9,wind=.40,active=.16,recover=.50,dmg=170,guard=36,reach=2.62,lunge=7.8,knock=7.3,stun=.57,heavy=True,self_jump=6.6,style="nesa_kick",pose_w="kick_w",pose_s="kick_s"),
 "c":dict(name="Pink Heart Smash",desc="Three forward heart-impact shockwaves. Blockable, but not parryable.",cd=7.5,type="strike",at="self",wind=.36,active=.13,recover=.36,dmg=156,guard=42,knock=7.4,stun=.56,heavy=True,no_parry=True,delay=.035,radius=2.72,repeat=3,interval=.36,style="nesa_heart_slam",pose_w="charge",pose_s="heavy_s"),
 "v":dict(name="Heartbreaker High Striker",desc="Brief vertical hammer counter. On a successful read, unleashes a huge heart-shaped impact. Failed reads refund 40% of the cooldown.",cd=26,type="buff",mode="nesa_high_striker",duration=.55,wind=.24,active=.0,recover=.55,pose_w="nesa_parry_w",pose_s="nesa_parry_s",style="nesa_high_striker"),
}
# Source-specific pose names are saved for later migration; existing rig poses
# are compatible aliases in the first playable port.
POSE_ALIASES = {"l1":("l1_w","l1_s"),"l2":("l2_w","l2_s"),"l3":("l3_w","l3_s"),
 "l4":("charge","heavy_s"),"heavy":("charge","l3_s"),"z":("l2_w","l2_s"),
 "x":("l3_w","l3_s"),"c":("charge","heavy_s"),"v":("charge","heavy_s")}

WEAPON_BRANCH = '''
		"hammer": # FRG19D Nesa - giant heart-shaped hammer, attached to right hand
			var pole := _pivot(r)
			_part(pole, _cyl(0.025, 0.025, 1.35, 14), _mat(L.band), Vector3(0, 0.49, 0))
			_part(pole, _cyl(0.038, 0.038, 0.14, 14), trim, Vector3(0, -0.11, 0))
			var head := _pivot(pole, Vector3(0, 1.22, 0))
			_part(head, _box(0.76, 0.42, 0.42), _mat(L.metal, true), Vector3(0, 0.05, 0))
			# Two pink lobes and a diamond-shaped point make a readable heart emblem.
			_part(head, _sph(0.19), _mat(L.trim), Vector3(-0.17, 0.12, -0.24))
			_part(head, _sph(0.19), _mat(L.trim), Vector3(0.17, 0.12, -0.24))
			_part(head, _box(0.31, 0.31, 0.08), _mat(L.tunic), Vector3(0, -0.075, -0.24), Vector3(0, 0, PI / 4))
			_part(head, _box(0.055, 0.46, 0.10), glow, Vector3(0, 0, -0.28))
			blade_base = _pivot(pole, Vector3(0, 0.78, 0))
			blade_tip = _pivot(pole, Vector3(0, 1.46, 0))
			cast_point = blade_tip
			shield_node = l
'''

FIGHTER_FIELDS = '''
# FRG19D Nesa's V skill: successful counter produces a strong heart finisher.
var nesa_counter_pending := false
var nesa_counter_slot := ""
var nesa_counter_max_cd := 0.0
'''

FIGHTER_TICK = '''
	# FRG19D: grant the stated partial cooldown refund only when V fails to counter.
	if nesa_counter_pending and counter_t <= 0.0:
		nesa_counter_pending = false
		if nesa_counter_slot != "" and cooldowns.has(nesa_counter_slot):
			cooldowns[nesa_counter_slot] = maxf(0.0, float(cooldowns[nesa_counter_slot]) - nesa_counter_max_cd * 0.40)
		nesa_counter_slot = ""
'''

BUFF_CASE = '''
		"nesa_high_striker": # FRG19D Nesa V, only valid incoming hits trigger the giant riposte
			f.counter_t = 0.55
			f.nesa_counter_pending = true
			f.nesa_counter_slot = f.atk_id
			f.nesa_counter_max_cd = float(a.get("cd", 26.0)) * f.cd_mult
			fx.number(f.chest() + Vector3(0, 0.9, 0), "HEART COUNTER", Color("#ffd5e5"), 0.8)
'''

COUNTER_CASE = '''
		"counter":
			if d.kit == "hammer" and d.nesa_counter_pending:
				# An actual successful counter, not an unconditional giant attack.
				d.nesa_counter_pending = false
				d.nesa_counter_slot = ""
				fx.number(d.chest() + Vector3(0, 0.6, 0), "HEARTBREAKER!", Color("#ffd5e5"), 1.4)
				var boom := d.attacks.heavy.duplicate(true)
				boom["type"] = "strike"
				boom["style"] = "nesa_giant_heart"
				boom["at"] = "self"
				boom["dmg"] = 580
				boom["guard"] = 90
				boom["knock"] = 12.5
				boom["stun"] = 1.0
				boom["heavy"] = true
				boom["radius"] = 3.5
				boom["delay"] = 0.05
				boom["repeat"] = 1
				_strike(d, boom, d.dmg_mult)
			else:
				fx.number(d.chest() + Vector3(0, 0.6, 0), "COUNTER!", Color("#ff9aa8"), 1.4)
				if attacker:
					var counter: Dictionary = d.attacks.heavy.duplicate()
					counter.dmg = 180; counter.heavy = true; counter.stun = 0.8
					apply_hit(d, attacker, counter, d.dmg_mult, attacker.chest(), -dir, false)
'''

STRIKE_CENTER = '''
		var center: Vector3 = src.position; center.y = 0
		# FRG19D: Nesa C advances the three heart impacts away from her.
		if String(a.get("style", "")) == "nesa_heart_slam" and f.kit == "hammer":
			center += f.forward() * (1.05 + float(i) * 0.75)
'''
STRIKE_AT = '''
			var at: Vector3 = Vector3(f.position.x, 0, f.position.z) if a.at == "self" else center
			if String(a.get("style", "")) == "nesa_heart_slam" and f.kit == "hammer":
				at = center
'''

IMPACT_CASE = '''
		"nesa_heart_slam", "nesa_giant_heart": # FRG19D heart hammer hit treatment
			fx.rocks(g, 20 if a.style == "nesa_heart_slam" else 34, 1.5)
			fx.ring(g, Color("#ff95c1"), radius * 1.3, 0.38, 0.94)
			fx.flash(g + Vector3(0, 0.7, 0), Color("#ffe1f0"), radius * 0.60, 0.18, 0.88)
			add_trauma(0.55 if a.style == "nesa_heart_slam" else 0.82)
'''


def load_json(root:Path, relative:str):
    try: return json.loads((root/relative).read_text(encoding="utf-8-sig"))
    except (OSError,ValueError) as exc: raise RuntimeError(f"Unable to parse {relative}: {exc}") from exc


def once(source:str, needle:str, replacement:str, where:str)->str:
    count = source.count(needle)
    if count != 1: raise RuntimeError(f"{where}: expected one stable anchor, got {count}; nothing installed")
    return source.replace(needle,replacement,1)


def bjson(obj)->bytes: return (json.dumps(obj,indent=2,ensure_ascii=False)+"\n").encode("utf-8")


def prepare(root:Path)->dict[str,bytes]:
    if not (root/"project.godot").is_file(): raise RuntimeError("Run from your Godot project folder containing project.godot")
    if not (root/"data/browser_kaizen_19c.json").is_file(): raise RuntimeError("Please install Update 19C first")
    roster = load_json(root,"data/roster.json")
    stats = load_json(root,"data/stats.json")
    attacks = load_json(root,"data/attacks.json")
    poses = load_json(root,"data/poses.json")
    if not isinstance(roster,list) or not all(isinstance(x,dict) for x in [stats,attacks,poses]):
        raise RuntimeError("Unknown roster/stat/attack/pose schema; existing project untouched")
    if CHARACTER in [str(c.get("id","")) for c in roster] or KIT in stats or KIT in poses or CHARACTER in attacks:
        raise RuntimeError("Nesa or hammer kit already exists. Refusing to overwrite existing character data")
    if "greatsword" not in stats or "greatsword" not in poses or "garrick" not in attacks:
        raise RuntimeError("Missing original greatsword base needed for migration")
    lib=root/"animations/greatsword.tres"
    if not lib.is_file(): raise RuntimeError("Missing animations/greatsword.tres")

    roster.append({"id":CHARACTER,"title":"Hammer Princess","role":"Bruiser - Giant Hammer",
       "desc":"A heart-hammer bruiser with weighty swings, a vaulting kick, heart shockwaves and a high-risk counter.",
       "stats":{"power":5,"speed":2,"range":3,"defense":4},"look":deepcopy(LOOK)})
    stats[KIT]=deepcopy(STATS)
    poses[KIT]=deepcopy(poses["greatsword"])
    moves={}
    for key, raw in MOVES.items():
        move=deepcopy(attacks["garrick"]["l1"])
        move.update(deepcopy(raw))
        move["browser_pose_w"]=raw["pose_w"]
        move["browser_pose_s"]=raw["pose_s"]
        move["pose_w"],move["pose_s"] = POSE_ALIASES[key]
        move["id"]=key
        move["element"]="force"
        move["type"]=raw.get("type","melee")
        move["no_parry"]=True  # NESA_MOMENTUM_V3 from browser: no perfect parry against hammer hits
        move["heavy"]=bool(raw.get("heavy",False))
        move["next"]=raw.get("next","")
        move["cd"]=float(raw.get("cd",0))
        move["multi_hit"]=int(raw.get("multi_hit",1))
        move["stagger"]=False
        move["self_jump"]=float(raw.get("self_jump",0))
        if key=="v": move["no_parry"]=False
        if move["pose_w"] not in poses[KIT] or move["pose_s"] not in poses[KIT]:
            raise RuntimeError(f"Nesa pose alias missing: {key}")
        moves[key]=move
    attacks[CHARACTER]=moves
    payload={"data/roster.json":bjson(roster),"data/stats.json":bjson(stats),
             "data/attacks.json":bjson(attacks),"data/poses.json":bjson(poses),
             "animations/hammer.tres":lib.read_bytes()}
    payload["data/browser_nesa_19d.json"]=bjson({
        "update":VERSION,"fighter":CHARACTER,"kit":KIT,
        "source":"https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts",
        "status":"FIRST PLAYABLE PASS ONLY — not full browser parity",
        "moves":MOVES,
        "implemented":["4-step combo","Momentum Cyclone timed contacts","Side Swipe","Upsie Daisie",
          "3 forward Pink Heart Smash pulses","Heartbreaker conditional counter and 40% failed-read refund",
          "procedural heart hammer","non-parryable hammer damage"],
        "remaining":["hold-to-control cyclone length","dynamic three-charge forward movement",
          "real counter-frame choreography","4x giant hammer geometric transformation","source-accurate bone choreography"]})
    payload["reports/nesa_19d.txt"]=(
       "Fight Royale Godot 19D — Nesa first playable port\n"
       "Requires 19C. Godot needs to import models/nesa.vrm for the correct model.\n"
       "No VRM rig edits are needed. Uses temporary greatsword animation poses.\n"
       "Four light attacks + charged spinning hammer + Z/X/C/V (3 equipped at once).\n"
       "Pink Heart Smash creates three sequential forward pulses; not full browser charge travel.\n"
       "V counter requires a real incoming attack; failed reads refund 40% cooldown.\n"
       "Full giant-hammer transformation and bespoke choreography deferred.\n"
       "No changes to shop or game modes.\n").encode("utf-8")
    p="scripts/fighter_model.gd"; model=(root/p).read_text(encoding="utf-8")
    model=once(model,"\tmatch kit:\n","\tmatch kit:\n"+WEAPON_BRANCH,p)
    payload[p]=model.encode("utf-8")
    p="scripts/fighter.gd"; fighter=(root/p).read_text(encoding="utf-8")
    fighter=once(fighter,"var guard_fatigue := 0\n","var guard_fatigue := 0\n"+FIGHTER_FIELDS,p)
    fighter=once(fighter,"\tcounter_t = maxf(counter_t - dt, 0.0)\n",
            "\tcounter_t = maxf(counter_t - dt, 0.0)\n"+FIGHTER_TICK,p)
    payload[p]=fighter.encode("utf-8")
    p="scripts/match.gd"; match=(root/p).read_text(encoding="utf-8")
    match=once(match,"\t\t\"counter\":\n\t\t\tfx.number(d.chest() + Vector3(0, 0.6, 0), \"COUNTER!\", Color(\"#ff9aa8\"), 1.4)\n\t\t\tif attacker:\n\t\t\t\tvar counter: Dictionary = d.attacks.heavy.duplicate()\n\t\t\t\tcounter.dmg = 180; counter.heavy = true; counter.stun = 0.8\n\t\t\t\tapply_hit(d, attacker, counter, d.dmg_mult, attacker.chest(), -dir, false)\n",COUNTER_CASE,p)
    match=once(match,"\t\tvar center: Vector3 = src.position; center.y = 0\n",STRIKE_CENTER,p)
    match=once(match,"\t\t\tvar at: Vector3 = Vector3(f.position.x, 0, f.position.z) if a.at == \"self\" else center\n",STRIKE_AT,p)
    match=once(match,"\t\t\"spin\":\n",IMPACT_CASE+"\t\t\"spin\":\n",p)
    match=once(match,"\t\t\"counter\":\n\t\t\tf.counter_t = float(a.duration)\n",
        "\t\t\"counter\":\n\t\t\tf.counter_t = float(a.duration)\n"+BUFF_CASE,p)
    payload[p]=match.encode("utf-8")
    p="data/weapon_profiles.json"
    if (root/p).is_file():
        profiles=load_json(root,p)
        if not isinstance(profiles.get("kits"),dict): raise RuntimeError("Invalid weapon profile structure")
        if KIT in profiles["kits"]:raise RuntimeError("Existing hammer weapon settings: refusing to overwrite")
        profiles["kits"][KIT]=deepcopy(profiles["kits"].get("greatsword",{}))
        payload[p]=bjson(profiles)
    p="data/ai_personalities.json"
    if (root/p).is_file():
        ai=load_json(root,p)
        if not isinstance(ai.get("fighters",{}),dict):raise RuntimeError("Invalid AI personality structure")
        ai["fighters"].setdefault(CHARACTER,{"archetype":"greatsword","attack_pace":0.86,
          "approach_scale":1.18,"skill_pace":0.98,"heavy_scale":1.26,"orbit_scale":0.7})
        payload[p]=bjson(ai)
    return payload


def digest(value:bytes|None)->str|None: return hashlib.sha256(value).hexdigest() if value is not None else None


def atomic_write(path:Path,data:bytes):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".frg19d-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def install(root:Path,dry_run:bool):
    if (root/"data/browser_nesa_19d.json").is_file():
        print("Update 19D already installed; preserved existing Nesa configuration.")
        return
    payload=prepare(root) # validate all anchors BEFORE any project modification
    changes={rel:data for rel,data in payload.items() if not (root/rel).is_file() or (root/rel).read_bytes()!=data}
    for rel in changes:print("Update:",rel)
    if dry_run:
        print("DRY RUN completed; no files changed")
        return
    backup=root.parent/(root.name+"_backups")/("roster_19d_"+datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")+"_"+uuid.uuid4().hex[:6])
    backup.mkdir(parents=True,exist_ok=False)
    manifest={"version":VERSION,"project":str(root),"files":{}}
    for rel,new in changes.items():
        old=(root/rel).read_bytes() if (root/rel).is_file() else None
        manifest["files"][rel]={"before":digest(old),"after":digest(new)}
        if old is not None:
            dest=backup/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(old)
    (backup/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    completed=[]
    try:
        for rel,new in changes.items():
            atomic_write(root/rel,new);completed.append(rel)
    except Exception:
        for rel in reversed(completed):
            saved=backup/rel
            if saved.is_file():atomic_write(root/rel,saved.read_bytes())
            else:(root/rel).unlink(missing_ok=True)
        raise
    print("Update 19D installed. Nesa available after Godot asset import. Backup:",backup)


def restore(root:Path, folder:Path):
    manifest=load_json(folder,"manifest.json")
    if manifest.get("project")!=str(root):raise RuntimeError("Backup does not belong to this project")
    for rel,state in manifest["files"].items():
        present=(root/rel).read_bytes() if (root/rel).is_file() else None
        if digest(present)!=state["after"]:raise RuntimeError(f"Refusing rollback: {rel} changed after installation")
    for rel,state in manifest["files"].items():
        saved=folder/rel
        if state["before"] is None:(root/rel).unlink(missing_ok=True)
        else:atomic_write(root/rel,saved.read_bytes())
    print("Restored:",folder)


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run",action="store_true")
    p.add_argument("--restore",type=Path)
    args=p.parse_args()
    root=Path.cwd().resolve()
    try:
        if args.restore:restore(root,args.restore.expanduser().resolve())
        else:install(root,args.dry_run)
        return 0
    except Exception as exc:
        print("ERROR:",exc,file=sys.stderr)
        return 1

if __name__=="__main__":raise SystemExit(main())
