#!/usr/bin/env python3
"""Fight Royale Godot Update 19T — Gale: Wind Dancer (first playable port).

Run in the Godot project directory: python install_19t_gale.py
Optional: --dry-run or --restore /path/to/backup
Requires 19S. Adds Gale without changing Duel vs CPU or CPU vs CPU.

Browser source used: https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts
Wind fighting style, quick punches, air dives and double jump are source-derived;
V remains an explicitly provisional Godot implementation. This does not claim
full browser animation parity.
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

VERSION = "19T.1"
MARKER = "FRG19T"

LOOK = {
    "name": "Gale", "body": "m", "vrm": "gale", "kit": "wind", "element": "wind",
    "outfit": "fighter", "style": "spiky", "hat": "", "hair": "#e4edf2",
    "hair_shade": "#97b9c3", "iris_top": "#31b6b3", "iris_bottom": "#9dfbe5",
    "eye_dark": "#17484a", "tunic": "#296e80", "band": "#9fe8e8",
    "pants": "#21384c", "boots": "#163040", "metal": "#cce4e8", "trim": "#78e9dc",
    "cape": "#226f83", "cape_bottom": "#0b3f5a", "glow": "#72f4dd",
    "shield": "#4aadb0", "emblem": "#c6ffed",
}

# The browser's wind() kit, with animation names adapted to existing knuckles.tres.
# The 4th slot (v) is a temporary Godot-exclusive finisher; do not mistake it
# for a canonical browser ultimate. Air variants are selected on activation.
MOVES = {
    "l1": dict(name="Wind Jab", type="melee", wind=.10, active=.06, recover=.14,
               dmg=46, guard=12, reach=1.55, lunge=3, knock=1.2, stun=.26,
               pose_w="k1_w", pose_s="k1_s", next="l2"),
    "l2": dict(name="Crosswind Hook", type="melee", wind=.10, active=.06, recover=.16,
               dmg=50, guard=12, reach=1.55, lunge=3, knock=1.4, stun=.28,
               pose_w="k2_w", pose_s="k2_s", next="l3"),
    "l3": dict(name="Tempest Uppercut", type="melee", wind=.17, active=.08, recover=.34,
               dmg=80, guard=22, reach=1.70, lunge=4, knock=4.5, stun=.45,
               pose_w="kh_w", pose_s="kh_s", next=""),
    "heavy": dict(name="Wind Breaker", type="projectile", wind=.12, active=.05,
                  recover=.50, dmg=200, guard=55, knock=6, stun=.70, heavy=True,
                  speed=18, size=1.7, style="shock", pierce=True,
                  pose_w="kh_w", pose_s="kh_s", next=""),
    "z": dict(name="Gale Fist", desc="Fast forward punch wrapped in wind.", cd=4,
              type="melee", wind=.14, active=.08, recover=.30, dmg=110,
              guard=30, reach=1.9, lunge=4, knock=5, stun=.50,
              pose_w="k1_w", pose_s="k1_s", air_variant="z_air"),
    "x": dict(name="Wind Step", desc="Quick dash strike through opponents.", cd=5,
              type="melee", wind=.10, active=.16, recover=.30, dmg=90,
              guard=25, reach=1.6, lunge=15, knock=3, stun=.40,
              pose_w="k2_w", pose_s="k2_s", air_variant="x_air"),
    "c": dict(name="Tornado Rise", desc="Rising whirlwind, three area pulses.", cd=15,
              type="strike", at="self", self_jump=9, wind=.08, active=.12,
              recover=.40, dmg=60, guard=20, knock=3, stun=.60,
              delay=.03, radius=2, repeat=3, interval=.14, style="spin",
              pose_w="kh_w", pose_s="kh_s", air_variant="c_air"),
    "v": dict(name="Tempest Finale", desc="Provisional Godot ultimate: a large four-pulse wind burst.",
              cd=20, type="strike", at="self", wind=.20, active=.10, recover=.75,
              dmg=85, guard=28, knock=4, stun=.60, delay=.12, radius=2.8,
              repeat=4, interval=.20, style="spin", heavy=True,
              pose_w="slam_w", pose_s="slam_s"),
    "z_air": dict(name="Downburst", type="strike", at="self", mode="gale_dive",
                  gale_smash=True, speed=26, lunge=2, wind=.08, active=.05,
                  recover=.40, dmg=130, guard=35, knock=6, stun=.60,
                  delay=.02, radius=2.2, style="slam", pose_w="slam_air", pose_s="slam_s"),
    "x_air": dict(name="Falling Star", type="strike", at="self", mode="gale_dive",
                  gale_smash=True, speed=22, lunge=11, wind=.06, active=.05,
                  recover=.45, dmg=160, guard=40, knock=6, stun=.80,
                  delay=.02, radius=1.8, style="slam", heavy=True,
                  pose_w="slam_air", pose_s="slam_s"),
    "c_air": dict(name="Hurricane Crash", type="strike", at="self", mode="gale_dive",
                  gale_smash=True, speed=28, lunge=4, wind=.10, active=.05,
                  recover=.60, dmg=80, guard=30, knock=7, stun=1.0,
                  delay=.02, radius=3, repeat=3, interval=.18, style="slam",
                  heavy=True, pose_w="slam_air", pose_s="slam_s"),
}


def encode_json(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def read_json(root: Path, rel: str):
    try:
        return json.loads((root / rel).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Cannot read {rel}: {exc}") from exc


def replace_once(text: str, old: str, new: str, rel: str) -> str:
    number = text.count(old)
    if number != 1:
        raise RuntimeError(f"{rel}: expected one anchor, found {number}: {old[:110]!r}")
    return text.replace(old, new, 1)


def build(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise RuntimeError("Run inside the Godot project folder (project.godot missing)")
    if not (root / "data/browser_bob_19s.json").is_file():
        raise RuntimeError("Install Update 19S before Update 19T")
    roster = read_json(root, "data/roster.json")
    attacks = read_json(root, "data/attacks.json")
    stats = read_json(root, "data/stats.json")
    poses = read_json(root, "data/poses.json")
    if len(roster) != len({x.get('id') for x in roster}):
        raise RuntimeError("Existing roster already contains duplicate IDs")
    if any(c.get("id") == "gale" for c in roster) or "gale" in attacks:
        raise RuntimeError("Gale exists already; refusing to overwrite another fighter")
    if "wind" in poses or "wind" in stats or (root / "animations/wind.tres").exists():
        raise RuntimeError("Wind kit assets already exist; no blind overwrite")
    if "knuckles" not in poses or "rook" not in attacks:
        raise RuntimeError("Existing knuckles reference moves/poses not present")
    if not (root / "animations/knuckles.tres").is_file():
        raise RuntimeError("Missing reference animation library: animations/knuckles.tres")
    for move in ("l1", "l2", "l3", "heavy", "z", "x", "c", "v"):
        if move not in attacks["rook"]:
            raise RuntimeError(f"Rook reference move missing: {move}")
    if not (root / "scripts/match.gd").is_file():
        raise RuntimeError("Missing match.gd")

    roster.append({
        "id": "gale", "title": "Wind Dancer", "role": "Fast Airborne Brawler",
        "desc": "Double-jumps, fast punch chains and converts grounded skills into dive smashes while airborne. Smash hits reduce skill cooldowns by 10%.",
        "stats": {"power": 3, "speed": 5, "range": 2, "defense": 2},
        "look": deepcopy(LOOK),
    })
    stats["wind"] = {"hp": 2200, "guard": 80, "move": 4.1, "walk": 3.3,
                     "parry": .20, "jump": 8.4}
    poses["wind"] = deepcopy(poses["knuckles"])
    source = attacks["rook"]
    kit = {}
    for key, changes in MOVES.items():
        base = source["l1" if key.startswith("l") and key != "heavy" else
                      "heavy" if key == "heavy" else "z"]
        data = deepcopy(base)
        data.update(changes)
        data["id"] = key
        data["element"] = "wind"
        if key in ("z", "x", "c", "v"):
            data["next"] = ""
        if key in ("z_air", "x_air", "c_air"):
            data["cd"] = 0  # original skill slot owns cooldown
            data["next"] = ""
            data["self_jump"] = 0
            data["count"] = 1
            data["pierce"] = False
        kit[key] = data
    attacks["gale"] = kit
    changes = {
        "data/roster.json": encode_json(roster),
        "data/attacks.json": encode_json(attacks),
        "data/stats.json": encode_json(stats),
        "data/poses.json": encode_json(poses),
        "animations/wind.tres": (root / "animations/knuckles.tres").read_bytes(),
        "data/browser_gale_19t.json": encode_json({
            "update": VERSION, "fighter": "gale", "kit": "wind",
            "source": "https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts",
            "abilities": ["Gale Fist", "Wind Step", "Tornado Rise"],
            "air_variants": ["Downburst", "Falling Star", "Hurricane Crash"],
            "ultimate_v": "provisional Tempest Finale (not claimed browser-equivalent)",
            "passive": "Confirmed air dive smash hit reduces each equipped skill's remaining cooldown by 10% of its base cooldown.",
            "animation": "Temporary use of existing knuckles pose library; custom wind pose kit later",
            "modes": ["Duel vs CPU", "CPU vs CPU"],
        }),
    }

    rel = "scripts/fighter.gd"
    s = (root / rel).read_text(encoding="utf-8")
    s = replace_once(s, 'var bob_barrel_request := false\n',
        '''var bob_barrel_request := false
# FRG19T — Gale: one extra mid-air jump, both jumps reset on landing.
var gale_jumps := 0
''', rel)
    s = replace_once(s, 'func _read_jump() -> void:\n\tvar pressed := in_jump and not _jump_prev\n\t_jump_prev = in_jump\n',
        '''func _read_jump() -> void:
	var pressed := in_jump and not _jump_prev
	_jump_prev = in_jump
	# FRG19T: double jump works with both player and CPU input; no editor rigging.
	if kit == "wind" and pressed and not on_ground and gale_jumps == 1 and state in [S.IDLE, S.BLOCK]:
		vel_y = jump_v * 0.88
		gale_jumps = 2
		if state == S.BLOCK: _set_state(S.IDLE)
		return
''', rel)
    s = replace_once(s, '\t\tvel_y = jump_v\n\t\ton_ground = false\n\t\tif state == S.BLOCK: _set_state(S.IDLE)\n',
        '''		vel_y = jump_v
		on_ground = false
		if kit == "wind": gale_jumps = 1
		if state == S.BLOCK: _set_state(S.IDLE)
''', rel)
    s = replace_once(s, '\t\tposition.y = 0.0; vel_y = 0.0; on_ground = true\n\t\tlanded.emit(self)\n',
        '''		position.y = 0.0; vel_y = 0.0; on_ground = true
		if kit == "wind": gale_jumps = 0
		landed.emit(self)
''', rel)
    s = replace_once(s, '\tatk = attacks[aid].duplicate(true)\n',
        '''	atk = attacks[aid].duplicate(true)
	# FRG19T: use the equipped skill's own aerial version when Gale is airborne.
	if kit == "wind" and not on_ground and aid in ["z", "x", "c", "v"]:
		var air_variant: String = String(atk.get("air_variant", ""))
		if not air_variant.is_empty() and attacks.has(air_variant):
			atk = attacks[air_variant].duplicate(true)
			atk["id"] = aid
''', rel)
    s = replace_once(s, '\tif float(atk.self_jump) > 0.0 and atk.mode != "leap":\n',
        '''	if kit == "wind" and float(atk.self_jump) > 0.0 and on_ground:
		gale_jumps = 1
	if float(atk.self_jump) > 0.0 and atk.mode != "leap":
''', rel)
    s = replace_once(s, 'func _attack_step() -> void:\n\tvar w: float = float(atk.wind) * attack_time_multiplier()\n',
        '''func _attack_step() -> void:
	var w: float = float(atk.wind) * attack_time_multiplier()
''', rel)
    s = replace_once(s, '\tvar r: float = float(atk.recover) * attack_time_multiplier()\n\tif atk.mode == "leap":\n',
        '''	var r: float = float(atk.recover) * attack_time_multiplier()
	# FRG19T: genuine aerial dive, with one slam on actual touchdown.
	# No airborne instant-hit and no repeating the touchdown callback.
	if kit == "wind" and String(atk.get("mode", "")) == "gale_dive":
		if atk_phase == 0 and state_t >= w:
			atk_phase = 1
			vel_y = -maxf(float(atk.get("speed", 24.0)), 12.0)
			if opponent != null and not opponent.is_down():
				var delta: Vector3 = opponent.position - position
				delta.y = 0.0
				_leap_vel = delta.normalized() * minf(float(atk.get("lunge", 2.0)), delta.length() * 2.0)
			else:
				_leap_vel = forward() * minf(float(atk.get("lunge", 2.0)), 4.0)
		elif atk_phase == 1:
			if on_ground:
				atk_phase = 2
				state_t = w + ac
				_leap_vel = Vector3.ZERO
				swing.emit(self)
			elif state_t > w + 2.0:
				_leap_vel = Vector3.ZERO
				_finish_attack()
				_set_state(S.IDLE)
		elif atk_phase == 2 and state_t >= w + ac + r:
			_finish_attack()
			_set_state(S.IDLE)
		return
	if atk.mode == "leap":
''', rel)
    s = replace_once(s, 'if state == S.ATTACK and atk.get("mode", "") == "leap" and atk_phase == 1:',
        'if state == S.ATTACK and String(atk.get("mode", "")) in ["leap", "gale_dive"] and atk_phase == 1: # FRG19T', rel)
    s = replace_once(s, 'func status_summary() -> String:\n\t# FRG19S',
        '''func status_summary() -> String:
	# FRG19T: display Gale's double-jump state in both modes.
	if kit == "wind":
		return "DOUBLE JUMP %d/2 | SMASH -10%% CD" % gale_jumps
	# FRG19S''', rel)
    changes[rel] = s.encode("utf-8")

    rel = "scripts/fighter_model.gd"
    s = (root / rel).read_text(encoding="utf-8")
    s = replace_once(s, '\tmatch kit:\n\t\t"bomb": # FRG19S',
        '''	match kit:
		"wind": # FRG19T — lightweight glowing wind wraps on both fists.
			for grip in [r, l]:
				_part(grip, _box(0.105, 0.085, 0.105), _mat(L.metal, true), Vector3(0.03, 0, 0))
				_part(grip, _box(0.12, 0.015, 0.12), glow, Vector3(0.03, 0.05, 0))
			blade_base = _pivot(r, Vector3(0, 0.02, 0))
			blade_tip = _pivot(r, Vector3(0.14, 0.0, 0))
			cast_point = _pivot(r, Vector3(0, 0.16, 0.13))
			shield_node = l
		"bomb": # FRG19S''', rel)
    changes[rel] = s.encode("utf-8")

    rel = "scripts/match.gd"
    s = (root / rel).read_text(encoding="utf-8")
    s = replace_once(s, '\tvar result := d.receive_hit(attacker, incoming_attack, delivered_power)\n',
        '''	var result := d.receive_hit(attacker, incoming_attack, delivered_power)
	# FRG19T: only confirmed Gale dive-smash HP hits refund cooldowns.
	# One victim per duel; blocked/parried/invulnerable hits grant nothing.
	if attacker is Fighter and attacker.kit == "wind" and bool(a.get("gale_smash", false)) and result in ["hit", "crit", "ko"]:
		for key in ["z", "x", "c"]:
			var own_skill: Dictionary = attacker.attacks.get(key, {})
			var base_cd: float = float(own_skill.get("cd", 0.0)) * attacker.cd_mult
			attacker.cooldowns[key] = maxf(0.0, float(attacker.cooldowns.get(key, 0.0)) - base_cd * 0.10)
''', rel)
    s = replace_once(s, '\t# FRG18A: small selection of per-element and skill-impact sounds.\n',
        '''	# FRG19T: the wind smash has a pale vortex rim without new shaders.
	if bool(a.get("gale_smash", false)):
		fx.ring(g + Vector3(0, 0.1, 0), Color("#9afbe9"), radius * 1.25, 0.28, 0.85)
	# FRG18A: small selection of per-element and skill-impact sounds.
''', rel)
    changes[rel] = s.encode("utf-8")

    for rel, personality in [
        ("data/ai_personalities.json", {"archetype": "knuckles", "attack_pace": 1.30,
                                        "orbit_scale": 1.45, "approach_scale": 1.30,
                                        "dodge_scale": 1.26, "jump_scale": 1.30}),
        ("data/ai_tactics_13b.json", {"guard_pressure": 1.2, "guard_reset_threshold": .22,
                                      "skill_bias": {"z": .20, "x": .16, "c": .10}}),
    ]:
        obj = read_json(root, rel)
        fighters = obj.get("fighters")
        if not isinstance(fighters, dict):
            raise RuntimeError(f"{rel} does not contain fighters dictionary")
        if "gale" in fighters:
            raise RuntimeError(f"{rel}: Gale personality exists; refusing overwrite")
        fighters["gale"] = personality
        changes[rel] = encode_json(obj)
    return changes


def checksum(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".frg19t-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def install(root: Path, dry_run: bool) -> None:
    if (root / "data/browser_gale_19t.json").is_file():
        print("19T already installed; no changes")
        return
    changes = build(root)  # Preflight verifies every anchor before touching disk.
    modified = {rel: data for rel, data in changes.items()
                if not (root / rel).is_file() or (root / rel).read_bytes() != data}
    for rel in modified:
        print("Update:", rel)
    if dry_run:
        print("19T dry-run passed; no project files changed")
        return
    backup = root.parent / (root.name + "_backups") / (
        "gale_19t_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    info = {"version": VERSION, "project": str(root), "files": {}}
    for rel, data in modified.items():
        previous = (root / rel).read_bytes() if (root / rel).is_file() else None
        info["files"][rel] = {"before": checksum(previous), "after": checksum(data)}
        if previous is not None:
            file_path = backup / rel
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(previous)
    (backup / "manifest.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    written = []
    try:
        for rel, data in modified.items():
            atomic_write(root / rel, data)
            written.append(rel)
    except BaseException:
        for rel in reversed(written):
            saved = backup / rel
            if saved.is_file():
                atomic_write(root / rel, saved.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print("19T installed. Backup:", backup)
    print("Gale VRM: models/gale.vrm (optional; fallback avatar will be used if absent)")


def restore(root: Path, backup: Path) -> None:
    manifest = read_json(backup, "manifest.json")
    if manifest.get("project") != str(root):
        raise RuntimeError("Backup belongs to a different project")
    for rel, hashes in manifest["files"].items():
        current = (root / rel).read_bytes() if (root / rel).is_file() else None
        if checksum(current) != hashes["after"]:
            raise RuntimeError("Cannot restore because a file changed after install: " + rel)
    for rel, hashes in manifest["files"].items():
        previous = backup / rel
        if hashes["before"] is None:
            (root / rel).unlink(missing_ok=True)
        else:
            atomic_write(root / rel, previous.read_bytes())
    print("Restored:", backup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args()
    try:
        root = Path.cwd().resolve()
        if args.restore:
            restore(root, args.restore.resolve())
        else:
            install(root, args.dry_run)
        return 0
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
