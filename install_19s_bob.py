#!/usr/bin/env python3
"""Fight Royale Godot Update 19S — Bob: Mad Bomber.

Run from the Godot project directory:
    python install_19s_bob.py

Optional: --dry-run, --restore PATH.
Requires Update 19R. Preserves existing fighters, sound files, and VRMs.

Reference (2026-11-10):
https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts
The mine cap is TWO per the user's later balance preference (browser file says three).
This is a first playable port, not a claim of exact full browser choreography.
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

VERSION = "19S.1"
MARKER = "FRG19S"
SOURCE = "https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts"

LOOK = {
    "name": "Bob", "body": "m", "vrm": "bob", "kit": "bomb", "element": "blast",
    "outfit": "mage", "style": "messy", "hat": "goggles", "hair": "#65402f",
    "hair_shade": "#a86b35", "iris_top": "#f5a623", "iris_bottom": "#ffd46e",
    "eye_dark": "#503019", "tunic": "#a45427", "band": "#f2b651",
    "pants": "#352a35", "boots": "#322522", "metal": "#d7b78c",
    "trim": "#ffce71", "cape": "#5d3029", "cape_bottom": "#b25528",
    "glow": "#ff9e35", "shield": "#71523b", "emblem": "#f7d45e",
}

# Browser kit attack figures translated into Godot's existing Attack schema.
# Poses temporarily use compatible mage throws; custom Bob animation is a follow-up.
MOVES = {
  "l1": dict(type="lob", wind=.22, active=.05, recover=.36, dmg=35, guard=10, knock=1.3, stun=.20, delay=.65, radius=.8, style="bomb", size=.7, next="l2"),
  "l2": dict(type="lob", wind=.22, active=.05, recover=.38, dmg=40, guard=10, knock=1.5, stun=.20, delay=.65, radius=.8, style="bomb", size=.7, next="l3"),
  "l3": dict(type="lob", wind=.30, active=.05, recover=.50, dmg=28, guard=8, knock=2.0, stun=.25, delay=.70, radius=.8, count=3, spread=.35, style="bomb", size=.6, next=""),
  "heavy": dict(type="lob", wind=.30, active=.05, recover=.70, dmg=150, guard=40, knock=5, stun=.5, heavy=True, delay=1.0, radius=1.5, style="bomb", size=1.8, next=""),
  "z": dict(name="Land Mine", desc="Plant up to two armed mines; store up to four charges.", cd=8, type="mine", wind=.18, active=.05, recover=.30, dmg=110, guard=30, knock=4, stun=.5, radius=1.2, style="mine"),
  "x": dict(name="Paralyze Bomb", desc="Lob a crackling bomb that paralyzes enemies in the blast.", cd=11, type="lob", wind=.22, active=.05, recover=.45, dmg=65, guard=20, knock=1.5, stun=.3, delay=.65, radius=1.5, style="bomb", size=1.3, apply_status="paralyze", status_duration=1.5),
  "c": dict(name="Powder Keg", desc="Set down a keg; press the same skill again to detonate it.", cd=18, type="barrel", wind=.3, active=.05, recover=.50, dmg=200, guard=55, knock=6, stun=.7, heavy=True, radius=2.0, style="powder_keg"),
  "v": dict(name="Cluster Bomb", desc="Four distinct explosions around a warning circle.", cd=10, type="lob", wind=.2, active=.05, recover=.4, dmg=80, guard=22, knock=4, stun=.45, delay=.85, radius=1.5, repeat=4, interval=.12, style="clusterbomb", size=1.65),
}

BOB_RUNTIME = '# FRG19S — Bob\'s bomb objects. Independent of ordinary projectile clashes,\n# explosions occur at the recorded landing position and can be dodged/guarded.\nfunc _bob_prop(radius: float, color: Color, kind: String) -> Node3D:\n    var node := Node3D.new()\n    node.name = "Bob" + kind\n    add_child(node)\n    var shell := MeshInstance3D.new()\n    var ball := SphereMesh.new()\n    ball.radius = radius\n    ball.height = radius * 2.0\n    shell.mesh = ball\n    shell.material_override = Fx.unlit(color)\n    node.add_child(shell)\n    var fuse := MeshInstance3D.new()\n    var fuse_mesh := CylinderMesh.new()\n    fuse_mesh.height = 0.13\n    fuse_mesh.top_radius = 0.027\n    fuse_mesh.bottom_radius = 0.027\n    fuse.mesh = fuse_mesh\n    fuse.position = Vector3(0, radius + 0.05, 0)\n    fuse.material_override = Fx.unlit(Color("#ffe29c"))\n    node.add_child(fuse)\n    return node\n\nfunc _bob_throw(f: Fighter, a: Dictionary, power: float) -> void:\n    if f.is_down() or round_over: return\n    var destination: Vector3 = f.opponent.position if f.opponent != null else f.position + f.forward() * 4.0\n    destination.y = 0.05\n    var offset: Vector3 = destination - f.position\n    offset.y = 0.0\n    if offset.length() > 8.5: destination = f.position + offset.normalized() * 8.5\n    var is_cluster: bool = String(a.get("style", "")) == "clusterbomb"\n    var count: int = 4 if is_cluster else maxi(1, int(a.get("count", 1)))\n    var base_delay: float = maxf(0.15, float(a.get("delay", 0.65)))\n    if is_cluster: fx.telegraph(destination, Color("#ffa047"), float(a.get("radius", 1.5)) * 2.0, base_delay + 0.36)\n    for i in range(count):\n        var scatter := Vector3.ZERO\n        if is_cluster:\n            scatter = Vector3(cos(TAU * float(i) / 4.0), 0, sin(TAU * float(i) / 4.0)) * 0.82\n        elif count > 1:\n            scatter = Vector3(float(i) - float(count - 1) * 0.5, 0, 0) * float(a.get("spread", .35)) * 2.0\n        var landing: Vector3 = destination + scatter\n        landing.y = 0.05\n        var launch: Vector3 = f.chest() + f.forward() * 0.3\n        var orb := _bob_prop(0.085 * float(a.get("size", 1.0)), Color("#ea9537"), "Lob19S")\n        orb.global_position = launch\n        var travel: float = base_delay + (float(i) * float(a.get("interval", .12)) if is_cluster else 0.0)\n        _bob_lobs.append({"node":orb, "owner":f, "from":launch, "to":landing,\n            "flight":0.0, "duration":travel, "atk":a.duplicate(true), "power":power})\n    fx.flash(f.chest(), Color("#ffbd6b"), 0.25, 0.12, 0.7)\n\nfunc _bob_place_mine(f: Fighter, a: Dictionary, power: float) -> void:\n    if f.is_down() or f.bob_mine_charges <= 0: return\n    f.bob_mine_charges -= 1\n    if f.bob_mine_charges == 3 and f.bob_mine_recharge <= 0.0: f.bob_mine_recharge = 8.0\n    # Additional charges can be used immediately; the replenishment timer is independent.\n    f.cooldowns[f.atk_id] = 0.0\n    var owned: Array[Dictionary] = []\n    for rec in _bob_mines:\n        if rec.get("owner") == f: owned.append(rec)\n    if owned.size() >= 2:\n        var oldest: Dictionary = owned[0]\n        if is_instance_valid(oldest.get("node")): oldest["node"].queue_free()\n        _bob_mines.erase(oldest)\n    var mine := _bob_prop(0.17, Color("#db713c"), "Mine19S")\n    mine.scale.y = 0.43\n    mine.global_position = Vector3(f.position.x, 0.09, f.position.z)\n    _bob_mines.append({"node":mine, "owner":f, "team":f.team, "atk":a.duplicate(true),\n        "power":power, "arm":0.5, "life":30.0})\n    fx.ring(mine.global_position, Color("#ffb552"), 0.7, 0.24, 0.7)\n\nfunc _bob_plant_keg(f: Fighter, a: Dictionary, power: float) -> void:\n    if f.is_down() or f.bob_barrel_active: return\n    var keg := Node3D.new()\n    keg.name = "BobPowderKeg19S"\n    add_child(keg)\n    var barrel := MeshInstance3D.new()\n    var cylinder := CylinderMesh.new()\n    cylinder.top_radius = .27\n    cylinder.bottom_radius = .27\n    cylinder.height = .66\n    barrel.mesh = cylinder\n    barrel.material_override = Fx.unlit(Color("#70432e"))\n    keg.add_child(barrel)\n    var band := MeshInstance3D.new()\n    var band_mesh := CylinderMesh.new()\n    band_mesh.top_radius = .28\n    band_mesh.bottom_radius = .28\n    band_mesh.height = .10\n    band.mesh = band_mesh\n    band.position.y = .18\n    band.material_override = Fx.unlit(Color("#dba85e"))\n    keg.add_child(band)\n    keg.global_position = f.position + f.forward() * 1.0 + Vector3(0, .35, 0)\n    _bob_kegs.append({"node":keg, "owner":f, "team":f.team, "atk":a.duplicate(true),\n        "power":power, "life":20.0})\n    f.bob_barrel_active = true\n    f.bob_barrel_skill_key = f.atk_id\n    f.cooldowns[f.atk_id] = 0.0  # cooldown starts on detonation, not placement\n    fx.ring(keg.global_position, Color("#f4b45b"), 1.0, .30, .8)\n\nfunc _bob_detonate_keg(f: Fighter) -> void:\n    for rec in _bob_kegs.duplicate():\n        if rec.get("owner") != f: continue\n        _bob_explode_at(f, rec["atk"], float(rec["power"]), rec["node"].global_position)\n        if is_instance_valid(rec.get("node")): rec["node"].queue_free()\n        _bob_kegs.erase(rec)\n        f.bob_barrel_active = false\n        if not f.bob_barrel_skill_key.is_empty():\n            f.cooldowns[f.bob_barrel_skill_key] = float(rec["atk"].get("cd", 18.0)) * f.cd_mult\n        f.bob_barrel_skill_key = ""\n        return\n\nfunc _bob_explode_at(owner: Fighter, atk: Dictionary, power: float, pos: Vector3) -> void:\n    if not is_instance_valid(owner) or owner.is_down() or round_over: return\n    var center := Vector3(pos.x, 0.0, pos.z)\n    var radius := float(atk.get("radius", 1.2))\n    _impact(atk, center, Color("#ff9e3d"), radius)\n    for d in enemies_of(owner):\n        if not is_instance_valid(d) or d.is_down(): continue\n        var to: Vector3 = d.position - center\n        to.y = 0.0\n        if to.length() > radius + d.radius * .5 or d.airborne(): continue\n        var direction: Vector3 = to.normalized() if to.length() > .05 else owner.forward()\n        apply_hit(owner, d, atk, power, d.chest(), direction, true)\n\nfunc _bob_step(dt: float) -> void:\n    if dt <= 0.0 or round_over: return\n    for rec in _bob_lobs.duplicate():\n        var node: Node3D = rec["node"]\n        var owner: Fighter = rec["owner"]\n        if not is_instance_valid(node) or not is_instance_valid(owner) or owner.is_down():\n            if is_instance_valid(node): node.queue_free()\n            _bob_lobs.erase(rec)\n            continue\n        rec["flight"] = float(rec["flight"]) + dt\n        var duration: float = maxf(.01, float(rec["duration"]))\n        var t: float = clampf(float(rec["flight"]) / duration, 0.0, 1.0)\n        node.global_position = rec["from"].lerp(rec["to"], t) + Vector3(0, 2.0 * sin(PI * t), 0)\n        node.rotation.z += dt * 4.0\n        if t >= 1.0:\n            _bob_explode_at(owner, rec["atk"], float(rec["power"]), rec["to"])\n            node.queue_free()\n            _bob_lobs.erase(rec)\n    for rec in _bob_mines.duplicate():\n        var node: Node3D = rec["node"]\n        var owner: Fighter = rec["owner"]\n        if not is_instance_valid(node) or not is_instance_valid(owner) or owner.is_down():\n            if is_instance_valid(node): node.queue_free()\n            _bob_mines.erase(rec)\n            continue\n        rec["arm"] = float(rec["arm"]) - dt\n        rec["life"] = float(rec["life"]) - dt\n        if float(rec["life"]) <= 0.0:\n            node.queue_free()\n            _bob_mines.erase(rec)\n            continue\n        if float(rec["arm"]) > 0.0: continue\n        for d in enemies_of(owner):\n            if d.position.distance_to(node.global_position) > float(rec["atk"].get("radius", 1.2)): continue\n            _bob_explode_at(owner, rec["atk"], float(rec["power"]), node.global_position)\n            node.queue_free()\n            _bob_mines.erase(rec)\n            break\n    for rec in _bob_kegs.duplicate():\n        var node: Node3D = rec["node"]\n        var owner: Fighter = rec["owner"]\n        if not is_instance_valid(node) or not is_instance_valid(owner) or owner.is_down():\n            if is_instance_valid(owner):\n                owner.bob_barrel_active = false\n                owner.bob_barrel_skill_key = ""\n            if is_instance_valid(node): node.queue_free()\n            _bob_kegs.erase(rec)\n            continue\n        rec["life"] = float(rec["life"]) - dt\n        var triggered: bool = float(rec["life"]) <= 0.0\n        if not triggered:\n            for d in enemies_of(owner):\n                var flat: Vector3 = d.position - node.global_position\n                flat.y = 0.0\n                if d.active_melee() and flat.length() < float(d.atk.get("reach", 1.5)) + .25:\n                    triggered = true\n                    break\n        if not triggered:\n            for p in _projectiles.duplicate():\n                if int(p.get("team", -1)) == owner.team: continue\n                if not is_instance_valid(p.get("node")): continue\n                if p["node"].global_position.distance_to(node.global_position) > .58: continue\n                p["node"].queue_free()\n                _projectiles.erase(p)\n                triggered = true\n                break\n        if triggered: _bob_detonate_keg(owner)\n'



def enc(o):
    return (json.dumps(o, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

def read_json(root: Path, relative: str):
    try:
        return json.loads((root / relative).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise RuntimeError(f"Cannot read {relative}: {e}") from e

def patch(t: str, before: str, after: str, name: str) -> str:
    count = t.count(before)
    if count != 1:
        raise RuntimeError(f"{name}: anchor expected once, found {count}: {before[:80]!r}. No changes made")
    return t.replace(before, after, 1)

def build(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise RuntimeError("Run inside your Godot project folder (project.godot not found)")
    if not (root / "data/browser_kira_19r.json").is_file():
        raise RuntimeError("Install Update 19R before Update 19S")
    roster = read_json(root, "data/roster.json")
    attacks = read_json(root, "data/attacks.json")
    stats = read_json(root, "data/stats.json")
    poses = read_json(root, "data/poses.json")
    if any(x.get("id") == "bob" for x in roster) or "bob" in attacks:
        raise RuntimeError("Bob already exists; refusing to overwrite your fighter")
    if len(roster) != len({x.get("id") for x in roster}):
        raise RuntimeError("Existing roster has duplicate IDs")
    if not all(key in poses for key in ["mage"]) or "raven" not in attacks:
        raise RuntimeError("Missing mage poses or reference attacks")
    if "bomb" in stats or "bomb" in poses or (root / "animations/bomb.tres").exists():
        raise RuntimeError("Existing bomb assets found; audit manually before installing")

    roster.append({"id":"bob", "title":"Mad Bomber", "role":"Explosives - Trap Specialist",
                   "desc":"Lobbed firecrackers, stored land mines, paralyzing bombs, a remote powder keg, and a four-blast cluster.",
                   "stats":{"power":4,"speed":3,"range":5,"defense":2}, "look": deepcopy(LOOK)})
    stats["bomb"] = {"hp":2100, "guard":70, "move":3.5, "walk":2.8, "parry":.16, "jump":7.0}
    # Preexisting mage poses map to valid imported animation tracks, no bone re-rigging needed.
    poses["bomb"] = deepcopy(poses["mage"])
    bases = attacks["raven"]
    mapped = {}
    for key, changes in MOVES.items():
        based = bases["l1" if key.startswith("l") else "heavy" if key == "heavy" else "z"]
        a = deepcopy(based)
        a.update(changes)
        a["id"] = key
        a["element"] = "blast"
        a["pose_w"] = "mh_w" if key in ["heavy","c","v"] else "m1_w"
        a["pose_s"] = "mh_s" if key in ["heavy","c","v"] else "m1_s"
        a["reach"] = 1.75
        a["lunge"] = 0
        a["at"] = "target"
        a["pierce"] = False
        a["count"] = 3 if key == "l3" else 1
        a["repeat"] = 4 if key == "v" else 1
        a["spread"] = .35 if key == "l3" else 0
        a["interval"] = .12 if key == "v" else .3
        a["next"] = changes.get("next", "")
        mapped[key] = a
    attacks["bob"] = mapped
    files = {
        "data/roster.json": enc(roster),
        "data/attacks.json": enc(attacks),
        "data/stats.json": enc(stats),
        "data/poses.json": enc(poses),
        "animations/bomb.tres": (root / "animations/mage.tres").read_bytes(),
    }

    rel = "scripts/fighter.gd"
    s = (root / rel).read_text(encoding="utf-8")
    s = patch(s,
        'const RANGED_REST := {"mage": 1.2, "bow": 1.3}',
        'const RANGED_REST := {"mage": 1.2, "bow": 1.3, "bomb": 1.2} # FRG19S', rel)
    s = patch(s, 'var kira_air_strikes := 0\n',
        """var kira_air_strikes := 0
