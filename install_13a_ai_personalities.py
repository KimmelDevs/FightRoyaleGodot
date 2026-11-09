#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot — Update 13A: fighter-specific CPU personalities.

Run inside the Godot project directory:
    python install_13a_ai_personalities.py
Optional: --dry-run, --restore BACKUP_DIRECTORY, --check-godot
Requires Updates 12A–12D. Changes AI decisions only; does not remove any fighter.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

VERSION = "13A.1"
AI_FILE = "scripts/ai_brain.gd"
PROFILE_FILE = "data/ai_personalities.json"
REPORT_FILE = "reports/ai_personalities_13a.txt"
MARKER = "# FRG13A - fighter-specific AI personality profiles"

# These are MULTIPLIERS of the difficulty preset; no damage, stats, cooldowns,
# or roster membership are changed. Future fighters inherit their kit profile.
PROFILE_DATA = {
    "version": "13A.1",
    "description": "AI behavior only. Difficulty is preserved. Unlisted fighters inherit their kit archetype.",
    "archetypes": {
        "knight": {"range_scale": 1.02, "approach_scale": 0.92, "orbit_scale": 0.70, "retreat_scale": 0.75, "block_scale": 1.27, "parry_scale": 1.08, "dodge_scale": 0.78, "attack_pace": 0.94, "skill_pace": 0.95, "heavy_scale": 1.16},
        "greatsword": {"range_scale": 1.09, "approach_scale": 1.08, "orbit_scale": 0.58, "retreat_scale": 0.75, "block_scale": 0.94, "parry_scale": 1.02, "dodge_scale": 0.77, "attack_pace": 0.83, "skill_pace": 0.92, "heavy_scale": 1.42},
        "katana": {"range_scale": 1.03, "approach_scale": 1.02, "orbit_scale": 1.23, "retreat_scale": 0.96, "block_scale": 0.94, "parry_scale": 1.25, "dodge_scale": 1.13, "attack_pace": 1.17, "skill_pace": 1.08, "heavy_scale": 0.82},
        "mage": {"range_scale": 1.10, "approach_scale": 0.92, "orbit_scale": 1.14, "retreat_scale": 1.20, "block_scale": 0.85, "parry_scale": 0.76, "dodge_scale": 1.22, "attack_pace": 1.00, "skill_pace": 1.27, "heavy_scale": 0.89},
        "bow": {"range_scale": 1.15, "approach_scale": 0.90, "orbit_scale": 1.06, "retreat_scale": 1.25, "block_scale": 0.82, "parry_scale": 0.81, "dodge_scale": 1.30, "attack_pace": 1.07, "skill_pace": 1.10, "heavy_scale": 0.89},
        "assassin": {"range_scale": 0.91, "approach_scale": 1.23, "orbit_scale": 1.44, "retreat_scale": 1.05, "block_scale": 0.77, "parry_scale": 1.15, "dodge_scale": 1.35, "attack_pace": 1.30, "skill_pace": 1.19, "heavy_scale": 0.62},
        "knuckles": {"range_scale": 0.91, "approach_scale": 1.24, "orbit_scale": 0.76, "retreat_scale": 0.68, "block_scale": 1.15, "parry_scale": 0.95, "dodge_scale": 0.96, "attack_pace": 1.25, "skill_pace": 1.03, "heavy_scale": 1.13},
        "kicks": {"range_scale": 1.00, "approach_scale": 1.18, "orbit_scale": 1.32, "retreat_scale": 0.93, "block_scale": 0.82, "parry_scale": 1.09, "dodge_scale": 1.37, "attack_pace": 1.21, "skill_pace": 1.11, "heavy_scale": 0.92},
    },
    "fighters": {
        "aster": {"block_scale": 1.39, "orbit_scale": 0.59, "heavy_scale": 1.10},
        "garrick": {"approach_scale": 1.24, "retreat_scale": 0.60, "heavy_scale": 1.52},
        "kaede": {"parry_scale": 1.38, "orbit_scale": 1.30, "attack_pace": 1.11},
        "ember": {"retreat_scale": 1.33, "skill_pace": 1.34, "dodge_scale": 1.25},
        "marina": {"range_scale": 1.17, "retreat_scale": 1.20, "block_scale": 1.05},
        "nyx": {"attack_pace": 1.42, "orbit_scale": 1.49, "heavy_scale": 0.50},
        "rook": {"block_scale": 1.34, "approach_scale": 1.18, "retreat_scale": 0.57},
        "kira": {"orbit_scale": 1.49, "dodge_scale": 1.44, "attack_pace": 1.32},
        "ash": {"retreat_scale": 1.20, "range_scale": 1.10, "skill_pace": 1.12},
        "raven": {"skill_pace": 1.29, "orbit_scale": 1.18, "parry_scale": 0.83},
        "zarek": {"archetype": "katana", "approach_scale": 1.20, "parry_scale": 1.24},
        "kaizen": {"archetype": "greatsword", "approach_scale": 1.24, "heavy_scale": 1.31},
        "nythera": {"archetype": "katana", "range_scale": 1.18, "orbit_scale": 1.24},
        "zenith": {"archetype": "katana", "range_scale": 1.15, "skill_pace": 1.25},
        "zephyr": {"archetype": "knuckles", "parry_scale": 1.30, "orbit_scale": 1.31},
        "roxy": {"archetype": "mage", "retreat_scale": 1.28, "skill_pace": 1.29},
        "nesa": {"archetype": "greatsword", "approach_scale": 1.23, "heavy_scale": 1.36},
        "veyr": {"archetype": "katana", "attack_pace": 1.21, "parry_scale": 1.11},
        "renji": {"archetype": "knuckles", "parry_scale": 1.40, "heavy_scale": 0.71},
    },
}

