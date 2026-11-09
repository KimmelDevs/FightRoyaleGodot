#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot - Update 12D: Master AI tactical decisions and interruption safety.

From your Godot project directory:
    python install_12d_master_ai.py

Optional:
    python install_12d_master_ai.py --dry-run
    python install_12d_master_ai.py --check-godot
    python install_12d_master_ai.py --restore PATH_TO_BACKUP

Requires AI Updates 12A, 12B and 12C. Does not edit assets or balance data.
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

VERSION = "12D.1"
AI_PATH = "scripts/ai_brain.gd"
REPORT_PATH = "reports/master_ai_12d.txt"
MARKER = "# FRG12D - master tactical skill choice and interruption-safe inputs"
FIELDS = '''# FRG12D - master tactical skill choice and interruption-safe inputs
var _tactical_tries := 0
'''

TACTICAL_FUNCTION = '''func _select_tactical_skill(f: Fighter, o: Fighter, dist: float) -> String:
	# Only choose *equipped* skills that can execute from current range.
	# Lower difficulties retain their original random skill choices.
	var best_key := ""
	var best_score := -999.0
	var enemy_open: bool = o.state in [Fighter.S.HITSTUN, Fighter.S.STAGGER]
	var enemy_attacking: bool = o.state in [Fighter.S.ATTACK, Fighter.S.CHARGE]
	for key in ["z", "x", "c"]:
		if not _usable_skill(f, o, key, dist):
			continue
		var ability: Dictionary = f.attacks.get(key, {})
		var kind: String = String(ability.get("type", ""))
		var score: float = 0.25 + randf_range(-0.10, 0.10)
		match kind:
			"melee":
				var reach: float = float(ability.get("reach", 2.0))
				score += 0.55 if dist <= reach else 0.10
				if enemy_open: score += 0.75
				if o.state == Fighter.S.BLOCK: score += 0.18
			"projectile":
				score += 0.55 if dist > 3.0 else 0.05
				if enemy_open: score += 0.25
			"strike":
				var self_centered: bool = String(ability.get("at", "target")) == "self"
				score += (0.55 if dist < 2.8 else 0.10) if self_centered else 0.48
				if enemy_open: score += 0.30
			"blink":
				score += 0.75 if dist > 2.6 else 0.08
				if o.kit in RANGED: score += 0.20
			"buff":
				if String(ability.get("mode", "")) == "counter":
					score += 1.0 if enemy_attacking else -0.5
				else:
					var hp_fraction: float = f.hp / maxf(f.max_hp, 1.0)
					var guard_fraction: float = f.guard / maxf(f.max_guard, 1.0)
					score += 0.90 if hp_fraction < 0.45 or guard_fraction < 0.3 else 0.15
			_:
				continue
		if score > best_score:
			best_score = score
			best_key = key
	return best_key

'''

REPORT = '''FIGHT ROYALE GODOT — UPDATE 12D — MASTER AI REFINEMENTS

Requires 12A + 12B + 12C. Works in Duel vs CPU and CPU vs CPU.

- Pending attack and defensive inputs are cleared on HITSTUN/STAGGER, preventing
  stale actions from firing when the CPU recovers.
- AI skill decision cooldown now advances in real time even when the fighter is
  attacking or defending, instead of only during an idle frame.
- Hard/Master evaluate equipped skills using actual cooldown, distance, attack
  type and the opponent's current state. Easy/Normal keep simpler choices.
- If no skill is usable, the CPU rechecks shortly instead of wasting its entire
  skill-decision interval.
- Cooldown dictionary access is guarded against missing entries.
- No character stats, cooldown durations, hitboxes or model files are changed.

TEST IN GODOT:
1. CPU vs CPU: choose Master vs Hard with two melee characters.
2. Verify guard/parry/hitstun do not trigger stale attack inputs afterwards.
3. Verify CPUs use attacks and usable skills; compare to Easy vs Normal.
4. Test a melee fighter vs a ranged fighter and a rematch.
5. Check Godot Debugger for errors. Python checks cannot verify live gameplay.
'''