# FRG19S — Bob: four stored mine charges, a single active powder keg.
var bob_mine_charges := 4
var bob_mine_recharge := 0.0
var bob_barrel_active := false
var bob_barrel_skill_key := ""
var bob_barrel_request := false
""", rel)
    s = patch(s, 'func status_summary() -> String:\n\tvar summary:',
        """func status_summary() -> String:
	# FRG19S — Bob's remote keg and mine charges are readable in both modes.
	if kit == "bomb":
		var btext: String = "MINES %d/4" % bob_mine_charges
		if bob_barrel_active: btext += " · KEG ARMED"
		return btext
	var summary:""", rel)
    s = patch(s, '\tfor k in cooldowns: cooldowns[k] = maxf(cooldowns[k] - dt, 0.0)\n',
        """	# FRG19S: restore one stored mine every 8s, up to four.
	if kit == "bomb" and bob_mine_charges < 4:
		bob_mine_recharge -= dt
		if bob_mine_recharge <= 0.0:
			bob_mine_charges += 1
			bob_mine_recharge = 8.0 if bob_mine_charges < 4 else 0.0
	for k in cooldowns: cooldowns[k] = maxf(cooldowns[k] - dt, 0.0)
""", rel)
    s = patch(s, '\t# FRG19C: X recast reels a previously bound enemy to Kaizen (even during X cooldown).\n',
        """	# FRG19S: pressing the assigned Powder Keg key again requests its explosion.
	# This bypasses its cooldown only while a placed keg exists; otherwise normal rules apply.
	if kit == "bomb" and bob_barrel_active and in_skill != "" and in_skill == bob_barrel_skill_key:
		bob_barrel_request = true
		in_skill = ""
		_queued_skill = ""
		_queued_skill_t = 0.0
		return
	if kit == "bomb" and in_skill != "" and attacks.has(in_skill):
		if String(attacks[in_skill].get("type", "")) == "mine" and bob_mine_charges <= 0:
			in_skill = ""
			return
	# FRG19C: X recast reels a previously bound enemy to Kaizen (even during X cooldown).
