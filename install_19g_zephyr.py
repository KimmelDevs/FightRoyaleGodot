#!/usr/bin/env python3
"""Fight Royale Godot 19G — Zephyr Dragon Dancer (first playable port).

Run: python install_19g_zephyr.py
Optional: --dry-run | --restore PATH
Requires: Update 19F (Zenith).

Adds the three-section staff, five basic strikes, three defendable multi-contact
skills and counter, four F-switched grips, Dragon Rhythm, and safe asset fallbacks.
Actual hand-to-segment choreography, switches during attacks, unique bone poses,
and exact browser AI are planned for 19H onward, not claimed here.
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

VERSION = "19G.1"
CHARACTER = "zephyr"
BROWSER = "https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts"
LOOK = dict(
    name="Zephyr",body="m",vrm="zephyr",kit="tristaff",element="dragon",
    outfit="martial",style="short",hat="none",hair="#263f45",
    hair_shade="#76939a",iris_top="#1e8c7e",iris_bottom="#b6ffe2",
    eye_dark="#113034",tunic="#203a43",band="#85bba5",
    pants="#19242e",boots="#202936",metal="#e0e8df",trim="#d5be82",
    cape="#274a53",cape_bottom="#84c7ae",glow="#78eed0",
    shield="#243e48",emblem="#e8d9a0")
# Values from current browser kits.ts; multi-hit skills use independently
# defendable beats instead of one early impact.
MOVES = {
    "l1": dict(name="Dragon Entry",wind=.13,active=.075,recover=.18,dmg=48,guard=14,reach=2.09,lunge=2.35,knock=.5,stun=.17,style="zephyr_staff",next="l2"),
    "l2": dict(name="Backwind Catch",wind=.15,active=.08,recover=.19,dmg=55,guard=15,reach=2.10,lunge=2.,knock=.58,stun=.18,style="zephyr_staff",next="l3"),
    "l3": dict(name="Underarm Eight",wind=.15,active=.085,recover=.20,dmg=61,guard=17,reach=2.16,lunge=2.15,knock=.68,stun=.21,style="zephyr_staff",next="l4"),
    "l4": dict(name="Orbit Wheel",wind=.19,active=.12,recover=.24,dmg=71,guard=20,reach=2.26,lunge=2.25,knock=1.4,stun=.25,style="zephyr_staff",next="l5"),
    "l5": dict(name="Twin-End Verdict",wind=.23,active=.1,recover=.43,dmg=105,guard=32,reach=2.28,lunge=2.15,knock=4.,stun=.4,style="zephyr_finisher"),
    "heavy": dict(name="Dragon Tail Break",wind=.29,active=.13,recover=.53,dmg=166,guard=52,reach=2.52,lunge=2.25,knock=5.1,stun=.51,heavy=True,style="zephyr_finisher"),
    "z": dict(name="Serpent Wheel",desc="Three separately defendable revolving staff contacts.",cd=8,wind=.19,active=.59,recover=.41,dmg=51,guard=17,reach=2.35,lunge=2.6,knock=.75,stun=.17,style="zephyr_serpent",multi_hit=3),
    "x": dict(name="Dragon Reversal",desc="Brief counter stance. Failed reads leave you vulnerable.",cd=10,type="buff",mode="counter",duration=.34,wind=.04,active=.04,recover=.53,dmg=0,guard=0,reach=1.,lunge=0,knock=0,stun=0,style="zephyr_reversal"),
    "c": dict(name="Heavenly Cyclone",desc="Five individually defendable staff transitions.",cd=17,wind=.29,active=1.18,recover=.57,dmg=49,guard=16,reach=2.42,lunge=1.8,knock=.7,stun=.16,style="zephyr_cyclone",multi_hit=5),
    "v": dict(name="Ninefold Dragon",desc="Nine timed three-section staff hits, all blockable, parryable and clashable.",cd=42,wind=.4,active=1.90,recover=.75,dmg=33,guard=11,reach=2.36,lunge=1.8,knock=.65,stun=.13,style="zephyr_ninefold",multi_hit=9)
}
# The new kit temporarily reuses tested glaive pose animation names; original
# browser Zephyr authored zd* animations will be brought in after visual tuning.
POSE_ALIASES = {"l1":"l1", "l2":"l2", "l3":"l3", "l4":"l4", "l5":"l5", "heavy":"heavy", "z":"z", "x":"x", "c":"c", "v":"v"}

MODEL_STAFF = r'''
		"tristaff": # FRG19G — visible sanjiekun, three rods and two linked joints
			var root := _pivot(r, Vector3(0, -0.16, 0))
			var rod_mat := _mat(L.metal, true)
			var grip_mat := _mat(L.band)
			for i in range(3):
				var section := _pivot(root)
				_part(section, _cyl(0.024, 0.024, 0.54, 12), rod_mat, Vector3(0, 0.27, 0))
				_part(section, _cyl(0.029, 0.029, 0.10, 12), grip_mat, Vector3(0, 0.11, 0))
				_part(section, _cyl(0.029, 0.029, 0.06, 12), trim, Vector3(0, 0.51, 0))
				if i < 2:
					for j in range(3):
						_part(section, _cyl(0.012, 0.012, 0.065, 10), trim, Vector3(0, 0.56 + float(j) * 0.052, 0))
				zephyr_sections.append(section)
			set_tristaff_mode(0)
			blade_base = _pivot(root, Vector3(0, 0.26, 0))
			blade_tip = _pivot(root, Vector3(0, 1.69, 0))
			cast_point = blade_tip
			shield_node = l
'''
MODEL_MODE = r'''
# FRG19G — grip silhouette preview. Real two-handed IK/choreography follows in 19H.
func set_tristaff_mode(new_mode: int) -> void:
	if zephyr_sections.size() != 3:
		return
	var mode_id: int = posmod(new_mode, 4)
	for section in zephyr_sections:
		if is_instance_valid(section):
			section.rotation = Vector3.ZERO
			section.scale = Vector3.ONE
	match mode_id:
		0: # STAFF: straight three-piece pole
			for i in range(3): zephyr_sections[i].position = Vector3(0, 0.56 * float(i), 0)
		1: # SPLIT: both free ends angled away from the central grip
			zephyr_sections[0].position = Vector3(0, 0, 0)
			zephyr_sections[1].position = Vector3(0, 0.55, 0)
			zephyr_sections[2].position = Vector3(0.17, 0.96, 0)
			zephyr_sections[0].rotation.z = -0.40
			zephyr_sections[2].rotation.z = 0.68
		2: # WHIP: extended, flexing outer rod
			zephyr_sections[0].position = Vector3(0, 0, 0)
			zephyr_sections[1].position = Vector3(0, 0.55, 0)
			zephyr_sections[2].position = Vector3(-0.15, 1.04, 0)
			zephyr_sections[2].rotation.z = -0.72
		3: # FOLDED: shorter, quicker profile
			zephyr_sections[0].position = Vector3(0, 0, 0)
			zephyr_sections[1].position = Vector3(0.085, 0.06, 0)
			zephyr_sections[2].position = Vector3(-0.085, 0.08, 0)
			zephyr_sections[1].rotation.z = PI
			zephyr_sections[2].rotation.z = PI
'''
FIGHTER_FIELDS = r'''
# FRG19G Zephyr: STAFF / SPLIT / WHIP / FOLDED and 25-second Dragon Rhythm.
var in_mode_switch := false
var zephyr_mode := 0
var zephyr_mode_cooldown := 0.0
var zephyr_rhythm_stacks := 0
var zephyr_rhythm_seconds := 0.0
'''
FIGHTER_TICK = r'''
	if kit == "tristaff":
		zephyr_mode_cooldown = maxf(zephyr_mode_cooldown - dt, 0.0)
		if zephyr_rhythm_seconds > 0.0:
			zephyr_rhythm_seconds = maxf(0.0, zephyr_rhythm_seconds - dt)
			if zephyr_rhythm_seconds <= 0.0:
				zephyr_rhythm_stacks = 0
		if in_mode_switch and zephyr_mode_cooldown <= 0.0 and state in [S.IDLE, S.BLOCK]:
			zephyr_mode = (zephyr_mode + 1) % 4
			zephyr_mode_cooldown = 0.38
			if model != null:
				model.set_tristaff_mode(zephyr_mode)
'''
FIGHTER_PASSIVE = r'''
	# Dragon Rhythm earns stacks only on real contacts and defense success.
	if kit == "tristaff" and event_id in ["landed_hit", "blocked", "parried", "clashed", "projectile_destroyed"]:
		zephyr_rhythm_stacks = mini(zephyr_rhythm_stacks + 1, 3)
		zephyr_rhythm_seconds = 25.0
'''
MATCH_MULTI = r'''
# FRG19G — independently timed, defendable strikes (no guaranteed damage).
func _zephyr_schedule_beats(f: Fighter, a: Dictionary) -> void:
	var count: int = int(a.get("multi_hit", 1))
	if count <= 1 or not f.active_melee():
		return
	var serial: int = f.swing_serial
	var round_id: int = _round
	var span: float = float(a.get("active", 0.0)) * f.attack_time_multiplier()
	for beat in range(1, count):
		var wait_time: float = span * float(beat) / float(count)
		later(wait_time, func():
			_zephyr_beat(f, a, serial, round_id, beat))

func _zephyr_beat(f: Fighter, a: Dictionary, serial: int, round_id: int, beat: int) -> void:
	if round_over or _round != round_id or not is_instance_valid(f) or f.is_down():
		return
	if f.swing_serial != serial or not f.active_melee():
		return
	_melee(f, a, beat)
'''

def read_json(root: Path, rel: str):
    try:
        return json.loads((root / rel).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Cannot read {rel}: {exc}") from exc

def jbytes(value) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

def once(code: str, needle: str, replacement: str, file: str) -> str:
    count = code.count(needle)
    if count != 1:
        raise RuntimeError(f"{file}: patch anchor expected 1 occurrence, found {count}: {needle[:75]!r}")
    return code.replace(needle, replacement, 1)

def build(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise RuntimeError("Run from the Godot folder containing project.godot")
    if not (root / "data/browser_zenith_19f.json").is_file():
        raise RuntimeError("Requires Update 19F (Zenith) first")
    roster = read_json(root, "data/roster.json")
    attacks = read_json(root, "data/attacks.json")
    poses = read_json(root, "data/poses.json")
    stats = read_json(root, "data/stats.json")
    if not isinstance(roster, list) or not all(isinstance(v, dict) for v in (attacks, poses, stats)):
        raise RuntimeError("Unexpected roster / attacks / poses / stats JSON schema")
    ids = [v.get("id") for v in roster]
    if len(set(ids)) != len(ids) or CHARACTER in ids or CHARACTER in attacks or "tristaff" in stats:
        raise RuntimeError("Zephyr already exists or roster contains duplicates; refusing to overwrite")
    if "zarek" not in attacks or "glaive" not in stats or "glaive" not in poses:
        raise RuntimeError("Expected 19B Glaive data is missing")
    anim = root / "animations/glaive.tres"
    if not anim.is_file():
        raise RuntimeError("Missing animations/glaive.tres (needed as first-pass rig pose template)")

    roster.append({"id": CHARACTER, "title": "Dragon Dancer", "role": "Martial Artist - Three-Section Staff",
        "desc": "Four staff grips, defensive counters and Dragon Rhythm earned by successful combat contacts.",
        "stats": {"power":4,"speed":4,"range":3,"defense":4}, "look":deepcopy(LOOK)})
    stats["tristaff"] = {"hp":2670,"guard":82,"move":3.90,"walk":3.05,"parry":0.205,"jump":7.9}
    poses["tristaff"] = deepcopy(poses["glaive"])
    new_attacks = {}
    for key, change in MOVES.items():
        alias = POSE_ALIASES[key]
        if alias not in attacks["zarek"]:
            raise RuntimeError(f"Missing Glaive reference move {alias}")
        attack = deepcopy(attacks["zarek"][alias])
        attack.update(deepcopy(change))
        attack["id"] = key
        attack["element"] = "dragon"
        attack["next"] = change.get("next", "")
        attack["type"] = change.get("type", "melee")
        attack["heavy"] = bool(change.get("heavy", False))
        attack["cd"] = float(change.get("cd", 0))
        attack["multi_hit"] = int(change.get("multi_hit", 1))
        attack["mode"] = change.get("mode", "")
        attack["duration"] = float(change.get("duration", 0))
        attack["pose_w"] = attacks["zarek"][alias]["pose_w"]
        attack["pose_s"] = attacks["zarek"][alias]["pose_s"]
        for posefield in ("pose_w", "pose_s"):
            if attack[posefield] not in poses["tristaff"]:
                raise RuntimeError(f"Zephyr {key} has missing pose: {attack[posefield]}")
        new_attacks[key] = attack
    attacks[CHARACTER] = new_attacks
    result = {
        "data/roster.json": jbytes(roster),
        "data/attacks.json": jbytes(attacks),
        "data/stats.json": jbytes(stats),
        "data/poses.json": jbytes(poses),
        "animations/tristaff.tres": anim.read_bytes(),
    }

    path = "scripts/fighter_model.gd"
    code = (root / path).read_text(encoding="utf-8")
    code = once(code, "var blade_base: Node3D", "var zephyr_sections: Array[Node3D] = [] # FRG19G\nvar blade_base: Node3D", path)
    code = once(code, '\t\t"hammer": # FRG19D', MODEL_STAFF + '\t\t"hammer": # FRG19D', path)
    code = once(code, 'func _build_weapons() -> void:\n', MODEL_MODE + '\nfunc _build_weapons() -> void:\n', path)
    result[path] = code.encode("utf-8")

    path = "scripts/keys.gd"
    code = (root / path).read_text(encoding="utf-8")
    code = once(code, '\t["skill1", "Skill 1"],', '\t["mode", "Switch staff grip"], # FRG19G\n\t["skill1", "Skill 1"],', path)
    code = once(code, '\t"skill1": ["k:%d" % KEY_Z, ""],', '\t"mode": ["k:%d" % KEY_F, ""], # FRG19G\n\t"skill1": ["k:%d" % KEY_Z, ""],', path)
    result[path] = code.encode("utf-8")

    path = "scripts/player_brain.gd"
    code = (root / path).read_text(encoding="utf-8")
    code = once(code, 'var _dodge_pending := false', 'var _mode_pending := false # FRG19G\nvar _dodge_pending := false', path)
    code = once(code, 'if Keys.matches("dodge", e): _dodge_pending = true',
                'if Keys.matches("dodge", e): _dodge_pending = true\n\t\tif Keys.matches("mode", e): _mode_pending = true', path)
    code = once(code, '\tf.in_sprint = Keys.held("sprint")\n',
                '\tf.in_sprint = Keys.held("sprint")\n\tif f.kit == "tristaff" and _mode_pending: f.in_mode_switch = true\n\t_mode_pending = false\n', path)
    result[path] = code.encode("utf-8")

    path = "scripts/fighter.gd"
    code = (root / path).read_text(encoding="utf-8")
    code = once(code, 'var zenith_magnetic_stacks := 0', FIGHTER_FIELDS + 'var zenith_magnetic_stacks := 0', path)
    code = once(code, 'in_attack = false; in_block = false; in_jump = false;',
                'in_mode_switch = false; in_attack = false; in_block = false; in_jump = false;', path)
    code = once(code, '\t# FRG19F Zenith: consecutive landed hits refresh the 5s charge duration.\n',
                FIGHTER_TICK + '\t# FRG19F Zenith: consecutive landed hits refresh the 5s charge duration.\n', path)
    code = once(code, 'func notify_passive_event(event_id: String, other: Node = null) -> void:\n',
                'func notify_passive_event(event_id: String, other: Node = null) -> void:\n' + FIGHTER_PASSIVE, path)
    code = once(code, '\treturn summary\n\n# FRG15D - status HUD and countdown indicators\n',
                '\tif kit == "tristaff":\n\t\tvar tag: String = ["STAFF", "SPLIT", "WHIP", "FOLDED"][zephyr_mode] + " · Rhythm x%d" % zephyr_rhythm_stacks\n\t\treturn tag if summary.is_empty() else tag + ", " + summary\n\treturn summary\n\n# FRG15D - status HUD and countdown indicators\n', path)
    code = once(code, '\treturn (1.0 / maxf(1.0 - 0.02 * float(guard_fatigue), 0.5)) * status_runtime.attack_time_multiplier() / (factor * metal_factor)\n',
                '\tvar dragon_mode_speed: float = [1.0, 1.20, 0.94, 1.50][zephyr_mode] if kit == "tristaff" else 1.0\n'
                '\tvar dragon_rhythm_speed: float = 1.0 + 0.20 * float(zephyr_rhythm_stacks) if kit == "tristaff" else 1.0\n'
                '\treturn (1.0 / maxf(1.0 - 0.02 * float(guard_fatigue), 0.5)) * status_runtime.attack_time_multiplier() / (factor * metal_factor * dragon_mode_speed * dragon_rhythm_speed)\n', path)
    code = once(code, '\tatk = attacks[aid]\n',
                '\tatk = attacks[aid].duplicate(true)\n'
                '\tif kit == "tristaff" and String(atk.get("type", "melee")) == "melee":\n'
                '\t\tmatch zephyr_mode:\n'
                '\t\t\t1: atk["reach"] = float(atk.reach) * 1.07\n'
                '\t\t\t2: atk["reach"] = float(atk.reach) * 1.20\n'
                '\t\t\t3: atk["reach"] = float(atk.reach) * 0.75\n', path)
    code = once(code, '\tvar dmg: float = float(a.dmg) * power * status_runtime.incoming_multiplier()\n',
                '\tvar dmg: float = float(a.dmg) * power * status_runtime.incoming_multiplier()\n'
                '\t# Staff mastery reduces normal damage; SPLIT grip trades guard for speed.\n'
                '\tif kit == "tristaff": dmg *= 1.08 if zephyr_mode == 1 else 0.90\n', path)
    code = once(code, '\tif state == S.BLOCK:\n\t\tif state_t <= parry_window',
                '\tif state == S.BLOCK and not (kit == "tristaff" and zephyr_mode == 1):\n\t\tif state_t <= parry_window', path)
    result[path] = code.encode("utf-8")

    path = "scripts/match.gd"
    code = (root / path).read_text(encoding="utf-8")
    code = once(code, '\tmatch a.type:\n\t\t"projectile": _fire(f, a)\n',
                '\tif f.kit == "tristaff" and String(a.get("type", "")) == "melee":\n\t\t_zephyr_schedule_beats(f, a)\n'
                '\tmatch a.type:\n\t\t"projectile": _fire(f, a)\n', path)
    code = once(code, 'func _active_melee_contact(f: Fighter) -> void:\n',
                MATCH_MULTI + '\nfunc _active_melee_contact(f: Fighter) -> void:\n', path)
    code = once(code, 'func _melee(f: Fighter, a: Dictionary) -> void:',
                'func _melee(f: Fighter, a: Dictionary, beat: int = 0) -> void:', path)
    code = once(code, 'var contact_key := "%d:%d" % [f.id, f.swing_serial]',
                'var contact_key := "%d:%d:%d" % [f.id, f.swing_serial, beat]', path)
    code = once(code, 'var other_key := "%d:%d" % [d.id, d.swing_serial]',
                'var other_key := "%d:%d:0" % [d.id, d.swing_serial]', path)
    result[path] = code.encode("utf-8")

    ai_path = "data/ai_personalities.json"
    if (root / ai_path).exists():
        ai = read_json(root, ai_path)
        if not isinstance(ai, dict) or not isinstance(ai.get("fighters"), dict):
            raise RuntimeError("Unsupported AI personalities schema")
        ai["fighters"][CHARACTER] = {"archetype":"glaive", "attack_pace":1.12,
            "skill_pace":1.08, "approach_scale":1.03, "orbit_scale":1.16, "parry_scale":1.12}
        result[ai_path] = jbytes(ai)
    result["data/browser_zephyr_19g.json"] = jbytes({
        "version":VERSION,"character":CHARACTER,"browser_reference":BROWSER,
        "status":"FIRST PLAYABLE PORT — browser choreography parity not yet reached",
        "included":["five-hit staff light combo","heavy tail break","three-hit Serpent Wheel",
                    "Dragon Reversal counter","five-hit Heavenly Cyclone","nine-hit Ninefold Dragon",
                    "four F-key grip modes","Dragon Rhythm 3 stacks (25 seconds)",
                    "3 visibly segmented staff rods with linked joints"],
        "pending":["per-mode authored attack variants","exact three-section staff physics and two-hand IK",
                   "mode-switch flourish attacks","mode-specific block and parry tuning",
                   "unique zd* pose animation library","character-specific AI switching and combo selection",
                   "verified gameplay tests in Godot"]})
    result["reports/zephyr_19g.txt"] = (
        "Fight Royale Update 19G — Zephyr Dragon Dancer\n"
        "First playable port with 4 grip modes (F), five basic attacks, three special multi-contact attacks, a counter and Rhythm.\n"
        "The fighter requires animations/tristaff.tres (installed automatically).\n"
        "Add models/zephyr.vrm, then open Godot Editor once to import the VRM.\n"
        "F is mapped through Settings > Controls as Switch staff grip.\n"
        "Temporary pose source: glaive; bespoke three-section staff IK follows.\n"
        "No shop, economy, online, teams or survival changes.\n"
        ).encode("utf-8")
    return result

def digest(data: bytes | None):
    return hashlib.sha256(data).hexdigest() if data is not None else None

def atomic(path: Path, value: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".frg19g-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def install(root: Path, dry: bool):
    if (root / "data/browser_zephyr_19g.json").exists():
        print("Update 19G already installed; no changes.")
        return
    output = build(root)
    changed = {rel: new for rel, new in output.items()
               if not (root/rel).exists() or (root/rel).read_bytes() != new}
    for rel in changed:
        print("Update:", rel)
    if dry:
        print("Dry run OK; no files changed.")
        return
    target = root.parent / (root.name + "_backups") / (
        "zephyr_19g_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    target.mkdir(parents=True, exist_ok=False)
    manifest = {"version":VERSION,"project":str(root),"files":{}}
    for rel, new in changed.items():
        old = (root/rel).read_bytes() if (root/rel).is_file() else None
        manifest["files"][rel] = {"before":digest(old),"after":digest(new)}
        if old is not None:
            saved = target / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(old)
    (target / "manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    completed = []
    try:
        for rel,new in changed.items():
            atomic(root/rel,new)
            completed.append(rel)
    except BaseException:
        for rel in reversed(completed):
            old = target/rel
            if old.is_file():
                atomic(root/rel,old.read_bytes())
            else:
                (root/rel).unlink(missing_ok=True)
        raise
    print("Installed Zephyr 19G. Backup:", target)

def restore(root: Path, saved: Path):
    manifest=read_json(saved,"manifest.json")
    if manifest.get("project") != str(root):
        raise RuntimeError("Backup belongs to another project")
    for rel,meta in manifest["files"].items():
        current = (root/rel).read_bytes() if (root/rel).is_file() else None
        if digest(current) != meta["after"]:
            raise RuntimeError(f"Cannot restore {rel}: file changed since installation")
    for rel,meta in manifest["files"].items():
        old = saved/rel
        if meta["before"] is None:
            (root/rel).unlink(missing_ok=True)
        else:
            atomic(root/rel,old.read_bytes())
    print("Restored:",saved)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--restore", type=Path)
    args=p.parse_args()
    root=Path.cwd().resolve()
    try:
        if args.restore: restore(root,args.restore.expanduser().resolve())
        else: install(root,args.dry_run)
    except Exception as exc:
        print("ERROR:",exc,file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