FIELDS = '''# FRG13A - fighter-specific AI personality profiles
const PERSONALITY_FILE := "res://data/ai_personalities.json"
var _personality: Dictionary = {}
var _personality_loaded := false
'''

LOADER = '''func _load_fighter_personality(f: Fighter) -> void:
	# Resolve the actual roster ID, not a possibly reused VRM file name.
	_personality_loaded = true
	var fighter_id: String = String(Data.character(f.char_index).get("id", ""))
	if not FileAccess.file_exists(PERSONALITY_FILE):
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(PERSONALITY_FILE))
	if not (parsed is Dictionary):
		push_warning("FRG13A: malformed personality JSON, using default CPU behavior")
		return
	var archetypes: Dictionary = parsed.get("archetypes", {})
	var fighters: Dictionary = parsed.get("fighters", {})
	var specific: Dictionary = fighters.get(fighter_id, {})
	var archetype: String = String(specific.get("archetype", f.kit))
	_personality = archetypes.get(archetype, {}).duplicate(true)
	_personality.merge(specific, true)
	# Apply personal tendencies as *bounded multipliers* to the difficulty
	# preset. Easy stays Easy and Master stays Master.
	p["block"] = clampf(float(p["block"]) * float(_personality.get("block_scale", 1.0)), 0.0, 0.88)
	p["parry"] = clampf(float(p["parry"]) * float(_personality.get("parry_scale", 1.0)), 0.0, 0.52)
	p["jump"] = clampf(float(p["jump"]) * float(_personality.get("dodge_scale", 1.0)), 0.0, 0.70)
	p["think"] = clampf(float(p["think"]) / maxf(float(_personality.get("attack_pace", 1.0)), 0.5), 0.36, 2.3)
	var skill_pace: float = maxf(float(_personality.get("skill_pace", 1.0)), 0.5)
	var timings: Array = p["skill"]
	p["skill"] = [maxf(float(timings[0]) / skill_pace, 0.4), maxf(float(timings[1]) / skill_pace, 0.7)]

'''

REPORT = '''FIGHT ROYALE GODOT — UPDATE 13A — AI PERSONALITIES

This installer enhances BOTH Duel vs CPU and CPU vs CPU.
Difficulty continues to determine skill, reaction speed, and consistency.
Character archetype determines spacing, aggression, circling, guarding,
parrying, dodging, combo pace, heavy preference, and skill frequency.

Edit data/ai_personalities.json only if you want to tune personality values.
Existing roster, abandoned-character placeholders, damage, ability kits,
VRM files and animation scripts are untouched.

This is the baseline archetype layer. Later 13B/13C updates may introduce
more detailed per-character tactics once the final browser roster is known.

CHECK IN GODOT:
1. Aster vs Nyx on Hard: defensive knight vs mobile assassin.
2. Ember vs Garrick on Master: ranged spacing vs aggressive approach.
3. CPU vs CPU: verify neither fighter remains stuck circling indefinitely.
4. Duel vs CPU: ensure choosing difficulty still changes reaction speed.
'''