""", rel)
    files[rel] = s.encode("utf-8")

    rel = "scripts/ai_brain.gd"
    s = (root / rel).read_text(encoding="utf-8")
    s = patch(s, 'const RANGED := ["mage", "bow"]', 'const RANGED := ["mage", "bow", "bomb"] # FRG19S', rel)
    s = patch(s, '\t\t"projectile":\n\t\t\treturn dist >= 1.1 and dist < 10.5\n',
        """		"projectile", "lob":
			return dist >= 1.1 and dist < 10.5
		"mine":
			return dist < 5.2 and f.bob_mine_charges > 0
		"barrel":
			return dist < 6.5
""", rel)
    s = patch(s, '\t\t\t"projectile":\n\t\t\t\tscore += 0.55 if dist > 3.0 else 0.05\n',
        """			"projectile", "lob":
				score += 0.55 if dist > 3.0 else 0.05
			"mine":
				score += 0.65 if dist < 3.4 else 0.30
			"barrel":
				score += 0.80 if dist < 4.0 else 0.20
""", rel)
    files[rel] = s.encode("utf-8")

    rel = "scripts/fighter_model.gd"
    s = (root / rel).read_text(encoding="utf-8")
    s = patch(s, '\tmatch kit:\n\n\n\t\t"tristaff":',
        """	match kit:
		"bomb": # FRG19S: two-handed grenade maker; no magic staff.
			var right_bomb := _pivot(r, Vector3(0, 0.12, 0))
			_part(right_bomb, _sph(0.095), _mat(L.metal, true), Vector3.ZERO)
			_part(right_bomb, _cyl(0.034, 0.034, 0.065, 12), trim, Vector3(0, 0.11, 0))
			_part(right_bomb, _box(0.022, 0.10, 0.022), glow, Vector3(0.025, 0.17, 0))
			var pouch := _pivot(l, Vector3(-0.03, -0.06, 0))
			_part(pouch, _box(0.18, 0.16, 0.13), _mat(L.band), Vector3(0, 0.04, 0))
			_part(pouch, _box(0.19, 0.045, 0.15), trim, Vector3(0, 0.13, 0))
			blade_base = right_bomb
			blade_tip = _pivot(right_bomb, Vector3(0, 0.18, 0))
			cast_point = _pivot(r, Vector3(0, 0.19, 0.06))
			shield_node = l

		"tristaff":""", rel)
    files[rel] = s.encode("utf-8")

    rel = "scripts/match.gd"
    s = (root / rel).read_text(encoding="utf-8")
    s = patch(s, 'var _projectiles: Array = []    # dictionaries\n',
        """var _projectiles: Array = []    # dictionaries
