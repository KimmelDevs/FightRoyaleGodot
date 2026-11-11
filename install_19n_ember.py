#!/usr/bin/env python3
"""Fight Royale Godot 19N — Ember / Flame Witch first playable refinement.

Run: python install_19n_ember.py
Optional: --dry-run | --restore BACKUP_DIRECTORY
Requires Update 19M. Only Ember's skill table is rebalanced.
Adds 20-second ground-fire hazards, basic burn status, and a consumptive
Absolute Combustion beam. Full browser VFX choreography is future work.
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

VERSION = "19N.1"
MARKER = "FRG19N"


def read_json(root: Path, rel: str):
    try:
        return json.loads((root / rel).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Cannot read {rel}: {exc}") from exc


def as_bytes(obj) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def replace_once(source: str, old: str, new: str, rel: str) -> str:
    n = source.count(old)
    if n != 1:
        raise RuntimeError(f"{rel}: expected exactly one anchor ({old[:85]!r}), found {n}; no files written")
    return source.replace(old, new, 1)


def build(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise RuntimeError("Run inside the Godot project directory (project.godot missing)")
    if not (root / "data/browser_kaede_19m.json").is_file():
        raise RuntimeError("Update 19M must be installed first")
    roster = read_json(root, "data/roster.json")
    ember = [r for r in roster if r.get("id") == "ember"]
    if len(ember) != 1 or ember[0].get("look", {}).get("element") != "fire" or ember[0].get("look", {}).get("kit") != "mage":
        raise RuntimeError("Original Ember (fire mage) must be present exactly once")
    if not (root / "animations/mage.tres").is_file():
        raise RuntimeError("Missing Ember's existing mage animation library")
    attacks = read_json(root, "data/attacks.json")
    t = attacks.get("ember")
    if not isinstance(t, dict) or not all(s in t for s in ("l1", "l2", "l3", "heavy", "z", "x", "c", "v")):
        raise RuntimeError("Original Ember's eight attacks are required")
    if t["z"].get("name") != "Flame Burst" or t["c"].get("name") != "Meteor" or t["v"].get("name") != "Inferno Ring":
        raise RuntimeError("Unexpected Ember attack data; refusing blind changes")
    # Current browser fire mage has 0.85x basic damage and reduced blast radii.
    for aid, damage in (("l1", 46.75), ("l2", 51.0), ("l3", 35.7)):
        t[aid]["dmg"] = damage
    t["heavy"].update(dmg=155, radius=1.05, wind=0.15, active=0.05,
        recover=0.55, delay=0.50, style="explosion", fire_patch=True,
        desc="Charged fire blast leaves a burning patch for 20 seconds.")
    t["z"].update(dmg=95, radius=2.3, cd=6, apply_status="burn",
        status_duration=4.0)
    t["x"].update(dmg=31, count=5, speed=16, spread=0.45, cd=7,
        apply_status="burn", status_duration=4.0)
    t["c"].update(dmg=215, radius=2.1, delay=0.9, cd=12,
        fire_patch=True, apply_status="burn", status_duration=4.0,
        desc="Drop a meteor at the target and leave burning ground for 20 seconds.")
    t["v"].update(name="Absolute Combustion", type="buff", mode="ember_ignition",
        wind=0.50, active=0.06, recover=0.80, cd=16,
        dmg=0, radius=0.0, repeat=1, count=1, apply_status="", fire_patch=False,
        pose_w="mh_w", pose_s="mh_s",
        desc="Consume your fire patches and an enemy's active burn to amplify a white-hot directional beam.")
    changes: dict[str, bytes] = {"data/attacks.json": as_bytes(attacks)}

    # 15A's status registry does not have burn yet. Use its existing DOT runtime.
    rules = read_json(root, "data/status_rules_15a.json")
    effects = rules.get("effects")
    if not isinstance(effects, dict):
        raise RuntimeError("15A status rules are missing effects dictionary")
    if "burn" in effects:
        raise RuntimeError("An existing burn status definition was found; refusing to overwrite its behavior")
    effects["burn"] = {
        "label": "Burn", "category": "debuff", "max_stacks": 1, "duration": 4.0,
        "dot_hp_fraction_per_second": 0.008, "modifiers": {}
    }
    changes["data/status_rules_15a.json"] = as_bytes(rules)

    rel = "scripts/fighter.gd"
    src = (root / rel).read_text(encoding="utf-8")
    src = replace_once(src,
        'var garrick_resolve := 0\n',
        '# FRG19N — tracks fire-mage ground hazards; each Fighter is round-local.\n'
        'var ember_ground_patches := 0\n'
        'var garrick_resolve := 0\n', rel)
    src = replace_once(src,
        '	if kit == "greatsword" and garrick_resolve > 0:\n',
        '	if kit == "mage" and String(look.get("element", "")) == "fire":\n'
        '		var fire_tag: String = "FIRE PATCHES %d" % ember_ground_patches\n'
        '		return fire_tag if summary.is_empty() else fire_tag + ", " + summary\n'
        '	if kit == "greatsword" and garrick_resolve > 0:\n', rel)
    changes[rel] = src.encode("utf-8")

    rel = "scripts/match.gd"
    src = (root / rel).read_text(encoding="utf-8")
    src = replace_once(src,
        'var _roxy_puppets: Array[Dictionary] = []\n',
        'var _roxy_puppets: Array[Dictionary] = []\n'
        '# FRG19N — Ember ground patches are fully owned by the match and reset per round.\n'
        'var _ember_patches: Array[Dictionary] = []\n', rel)
    src = replace_once(src,
        '	_roxy_puppets.clear()\n	fighters.clear(); _trails.clear();',
        '	_roxy_puppets.clear()\n'
        '	for ember_patch in _ember_patches:\n'
        '		if is_instance_valid(ember_patch["node"]): ember_patch["node"].queue_free()\n'
        '	_ember_patches.clear()\n'
        '	fighters.clear(); _trails.clear();', rel)
    src = replace_once(src,
        '	_roxy_step_puppets(dt)\n	_nythera_step_wells(dt)\n',
        '	_roxy_step_puppets(dt)\n'
        '	_ember_step_patches(dt) # FRG19N: no burning-ground ticks during pause\n'
        '	_nythera_step_wells(dt)\n', rel)
    src = replace_once(src,
        '			_impact(a, at, color, float(a.radius))\n			for d in enemies_of(f):\n',
        '			_impact(a, at, color, float(a.radius))\n'
        '			if f.kit == "mage" and String(f.look.get("element", "")) == "fire" and bool(a.get("fire_patch", false)):\n'
        '				_ember_add_patch(f, at, float(a.get("radius", 1.0)))\n'
        '			for d in enemies_of(f):\n', rel)
    src = replace_once(src,
        '	match a.mode:\n		"aster_judgment":',
        '	match a.mode:\n'
        '		"ember_ignition": # FRG19N: consume owned ground fire and an active burn\n'
        '			_ember_absolute_combustion(f, a)\n'
        '		"aster_judgment":', rel)
    # Add standalone Ember routines before existing Roxy snow-puppet functions.
    anchor = '# FRG19E — real moving snow-puppet summon, not a fake projectile or a strike.\n'
    ember_code = """# FRG19N — Ember ground fire: four max per caster, 20 seconds each.
