#!/usr/bin/env python3
"""Fight Royale Godot 19M: Kaede — Moonlit Blade, Counter Bloom and Thousand Cuts.

Run: python install_19m_kaede.py
Optional: --dry-run | --restore BACKUP_DIRECTORY

Updates Kaede's EXISTING character. Requires 19L.
No extra models, no shop, no character duplicates. Godot gameplay requires testing.
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

VERSION = "19M.1"
MARKER = "FRG19M"


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
        raise RuntimeError(f"{rel}: expected exactly one anchor ({old[:75]!r}), found {n}; no files written")
    return source.replace(old, new, 1)


def build(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise RuntimeError("Run this from the Godot project directory (project.godot missing)")
    if not (root / "data/browser_garrick_19l.json").is_file():
        raise RuntimeError("Update 19L must be installed first")
    roster = read_json(root, "data/roster.json")
    kaede = [r for r in roster if r.get("id") == "kaede"]
    if len(kaede) != 1 or kaede[0].get("look", {}).get("kit") != "katana":
        raise RuntimeError("Exactly one original Kaede katana fighter is required")
    attacks = read_json(root, "data/attacks.json")
    t = attacks.get("kaede")
    if not isinstance(t, dict) or not all(s in t for s in ("l1","l2","l3","heavy","z","x","c","v")):
        raise RuntimeError("Kaede's current skill data is missing")
    if t["z"].get("name") != "Counter Stance" or t["c"].get("name") != "Thousand Cuts":
        raise RuntimeError("Unexpected Kaede kit version; refusing blind changes")
    if not (root / "animations/katana.tres").is_file():
        raise RuntimeError("Missing existing katana animation library")
    t["z"].update(name="Counter Stance", type="buff", mode="counter", duration=0.9, cd=6,
        desc="On a confirmed Z counter, gain one Counter Bloom stack (max 4). Each stack restores 5% of her baseline damage; starts at 80%.")
    t["c"].update(name="Thousand Cuts", type="strike", at="target", style="kaede_thousand_cuts",
        wind=0.20, recover=0.75, dmg=48, guard=12, knock=1, stun=0.30,
        radius=1.5, delay=0.30, repeat=7, interval=0.07, cd=11,
        pose_w="charge", pose_s="heavy_s", lunge=0.0,
        desc="Plant feet and mark a fixed target area for seven rapid cuts. If none of the first three deals HP damage, cancel the remaining four.")
    changes: dict[str, bytes] = {"data/attacks.json": as_bytes(attacks)}

    rel = "scripts/fighter.gd"
    src = (root / rel).read_text(encoding="utf-8")
    src = replace_once(src,
        'var garrick_resolve := 0\n',
        '# FRG19M — Kaede Counter Bloom, round-local (new Fighter each rematch).\n'
        'var kaede_counter_bloom := 0\n'
        'var garrick_resolve := 0\n', rel)
    src = replace_once(src,
        '	if kit == "greatsword" and garrick_resolve > 0:\n',
        '	# FRG19M — Kaede-only counter passive (0.80× to 1.00× damage).\n'
        '	if kit == "katana":\n'
        '		var bloom: String = "COUNTER BLOOM %d/4" % kaede_counter_bloom\n'
        '		return bloom if summary.is_empty() else bloom + ", " + summary\n'
        '	if kit == "greatsword" and garrick_resolve > 0:\n', rel)
    src = replace_once(src,
        '	if counter_t > 0.0: counter_t = 0.0; return "counter"\n',
        '	if counter_t > 0.0:\n'
        '		counter_t = 0.0\n'
        '		# FRG19M — award only after an actual incoming hit triggers Z stance.\n'
        '		if kit == "katana": kaede_counter_bloom = mini(4, kaede_counter_bloom + 1)\n'
        '		return "counter"\n', rel)
    src = replace_once(src,
        '	atk = attacks[aid].duplicate(true)\n',
        '	atk = attacks[aid].duplicate(true)\n'
        '	# FRG19M — Kaede begins 20% weaker and regains 5% per confirmed Z counter.\n'
        '	if kit == "katana":\n'
        '		atk_power *= 0.80 + 0.05 * float(kaede_counter_bloom)\n'
        '		if aid == "c":\n'
        '			# Prevent residual dash/steering from sliding her during Thousand Cuts.\n'
        '			_steer_vel = Vector3.ZERO\n'
        '			_dash_t = 0.0\n'
        '			_dodge_t = 0.0\n', rel)
    changes[rel] = src.encode("utf-8")

    rel = "scripts/match.gd"
    src = (root / rel).read_text(encoding="utf-8")
    src = replace_once(src,
        '	var color := Color(f.look.glow)\n	var one := func(i: int, self_ref: Callable) -> void:\n',
        '	var color := Color(f.look.glow)\n'
        '	# FRG19M — capture the initial target point; no homing between slices.\n'
        '	var kaede_cuts: bool = f.kit == "katana" and String(a.get("style", "")) == "kaede_thousand_cuts"\n'
        '	var kaede_origin: Vector3 = f.opponent.position if kaede_cuts and f.opponent != null else f.position\n'
        '	kaede_origin.y = 0.0\n'
        '	var kaede_contact: Dictionary = {"connected": false}\n'
        '	var kaede_serial: int = f.swing_serial\n'
        '	var one := func(i: int, self_ref: Callable) -> void:\n', rel)
    src = replace_once(src,
        '		if rnd != _round or f.is_down(): return\n		var src = f if a.at == "self" or f.opponent == null else f.opponent\n\n		var center: Vector3 = src.position; center.y = 0\n',
        '		if rnd != _round or f.is_down(): return\n'
        '		if kaede_cuts and (f.swing_serial != kaede_serial or (i >= 3 and not bool(kaede_contact["connected"]))): return\n'
        '		var src = f if a.at == "self" or f.opponent == null else f.opponent\n\n'
        '		var center: Vector3 = kaede_origin if kaede_cuts else src.position; center.y = 0\n', rel)
    src = replace_once(src,
        '			if rnd != _round: return\n\n			var at: Vector3 = Vector3(f.position.x, 0, f.position.z) if a.at == "self" else center\n',
        '			if rnd != _round: return\n'
        '			if kaede_cuts and (f.is_down() or f.swing_serial != kaede_serial or (i >= 3 and not bool(kaede_contact["connected"]))): return\n\n'
        '			var at: Vector3 = Vector3(f.position.x, 0, f.position.z) if a.at == "self" else center\n', rel)
    src = replace_once(src,
        '					apply_hit(f, d, a, power, d.chest(), dir, true)\n				elif to.length() <= float(a.radius) + 1.0:\n',
        '					var hp_before: float = d.hp\n'
        '					apply_hit(f, d, a, power, d.chest(), dir, true)\n'
        '					# FRG19M — shield blocks and invulnerable misses do NOT count.\n'
        '					if kaede_cuts and i < 3 and d.hp < hp_before:\n'
        '						kaede_contact["connected"] = true\n'
        '				elif to.length() <= float(a.radius) + 1.0:\n', rel)
    src = replace_once(src,
        '		"iron_tempest": # FRG19L: individual greatsword swing contact VFX\n',
        '		"kaede_thousand_cuts": # FRG19M — sharp, stationary katana cut beats\n'
        '			fx.sparks(g + Vector3(0, 1.1, 0), color, 15, 6.0)\n'
        '			fx.flash(g + Vector3(0, 1.0, 0), Color("#ffe0eb"), 0.42, 0.10, 0.75)\n'
        '		"iron_tempest": # FRG19L: individual greatsword swing contact VFX\n', rel)
    src = replace_once(src,
        '					apply_hit(d, attacker, counter, d.dmg_mult, attacker.chest(), -dir, false)\n',
        '					var counter_power: float = d.dmg_mult\n'
        '					if d.kit == "katana": counter_power *= 0.80 + 0.05 * float(d.kaede_counter_bloom)\n'
        '					apply_hit(d, attacker, counter, counter_power, attacker.chest(), -dir, false)\n', rel)
    changes[rel] = src.encode("utf-8")
    changes["data/browser_kaede_19m.json"] = as_bytes({
        "version": VERSION, "character": "kaede", "state": "FIRST PLAYABLE REFINEMENT",
        "source": "https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts",
        "completed": ["confirmed Z counter builds Counter Bloom to 4 stacks", "damage 0.8x base to 1.0x at full bloom", "Counter Bloom appears in HUD", "Thousand Cuts fixed target zone", "Thousand Cuts cancels after first three slices if none cause real HP damage", "C cancels dash inertia and plays distinct effect"],
        "pending": ["seven bespoke sheath-and-draw poses", "advanced slash choreography and sound timing", "Godot engine playtest"],
        "notes": "Kaede VRM and original roster/save ID preserved. Other fighters remain unchanged."})
    changes["reports/kaede_19m.txt"] = (
        "19M — Kaede Moonlit Blade\n"
        "Z: confirmed counter increases Counter Bloom, 0/4 to 4/4.\n"
        "Damage: starts 0.80x, +0.05x per Bloom stack, 1.00x maximum.\n"
        "Thousand Cuts: fixed area, seven beats, remaining beats canceled if first three deal no HP damage.\n"
        "Pending animation refinement: custom sheath poses and Godot in-game verification.\n").encode("utf-8")
    return changes


def sha(blob: bytes | None) -> str | None:
    return hashlib.sha256(blob).hexdigest() if blob is not None else None


def atomic(path: Path, blob: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".frg19m-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def install(root: Path, dry_run: bool) -> None:
    if (root / "data/browser_kaede_19m.json").is_file():
        print("19M already installed; no changes")
        return
    planned = build(root)
    changed = {rel: blob for rel, blob in planned.items() if not (root / rel).is_file() or (root / rel).read_bytes() != blob}
    for rel in changed: print("Update:", rel)
    if dry_run:
        print("19M dry run passed; nothing written")
        return
    backup = root.parent / (root.name + "_backups") / ("kaede_19m_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
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
    print("Installed 19M. Backup:", backup)


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