def replace_once(s: str, old: str, new: str, context: str) -> str:
    n = s.count(old)
    if n != 1:
        raise ValueError(f"{context}: expected one matching code anchor; got {n}. File may differ from latest update.")
    return s.replace(old, new, 1)


def patch_function(s: str, name: str, old: str, new: str) -> str:
    matches = list(re.finditer(rf"(?m)^func {re.escape(name)}\(", s))
    if len(matches) != 1:
        raise ValueError(f"Function {name} expected once; got {len(matches)}")
    begin = matches[0].start()
    tail = re.search(r"(?m)^func [A-Za-z_][A-Za-z_0-9]*\(", s[matches[0].end():])
    end = matches[0].end() + tail.start() if tail else len(s)
    updated = replace_once(s[begin:end], old, new, name)
    return s[:begin] + updated + s[end:]


def patch_ai(s: str) -> str:
    if MARKER in s:
        if ("func _load_fighter_personality(" in s and
            "_load_fighter_personality(f)" in s and
            'float(_personality.get("heavy_scale", 1.0))' in s):
            return s
        raise ValueError("Update 13A appears incomplete; existing scripts preserved")
    for token in ("# FRG12A - deliberate spacing", "# FRG12B - predicted projectile defense",
                  "# FRG12C - grounded whiff punishment", "# FRG12D - master tactical skill choice"):
        if token not in s:
            raise ValueError("Missing earlier AI update: " + token + ". Run Updates 12A–12D first.")

    s = replace_once(s, 'const RANGED := ["mage", "bow"]\n',
                     'const RANGED := ["mage", "bow"]\n' + FIELDS, "personality fields")
    s = replace_once(s, 'p = PRESETS[clampi(level, 0, PRESETS.size() - 1)]',
                     'p = PRESETS[clampi(level, 0, PRESETS.size() - 1)].duplicate(true)', "difficulty preset isolation")
    start = s.index('func think(')
    s = s[:start] + LOADER + s[start:]
    s = patch_function(s, "think", 'if o == null or o.is_down(): return\n',
                       'if o == null or o.is_down(): return\n\tif not _personality_loaded:\n\t\t_load_fighter_personality(f)\n')

    s = patch_function(s, "_position", 'var preferred: float = _preferred_range(f)\n',
                       '''var preferred: float = _preferred_range(f)
	var orbit: float = clampf(float(_personality.get("orbit_scale", 1.0)), 0.4, 1.8)
	var approach: float = clampf(float(_personality.get("approach_scale", 1.0)), 0.6, 1.6)
	var retreat: float = clampf(float(_personality.get("retreat_scale", 1.0)), 0.5, 1.6)
''')
    exchanges = [
        ('desired = -toward * 0.85 + sideways * _orbit_sign * 0.5', 'desired = -toward * (0.85 * retreat) + sideways * _orbit_sign * (0.5 * orbit)'),
        ('desired = toward * 0.95 + sideways * _orbit_sign * 0.2', 'desired = toward * (0.95 * approach) + sideways * _orbit_sign * (0.2 * orbit)'),
        ('desired = sideways * _orbit_sign * 0.48', 'desired = sideways * _orbit_sign * (0.48 * orbit)'),
        ('desired = toward\n', 'desired = toward * approach + sideways * _orbit_sign * (0.12 * orbit)\n'),
        ('desired = sideways * _orbit_sign * 0.75 - toward * 0.12', 'desired = sideways * _orbit_sign * (0.75 * orbit) - toward * 0.12'),
        ('desired = sideways * _orbit_sign * 0.32', 'desired = sideways * _orbit_sign * (0.32 * orbit)'),
    ]
    for old, new in exchanges:
        s = patch_function(s, "_position", old, new)
    s = patch_function(s, "_preferred_range",
        '''if f.kit in RANGED:
		return 5.0 if f.kit == "mage" else 5.5
	var light: Dictionary = f.attacks.get("l1", {})
	return clampf(float(light.get("reach", 1.8)) - 0.15, 1.2, 2.4)
''',
        '''var base: float = 0.0
	if f.kit in RANGED:
		base = 5.0 if f.kit == "mage" else 5.5
	else:
		var light: Dictionary = f.attacks.get("l1", {})
		base = clampf(float(light.get("reach", 1.8)) - 0.15, 1.2, 2.4)
	return base * clampf(float(_personality.get("range_scale", 1.0)), 0.75, 1.3)
''')
    s = patch_function(s, "_offense",
        '''if not ranged and dist > float(light.get("reach", 1.8)) - 0.1:
		heavy_chance *= 0.6
''',
        '''if not ranged and dist > float(light.get("reach", 1.8)) - 0.1:
		heavy_chance *= 0.6
	heavy_chance = clampf(heavy_chance * float(_personality.get("heavy_scale", 1.0)), 0.03, 0.65)
''')
    return s


