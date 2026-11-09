#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot Update 13B — tactical AI identities.

Run from the project folder:
    python install_13b_tactical_identities.py
Optional:
    --dry-run, --check-godot, --restore PATH

Requires Update 13A. Never overwrites customized tactics JSON on repeat runs.
Changes AI only; never touches your fighters, skills, models, scenes or sound effects.
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

VERSION = "13B.1"
AI_FILE = "scripts/ai_brain.gd"
TACTICS_FILE = "data/ai_tactics_13b.json"
REPORT_FILE = "reports/ai_tactics_13b.txt"
MARKER = "# FRG13B - tactical identity (guard reset, pressure and skill bias)"

# Subtle changes to AI behavior. Values are not stats/damage buffs.
# Future character IDs will inherit archetype defaults until explicitly tuned.
TACTICS = {
    "version": VERSION,
    "description": "Tactical AI preferences; no character roster/stat/skill changes.",
    "archetypes": {
        "knight": {"guard_reset_threshold": 0.24, "guard_pressure": 0.9, "guard_break_bias": 1.05, "skill_bias": {"z": 0.14}},
        "greatsword": {"guard_reset_threshold": 0.12, "guard_pressure": 1.18, "guard_break_bias": 1.38, "skill_bias": {"x": 0.10}},
        "katana": {"guard_reset_threshold": 0.20, "guard_pressure": 1.12, "guard_break_bias": 0.86, "skill_bias": {"z": 0.08, "c": 0.12}},
        "mage": {"guard_reset_threshold": 0.22, "guard_pressure": 0.64, "guard_break_bias": 0.65, "skill_bias": {"x": 0.11}},
        "bow": {"guard_reset_threshold": 0.18, "guard_pressure": 0.70, "guard_break_bias": 0.72, "skill_bias": {"c": 0.10}},
        "assassin": {"guard_reset_threshold": 0.16, "guard_pressure": 1.30, "guard_break_bias": 0.72, "skill_bias": {"z": 0.15}},
        "knuckles": {"guard_reset_threshold": 0.20, "guard_pressure": 1.28, "guard_break_bias": 1.15, "skill_bias": {"x": 0.12}},
        "kicks": {"guard_reset_threshold": 0.16, "guard_pressure": 1.23, "guard_break_bias": 0.80, "skill_bias": {"c": 0.12}},
    },
    "fighters": {
        # Existing Godot roster: subtle signature tactics. No roster editing.
        "aster": {"guard_reset_threshold": 0.32, "guard_pressure": 0.95, "guard_break_bias": 1.30, "skill_bias": {"z": 0.18}},
        "garrick": {"guard_reset_threshold": 0.10, "guard_pressure": 1.42, "guard_break_bias": 1.48},
        "kaede": {"guard_reset_threshold": 0.20, "guard_pressure": 1.22, "skill_bias": {"c": 0.20}},
        "ember": {"guard_pressure": 0.50, "skill_bias": {"x": 0.20, "c": 0.06}},
        "marina": {"guard_reset_threshold": 0.28, "skill_bias": {"z": 0.15}},
        "nyx": {"guard_reset_threshold": 0.12, "guard_pressure": 1.48, "skill_bias": {"z": 0.22}},
        "rook": {"guard_reset_threshold": 0.30, "guard_pressure": 1.22, "guard_break_bias": 1.45},
        "kira": {"guard_reset_threshold": 0.12, "guard_pressure": 1.40, "skill_bias": {"c": 0.22}},
        "raven": {"guard_pressure": 0.65, "skill_bias": {"x": 0.16}},
        "ash": {"guard_pressure": 0.62, "skill_bias": {"c": 0.18}},
        # Future retained browser fighters can opt into tactics at migration time.
        "zarek": {"guard_pressure": 1.28, "skill_bias": {"z": 0.12}},
        "kaizen": {"guard_pressure": 1.40, "guard_break_bias": 1.38},
        "nythera": {"guard_pressure": 1.16, "skill_bias": {"x": 0.14}},
        "zenith": {"guard_pressure": 1.20, "skill_bias": {"c": 0.17}},
        "zephyr": {"guard_pressure": 1.22, "skill_bias": {"z": 0.16}},
        "roxy": {"guard_pressure": 0.53, "skill_bias": {"x": 0.18}},
        "nesa": {"guard_pressure": 1.34, "guard_break_bias": 1.50},
        "veyr": {"guard_pressure": 1.30, "skill_bias": {"c": 0.17}},
        "renji": {"guard_reset_threshold": 0.24, "skill_bias": {"z": 0.15}},
    },
}

TACTICS_LOADER = '''	# FRG13B - load per-fighter tactical preferences safely; no file is required
	if FileAccess.file_exists(TACTICS_FILE):
		var tactics_data: Variant = JSON.parse_string(FileAccess.get_file_as_string(TACTICS_FILE))
		if tactics_data is Dictionary:
			var common: Dictionary = tactics_data.get("archetypes", {})
			var unique: Dictionary = tactics_data.get("fighters", {})
			_tactics = common.get(archetype, {}).duplicate(true)
			_tactics.merge(unique.get(fighter_id, {}), true)
		else:
			push_warning("FRG13B: invalid tactical JSON; defaults will be used")
'''