def replace_once(s: str, old: str, new: str, context: str) -> str:
    n = s.count(old)
    if n != 1:
        raise ValueError(f"{context}: expected exactly 1 anchor; found {n}. Send latest scripts/ai_brain.gd for compatibility fix.")
    return s.replace(old, new, 1)


def function_span(s: str, name: str) -> tuple[int, int, str]:
    found = list(re.finditer(rf"(?m)^func {re.escape(name)}\(", s))
    if len(found) != 1:
        raise ValueError(f"Expected exactly one function {name}, found {len(found)}")
    begin = found[0].start()
    next_match = re.search(r"(?m)^func [A-Za-z_][A-Za-z_0-9]*\(", s[found[0].end():])
    end = found[0].end() + next_match.start() if next_match else len(s)
    return begin, end, s[begin:end]


def patch_function(s: str, name: str, before: str, after: str) -> str:
    begin, end, body = function_span(s, name)
    body = replace_once(body, before, after, name)
    return s[:begin] + body + s[end:]


def patch_ai(s: str) -> str:
    if MARKER in s:
        required = ("func _select_tactical_skill(", "_skill_cd = maxf(_skill_cd - dt, 0.0)",
                    "_select_tactical_skill(f, o, dist)", "_queue.clear()")
        if all(x in s for x in required):
            return s
        raise ValueError("Incomplete Update 12D found; not modifying unknown intermediate state")
    for token in ("# FRG12A - deliberate spacing", "# FRG12B - predicted projectile defense",
                  "# FRG12C - grounded whiff punishment", "func _usable_skill(", "func _offense("):
        if token not in s:
            raise ValueError("Requires completed Updates 12A, 12B and 12C; missing: " + token)

    s = replace_once(s, 'var _engage_t := 0.0\n', 'var _engage_t := 0.0\n' + FIELDS, "AI fields")

    think_old = '''	var o = f.opponent
	if o == null or o.is_down(): return
	if o is Fighter: _react(f, o)
'''
    think_new = '''	var o = f.opponent
	if o == null or o.is_down(): return
	# Count real elapsed time while a fighter is attacking, blocking or recovering.
	_skill_cd = maxf(_skill_cd - dt, 0.0)
	# An interrupted windup must not resume an old combo, parry or delayed dodge.
	if f.state in [Fighter.S.HITSTUN, Fighter.S.STAGGER, Fighter.S.KO, Fighter.S.WIN]:
		_queue.clear()
		_hold = 0.0
		_block_wait = -1.0
		_block_hold = 0.0
		_jump_wait = -1.0
		_projectile_dodge_wait = -1.0
		_bait_t = 0.0
		_punish_t = 0.0
		return
	if o is Fighter: _react(f, o)
'''
    s = patch_function(s, "think", think_old, think_new)

    # Preserve the lower-tier random ability selection; Hard/Master make
    # context-aware decisions without altering fighter attack definitions.
    start, _, _ = function_span(s, "_try_skill")
    s = s[:start] + TACTICAL_FUNCTION + s[start:]
    s = patch_function(s, "_try_skill",
        '''	if f.cooldowns[key] > 0.0: return false
''',
        '''	if float(f.cooldowns.get(key, 999.0)) > 0.0: return false
''')

    old_skill = '''	# Try an off-cooldown skill only if the position and its action type fit.
	_skill_cd -= dt
	if _skill_cd <= 0.0 and _punish_t <= 0.0:
		_skill_cd = _r(float(p.skill[0]), float(p.skill[1]))
		var keys := ["c", "x", "z"]
		keys.shuffle()
		if randf() < (0.65 if p.think <= 0.75 else 0.5):
			for key in keys:
				if _usable_skill(f, o, key, dist) and _try_skill(f, key, true):
					_queue.clear()
					return
'''
    new_skill = '''	# Do not spend an entire decision interval when no equipped skill fits.
	if _skill_cd <= 0.0 and _punish_t <= 0.0:
		var picked := ""
		if float(p.think) <= 1.0:
			# Hard/Master consider range, counters and punishable openings.
			picked = _select_tactical_skill(f, o, dist)
			if randf() > (0.82 if float(p.think) <= 0.75 else 0.63):
				picked = ""
		else:
			var keys := ["c", "x", "z"]
			keys.shuffle()
			if randf() < 0.50:
				for key in keys:
					if _usable_skill(f, o, key, dist):
						picked = key
						break
		if picked != "" and _try_skill(f, picked, true):
			_skill_cd = _r(float(p.skill[0]), float(p.skill[1]))
			_queue.clear()
			return
		# Retry occasionally, but not every frame.
		_skill_cd = 0.24 if float(p.think) <= 1.0 else 0.45
'''
    s = patch_function(s, "_offense", old_skill, new_skill)
    return s


