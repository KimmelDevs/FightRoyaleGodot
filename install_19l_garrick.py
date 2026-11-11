#!/usr/bin/env python3
"""Fight Royale Godot 19L: Garrick / Iron Vanguard greatsword refinement.

Run from the project directory: python install_19l_garrick.py
Optional: --dry-run | --restore BACKUP_DIRECTORY

Requires 19K. Ports Garrick's stagger Ground Slam, three-pulse Iron Tempest,
revised greatsword hit reach, and his projectile-only Resolve passive.
This is a first playable refinement, not complete browser animation parity.
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

VERSION = "19L.1"
MARKER = "FRG19L"


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
        raise RuntimeError(f"{rel}: expected exactly one anchor ({old[:70]!r}), found {n}; nothing written")
    return source.replace(old, new, 1)


def build(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise RuntimeError("Run from your Godot folder (project.godot required)")
    if not (root / "data/browser_aster_19k.json").is_file():
        raise RuntimeError("Install 19K first before 19L")
    roster = read_json(root, "data/roster.json")
    if len([r for r in roster if r.get("id") == "garrick"]) != 1:
        raise RuntimeError("Garrick must appear exactly once in the roster")
    attacks = read_json(root, "data/attacks.json")
    table = attacks.get("garrick")
    if not isinstance(table, dict) or not all(k in table for k in ("l1", "l2", "l3", "heavy", "z", "x", "c", "v")):
        raise RuntimeError("The existing Garrick kit is missing a required attack")
    if not (root / "animations/greatsword.tres").is_file():
        raise RuntimeError("Missing greatsword animation library")
    if table["z"].get("name") != "Ground Slam" or table["c"].get("name") != "Titan Cleave":
        raise RuntimeError("Unexpected Garrick skill layout; refusing unsafe patch")

    # Only Garrick's own character ID is modified. Preserve all other fighters.
    for key, reach, active in (("l1", 2.55, .14), ("l2", 2.60, .14), ("l3", 2.70, .17), ("heavy", 2.90, .18)):
        table[key]["reach"] = reach
        table[key]["active"] = active
    table["z"].update(
        name="Ground Slam", type="strike", at="self", style="slam", stagger=True,
        desc="Close shockwave that staggers foes; projectile interception is handled by the active weapon and Resolve passive.",
        radius=2.6, delay=.05, cd=6.0,
    )
    table["x"].update(
        name="Iron Tempest", type="strike", at="self", style="iron_tempest", wind=.28,
        active=.86, recover=.48, dmg=70, guard=22, knock=1.1, stun=.16,
        radius=2.8, repeat=3, interval=.30, delay=.04, lunge=1.65, cd=9.0,
        pose_w="charge", pose_s="heavy_s", heavy=False,
        desc="Three successive wide advancing greatsword sweeps. Each pulse is independently blockable, parryable or dodgeable.",
    )
    table["c"].update(
        name="Titan Cleave", type="strike", at="target", style="cleave", heavy=True,
        desc="Rock spikes erupt under the target. The follow-up rushing overhead strike will be refined separately.",
    )
    result: dict[str, bytes] = {"data/attacks.json": as_bytes(attacks)}

    rel = "scripts/fighter.gd"
    src = (root / rel).read_text(encoding="utf-8")
    src = replace_once(src,
        'var zarek_momentum := 0  # FRG19B projectile-destroy Clash Momentum\n',
        '# FRG19L — Garrick receives Resolve from confirmed projectile parries/interceptions.\n'
        'var garrick_resolve := 0\n'
        'var garrick_crack_cooldown := 0.0\n'
        'var zarek_momentum := 0  # FRG19B projectile-destroy Clash Momentum\n', rel)
    src = replace_once(src,
        '\t# FRG19B: only real projectile destroys earn Zarek\'s Clash Momentum.\n',
        '\t# FRG19L: never award Resolve for a normal melee block/parry.\n'
        '\tif kit == "greatsword" and event_id in ["projectile_parried", "projectile_destroyed"]:\n'
        '\t\tgarrick_resolve = mini(3, garrick_resolve + 1)\n'
        '\t# FRG19B: only real projectile destroys earn Zarek\'s Clash Momentum.\n', rel)
    src = replace_once(src,
        '\tif kit == "tristaff":\n\t\tvar tag: String = ["STAFF", "SPLIT", "WHIP", "FOLDED"][zephyr_mode]',
        '\tif kit == "greatsword" and garrick_resolve > 0:\n'
        '\t\tvar resolve_tag: String = "RESOLVE %d/3" % garrick_resolve\n'
        '\t\treturn resolve_tag if summary.is_empty() else resolve_tag + ", " + summary\n'
        '\tif kit == "tristaff":\n\t\tvar tag: String = ["STAFF", "SPLIT", "WHIP", "FOLDED"][zephyr_mode]', rel)
    src = replace_once(src,
        '\t# FRG19I reflection decays in match-time;',
        '\t# FRG19L: timer only advances with active match time.\n'
        '\tif kit == "greatsword":\n'
        '\t\tgarrick_crack_cooldown = maxf(0.0, garrick_crack_cooldown - dt)\n'
        '\t# FRG19I reflection decays in match-time;', rel)
    src = replace_once(src,
        '\t\t\trequested = in_move.normalized() * speed * steer\n',
        '\t\t\t# FRG19L: approaching with 2+ Resolve grants +20% speed, not sideways retreat speed.\n'
        '\t\t\tif kit == "greatsword" and garrick_resolve >= 2 and o != null and not o.is_down() and in_move.normalized().dot(dir) > 0.25:\n'
        '\t\t\t\tspeed *= 1.20\n'
        '\t\t\trequested = in_move.normalized() * speed * steer\n', rel)
    src = replace_once(src,
        '\t\t\tv = walk_speed * status_runtime.movement_multiplier()\n',
        '\t\t\tv = walk_speed * status_runtime.movement_multiplier()\n'
        '\t\t\tif kit == "greatsword" and garrick_resolve >= 2: v *= 1.20\n', rel)
    src = replace_once(src,
        '\tvar dmg: float = float(a.dmg) * power * status_runtime.incoming_multiplier()\n',
        '\tvar dmg: float = float(a.dmg) * power * status_runtime.incoming_multiplier()\n'
        '\t# FRG19L: 25% less projectile HP damage when advancing with 2+ Resolve.\n'
        '\t# The metadata is set by Match only for real projectile hits; guard cost remains unchanged.\n'
        '\tif kit == "greatsword" and bool(a.get("_garrick_resolve_defense", false)):\n'
        '\t\tdmg *= 0.75\n', rel)
    result[rel] = src.encode("utf-8")

    rel = "scripts/match.gd"
    src = (root / rel).read_text(encoding="utf-8")
    src = replace_once(src,
        '\t\tif dt > 0.0:\n\t\t\tf.tick(dt)\n',
        '\t\tif dt > 0.0:\n\t\t\tf.tick(dt)\n'
        '\t\t\t# FRG19L: subtle heavy footsteps with 3 Resolve; no simulation while paused.\n'
        '\t\t\tif f.kit == "greatsword" and f.garrick_resolve >= 3 and f.on_ground and f.model != null and f.model.walk > 0.25 and f.garrick_crack_cooldown <= 0.0:\n'
        '\t\t\t\tfx.rocks(f.position, 5, 0.25)\n'
        '\t\t\t\tf.garrick_crack_cooldown = 0.32\n', rel)
    src = replace_once(src,
        '\tvar result := d.receive_hit(attacker, a, power)\n',
        '\t# FRG19L: pass per-hit metadata rather than mutating shared attack dictionaries.\n'
        '\tvar incoming_attack: Dictionary = a\n'
        '\tif ranged and String(a.get("type", "")) == "projectile" and d.kit == "greatsword" and d.garrick_resolve >= 2 and d.opponent != null and not d.opponent.is_down():\n'
        '\t\tvar approach: Vector3 = d.opponent.position - d.position\n'
        '\t\tapproach.y = 0.0\n'
        '\t\tif approach.length_squared() > 0.01 and d.in_move.length_squared() > 0.01 and d.in_move.normalized().dot(approach.normalized()) > 0.25:\n'
        '\t\t\tincoming_attack = a.duplicate(true)\n'
        '\t\t\tincoming_attack["_garrick_resolve_defense"] = true\n'
        '\tvar result := d.receive_hit(attacker, incoming_attack, power)\n', rel)
    src = replace_once(src,
        '\telif result == "parry":\n\t\td.notify_passive_event("parried", attacker if attacker is Fighter else null)\n',
        '\telif result == "parry":\n'
        '\t\td.notify_passive_event("parried", attacker if attacker is Fighter else null)\n'
        '\t\t# FRG19L: only projectile parries, never melee parries, build Resolve.\n'
        '\t\tif ranged and String(a.get("type", "")) == "projectile":\n'
        '\t\t\td.notify_passive_event("projectile_parried", attacker if attacker is Fighter else null)\n', rel)
    src = replace_once(src,
        '\t\t"spin":\n\t\t\tfx.ring(g + Vector3(0, 1.0, 0), color, radius, 0.2, 0.9)\n',
        '\t\t"iron_tempest": # FRG19L: individual greatsword swing contact VFX\n'
        '\t\t\tfx.sparks(g + Vector3(0, 0.9, 0), color, 18, 5.3)\n'
        '\t\t\tfx.ring(g + Vector3(0, 0.65, 0), color, radius * 0.75, 0.18, 0.68)\n'
        '\t\t"spin":\n\t\t\tfx.ring(g + Vector3(0, 1.0, 0), color, radius, 0.2, 0.9)\n', rel)
    result[rel] = src.encode("utf-8")

    result["data/browser_garrick_19l.json"] = as_bytes({
        "version": VERSION, "character": "garrick", "state": "FIRST PLAYABLE REFINEMENT",
        "source": "https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts",
        "completed": ["greatsword extended attack reach", "staggering Ground Slam",
                       "Iron Tempest three independent strike pulses", "Resolve 0-3 only from projectile parries and destroys",
                       "2+ Resolve: 20% bonus approach speed and 25% less projectile HP damage while approaching",
                       "3 Resolve: small footstep rock effects", "HUD Resolve counter"],
        "not_yet_ported": ["Titan Cleave hit-confirmed recast overhead finisher", "individual 3-cut choreography and upper-air hit checking", "browser VFX parity"],
        "notes": "Existing VRM, weapons and old save IDs remain intact. 19K prerequisite checked."})
    result["reports/garrick_19l.txt"] = (
        "19L — Garrick Iron Vanguard\n"
        "Garrick retains his existing VRM and greatsword setup.\n"
        "X now emits three separate defendable Iron Tempest pulses. Z causes stagger.\n"
        "Resolve gains 1 stack for actual projectile parries or projectile destroys, capped at 3.\n"
        "At 2+ stacks: +20% approach speed and 25% projectile damage resistance while advancing.\n"
        "At 3 stacks: subtle rock cracks when walking.\n"
        "Pending: conditional Titan Cleave follow-up, full multi-cut choreography, aerial targets.\n"
        "Godot engine playtest has NOT been performed.\n").encode("utf-8")
    return result


def sha(blob: bytes | None) -> str | None:
    return hashlib.sha256(blob).hexdigest() if blob is not None else None


def atomic(path: Path, blob: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".frg19l-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def install(root: Path, dry_run: bool) -> None:
    if (root / "data/browser_garrick_19l.json").is_file():
        print("19L already installed; no changes")
        return
    planned = build(root)
    changed = {rel: blob for rel, blob in planned.items() if not (root / rel).is_file() or (root / rel).read_bytes() != blob}
    for rel in changed: print("Update:", rel)
    if dry_run:
        print("19L dry run passed; nothing written")
        return
    backup = root.parent / (root.name + "_backups") / ("garrick_19l_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
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
    print("Installed 19L. Backup:", backup)


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