COOLDOWN_RULES = '''	# FRG13B - one brief guard recovery step, never a persistent retreat
	_guard_reset_t = maxf(_guard_reset_t - dt, 0.0)
	_guard_reset_cd = maxf(_guard_reset_cd - dt, 0.0)
'''

BREATHER_RULES = '''	# Guard reset is brief and on cooldown. Don't retreat indefinitely or
	# interrupt an enemy attack, a whiff punish, or anti-stall engagement.
	var guard_threshold: float = clampf(float(_tactics.get("guard_reset_threshold", 0.18)), 0.06, 0.40)
	if _guard_reset_cd <= 0.0 and _guard_reset_t <= 0.0 and f.kit not in RANGED:
		if f.guard < f.max_guard * guard_threshold and f.state == Fighter.S.IDLE and o.state == Fighter.S.IDLE and _engage_t <= 0.0 and _punish_t <= 0.0:
			if distance < _preferred_range(f) + 0.75:
				_guard_reset_t = 0.38
				_guard_reset_cd = 4.0
'''

MOVEMENT_RULES = '''	# FRG13B - short guard-reset sidestep and controlled guard-break pressure
	# Both decisions still pass through the existing edge-avoidance code.
	if _guard_reset_t > 0.0 and not ranged and _punish_t <= 0.0 and _engage_t <= 0.0 and o.state == Fighter.S.IDLE:
		desired = sideways * (_orbit_sign * 0.70) - toward * 0.48
	elif not ranged and f.state == Fighter.S.IDLE and _punish_t <= 0.0:
		var pressure: float = clampf(float(_tactics.get("guard_pressure", 1.0)), 0.3, 1.6)
		var broken_guard: bool = o.guard < o.max_guard * 0.33 and o.state in [Fighter.S.IDLE, Fighter.S.BLOCK]
		if broken_guard and dist > preferred - 0.12 and dist < preferred + 1.9:
			desired = toward * pressure + sideways * (_orbit_sign * 0.08)
'''

HEAVY_RULES = '''	# FRG13B - heavy strikes are more attractive against guard-starved foes.
	# Always leave genuine whiff punishes fast (from Update 12C).
	if _punish_t <= 0.0 and o.state == Fighter.S.BLOCK and o.guard < o.max_guard * 0.40:
		var break_bias: float = clampf(float(_tactics.get("guard_break_bias", 1.0)), 0.35, 1.6)
		heavy_chance = clampf(heavy_chance + 0.10 * break_bias, 0.03, 0.68)
'''

REPORT = '''FIGHT ROYALE GODOT — UPDATE 13B: TACTICAL AI IDENTITIES

Requires 13A, 12D. Both Duel vs CPU and CPU vs CPU use this AI.
Adds:
 - Brief, cooldown-limited guard-recovery sidesteps for melee CPU fighters
 - Controlled pressure against opponents with weak guard
 - Heavy-attack preference against low-guard blockers (but not for whiff punishes)
 - Per-fighter skill weights for Hard/Master's tactical skill selector

Values are editable in data/ai_tactics_13b.json.
No fighter, skill, damage, VRM, animation, audio or game-mode files were changed.
Godot itself should be opened and a few CPU matches tested after installing.
'''


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected exactly one known anchor, found {count}; project file was left unchanged")
    return text.replace(old, new, 1)


def in_func(s: str, name: str, old: str, new: str) -> str:
    match = re.search(rf"(?m)^func {re.escape(name)}\(", s)
    if not match:
        raise ValueError("Missing AI function " + name)
    end = re.search(r"(?m)^func [A-Za-z_][A-Za-z_0-9]*\(", s[match.end():])
    finish = match.end() + end.start() if end else len(s)
    return s[:match.start()] + once(s[match.start():finish], old, new, name) + s[finish:]