# FRG19S — Bob's round-scoped bomb actors; never survive a restart.
var _bob_lobs: Array[Dictionary] = []
var _bob_mines: Array[Dictionary] = []
var _bob_kegs: Array[Dictionary] = []
""", rel)
    s = patch(s, '\tfor f in fighters: f.queue_free()\n',
        """	# FRG19S: remove all bombs, mines and kegs before changing rounds.
	for rec in _bob_lobs + _bob_mines + _bob_kegs:
		if is_instance_valid(rec.get("node")): rec["node"].queue_free()
	_bob_lobs.clear(); _bob_mines.clear(); _bob_kegs.clear()
	for f in fighters: f.queue_free()
""", rel)
    s = patch(s, 'if String(slot.peer).begins_with("cpu"): f.auto_approach = not f.kit in ["mage", "bow"]',
        'if String(slot.peer).begins_with("cpu"): f.auto_approach = not f.kit in ["mage", "bow", "bomb"] # FRG19S', rel)
    s = patch(s, '\t\tif dt > 0.0:\n\t\t\tf.tick(dt)\n',
        """		if dt > 0.0:
			f.tick(dt)
			# FRG19S: remote keg input is sampled after the player's/CPU's brain runs.
			if f.kit == "bomb" and f.bob_barrel_request:
				f.bob_barrel_request = false
				_bob_detonate_keg(f)