def sha(content: bytes | None) -> str | None:
    return hashlib.sha256(content).hexdigest() if content is not None else None


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".frg12d_" + uuid.uuid4().hex[:9] + ".tmp")
    try:
        tmp.write_bytes(content)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def plan(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise ValueError("Run from your Godot project directory containing project.godot")
    target = root / AI_PATH
    if not target.is_file():
        raise ValueError("Missing " + AI_PATH)
    original = target.read_text(encoding="utf-8-sig")
    changed = patch_ai(original)
    edits = {}
    if changed != original:
        edits[AI_PATH] = changed.encode("utf-8")
    if not (root / REPORT_PATH).is_file() or (root / REPORT_PATH).read_text(encoding="utf-8") != REPORT:
        edits[REPORT_PATH] = REPORT.encode("utf-8")
    return edits


def install(root: Path, edits: dict[str, bytes], dry: bool) -> None:
    if not edits:
        print("Update 12D already installed — nothing to change.")
        return
    print("Update 12D:")
    for name in edits:
        print(" - " + name)
    if dry:
        print("Dry run passed. No files changed.")
        return
    backup = (root.parent / (root.name + "_backups") /
              ("ai_12d_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:7]))
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for rel, content in edits.items():
        original = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest["files"][rel] = {"old": sha(original), "new": sha(content)}
        if original is not None:
            copy = backup / "originals" / rel
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(original)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    modified = []
    try:
        for rel, content in edits.items():
            atomic_write(root / rel, content)
            modified.append(rel)
    except Exception:
        for rel in reversed(modified):
            original = backup / "originals" / rel
            if original.is_file():
                atomic_write(root / rel, original.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print("Installed. Backup: " + str(backup))


def restore(root: Path, location: str) -> None:
    folder = Path(location).expanduser().resolve()
    data = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if data.get("version") != VERSION or Path(data["project"]).resolve() != root:
        raise ValueError("Backup is not an Update 12D backup for this project")
    for rel, info in data["files"].items():
        now = (root / rel).read_bytes() if (root / rel).is_file() else None
        if sha(now) != info["new"]:
            raise ValueError("Cannot safely restore; file changed after Update 12D: " + rel)
        if info["old"] is not None and not (folder / "originals" / rel).is_file():
            raise ValueError("Original backup missing: " + rel)
    for rel in data["files"]:
        original = folder / "originals" / rel
        if original.is_file():
            atomic_write(root / rel, original.read_bytes())
        else:
            (root / rel).unlink(missing_ok=True)
    print("Restored from " + str(folder))


def godot_check(root: Path) -> None:
    exe = shutil.which("godot") or shutil.which("godot4") or shutil.which("Godot")
    if not exe:
        print("Godot CLI not found on PATH; open the editor to validate GDScript")
        return
    r = subprocess.run([exe, "--headless", "--editor", "--path", str(root), "--quit"],
                       capture_output=True, text=True, timeout=120)
    print((r.stdout + "\n" + r.stderr)[-12000:])
    if r.returncode != 0:
        raise RuntimeError("Godot validation failed with exit code " + str(r.returncode))


def main() -> int:
    parser = argparse.ArgumentParser(description="Fight Royale Godot - Update 12D master AI")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", metavar="BACKUP_DIR")
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
    except Exception as ex:
        print("ERROR — " + str(ex), file=sys.stderr)
        print("Your existing game files were preserved if preflight failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