func _ember_add_patch(caster: Fighter, at: Vector3, radius: float) -> void:
    if not is_instance_valid(caster) or caster.is_down() or round_over: return
    var owned: Array = _ember_patches.filter(func(p): return p["owner"] == caster)
    if owned.size() >= 4:
        var oldest: Dictionary = owned[0]
        if is_instance_valid(oldest["node"]): oldest["node"].queue_free()
        _ember_patches.erase(oldest)
        caster.ember_ground_patches = maxi(0, caster.ember_ground_patches - 1)
    var marker := MeshInstance3D.new()
    var mesh := CylinderMesh.new()
    mesh.top_radius = 1.0
    mesh.bottom_radius = 1.0
    mesh.height = 0.015
    marker.mesh = mesh
    marker.material_override = Fx.unlit(Color("#ed692c"), 0.36, true)
    marker.scale = Vector3(radius, 1.0, radius)
    add_child(marker)
    marker.global_position = Vector3(at.x, 0.045, at.z)
    _ember_patches.append({"node": marker, "owner": caster, "center": Vector3(at.x, 0.0, at.z), "radius": radius, "left": 20.0, "tick": 0.0})
    caster.ember_ground_patches += 1
    fx.ring(at, Color("#ff8e36"), radius, 0.4, 0.7)