""", rel)
    s = patch(s, '\t_update_projectiles(dt)\n\t_roxy_step_puppets(dt)\n',
        """	_update_projectiles(dt)
	_bob_step(dt) # FRG19S: real-time bomb travel and armed trap checks.
	_roxy_step_puppets(dt)
""", rel)
    s = patch(s, '\tmatch a.type:\n\t\t"projectile": _fire(f, a)\n',
        """	match a.type:
		"lob": _bob_throw(f, a, f.atk_power) # FRG19S
		"mine": _bob_place_mine(f, a, f.atk_power)
		"barrel": _bob_plant_keg(f, a, f.atk_power)
		"projectile": _fire(f, a)
""", rel)
    s = patch(s, '\t\t"explosion", "meteor":\n\t\t\tfx.explosion(g, color, radius);',
        '\t\t"explosion", "meteor", "bomb", "clusterbomb", "mine", "powder_keg":\n\t\t\tfx.explosion(g, color, radius);', rel)
    s = patch(s, '\tif style_sound in ["explosion", "meteor"]:\n',
        '\tif style_sound in ["explosion", "meteor", "bomb", "clusterbomb", "mine", "powder_keg"]: # FRG19S\n', rel)
    s = patch(s, '# FRG19R — Phantom Step: staggerable, 3 independent timed kicks.\n', BOB_RUNTIME + '\n# FRG19R — Phantom Step: staggerable, 3 independent timed kicks.\n', rel)
    files[rel] = s.encode("utf-8")

    files["data/browser_bob_19s.json"] = enc({
        "version": VERSION, "fighter": "bob", "name": "Bob / Mad Bomber", "source": SOURCE,
        "status": "FIRST PLAYABLE PORT — runtime Godot validation still required",
        "details": ["3 throwing attacks plus charged bomb", "Z: stored mine charges 4 (two active maximum)",
                    "X: Paralyze Bomb on real damage", "C: planted Powder Keg with remote recast and enemy attack trigger",
                    "V: four distinct cluster blasts", "Round-scoped cleanup and visible bomb actors"],
        "pending": ["Unique Bob VRM and per-joint throw animations", "Exact browser charge recharge UI", "Godot gameplay smoke test"]
    })
    files["reports/bob_19s.txt"] = (
        "Fight Royale Godot 19S — Bob / Mad Bomber\n"
        "Browser kit: Lob, Land Mine, Paralyze Bomb, Powder Keg, Cluster Bomb.\n"
        "Two mine placements maximum; four stored charges.\n"
        "VRM models/bob.vrm optional; fallback avatar remains visible after import.\n"
        "Open the project in Godot editor to import models.\n"
        "Python install validated; actual Godot engine validation pending.\n"
    ).encode("utf-8")
    return files


def sha(blob: bytes | None):
    return hashlib.sha256(blob).hexdigest() if blob is not None else None


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".frg19s-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fp:
            fp.write(data); fp.flush(); os.fsync(fp.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def install(root: Path, dry_run: bool):
    if (root / "data/browser_bob_19s.json").is_file():
        print("Update 19S already installed; no changes.")
        return
    changes = build(root)
    changed = {name: blob for name, blob in changes.items()
               if not (root / name).is_file() or (root / name).read_bytes() != blob}
    for name in changed: print("Update:", name)
    if dry_run:
        print("19S dry-run passed; no project files changed.")
        return
    backup = root.parent / (root.name + "_backups") / (
        "bob_19s_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for rel, blob in changed.items():
        old = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest["files"][rel] = {"before":sha(old), "after":sha(blob)}
        if old is not None:
            saved = backup / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(old)
    (backup / "manifest.json").write_text(json.dumps(manifest,indent=2) + "\n",encoding="utf-8")
    done = []
    try:
        for rel, blob in changed.items():
            atomic_write(root / rel, blob); done.append(rel)
    except BaseException:
        for rel in reversed(done):
            saved = backup / rel
            if saved.is_file(): atomic_write(root / rel, saved.read_bytes())
            else: (root / rel).unlink(missing_ok=True)
        raise
    print("Installed Update 19S. Backup:", backup)


def restore(root: Path, backup: Path):
    info = read_json(backup, "manifest.json")
    if info.get("project") != str(root): raise RuntimeError("Backup belongs to another project")
    for rel, meta in info["files"].items():
        cur = (root / rel).read_bytes() if (root / rel).is_file() else None
        if sha(cur) != meta["after"]: raise RuntimeError("File changed since install: " + rel)
    for rel, meta in info["files"].items():
        saved = backup / rel
        if meta["before"] is None: (root / rel).unlink(missing_ok=True)
        else: atomic_write(root / rel, saved.read_bytes())
    print("Restored", backup)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--restore", type=Path)
    args = p.parse_args()
    try:
        root = Path.cwd().resolve()
        if args.restore: restore(root, args.restore.resolve())
        else: install(root, args.dry_run)
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
