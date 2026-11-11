#!/usr/bin/env python3
"""Fight Royale Godot Update 19H — Nythera: Gravity Reaper (first playable port).

Run in the Godot project: python install_19h_nythera.py
Optional: --dry-run or --restore PATH_TO_BACKUP
Requires Update 19G (Zephyr) before installation.

Adds Nythera with a six-hit scythe combo, Moonfloat/Dreadfall switching,
Orbit Mark debuffs, Dreadfall momentum, three-beat Z/X, Event Horizon,
four-beat V and a procedural single-blade scythe. Exact VRM pose choreography,
physics-driven gravity fields, and final browser balance are not yet claimed.
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

VERSION = "19H.1"
CHARACTER = "nythera"
LOOK = {
    "name":"Nythera", "body":"f", "vrm":"nythera", "kit":"scythe", "element":"gravity",
    "outfit":"reaper", "style":"long", "hat":"none",
    "hair":"#c7d2ec", "hair_shade":"#8293bb", "iris_top":"#aa8fff",
    "iris_bottom":"#e9d6ff", "eye_dark":"#2a2148", "tunic":"#2b2341",
    "band":"#6d5c8a", "pants":"#292438", "boots":"#1a1729", "metal":"#8f92b1",
    "trim":"#a58bdb", "cape":"#251b3d", "cape_bottom":"#5c4e92",
    "glow":"#bc89ff", "shield":"#322753", "emblem":"#c4b1ef"
}
# Base values from browser gravityScythe() in kits.ts (first playable approximation).
# Standard Godot move template supplies all other required keys.
MOVES = {
    "l1": dict(name="Open Crescent",wind=.085,active=.08,recover=.115,dmg=65,guard=15,reach=2.40,lunge=2.35,knock=.38,stun=.15,style="gravity_crescent",next="l2"),
    "l2": dict(name="Crossed Moon",wind=.09,active=.08,recover=.125,dmg=71,guard=16,reach=2.46,lunge=2.40,knock=.40,stun=.16,style="gravity_crescent",next="l3"),
    "l3": dict(name="Turning Reap",wind=.10,active=.08,recover=.135,dmg=76,guard=18,reach=2.48,lunge=2.40,knock=.50,stun=.17,style="gravity_crescent",next="l4"),
    "l4": dict(name="Orbit Bloom",wind=.105,active=.09,recover=.145,dmg=83,guard=19,reach=2.52,lunge=2.50,knock=.58,stun=.19,style="gravity_bloom",next="l5"),
    "l5": dict(name="Reversal Hook",wind=.11,active=.09,recover=.15,dmg=84,guard=21,reach=2.54,lunge=2.30,knock=.55,stun=.18,style="gravity_crescent",next="l6"),
    "l6": dict(name="Eclipse Reap",wind=.145,active=.11,recover=.24,dmg=120,guard=30,reach=2.56,lunge=2.60,knock=2.65,stun=.32,style="gravity_bloom"),
    "heavy": dict(name="Grave Descent",wind=.24,active=.10,recover=.52,dmg=155,guard=44,reach=2.53,lunge=3.15,knock=4.4,stun=.46,heavy=True,style="gravity_grave"),
    "z": dict(name="Crescent Snare",desc="Three individually defendable scythe cuts. Moonfloat marks; Dreadfall consumes marks.",cd=6.5,wind=.15,active=.45,recover=.25,dmg=45,guard=12,reach=2.68,lunge=2.6,knock=.75,stun=.18,style="gravity_snare",multi_hit=3),
    "x": dict(name="Zero-G Ascension",desc="Three rising scythe cuts; each may be blocked, parried, dodged or clashed.",cd=9.,wind=.18,active=.54,recover=.28,dmg=49,guard=13,reach=2.68,lunge=2.95,knock=1.2,stun=.21,style="gravity_ascend",multi_hit=3),
    "c": dict(name="Event Horizon",desc="Moonfloat creates a pulling field. Dreadfall causes a telegraphed collapse.",cd=14.,type="buff",mode="gravity_well",wind=.32,active=.1,recover=.43,dmg=0,guard=0,reach=2.8,lunge=0,knock=0,stun=0,radius=2.8,duration=2.6,style="gravity_well"),
    "v": dict(name="Black Star Requiem",desc="Four independently defendable eclipse scythe strikes.",cd=43.,wind=.36,active=1.04,recover=.53,dmg=40,guard=15,reach=2.9,lunge=2.2,knock=1.,stun=.18,style="gravity_requiem",multi_hit=4)
}
POSE_FROM = {"l1":"l1","l2":"l2","l3":"l3","l4":"l4","l5":"l5","l6":"l5",
             "heavy":"heavy","z":"z","x":"x","c":"c","v":"v"}

MODEL_SCYTHE = r'''
		"scythe": # FRG19H — single curved gravity scythe with a long handle
			var shaft := _pivot(r, Vector3(0, -0.26, 0))
			_part(shaft, _cyl(0.021, 0.021, 1.83, 16), _mat(L.band), Vector3(0, 0.72, 0))
			_part(shaft, _cyl(0.028, 0.028, 0.16, 12), trim, Vector3(0, -0.11, 0))
			_part(shaft, _box(0.08, 0.26, 0.05), glow, Vector3(0, 1.47, -0.02))
			var blade := _pivot(shaft, Vector3(0, 1.59, 0))
			# Curved blade sweeps right, then hooks downward; not a straight sword.
			_part(blade, _box(0.35, 0.085, 0.065), steel, Vector3(0.14, 0.04, 0), Vector3(0, 0, 0.16))
			_part(blade, _box(0.30, 0.075, 0.056), steel, Vector3(0.43, 0.12, 0), Vector3(0, 0, 0.47))
			_part(blade, _box(0.23, 0.064, 0.048), steel, Vector3(0.64, 0.06, 0), Vector3(0, 0, 0.97))
			_part(blade, _box(0.19, 0.045, 0.036), glow, Vector3(0.69, -0.12, -0.015), Vector3(0, 0, 1.26))
			_part(blade, _cyl(0.0, 0.042, 0.14, 10), steel, Vector3(0.77, -0.18, 0), Vector3(0, 0, 1.16))
			blade_base = _pivot(shaft, Vector3(0, 1.53, 0))
			blade_tip = _pivot(blade, Vector3(0.79, -0.22, 0))
			cast_point = blade_tip
			shield_node = l
'''

FIGHTER_FIELDS = r'''
# FRG19H — Nythera's Moonfloat / Dreadfall stance and temporary Orbit Marks.
var nythera_mode := 0 # 0 Moonfloat, 1 Dreadfall
var nythera_mode_cd := 0.0
var nythera_orbit_marks := 0 # On the DEFENDER, stacked only by Nythera
var nythera_orb_seconds := 0.0
var nythera_dread_stacks := 0 # On Nythera, +0.1 attack speed per consumed mark
var nythera_well_seconds := 0.0
'''
FIGHTER_TICK = r'''
	# FRG19H: F switches between Moonfloat and Dreadfall; do not reuse a held switch.
	if kit == "scythe":
		nythera_mode_cd = maxf(0.0, nythera_mode_cd - dt)
		if in_mode_switch and nythera_mode_cd <= 0.0 and state in [S.IDLE, S.BLOCK]:
			nythera_mode = 1 - nythera_mode
			nythera_mode_cd = 0.35
			if model != null: model.flash(Color("#b6aaff") if nythera_mode == 0 else Color("#e9a5ff"), 0.18)
	if nythera_orb_seconds > 0.0:
		nythera_orb_seconds = maxf(0.0, nythera_orb_seconds - dt)
		if nythera_orb_seconds <= 0.0: nythera_orbit_marks = 0
'''
FIGHTER_PASSIVE = r'''
	# Only genuinely damaging hits build / consume Orbit Marks. No reward from blocks/parries.
	if kit == "scythe" and event_id == "landed_hit" and other is Fighter:
		if nythera_mode == 0:
			other.nythera_orbit_marks = mini(6, other.nythera_orbit_marks + 1)
			other.nythera_orb_seconds = 10.0
		else:
			if other.nythera_orbit_marks > 0:
				other.nythera_orbit_marks -= 1
				nythera_dread_stacks = mini(14, nythera_dread_stacks + 1)
'''

MATCH_MULTI = r'''
# FRG19H — scythe skill beats use the ordinary hit/parry/block/clash pipeline.
func _nythera_schedule_beats(f: Fighter, a: Dictionary) -> void:
	var count: int = int(a.get("multi_hit", 1))
	if count <= 1 or not f.active_melee(): return
	var serial: int = f.swing_serial
	var round_id: int = _round
	var span: float = float(a.get("active", 0.0)) * f.attack_time_multiplier()
	for beat in range(1, count):
		var wait_time: float = span * float(beat) / float(count)
		later(wait_time, func():
			_nythera_beat(f, a, serial, round_id, beat))

func _nythera_beat(f: Fighter, a: Dictionary, serial: int, round_id: int, beat: int) -> void:
	if round_over or _round != round_id or not is_instance_valid(f) or f.is_down(): return
	if f.swing_serial != serial or not f.active_melee(): return
	_melee(f, a, beat)

func _nythera_step_wells(dt: float) -> void:
	if dt <= 0.0 or round_over: return
	for f in fighters:
		if f.kit != "scythe" or f.is_down() or f.nythera_well_seconds <= 0.0: continue
		f.nythera_well_seconds = maxf(0.0, f.nythera_well_seconds - dt)
		var center: Vector3 = f.global_position
		for target in enemies_of(f):
			var delta: Vector3 = center - target.global_position
			delta.y = 0.0
			var gap: float = delta.length()
			if gap > 0.95 and gap <= 2.8:
				var pull: float = minf(gap - 0.95, dt * 1.3)
				target.position += delta.normalized() * pull
'''

BUFF_GRAVITY = r'''
		"gravity_well":
			# Moonfloat pulls enemies, Dreadfall collapses in a dodgeable circle.
			if f.kit == "scythe" and f.nythera_mode == 0:
				f.nythera_well_seconds = 2.6
				fx.ring(f.position, Color("#a98bef"), 2.8, 0.38, 0.75)
				fx.number(f.chest() + Vector3(0, 0.7, 0), "EVENT HORIZON", Color("#d7c4ff"), 0.85)
			else:
				f.nythera_well_seconds = 0.0
				var pulse: Dictionary = a.duplicate(true)
				pulse["type"] = "strike"
				pulse["at"] = "self"
				pulse["dmg"] = 116.0
				pulse["guard"] = 37.0
				pulse["knock"] = 4.6
				pulse["stun"] = 0.34
				pulse["heavy"] = true
				pulse["delay"] = 0.36
				pulse["radius"] = 2.7
				pulse["repeat"] = 1
				pulse["style"] = "gravity_meteor"
				_strike(f, pulse, f.atk_power)
'''


def read_json(root: Path, rel: str):
    try:
        return json.loads((root / rel).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Could not read {rel}: {exc}") from exc


def jbytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def once(src: str, anchor: str, value: str, rel: str) -> str:
    n = src.count(anchor)
    if n != 1:
        raise RuntimeError(f"{rel}: expected one anchor, found {n}: {anchor[:80]!r}")
    return src.replace(anchor, value, 1)


def build(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise RuntimeError("Open PowerShell in the folder containing project.godot")
    if not (root / "data/browser_zephyr_19g.json").is_file():
        raise RuntimeError("Update 19G (Zephyr) must be installed first")
    roster = read_json(root, "data/roster.json")
    attacks = read_json(root, "data/attacks.json")
    stats = read_json(root, "data/stats.json")
    poses = read_json(root, "data/poses.json")
    if not isinstance(roster, list) or not all(isinstance(d, dict) for d in (attacks,stats,poses)):
        raise RuntimeError("Unexpected roster, stats, poses or attacks format")
    ids = [r.get("id") for r in roster]
    if len(set(ids)) != len(ids) or CHARACTER in ids or CHARACTER in attacks or "scythe" in stats:
        raise RuntimeError("Duplicate Nythera or incompatible preexisting scythe kit; no files changed")
    if "zarek" not in attacks or "glaive" not in stats or "glaive" not in poses:
        raise RuntimeError("Missing previous Glaive animation template")
    template_anim = root / "animations/glaive.tres"
    if not template_anim.is_file():
        raise RuntimeError("Missing animations/glaive.tres")
    roster.append({"id": CHARACTER, "title":"Gravity Reaper", "role":"Scythe - Moonfloat / Dreadfall",
                   "desc":"Marks enemies with gravity orbs, then consumes them for Dreadfall momentum.",
                   "stats":{"power":4,"speed":4,"range":4,"defense":3}, "look":deepcopy(LOOK)})
    stats["scythe"] = {"hp":2200,"guard":84,"move":3.72,"walk":3.02,"parry":.19,"jump":8.0}
    poses["scythe"] = deepcopy(poses["glaive"])
    output_attacks = {}
    for key, values in MOVES.items():
        alias = POSE_FROM[key]
        src = attacks["zarek"].get(alias)
        if not isinstance(src, dict):
            raise RuntimeError(f"Missing template move for {key}")
        atk = deepcopy(src)
        atk.update(deepcopy(values))
        atk["id"] = key
        atk["element"] = "gravity"
        atk["next"] = values.get("next", "")
        atk["type"] = values.get("type", "melee")
        atk["heavy"] = bool(values.get("heavy", False))
        atk["cd"] = float(values.get("cd", 0.0))
        atk["multi_hit"] = int(values.get("multi_hit", 1))
        atk["mode"] = values.get("mode", "")
        atk["duration"] = float(values.get("duration", 0.0))
        atk["pose_w"] = src["pose_w"]
        atk["pose_s"] = src["pose_s"]
        for k in ("pose_w","pose_s"):
            if atk[k] not in poses["scythe"]:
                raise RuntimeError(f"Missing Nythera pose {atk[k]}")
        output_attacks[key] = atk
    attacks[CHARACTER] = output_attacks
    out = {
        "data/roster.json": jbytes(roster),
        "data/attacks.json": jbytes(attacks),
        "data/stats.json": jbytes(stats),
        "data/poses.json": jbytes(poses),
        "animations/scythe.tres": template_anim.read_bytes(),
    }
    path = "scripts/fighter_model.gd"
    code = (root/path).read_text(encoding="utf-8")
    code = once(code, '\t\t"hammer": # FRG19D', MODEL_SCYTHE + '\t\t"hammer": # FRG19D', path)
    out[path] = code.encode("utf-8")

    path = "scripts/player_brain.gd"
    code = (root/path).read_text(encoding="utf-8")
    code = once(code, 'if f.kit == "tristaff" and _mode_pending: f.in_mode_switch = true',
                'if f.kit in ["tristaff", "scythe"] and _mode_pending: f.in_mode_switch = true', path)
    out[path] = code.encode("utf-8")

    path = "scripts/fighter.gd"
    code = (root/path).read_text(encoding="utf-8")
    code = once(code, 'var zephyr_mode := 0', FIGHTER_FIELDS + 'var zephyr_mode := 0', path)
    code = once(code, 'in_dodge = Vector3.ZERO; in_sprint = false',
                'in_dodge = Vector3.ZERO; in_sprint = false; in_mode_switch = false # FRG19H', path)
    code = once(code, '\t# FRG19F Zenith: consecutive landed hits refresh the 5s charge duration.\n',
                FIGHTER_TICK + '\t# FRG19F Zenith: consecutive landed hits refresh the 5s charge duration.\n', path)
    code = once(code, '\t# Dragon Rhythm earns stacks only on real contacts and defense success.\n',
                FIGHTER_PASSIVE + '\t# Dragon Rhythm earns stacks only on real contacts and defense success.\n', path)
    code = once(code, '\treturn summary\n\n# FRG15D - status HUD and countdown indicators\n',
                '\tif kit == "scythe":\n\t\tvar label: String = ("MOONFLOAT" if nythera_mode == 0 else "DREADFALL")\n'
                '\t\tlabel += " · Dread x%d" % nythera_dread_stacks if nythera_dread_stacks > 0 else ""\n'
                '\t\treturn label if summary.is_empty() else label + ", " + summary\n'
                '\tif nythera_orbit_marks > 0:\n'
                '\t\tvar marks: String = "Orbit x%d" % nythera_orbit_marks\n'
                '\t\treturn marks if summary.is_empty() else marks + ", " + summary\n'
                '\treturn summary\n\n# FRG15D - status HUD and countdown indicators\n', path)
    code = once(code, ' * status_runtime.attack_time_multiplier() / (factor * metal_factor * dragon_mode_speed * dragon_rhythm_speed)\n',
                ' * status_runtime.attack_time_multiplier() / (factor * metal_factor * dragon_mode_speed * dragon_rhythm_speed)'
                ' * (1.0 + 0.05 * float(nythera_orbit_marks)) / (1.0 + 0.10 * float(nythera_dread_stacks))\n', path)
    code = once(code, '\tatk = attacks[aid].duplicate(true)\n',
                '\tatk = attacks[aid].duplicate(true)\n'
                '\tif kit == "scythe" and String(atk.get("type", "melee")) == "melee":\n'
                '\t\tif nythera_mode == 1: atk_power *= 1.15\n'
                '\t\tif not on_ground: atk_power *= 3.0\n', path)
    code = once(code, '\tif state != S.BLOCK:\n\t\t_guard_delay -= dt\n',
                '\tif state != S.BLOCK:\n\t\t_guard_delay -= dt\n', path) if False else code
    code = once(code, 'guard = minf(guard + GUARD_REGEN * dt * status_runtime.guard_regen_multiplier(), max_guard)',
                'guard = minf(guard + GUARD_REGEN * dt * status_runtime.guard_regen_multiplier() * (1.0 - 0.05 * float(nythera_orbit_marks)), max_guard)',path)
    out[path] = code.encode("utf-8")

    path = "scripts/match.gd"
    code = (root/path).read_text(encoding="utf-8")
    code = once(code, '\t_roxy_step_puppets(dt)\n', '\t_roxy_step_puppets(dt)\n\t_nythera_step_wells(dt)\n',path)
    code = once(code, '\tif f.kit == "tristaff" and String(a.get("type", "")) == "melee":\n',
                '\tif f.kit == "scythe" and String(a.get("type", "")) == "melee": _nythera_schedule_beats(f, a)\n'
                '\tif f.kit == "tristaff" and String(a.get("type", "")) == "melee":\n', path)
    code = once(code, 'func _zephyr_schedule_beats(f: Fighter, a: Dictionary) -> void:\n',
                MATCH_MULTI + '\nfunc _zephyr_schedule_beats(f: Fighter, a: Dictionary) -> void:\n', path)
    code = once(code, '\t\t"frost_aegis":\n', BUFF_GRAVITY + '\n\t\t"frost_aegis":\n', path)
    out[path] = code.encode("utf-8")

    ai_path = "data/ai_personalities.json"
    if (root/ai_path).is_file():
        ai = read_json(root, ai_path)
        if not isinstance(ai,dict) or not isinstance(ai.get("fighters"),dict):
            raise RuntimeError("Unexpected AI personalities configuration")
        ai["fighters"][CHARACTER] = {"archetype":"glaive","attack_pace":1.06,
                                      "skill_pace":1.09,"approach_scale":1.03,"orbit_scale":1.20,"parry_scale":1.06}
        out[ai_path] = jbytes(ai)
    out["data/browser_nythera_19h.json"] = jbytes({
        "version":VERSION,"character":CHARACTER,
        "browser_reference":"https://github.com/KimmelDevs/Fight-Royale/blob/main/web/src/game/kits.ts",
        "status":"FIRST PLAYABLE PORT — VISUAL/BALANCE PARITY PENDING",
        "implemented":["six hit light combo","charged Grave Descent","three independently blockable Z/X contacts",
                       "Moonfloat and Dreadfall modes (F)","Orbit Marks, cap 6, 10s lifetime",
                       "Dreadfall momentum, cap 14","Moonfloat pulling well and Dreadfall telegraphed collapse",
                       "four-beat Black Star Requiem","procedural single curved scythe"],
        "pending":["custom gravity reaper VRM bone poses and animation library","full gravity orb visual system",
                   "specialized scythe choreography","AI autonomous mode switching","in-game Godot performance and balance validation"]})
    out["reports/nythera_19h.txt"] = (
        "Fight Royale Godot 19H - Nythera Gravity Reaper\n"
        "First playable port; use models/nythera.vrm and open Godot editor to import it.\n"
        "F switches Moonfloat/Dreadfall. Z: Crescent Snare; X: Zero-G Ascension; C: Event Horizon.\n"
        "Dreadfall uses Orbit Marks applied in Moonfloat to gain speed on real hits.\n"
        "Advanced scythe choreography and specific mode AI will follow.\n"
        "Only Duel vs CPU and CPU vs CPU; no shop or extra game modes.\n").encode("utf-8")
    return out


def digest(data: bytes|None):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def atomic(path: Path, value: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".frg19h-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def install(root: Path, dry: bool):
    if (root/"data/browser_nythera_19h.json").is_file():
        print("Update 19H already installed; no changes")
        return
    planned = build(root)
    changes = {rel: data for rel,data in planned.items() if not (root/rel).is_file() or (root/rel).read_bytes()!=data}
    for rel in changes: print("Update:",rel)
    if dry:
        print("Dry run OK; no files changed")
        return
    folder = root.parent / (root.name+"_backups") / (
        "nythera_19h_"+datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")+"_"+uuid.uuid4().hex[:6])
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {"version":VERSION,"project":str(root),"files":{}}
    for rel,new in changes.items():
        before = (root/rel).read_bytes() if (root/rel).is_file() else None
        manifest["files"][rel]={"before":digest(before),"after":digest(new)}
        if before is not None:
            save=folder/rel; save.parent.mkdir(parents=True, exist_ok=True); save.write_bytes(before)
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    done=[]
    try:
        for rel,new in changes.items():
            atomic(root/rel,new); done.append(rel)
    except BaseException:
        for rel in reversed(done):
            before=folder/rel
            if before.is_file(): atomic(root/rel,before.read_bytes())
            else: (root/rel).unlink(missing_ok=True)
        raise
    print("Installed Update 19H (Nythera). Backup:",folder)


def restore(root: Path, folder: Path):
    manifest=read_json(folder,"manifest.json")
    if manifest.get("project")!=str(root): raise RuntimeError("Backup belongs to a different project")
    for rel,meta in manifest.get("files",{}).items():
        now=(root/rel).read_bytes() if (root/rel).is_file() else None
        if digest(now)!=meta["after"]: raise RuntimeError("File changed since install: "+rel)
    for rel,meta in manifest["files"].items():
        old=folder/rel
        if meta["before"] is None: (root/rel).unlink(missing_ok=True)
        else: atomic(root/rel,old.read_bytes())
    print("Restore complete:",folder)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run",action="store_true")
    parser.add_argument("--restore",type=Path)
    args=parser.parse_args()
    root=Path.cwd().resolve()
    try:
        if args.restore: restore(root,args.restore.expanduser().resolve())
        else: install(root,args.dry_run)
    except Exception as err:
        print("ERROR:",err,file=sys.stderr)
        return 1
    return 0

if __name__=="__main__":
    raise SystemExit(main())