def hash_bytes(b: bytes | None) -> str | None:
    return hashlib.sha256(b).hexdigest() if b is not None else None


def write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp_13a_" + uuid.uuid4().hex[:8])
    try:
        temp.write_bytes(content)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def plan(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise ValueError("Run this installer inside your Godot project directory (project.godot missing)")
    ai = root / AI_FILE
    if not ai.is_file():
        raise ValueError("Missing scripts/ai_brain.gd")
    original = ai.read_text(encoding="utf-8-sig")
    modified = patch_ai(original)
    edits: dict[str, bytes] = {}
    if modified != original:
        edits[AI_FILE] = modified.encode("utf-8")
    # Preserve local personality tuning if the file already exists.
    dest = root / PROFILE_FILE
    if not dest.exists():
        edits[PROFILE_FILE] = (json.dumps(PROFILE_DATA, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    report = root / REPORT_FILE
    if not report.is_file() or report.read_text(encoding="utf-8") != REPORT:
        edits[REPORT_FILE] = REPORT.encode("utf-8")
    return edits


def install(root: Path, edits: dict[str, bytes], dry_run: bool) -> None:
    if not edits:
        print("Update 13A already installed. No changes.")
        return
    print("Update 13A planned changes:")
    for name in edits:
        print("  " + name)
    if dry_run:
        print("Dry run completed; no changes written.")
        return
    backup = (root.parent / (root.name + "_backups") /
              ("ai_13a_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]))
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for rel, content in edits.items():
        old = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest["files"][rel] = {"old": hash_bytes(old), "new": hash_bytes(content)}
        if old is not None:
            original = backup / "originals" / rel
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(old)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    written = []
    try:
        for rel, content in edits.items():
            write_atomic(root / rel, content)
            written.append(rel)
    except Exception:
        for rel in reversed(written):
            old = backup / "originals" / rel
            if old.is_file():
                write_atomic(root / rel, old.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print("Installed Update 13A. Backup:", backup)


def restore(root: Path, location: str) -> None:
    folder = Path(location).expanduser().resolve()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest["project"]).resolve() != root:
        raise ValueError("Backup does not belong to this Update 13A installation")
    for rel, info in manifest["files"].items():
        current = (root / rel).read_bytes() if (root / rel).is_file() else None
        if hash_bytes(current) != info["new"]:
            raise ValueError("Cannot restore: the file was changed after installation: " + rel)
    for rel, info in manifest["files"].items():
        old = folder / "originals" / rel
        if info["old"] is not None:
            if not old.is_file() or hash_bytes(old.read_bytes()) != info["old"]:
                raise ValueError("Missing/changed backup file: " + rel)
    for rel in manifest["files"]:
        old = folder / "originals" / rel
        if old.is_file():
            write_atomic(root / rel, old.read_bytes())
        else:
            (root / rel).unlink(missing_ok=True)
    print("Restored Update 13A backup:", folder)


def godot_check(root: Path) -> None:
    executable = shutil.which("godot") or shutil.which("godot4")
    if executable is None:
        print("Godot executable not on PATH; open the project in Godot Editor to import and check scripts.")
        return
    result = subprocess.run([executable, "--headless", "--editor", "--path", str(root), "--quit"],
                            text=True, capture_output=True, timeout=120)
    print((result.stdout + "\n" + result.stderr)[-12000:])
    if result.returncode != 0:
        raise RuntimeError("Godot script check failed (exit code %d)" % result.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fight Royale Godot - Update 13A AI personalities")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", metavar="BACKUP_DIRECTORY")
    parser.add_argument("--check-godot", action="store_true")
    args = parser.parse_args()
    root = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(root, args.restore)
        else:
            install(root, plan(root), args.dry_run)
            if args.check_godot and not args.dry_run:
                godot_check(root)
        return 0
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        print("No source files were changed if preflight failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
