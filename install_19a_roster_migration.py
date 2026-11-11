#!/usr/bin/env python3
"""Fight Royale Godot - Update 19A: browser roster migration foundation.

Run inside the Godot project folder:
    python install_19a_roster_migration.py

This deliberately does NOT replace live data/roster.json or combat data.
Unfinished characters must not become selectable with missing attacks/stats.
The next 19B+ installers will bring in characters and abilities in small batches.

Browser roster reference: https://github.com/KimmelDevs/Fight-Royale/blob/main/web/src/game/roster.ts
Reference checked: 2026-11-10.  Revalidate if your browser code has new local changes.
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

VERSION = "19A.1"
PLAN = Path("data/browser_migration_plan_19a.json")
REPORT = Path("reports/browser_roster_audit_19a.txt")
SOURCE = "https://github.com/KimmelDevs/Fight-Royale/blob/main/web/src/game/roster.ts"

# Source roster in latest published browser file, not the older Godot roster.
# Each record: ID, displayed title, combat kit, element, requested VRM filename.
# These are metadata for planning. Do NOT import as Godot abilities yet.
BROWSER_ROSTER = [
    ("renji", "The Counter Fist", "tonfa", "dark", "aster"),
    ("aster", "Azure Knight", "knight", "light", "aster"),
    ("vesper", "Crimson Duelist", "knight", "flame", "vesper"),
    ("garrick", "Iron Vanguard", "greatsword", "earth", "garrick"),
    ("kaede", "Moonlit Blade", "katana", "moon", "kaede"),
    ("ember", "Flame Witch", "mage", "fire", "ember"),
    ("marina", "Tide Sorceress", "mage", "water", "marina"),
    ("nyx", "Shadow Blade", "assassin", "shadow", "nyx"),
    ("rook", "Iron Fist", "knuckles", "force", "rook"),
    ("gale", "Wind Dancer", "wind", "wind", "gale"),
    ("bob", "Mad Bomber", "bomb", "blast", "bob"),
    ("kira", "Tempest Kicker", "kicks", "chi", "kira"),
    ("raven", "Hex Weaver", "mage", "electric", "raven"),
    ("ash", "Crimson Hunter", "bow", "blood", "ash"),
    ("veyr", "Venom Reaper", "sickle", "venom", "veyr"),
    ("zarek", "Storm Glaive", "glaive", "storm", "zarek"),
    ("kaizen", "Chainblade Berserker", "chainblade", "chain", "kaizen"),
    ("nesa", "Hammer Princess", "hammer", "force", "nesa"),
    ("roxy", "Snow Puppet Master", "mage", "frost", "roxy"),
    ("zenith", "The Iron Sovereign", "glaive", "metal", "zenith"),
    ("nythera", "Gravity Reaper", "scythe", "gravity", "nythera"),
    ("zephyr", "Dragon Dancer", "tristaff", "dragon", "zephyr"),
    ("raigo", "Iron Bastion", "axeflail", "iron", "garrick"),
]

# Characters from the older Godot roster absent from current browser roster.
# The user asked not to port discontinued concepts. No deletion of playable
# Godot entries occurs until replacement characters are fully implemented.
LEGACY_ONLY = ["volta", "sylva", "leon", "sakura", "yuki", "bruno"]
# Vesper still exists in the published browser roster, but appears in older
# concept discussions as a possible precursor to Veyr; flag for review rather
# than silently deciding to keep or delete her.
NEEDS_REVIEW = ["vesper"]
# Suggested port batches, not an instruction to overwrite current fighters.
BATCHES = [
    {"id": "19B", "fighters": ["zarek", "kaizen", "nesa"], "focus": "Weapon-heavy duelists and hammer combat"},
    {"id": "19C", "fighters": ["roxy", "nythera", "zenith"], "focus": "Ice, gravity and magnetic combat"},
    {"id": "19D", "fighters": ["zephyr", "renji", "raigo"], "focus": "Unique weapons, counters and stance systems"},
    {"id": "19E", "fighters": ["gale", "bob", "veyr"], "focus": "Movement, explosives and sickles"},
    {"id": "19F", "fighters": ["aster", "garrick", "kaede", "ember", "marina", "nyx", "rook", "kira", "raven", "ash"], "focus": "Reconcile existing kits with latest browser implementations"},
]


def digest(b: bytes | None) -> str | None:
    return hashlib.sha256(b).hexdigest() if b is not None else None


def json_file(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise RuntimeError(f"Cannot parse {path}: {e}") from e


def validate(root: Path):
    if not (root / "project.godot").is_file():
        raise RuntimeError("Run from your Godot project folder (containing project.godot).")
    data = root / "data"
    for name in ["roster.json", "attacks.json", "stats.json", "poses.json"]:
        if not (data / name).is_file():
            raise RuntimeError(f"Missing data/{name}; earlier foundation updates required.")
    roster = json_file(data / "roster.json")
    attacks = json_file(data / "attacks.json")
    stats = json_file(data / "stats.json")
    poses = json_file(data / "poses.json")
    if not isinstance(roster, list) or not all(isinstance(v, dict) and isinstance(v.get("id"), str) for v in roster):
        raise RuntimeError("data/roster.json must be an array of fighters with IDs")
    if not all(isinstance(x, dict) for x in (attacks, stats, poses)):
        raise RuntimeError("attacks.json, stats.json, poses.json must contain objects")
    ids = [x["id"] for x in roster]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate character ID in data/roster.json")
    # Block a migration when the currently active live roster is already broken.
    for char in roster:
        cid = char["id"]
        kit = char.get("look", {}).get("kit")
        missing = [p for p, good in [("attack table", cid in attacks),
                                     ("stats", kit in stats),
                                     ("poses", kit in poses)] if not good]
        if missing:
            raise RuntimeError(f"Live fighter {cid} is missing {', '.join(missing)}; fix live combat data first.")
    return roster, attacks, stats, poses


def make_plan() -> dict:
    return {
        "version": VERSION,
        "source": SOURCE,
        "source_checked": "2026-11-10",
        "purpose": "Migration staging. NOT yet active in Duel vs CPU or CPU vs CPU.",
        "scope": {"duel_vs_cpu": True, "cpu_vs_cpu": True,
                  "shop": False, "survival": False, "online": False},
        "rules": [
            "Never add a fighter to data/roster.json without attacks, stats and poses.",
            "Only bring forward continuing browser fighters; do not port legacy-only concepts.",
            "Keep existing working fighters until replacement kits pass validation.",
            "Always preserve user-provided VRM models and existing audio files.",
            "Recheck unpublished browser changes before migrating individual fighter mechanics.",
        ],
        "browser_fighters": [
            {"id": cid, "title": title, "kit": kit, "element": element,
             "vrm": vrm, "review_required": cid in NEEDS_REVIEW}
            for cid, title, kit, element, vrm in BROWSER_ROSTER
        ],
        "legacy_only_ids": LEGACY_ONLY,
        "needs_review_ids": NEEDS_REVIEW,
        "port_batches": BATCHES,
    }


def make_report(root: Path, roster: list, stats: dict, poses: dict) -> str:
    live = {v["id"] for v in roster}
    browser = {x[0] for x in BROWSER_ROSTER}
    models = root / "models"
    lines = [
        f"Fight Royale Godot - Update {VERSION}: Browser roster audit",
        f"Reference: {SOURCE}",
        "Reference date: 2026-11-10 (published browser source, not unpushed local edits)",
        f"Live Godot fighters: {len(live)}; published browser fighters: {len(browser)}",
        f"Already in Godot: {len(live & browser)}; queued additions: {len(browser - live)}",
        "",
        "QUEUED TO PORT (NOT YET PLAYABLE IN GODOT):",
    ]
    for cid, title, kit, element, vrm in BROWSER_ROSTER:
        if cid not in live:
            found = (models / f"{cid}.vrm").is_file()
            fallback = (models / f"{vrm}.vrm").is_file()
            lines.append(f"  {cid:10} kit={kit:11} model={'own' if found else 'fallback' if fallback else 'missing'} ({vrm}.vrm)")
    lines += ["", "LEGACY-ONLY IN GODOT (NOT QUEUED FOR REMAKE):"]
    lines += ["  " + cid for cid in sorted(live - browser)] or ["  none"]
    lines += ["", "REVIEW BEFORE RETIRING:", "  vesper - exists in browser roster, but its continued status is uncertain.",
              "", "MISSING NEW KIT DEFINITIONS IN CURRENT GODOT:"]
    new_kits = sorted(set(x[2] for x in BROWSER_ROSTER) - set(stats) - set(poses))
    lines += ["  " + kit for kit in new_kits] or ["  none"]
    lines += ["", "PLANNED BATCHES:"]
    for batch in BATCHES:
        lines.append("  " + batch["id"] + ": " + ", ".join(batch["fighters"]))
    lines += ["", "This update changes NO live roster, attacks, animation poses, or balance.",
              "Existing Duel vs CPU and CPU vs CPU should remain unchanged.",
              "Next step: import fully implemented character batches; avoid placeholder skills.", ""]
    return "\n".join(lines)


def atomic_write(path: Path, payload: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".frg19a-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def execute(root: Path, dry: bool):
    roster, _, stats, poses = validate(root)
    plan = (json.dumps(make_plan(), indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if (root / PLAN).is_file() and (root / PLAN).read_bytes() != plan:
        # 19A is a static planning file, not a game runtime setting. Still,
        # preserve any user edits instead of silently clobbering them.
        existing = json_file(root / PLAN)
        if existing.get("version") == VERSION:
            plan = (root / PLAN).read_bytes()
        else:
            raise RuntimeError("Existing migration plan differs; refusing to overwrite another version.")
    desired = {str(PLAN): plan,
               str(REPORT): make_report(root, roster, stats, poses).encode("utf-8")}
    changes = {p: b for p, b in desired.items()
               if not (root / p).is_file() or (root / p).read_bytes() != b}
    if not changes:
        print("Update 19A already installed; no changes.")
        return
    for path in changes:
        print("Update:", path)
    if dry:
        print("DRY RUN: no changes made.")
        return
    backup = root.parent / (root.name + "_backups") / (
        "roster_19a_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for rel, body in changes.items():
        target = root / rel
        old = target.read_bytes() if target.is_file() else None
        manifest["files"][rel] = {"before": digest(old), "after": digest(body)}
        if old is not None:
            stored = backup / rel
            stored.parent.mkdir(parents=True, exist_ok=True)
            stored.write_bytes(old)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    installed = []
    try:
        for rel, body in changes.items():
            atomic_write(root / rel, body)
            installed.append(rel)
    except Exception:
        for rel in reversed(installed):
            saved = backup / rel
            if saved.is_file():
                atomic_write(root / rel, saved.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print("Update 19A installed. Live roster and combat files unchanged.")
    print("Report:", REPORT)
    print("Backup:", backup)


def restore(root: Path, backup: Path):
    manifest = json_file(backup / "manifest.json")
    if manifest.get("project") != str(root):
        raise RuntimeError("Backup belongs to another project folder")
    for rel, meta in manifest["files"].items():
        current = (root / rel).read_bytes() if (root / rel).is_file() else None
        if digest(current) != meta["after"]:
            raise RuntimeError(f"Cannot restore: {rel} changed since installation")
    for rel, meta in manifest["files"].items():
        stored = backup / rel
        if meta["before"] is None:
            (root / rel).unlink(missing_ok=True)
        else:
            atomic_write(root / rel, stored.read_bytes())
    print("Update 19A restored from", backup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    try:
        if args.restore:
            restore(root, args.restore.expanduser().resolve())
        else:
            execute(root, args.dry_run)
    except Exception as e:
        print("ERROR:", e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