func _ember_step_patches(dt: float) -> void:
    if dt <= 0.0 or round_over: return
    for patch in _ember_patches.duplicate():
        var caster: Fighter = patch["owner"]
        patch["left"] = float(patch["left"]) - dt
        if not is_instance_valid(caster) or caster.is_down() or float(patch["left"]) <= 0.0:
            if is_instance_valid(patch["node"]): patch["node"].queue_free()
            _ember_patches.erase(patch)
            if is_instance_valid(caster): caster.ember_ground_patches = maxi(0, caster.ember_ground_patches - 1)
            continue
        patch["tick"] = float(patch["tick"]) + dt
        if float(patch["tick"]) < 0.75: continue
        patch["tick"] = 0.0
        for defender in enemies_of(caster):
            var to_fire: Vector3 = defender.position - patch["center"]
            to_fire.y = 0.0
            if to_fire.length() <= float(patch["radius"]) + defender.radius * 0.35 and not defender.airborne():
                defender.add_status("burn", 1, 1.25)
                fx.motes(defender.position + Vector3(0.0, 0.12, 0.0), Color("#ff9a39"), 2)

func _ember_absolute_combustion(caster: Fighter, attack: Dictionary) -> void:
    if not is_instance_valid(caster) or caster.is_down() or round_over: return
    var total_fire := 0
    for patch in _ember_patches.duplicate():
        if patch["owner"] != caster: continue
        # The beam consumes nearby owned ground fire, not an enemy's fire.
        if caster.position.distance_to(patch["center"]) > 12.0: continue
        total_fire += 1
        if is_instance_valid(patch["node"]): patch["node"].queue_free()
        _ember_patches.erase(patch)
        caster.ember_ground_patches = maxi(0, caster.ember_ground_patches - 1)
    var start_pos: Vector3 = caster.chest()
    var direction: Vector3 = caster.forward()
    if caster.opponent != null and not caster.opponent.is_down():
        direction = caster.opponent.chest() - start_pos
        direction.y = 0.0
        if direction.length_squared() > 0.01: direction = direction.normalized()
        else: direction = caster.forward()
    direction.y = 0.0
    direction = direction.normalized()
    # Strong beam visuals use the existing FX API, no new audio or materials required.
    for i in range(8):
        var pos: Vector3 = start_pos + direction * (0.8 + float(i) * 1.20)
        fx.flash(pos, Color("#fff1b5"), 0.45 + float(total_fire) * 0.07, 0.20, 0.9)
    fx.ring(caster.position, Color("#ff8c41"), 2.2 + float(total_fire) * 0.28, 0.36, 0.85)
    var hit_count := 0
    for defender in enemies_of(caster):
        var to_target: Vector3 = defender.chest() - start_pos
        var forward_distance: float = to_target.dot(direction)
        if forward_distance < 0.0 or forward_distance > 10.2: continue
        var nearest: Vector3 = start_pos + direction * forward_distance
        if defender.chest().distance_to(nearest) > 1.10 + defender.radius: continue
        var burn_consumed := 0
        if defender.status_runtime != null and defender.status_runtime.has_effect("burn"):
            defender.remove_status("burn")
            burn_consumed = 1
        var beam_attack: Dictionary = attack.duplicate(true)
        beam_attack["type"] = "strike"
        beam_attack["style"] = "ember_beam"
        beam_attack["dmg"] = 150.0 + 32.0 * float(total_fire) + 50.0 * float(burn_consumed)
        beam_attack["guard"] = 48.0 + 12.0 * float(total_fire)
        beam_attack["knock"] = 5.0
        beam_attack["stun"] = 0.55
        beam_attack["heavy"] = true
        beam_attack["apply_status"] = "burn"
        beam_attack["status_duration"] = 4.0
        apply_hit(caster, defender, beam_attack, caster.atk_power, defender.chest(), direction, true)
        hit_count += 1
    fx.number(start_pos + Vector3(0.0, 0.65, 0.0), "ABSOLUTE COMBUSTION", Color("#fff2b5"), 0.85)
    if hit_count == 0: fx.number(start_pos, "MISS", Color("#ffc9a7"), 0.7)

