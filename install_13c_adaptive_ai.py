#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot Update 13C — adaptive opponent reading.

From the Godot project folder:
    python install_13c_adaptive_ai.py

Also supports --dry-run, --check-godot, --restore BACKUP_DIRECTORY.
Requires Update 13B. Modifies only scripts/ai_brain.gd and creates optional
AI configuration and audit files. Existing configuration is never replaced.
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

VERSION = "13C.1"
AI_FILE = "scripts/ai_brain.gd"
CONFIG_FILE = "data/ai_adaptation_13c.json"
REPORT_FILE = "reports/ai_adaptation_13c.txt"
MARKER = "# FRG13C - adaptive opponent reading (observed patterns only)"

CONFIG = {
    "version": VERSION,
    "description": "Bounded AI adaptation based only on observed attacks and blocking; no damage/stat modifications.",
    "sample_min": 4,
    "max_read_events": 12,
    "decay_seconds": 9.0,
    "heavy_ratio_threshold": 0.60,
    "block_memory_threshold": 0.43,
    "difficulty": {
        "Hard": {"parry_bonus": 0.025, "charged_bias": 0.07, "skill_guard_bias": 0.12},
        "Master": {"parry_bonus": 0.060, "charged_bias": 0.12, "skill_guard_bias": 0.22},
    },
}

STATE = '''# FRG13C - learn only actions the opponent visibly commits to
const ADAPTATION_FILE := "res://data/ai_adaptation_13c.json"
var _difficulty_level: int = 0
var _read_settings: Dictionary = {}
var _enemy_last_read_swing: int = -1
var _enemy_light_reads: int = 0
var _enemy_heavy_reads: int = 0
var _enemy_block_memory: float = 0.0
var _enemy_read_decay_timer: float = 9.0
'''

OBSERVE_FUNCTIONS = '''
func _load_read_settings() -> void:
	_read_settings = {
		"sample_min": 4,
		"max_read_events": 12,
		"decay_seconds": 9.0,
		"heavy_ratio_threshold": 0.60,
		"block_memory_threshold": 0.43,
		"difficulty": {
			"Hard": {"parry_bonus": 0.025, "charged_bias": 0.07, "skill_guard_bias": 0.12},
			"Master": {"parry_bonus": 0.060, "charged_bias": 0.12, "skill_guard_bias": 0.22},
		},
	}
	if not FileAccess.file_exists(ADAPTATION_FILE):
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(ADAPTATION_FILE))
	if parsed is Dictionary:
		_read_settings.merge(parsed, true)
	else:
		push_warning("FRG13C: malformed adaptation JSON; using built-in limits")

func _read_level() -> Dictionary:
	if _difficulty_level < 2:
		return {}
	var difficulty_data: Dictionary = _read_settings.get("difficulty", {})
	return difficulty_data.get("Master" if _difficulty_level >= 3 else "Hard", {})

func _observe_opponent(f: Fighter, o: Fighter, dt: float) -> void:
	# Each new melee swing is observed once, regardless of frame rate. No
	# future inputs, cooldown inspection, or hidden states are used.
	if o.state == Fighter.S.ATTACK and String(o.atk.get("type", "")) == "melee":
		if o.swing_serial != _enemy_last_read_swing:
			_enemy_last_read_swing = o.swing_serial
			if bool(o.atk.get("heavy", false)):
				_enemy_heavy_reads += 1
			else:
				_enemy_light_reads += 1
			var cap: int = clampi(int(_read_settings.get("max_read_events", 12)), 4, 24)
			if _enemy_heavy_reads + _enemy_light_reads > cap:
				# Decay the larger bucket so old habits gradually lose weight.
				if _enemy_heavy_reads >= _enemy_light_reads:
					_enemy_heavy_reads -= 1
				else:
					_enemy_light_reads -= 1
	_enemy_read_decay_timer -= dt
	if _enemy_read_decay_timer <= 0.0:
		_enemy_read_decay_timer = clampf(float(_read_settings.get("decay_seconds", 9.0)), 3.0, 30.0)
		_enemy_heavy_reads = maxi(0, _enemy_heavy_reads - 1)
		_enemy_light_reads = maxi(0, _enemy_light_reads - 1)
	var dist: float = f.position.distance_to(o.position)
	var nearby_guard: bool = o.state == Fighter.S.BLOCK and dist <= _preferred_range(f) + 1.0
	var delta_memory: float = 0.23 if nearby_guard else -0.14
	_enemy_block_memory = clampf(_enemy_block_memory + delta_memory * dt, 0.0, 1.0)

func _heavy_habit_parry_bonus() -> float:
	var options: Dictionary = _read_level()
	if options.is_empty():
		return 0.0
	var samples: int = _enemy_heavy_reads + _enemy_light_reads
	if samples < clampi(int(_read_settings.get("sample_min", 4)), 3, 12):
		return 0.0
	var ratio: float = float(_enemy_heavy_reads) / float(maxi(samples, 1))
	if ratio < clampf(float(_read_settings.get("heavy_ratio_threshold", 0.60)), 0.50, 0.90):
		return 0.0
	return clampf(float(options.get("parry_bonus", 0.0)), 0.0, 0.08)

func _guard_habit() -> bool:
	return not _read_level().is_empty() and _enemy_block_memory >= clampf(float(_read_settings.get("block_memory_threshold", 0.43)), 0.2, 0.85)
'''

