#!/usr/bin/env python3
"""Fight Royale Godot — 19P: Marina, Water Mage / Healing Water.

Run in the Godot project folder: python install_19p_marina.py
Optional: --dry-run; --restore PATH_TO_BACKUP

Requires 19O. Changes only the existing Marina fighter kit and shared combat
hooks needed for her defensive bubble and timed healing pool. No shop/modes.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

VERSION = "19P.1"

def read_json(root: Path, rel: str):
    try:
        return json.loads((root / rel).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"{rel}: {exc}") from exc

def json_bytes(data) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

def replace_exact(src: str, old: str, new: str, rel: str) -> str:
    found = src.count(old)
    if found != 1:
        raise RuntimeError(f"{rel}: expected exactly one anchor {old[:90]!r}, found {found}; project unchanged")
    return src.replace(old, new, 1)

def build(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise RuntimeError("project.godot not found. Run inside your Godot project.")
    if not (root / "data/browser_rook_19o.json").is_file():
        raise RuntimeError("Install Update 19O before Update 19P.")
    roster = read_json(root, "data/roster.json")
    marina = [r for r in roster if r.get("id") == "marina"]
    if len(marina) != 1 or marina[0].get("look", {}).get("kit") != "mage" or marina[0].get("look", {}).get("element") != "water":
        raise RuntimeError("Expected the original Marina (mage/water), exactly once.")
    attacks = read_json(root, "data/attacks.json")
    m = attacks.get("marina")
    if not isinstance(m, dict) or any(k not in m for k in ("l1", "l2", "l3", "heavy", "z", "x", "c", "v")):
        raise RuntimeError("Existing Marina skill table incomplete; aborting.")
    if m["z"].get("name") != "Bubble Ward" or m["c"].get("name") != "Ocean Requiem" or m["v"].get("name") not in ("Healing Water", "Healing Rain"):
        raise RuntimeError("Unrecognized Marina kit. No changes applied.")
    if not (root / "animations/mage.tres").is_file():
        raise RuntimeError("Missing mage animation library.")
    m["z"].update(type="buff", mode="marina_bubble", duration=5.0, cd=17.0,
                  dmg=0, guard=0, desc="A 5-second water bubble halves incoming HP damage, not guard damage. Marina can still be KO'd.")
    m["v"].update(name="Healing Water", type="buff", mode="healing_water", duration=5.0, radius=2.6, cd=15.0,
                  dmg=0, guard=0, desc="A 5-second water pool; allies inside heal 3.5% max HP every 0.6s, up to 28% each per cast.")
    # Keep Tidal Ring and Ocean Requiem's original strength and delivery.
    for key in ("x", "c"):
        m[key]["apply_status"] = "slow"
        m[key]["status_duration"] = 3.0
        m[key]["status_chance"] = 1.0
        m[key]["status_stacks"] = 1
    changes = {"data/attacks.json": json_bytes(attacks)}

    rel = "scripts/fighter.gd"
    src = (root / rel).read_text(encoding="utf-8")
    src = replace_exact(src, "var ward_t := 0.0\n", "var ward_t := 0.0\n# FRG19P — Marina's Bubble Ward mitigates HP damage, never makes her immune.\nvar marina_bubble_t := 0.0\n", rel)
    src = replace_exact(src, "\tward_t = maxf(ward_t - dt, 0.0)\n", "\tward_t = maxf(ward_t - dt, 0.0)\n\tmarina_bubble_t = maxf(marina_bubble_t - dt, 0.0) # FRG19P\n", rel)
    src = replace_exact(src,
        '\tif kit == "mage" and String(look.get("element", "")) == "fire":\n',
        '\t# FRG19P — separate Marina bubble timer visible in both game modes.\n'
        '\tif kit == "mage" and String(look.get("element", "")) == "water" and marina_bubble_t > 0.0:\n'
        '\t\tvar bubble_tag: String = "BUBBLE %.1fs · 50%% HP DMG" % marina_bubble_t\n'
        '\t\treturn bubble_tag if summary.is_empty() else bubble_tag + ", " + summary\n'
        '\tif kit == "mage" and String(look.get("element", "")) == "fire":\n', rel)
    src = replace_exact(src,
        '\tvar dmg: float = float(a.dmg) * power * status_runtime.incoming_multiplier()\n',
        '\tvar dmg: float = float(a.dmg) * power * status_runtime.incoming_multiplier()\n'
        '\t# FRG19P: halve HP damage before guard-break chip calculation, not guard loss.\n'
        '\tif kit == "mage" and String(look.get("element", "")) == "water" and marina_bubble_t > 0.0:\n'
        '\t\tdmg *= 0.5\n', rel)
    changes[rel] = src.encode("utf-8")

    rel = "scripts/match.gd"
    src = (root / rel).read_text(encoding="utf-8")
    src = replace_exact(src,
        'var _ember_patches: Array[Dictionary] = []\n',
        'var _ember_patches: Array[Dictionary] = []\n'
        '# FRG19P — team-aware healing pools, cleared each round.\n'
        'var _marina_pools: Array[Dictionary] = []\n', rel)
    src = replace_exact(src,
        '\t_ember_patches.clear()\n\tfighters.clear();',
        '\t_ember_patches.clear()\n'
        '\tfor water_pool in _marina_pools:\n'
        '\t\tif is_instance_valid(water_pool["node"]): water_pool["node"].queue_free()\n'
        '\t_marina_pools.clear()\n'
        '\tfighters.clear();', rel)
    src = replace_exact(src,
        '\t_ember_step_patches(dt) # FRG19N: no burning-ground ticks during pause\n',
        '\t_ember_step_patches(dt) # FRG19N: no burning-ground ticks during pause\n'
        '\t_marina_step_pools(dt) # FRG19P: heal only while simulation advances\n', rel)
    src = replace_exact(src,
        '\tmatch a.mode:\n\t\t"ember_ignition":',
        '\tmatch a.mode:\n'
        '\t\t"marina_bubble": # FRG19P: HP damage mitigation, not the old invincible ward.\n'
        '\t\t\tf.marina_bubble_t = float(a.get("duration", 5.0))\n'
        '\t\t\tfx.ring(f.position, Color("#73d8ff"), 1.6, 0.30, 0.8)\n'
        '\t\t\tfx.number(f.chest() + Vector3(0, 0.8, 0), "BUBBLE WARD", Color("#a5efff"), 0.8)\n'
        '\t\t"healing_water":\n'
        '\t\t\tif f.kit == "mage" and String(f.look.get("element", "")) == "water":\n'
        '\t\t\t\t_marina_spawn_pool(f, a)\n'
        '\t\t"ember_ignition":', rel)
    anchor = '# FRG19N — Ember ground fire: four max per caster, 20 seconds each.\n'
    functions = '''# FRG19P — Healing Water is a real area, not an instant self-heal.
func _marina_spawn_pool(caster: Fighter, attack: Dictionary) -> void:
    if not is_instance_valid(caster) or caster.is_down() or round_over: return
    var radius: float = float(attack.get("radius", 2.6))
    var marker := MeshInstance3D.new()
    var mesh := CylinderMesh.new()
    mesh.top_radius = 1.0
    mesh.bottom_radius = 1.0
    mesh.height = 0.02
    marker.mesh = mesh
    marker.material_override = Fx.unlit(Color("#5fbde2"), 0.30, true)
    marker.scale = Vector3(radius, 1.0, radius)
    add_child(marker)
    marker.global_position = Vector3(caster.position.x, 0.05, caster.position.z)
    _marina_pools.append({"node": marker, "owner": caster, "team": caster.team,
        "center": Vector3(caster.position.x, 0.0, caster.position.z),
        "radius": radius, "seconds": float(attack.get("duration", 5.0)),
        "pulse": 0.0, "healed": {}})
    fx.ring(caster.position, Color("#9aeaff"), radius, 0.40, 0.75)
    fx.number(caster.chest() + Vector3(0, 0.8, 0), "HEALING WATER", Color("#a8ffff"), 0.85)

func _marina_step_pools(dt: float) -> void:
    if dt <= 0.0 or round_over: return
    for pool in _marina_pools.duplicate():
        var owner: Fighter = pool["owner"]
        pool["seconds"] = float(pool["seconds"]) - dt
        if not is_instance_valid(owner) or owner.is_down():
            pool["seconds"] = 0.0
        if float(pool["seconds"]) <= 0.0:
            if is_instance_valid(pool["node"]): pool["node"].queue_free()
            _marina_pools.erase(pool)
            continue
        pool["pulse"] = float(pool["pulse"]) + dt
        if float(pool["pulse"]) < 0.6: continue
        pool["pulse"] = float(pool["pulse"]) - 0.6
        for ally in fighters:
            if ally.team != int(pool["team"]) or ally.is_down(): continue
            var delta: Vector3 = ally.position - pool["center"]
            delta.y = 0.0
            if delta.length() > float(pool["radius"]) + ally.radius * 0.2: continue
            var ledger: Dictionary = pool["healed"]
            var key: String = str(ally.id)
            var pulses: int = int(ledger.get(key, 0))
            if pulses >= 8: continue # eight pulses * 3.5% = 28% per fighter.
            ledger[key] = pulses + 1
            var amount: float = ally.max_hp * 0.035
            ally.heal(amount)
            fx.motes(ally.position + Vector3(0.0, 0.55, 0.0), Color("#89f6ef"), 4)
            fx.number(ally.chest() + Vector3(0.0, 0.35, 0.0), "+%d" % int(amount), Color("#a8ffe9"), 0.55)

'''
    src = replace_exact(src, anchor, functions + anchor, rel)
    changes[rel] = src.encode("utf-8")
    changes["data/browser_marina_19p.json"] = json_bytes({
        "version": VERSION, "character": "marina", "state": "FIRST PLAYABLE REFINEMENT",
        "source": "https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts",
        "changes": [
            "Bubble Ward: 5s, 50% incoming HP damage reduction, 17s cooldown; guard unchanged",
            "Healing Water: visible pool at cast point, 5s lifetime, radius 2.6",
            "Healing Water pulses every 0.6s for 3.5% max HP; eight-pulse 28% cap",
            "Pool allies/owner only, range checks each pulse, no healing outside it",
            "Tidal Ring and Ocean Requiem apply 3s slow on successful damaging contact",
            "Preserve original projectile attacks, mage animation library, other mages and fighter IDs",
        ],
        "pending": ["Godot VRM visual alignment and gameplay testing", "water-specific particle effects and pose polish"],
    })
    changes["reports/marina_19p.txt"] = (
        "19P — Marina / Water Mage\n"
        "Z Bubble Ward: 5s, 50% incoming HP damage, does not block KO, 17s cooldown.\n"
        "V Healing Water: 5s water pool, radius 2.6, 3.5% maximum HP every 0.6s, maximum 28%.\n"
        "X Tidal Ring and C Ocean Requiem: slow for 3s on a real hit.\n"
        "VRM assets and other characters preserved.\n"
        "Python static tests do not replace Godot engine playtesting.\n"
    ).encode("utf-8")
    return changes

def sha(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None

def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".frg19p-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)

def install(root: Path, dry_run: bool) -> None:
    if (root / "data/browser_marina_19p.json").is_file():
        print("Update 19P already installed; no changes.")
        return
    changes = build(root)  # All anchors and dependencies checked before any write.
    altered = {rel: blob for rel, blob in changes.items() if not (root / rel).is_file() or (root / rel).read_bytes() != blob}
    for rel in altered: print("Update:", rel)
    if dry_run:
        print("19P dry run passed; no files changed.")
        return
    backup = root.parent / (root.name + "_backups") / ("marina_19p_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for rel, blob in altered.items():
        old = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest["files"][rel] = {"before": sha(old), "after": sha(blob)}
        if old is not None:
            saved = backup / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(old)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    completed = []
    try:
        for rel, blob in altered.items():
            atomic_write(root / rel, blob)
            completed.append(rel)
    except BaseException:
        for rel in reversed(completed):
            previous = backup / rel
            if previous.is_file(): atomic_write(root / rel, previous.read_bytes())
            else: (root / rel).unlink(missing_ok=True)
        raise
    print("19P installed. Backup:", backup)

def restore(root: Path, backup: Path) -> None:
    manifest = read_json(backup, "manifest.json")
    if manifest.get("project") != str(root):
        raise RuntimeError("Backup belongs to a different project.")
    for rel, item in manifest["files"].items():
        present = (root / rel).read_bytes() if (root / rel).is_file() else None
        if sha(present) != item["after"]:
            raise RuntimeError("File changed after installation; restore aborted: " + rel)
    for rel, item in manifest["files"].items():
        prior = backup / rel
        if item["before"] is None: (root / rel).unlink(missing_ok=True)
        else: atomic_write(root / rel, prior.read_bytes())
    print("Restored:", backup)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    try:
        if args.restore: restore(root, args.restore.expanduser().resolve())
        else: install(root, args.dry_run)
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