"""
    # Ensure every new helper uses tab indentation, consistent with Godot conventions.
    ember_code = '\n'.join(('\t' + line[4:] if line.startswith('    ') else line) for line in ember_code.splitlines()) + '\n'
    # Line-by-line incremental 4-space block to tab conversion.
    def indent_line(line):
        n = len(line) - len(line.lstrip(' '))
        return '\t' * (n // 4) + line[n:] if n else line
    ember_code = '\n'.join(indent_line(line.replace('\t','    ')) for line in ember_code.splitlines()) + '\n'
    src = replace_once(src, anchor, ember_code + anchor, rel)
    changes[rel] = src.encode("utf-8")
    changes["data/browser_ember_19n.json"] = as_bytes({
        "version": VERSION, "character": "ember", "state": "FIRST PLAYABLE REFINEMENT",
        "source": "https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts",
        "completed": ["reduced mage fire basic damage", "reduced heavy, Z, X and C damage to browser values", "20-second burning patches on heavy and Meteor, four per Ember", "burn debuff on confirmed Z/X/C hit and patch exposure", "Absolute Combustion beam consumes Ember's nearby patches and target burn", "patch count shown in HUD", "reset of patches between rounds and no ticking during pause"],
        "pending": ["longer custom beam choreography and VFX", "exact browser collision and scaling parity", "Godot engine playtest"],
        "notes": "Ember's existing VRM, staff, mage animation set and character ID are preserved. No shop or other modes added."
    })
    changes["reports/ember_19n.txt"] = (
        "19N — Ember Flame Witch\n"
        "Basic bolts -15% damage; heavy explosion 155 and radius 1.05; Flame Burst 95; five Fireball Volley bolts at 31; Meteor 215.\n"
        "Heavy and Meteor leave 20-second fire patches; max 4 per Ember, burning victims who remain on them.\n"
        "Absolute Combustion consumes nearby own fire patches and burns before dealing a directional beam hit.\n"
        "Patch count visible in HUD; projectiles and other fighters are unchanged.\n"
        "Actual Godot engine playtest NOT performed.\n").encode("utf-8")
    return changes


def sha(blob: bytes | None) -> str | None:
    return hashlib.sha256(blob).hexdigest() if blob is not None else None


def atomic(path: Path, blob: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".frg19n-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def install(root: Path, dry_run: bool) -> None:
    if (root / "data/browser_ember_19n.json").is_file():
        print("19N already installed; no changes")
        return
    planned = build(root)
    changed = {rel: blob for rel, blob in planned.items() if not (root / rel).is_file() or (root / rel).read_bytes() != blob}
    for rel in changed: print("Update:", rel)
    if dry_run:
        print("19N dry run passed; nothing written")
        return
    backup = root.parent / (root.name + "_backups") / ("ember_19n_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for rel, new in changed.items():
        old = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest["files"][rel] = {"before": sha(old), "after": sha(new)}
        if old is not None:
            dest = backup / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(old)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    completed = []
    try:
        for rel, blob in changed.items():
            atomic(root / rel, blob)
            completed.append(rel)
    except BaseException:
        for rel in reversed(completed):
            previous = backup / rel
            if previous.is_file(): atomic(root / rel, previous.read_bytes())
            else: (root / rel).unlink(missing_ok=True)
        raise
    print("Installed 19N. Backup:", backup)


def restore(root: Path, backup: Path) -> None:
    manifest = read_json(backup, "manifest.json")
    if manifest.get("project") != str(root):
        raise RuntimeError("Backup belongs to a different project")
    for rel, meta in manifest["files"].items():
        existing = (root / rel).read_bytes() if (root / rel).is_file() else None
        if sha(existing) != meta["after"]:
            raise RuntimeError("File changed since installation, so restore was aborted: " + rel)
    for rel, meta in manifest["files"].items():
        original = backup / rel
        if meta["before"] is None: (root / rel).unlink(missing_ok=True)
        else: atomic(root / rel, original.read_bytes())
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