REPORT = '''FIGHT ROYALE GODOT — UPDATE 13C: ADAPTIVE OPPONENT READING

Requires Update 13B (including 13A and the 12-series AI patches).

Hard and Master CPUs can respond to OBSERVED opponent habits:
- Tracks actual melee attack starts, once per swing.
- After sufficient samples, slightly improves defensive timing against repeated heavy swings.
- Notices frequent nearby blocking and modestly favors guard pressure.
- Weights equipped, usable guard-damaging melee skills slightly higher when facing a defensive habit.
- Forgotten/decayed reads prevent permanent counterplay and perfect prediction.
- Easy and Normal retain their original behavior; no hidden-input reading.

Configuration: data/ai_adaptation_13c.json. No shop, roster, VRM, SFX, scene, character stats or combat damage changes.
This is a code-level installation test; verify in Godot with multiple matches.
'''


def once(source: str, old: str, new: str, label: str) -> str:
    n = source.count(old)
    if n != 1:
        raise ValueError(f"{label}: expected exactly one anchor, got {n}; no files changed")
    return source.replace(old, new, 1)


def in_func(source: str, func: str, old: str, new: str) -> str:
    found = re.search(rf"(?m)^func {re.escape(func)}\(", source)
    if not found:
        raise ValueError(f"Missing function {func}; no changes applied")
    next_func = re.search(r"(?m)^func [A-Za-z_][A-Za-z_0-9]*\(", source[found.end():])
    finish = found.end() + next_func.start() if next_func else len(source)
    return source[:found.start()] + once(source[found.start():finish], old, new, func) + source[finish:]


def patch_ai(source: str) -> str:
    if MARKER in source:
        required = ("_observe_opponent(f, o, dt)", "_load_read_settings()", "_guard_habit()", "_heavy_habit_parry_bonus()")
        if all(k in source for k in required):
            return source
        raise ValueError("Partial Update 13C detected; refusing to overwrite")
    for prerequisite in ("# FRG13B - tactical identity", "# FRG13A - fighter-specific", "# FRG12D - master tactical skill choice"):
        if prerequisite not in source:
            raise ValueError("Missing prerequisite: " + prerequisite + " — install Update 13B first")
    source = once(source,
        'const TACTICS_FILE := "res://data/ai_tactics_13b.json"\n',
        'const TACTICS_FILE := "res://data/ai_tactics_13b.json"\n' + MARKER + '\n' + STATE,
        "AI settings and state")
    source = in_func(source, "_init",
        '\tp = PRESETS[clampi(level, 0, PRESETS.size() - 1)].duplicate(true)\n',
        '\t_difficulty_level = clampi(level, 0, PRESETS.size() - 1)\n\tp = PRESETS[_difficulty_level].duplicate(true)\n\t_load_read_settings()\n')
    source = in_func(source, "think",
        '\tif o is Fighter: _react(f, o)\n\t_dodge(f)\n',
        '\tif o is Fighter: _react(f, o)\n\t_observe_opponent(f, o, dt)\n\t_dodge(f)\n')
    source = in_func(source, "_react",
        '''\t\tvar r := randf()
\t\tvar bc: float = p.block * (0.75 if o.atk.heavy else 1.0)
\t\tif r < p.parry: _schedule(maxf(tth - 0.07, 0.0), 0.3)
\t\telif r < p.parry + bc: _schedule(_r(p.react[0], p.react[1]) * 0.6, tth + 0.45)
\t\telif r < p.parry + bc + 0.15: _try_skill(f, "z", true)
''',
        '''\t\tvar r := randf()
\t\tvar bc: float = float(p.block) * (0.75 if o.atk.heavy else 1.0)
\t\tvar parry_read: float = clampf(float(p.parry) + _heavy_habit_parry_bonus(), 0.0, 0.52)
\t\tif r < parry_read: _schedule(maxf(tth - 0.07, 0.0), 0.3)
\t\telif r < parry_read + bc: _schedule(_r(p.react[0], p.react[1]) * 0.6, tth + 0.45)
\t\telif r < parry_read + bc + 0.15: _try_skill(f, "z", true)
''')
    source = in_func(source, "_select_tactical_skill",
        '''\t\tif score > best_score:
\t\t\tbest_score = score
''',
        '''\t\t# FRG13C - favor high-guard-damage melee skills only against a
\t\t# repeatedly observed blocking habit, never bypassing eligibility.
\t\tif _guard_habit() and kind == "melee" and o.state == Fighter.S.BLOCK:
\t\t\tvar guard_value: float = clampf(float(ability.get("guard", 0.0)) / 65.0, 0.0, 1.0)
\t\t\tscore += guard_value * clampf(float(_read_level().get("skill_guard_bias", 0.0)), 0.0, 0.3)
\t\tif score > best_score:
\t\t\tbest_score = score
''')
    source = in_func(source, "_offense",
        '''\theavy_chance = clampf(heavy_chance * float(_personality.get("heavy_scale", 1.0)), 0.03, 0.65)
''',
        '''\theavy_chance = clampf(heavy_chance * float(_personality.get("heavy_scale", 1.0)), 0.03, 0.65)
\t# FRG13C - moderately favor heavy pressure against persistent blockers.
\t# Do not slow down immediate whiff punishments.
\tif _punish_t <= 0.0 and not ranged and o.state == Fighter.S.BLOCK and _guard_habit():
\t\theavy_chance = clampf(heavy_chance + clampf(float(_read_level().get("charged_bias", 0.0)), 0.0, 0.16), 0.03, 0.68)
''')
    # Put helper functions at end to keep no other code modifications necessary.
    source = source.rstrip() + "\n" + OBSERVE_FUNCTIONS
    return source