def patch_ai(s: str) -> str:
    if MARKER in s:
        markers = ("const TACTICS_FILE", "var _guard_reset_cd", "var _tactics", "_tactics.get(\"skill_bias\"", "_guard_reset_t > 0.0")
        if all(m in s for m in markers):
            return s
        raise ValueError("Update 13B is partially present; no changes were applied")
    for required in ("# FRG13A - fighter-specific AI personality profiles", "_load_fighter_personality(f)", "# FRG12D - master tactical skill choice"):
        if required not in s:
            raise ValueError("Missing prerequisite AI marker: " + required + ". Install 12D then 13A.")
    s = once(s, 'const PERSONALITY_FILE := "res://data/ai_personalities.json"\n',
             'const PERSONALITY_FILE := "res://data/ai_personalities.json"\n' + MARKER + '\nconst TACTICS_FILE := "res://data/ai_tactics_13b.json"\n', "tactics constant")
    s = once(s, 'var _personality_loaded := false\n',
             'var _personality_loaded := false\nvar _tactics: Dictionary = {}\nvar _guard_reset_t := 0.0\nvar _guard_reset_cd := 0.0\n', "tactics state")
    s = in_func(s, "_load_fighter_personality",
        '\t_personality.merge(specific, true)\n',
        '\t_personality.merge(specific, true)\n' + TACTICS_LOADER)
    s = in_func(s, "_analyze_openings",
        '\tvar distance: float = offset.length()\n',
        '\tvar distance: float = offset.length()\n' + COOLDOWN_RULES + BREATHER_RULES)
    s = in_func(s, "_position",
        '\t# Do not retreat forever along the ring. Both classes must steer inward\n',
        MOVEMENT_RULES + '\t# Do not retreat forever along the ring. Both classes must steer inward\n')
    s = in_func(s, "_select_tactical_skill",
        '\t\tvar score: float = 0.25 + randf_range(-0.10, 0.10)\n',
        '''\t\tvar score: float = 0.25 + randf_range(-0.10, 0.10)
\t\t# FRG13B - character preference never overrides range/cooldown eligibility
\t\tvar preferred_skills: Dictionary = _tactics.get("skill_bias", {})
\t\tscore += clampf(float(preferred_skills.get(key, 0.0)), -0.3, 0.3)
''')
    s = in_func(s, "_offense",
        '''\theavy_chance = clampf(heavy_chance * float(_personality.get("heavy_scale", 1.0)), 0.03, 0.65)
''',
        '''\theavy_chance = clampf(heavy_chance * float(_personality.get("heavy_scale", 1.0)), 0.03, 0.65)
''' + HEAVY_RULES)
    return s


def sha(content: bytes | None) -> str | None:
    return hashlib.sha256(content).hexdigest() if content is not None else None


def atomic_write(dest: Path, content: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp_13b_" + uuid.uuid4().hex[:8])
    try:
        tmp.write_bytes(content)
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)


def plan(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise ValueError("project.godot not found; run installer from inside your Godot project folder")
    file = root / AI_FILE
    if not file.is_file():
        raise ValueError("Missing scripts/ai_brain.gd")
    old = file.read_text(encoding="utf-8-sig")
    updated = patch_ai(old)
    changes: dict[str, bytes] = {}
    if old != updated:
        changes[AI_FILE] = updated.encode("utf-8")
    if not (root / TACTICS_FILE).exists():
        changes[TACTICS_FILE] = (json.dumps(TACTICS, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    current_report = root / REPORT_FILE
    if not current_report.is_file() or current_report.read_text(encoding="utf-8") != REPORT:
        changes[REPORT_FILE] = REPORT.encode("utf-8")
    return changes


def install(root: Path, changes: dict[str, bytes], dry_run: bool) -> None:
    if not changes:
        print("Update 13B already installed; no changes.")
        return
    print("Update 13B:")
    for rel in changes:
        print(" - " + rel)
    if dry_run:
        print("Dry run complete. Nothing changed.")
        return
    backup = root.parent / (root.name + "_backups") / ("ai_13b_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for rel, content in changes.items():
        old = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest["files"][rel] = {"before": sha(old), "after": sha(content)}
        if old is not None:
            original = backup / "originals" / rel
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(old)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    written: list[str] = []
    try:
        for rel, content in changes.items():
            atomic_write(root / rel, content)
            written.append(rel)
    except Exception:
        for rel in reversed(written):
            original = backup / "originals" / rel
            if original.exists():
                atomic_write(root / rel, original.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print("Installed Update 13B. Backup:", backup)


def restore(root: Path, name: str) -> None:
    backup = Path(name).expanduser().resolve()
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest["project"]).resolve() != root:
        raise ValueError("Wrong backup or project for this Update 13B restoration")
    for rel, hashes in manifest["files"].items():
        current = (root / rel).read_bytes() if (root / rel).is_file() else None
        if sha(current) != hashes["after"]:
            raise ValueError("Refusing restore; file was modified after 13B: " + rel)
        original = backup / "originals" / rel
        if hashes["before"] is not None:
            if not original.is_file() or sha(original.read_bytes()) != hashes["before"]:
                raise ValueError("Corrupt backup: " + rel)
    for rel, hashes in manifest["files"].items():
        original = backup / "originals" / rel
        if original.is_file():
            atomic_write(root / rel, original.read_bytes())
        else:
            (root / rel).unlink(missing_ok=True)
    print("Restored Update 13B backup:", backup)


def godot_check(root: Path) -> None:
    exe = shutil.which("godot") or shutil.which("godot4")
    if exe is None:
        print("Godot executable not available on PATH. Open the project in the Godot editor for script validation.")
        return
    r = subprocess.run([exe, "--headless", "--editor", "--path", str(root), "--quit"], capture_output=True, text=True, timeout=150)
    print((r.stdout + "\n" + r.stderr)[-12000:])
    if r.returncode != 0:
        raise RuntimeError("Godot script validation failed (exit %s)" % r.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fight Royale Godot Update 13B — tactical AI identities")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-godot", action="store_true")
    parser.add_argument("--restore", metavar="BACKUP_DIRECTORY")
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
        return 1


if __name__ == "__main__":
    sys.exit(main())