def sha(b: bytes | None) -> str | None:
    return hashlib.sha256(b).hexdigest() if b is not None else None


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp_13c_" + uuid.uuid4().hex[:8])
    try:
        tmp.write_bytes(content)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def make_plan(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise ValueError("project.godot not found. Run inside your Godot project folder.")
    file = root / AI_FILE
    if not file.is_file():
        raise ValueError("Missing " + AI_FILE)
    old = file.read_text(encoding="utf-8-sig")
    updated = patch_ai(old)
    plan: dict[str, bytes] = {}
    if old != updated:
        plan[AI_FILE] = updated.encode("utf-8")
    if not (root / CONFIG_FILE).exists():
        plan[CONFIG_FILE] = (json.dumps(CONFIG, indent=2) + "\n").encode("utf-8")
    report = root / REPORT_FILE
    if not report.is_file() or report.read_text(encoding="utf-8") != REPORT:
        plan[REPORT_FILE] = REPORT.encode("utf-8")
    return plan


def install(root: Path, plan: dict[str, bytes], dry_run: bool) -> None:
    if not plan:
        print("Update 13C already installed; nothing changed.")
        return
    print("Update 13C changes:")
    for key in plan:
        print(" -", key)
    if dry_run:
        print("Dry run only; no files changed.")
        return
    backup = root.parent / (root.name + "_backups") / (
        "ai_13c_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for rel, content in plan.items():
        old = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest["files"][rel] = {"before": sha(old), "after": sha(content)}
        if old is not None:
            dest = backup / "originals" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(old)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    written: list[str] = []
    try:
        for rel, content in plan.items():
            atomic_write(root / rel, content)
            written.append(rel)
    except Exception:
        for rel in reversed(written):
            orig = backup / "originals" / rel
            if orig.is_file():
                atomic_write(root / rel, orig.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print("Installed Update 13C. Backup:", backup)


def restore(root: Path, directory: str) -> None:
    backup = Path(directory).expanduser().resolve()
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest["project"]).resolve() != root:
        raise ValueError("Backup does not belong to this update/project")
    for rel, sig in manifest["files"].items():
        file = root / rel
        now = file.read_bytes() if file.is_file() else None
        if sha(now) != sig["after"]:
            raise ValueError("File changed after installation; won't overwrite: " + rel)
        orig = backup / "originals" / rel
        if sig["before"] is not None and (not orig.is_file() or sha(orig.read_bytes()) != sig["before"]):
            raise ValueError("Backup is corrupted: " + rel)
    for rel, sig in manifest["files"].items():
        orig = backup / "originals" / rel
        if orig.is_file():
            atomic_write(root / rel, orig.read_bytes())
        else:
            (root / rel).unlink(missing_ok=True)
    print("Restored:", backup)


def check_godot(root: Path) -> None:
    exe = shutil.which("godot") or shutil.which("godot4")
    if exe is None:
        print("Godot not on PATH; open the project in Godot Editor to validate scripts.")
        return
    done = subprocess.run([exe, "--headless", "--editor", "--path", str(root), "--quit"],
                          capture_output=True, text=True, timeout=150)
    print((done.stdout + "\n" + done.stderr)[-12000:])
    if done.returncode:
        raise RuntimeError("Godot headless check failed: " + str(done.returncode))


def main() -> int:
    parser = argparse.ArgumentParser(description="Fight Royale Godot Update 13C — adaptive opponent reads")
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
            install(root, make_plan(root), args.dry_run)
            if args.check_godot and not args.dry_run:
                check_godot(root)
        return 0
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
