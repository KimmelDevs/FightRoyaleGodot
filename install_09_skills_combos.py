#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot — Update 09: responsive skills and combo input.

From the Godot project directory:
    python install_09_skills_combos.py

Options:
    python install_09_skills_combos.py --dry-run
    python install_09_skills_combos.py --check-godot
    python install_09_skills_combos.py --godot "C:/path/to/Godot.exe" --check-godot
    python install_09_skills_combos.py --restore "<backup folder shown by installer>"

Updates only scripts/fighter.gd and a report. Existing fighter stats, animations,
VRMs, weapon profiles, skill cooldown values, and SFX are not modified.
Requires Update 08 defense. Stdlib only, atomic writes, backup and safe restore.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

VERSION = "09.0"
MARKER = "# FRG09 - queued skills and combo input"
FIGHTER = "scripts/fighter.gd"
REPORT = "reports/skills_combos_09.txt"


def sha(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def replace_exact(source: str, old: str, new: str, label: str) -> str:
    found = source.count(old)
    if found != 1:
        raise RuntimeError(
            f"{label}: expected one matching code section, found {found}. "
            "Nothing was changed. Send your current scripts/fighter.gd for a tailored patch."
        )
    return source.replace(old, new, 1)


def patch_fighter(s: str) -> str:
    if MARKER in s:
        required = (
            "const SKILL_BUFFER_SECONDS := 0.45",
            "var _queued_skill := \"\"",
            "var _queued_light_t := 0.0",
            "func _read_skill(dt: float) -> void:",
            "func _try_queued_skill() -> void:",
            "func _try_queued_light(dt: float) -> void:",
            "_read_skill(dt)",
        )
        if all(x in s for x in required):
            return s
        raise RuntimeError("Update 09 marker exists, but some functions are missing; refusing to overwrite")

    prerequisites = (
        "class_name Fighter", "func _read_attack(dt: float)",
        "func _read_skill() -> void:", "func _request_light() -> void:",
        "func _interrupt_attack() -> void:", "attack_time_multiplier()",
        "guard_fatigue", "func _attack_step() -> void:",
        "func _start_attack(aid: String)", "func _finish_attack() -> void:",
        "# FRG08 - defense and guard fatigue",
    )
    missing = [x for x in prerequisites if x not in s]
    if missing:
        raise RuntimeError(
            "Expected Update 08 fighter code not found: " + ", ".join(missing) +
            ". Install earlier updates first or provide updated scripts/fighter.gd."
        )

    s = replace_exact(
        s,
        'const HOLD_T := 0.22\nconst CHARGE_MAX := 0.9',
        'const HOLD_T := 0.22\nconst CHARGE_MAX := 0.9\n'
        + MARKER + '\n'
        + 'const SKILL_BUFFER_SECONDS := 0.45  # Valid skill presses wait briefly for recovery\n'
        + 'const LIGHT_BUFFER_SECONDS := 0.24  # Late taps during attack rest\n',
        "new buffer durations",
    )
    s = replace_exact(
        s,
        'var _buffered := false\nvar _atk_prev := false',
        'var _buffered := false\n'
        'var _queued_skill := ""\n'
        'var _queued_skill_t := 0.0\n'
        'var _queued_light_t := 0.0\n'
        'var _atk_prev := false',
        "fighter queued input state",
    )
    s = replace_exact(
        s,
        '\t_read_attack(dt)\n\t_read_jump()\n\t_read_skill()\n\tmatch state:',
        '\t_read_attack(dt)\n\t_read_jump()\n\t_read_skill(dt)\n\tmatch state:',
        "tick reads skill with delta",
    )
    s = replace_exact(
        s,
        '\t\tS.HITSTUN, S.STAGGER:\n\t\t\tif state_t >= _stun: _set_state(S.IDLE)\n\t_move(dt)',
        '\t\tS.HITSTUN, S.STAGGER:\n\t\t\tif state_t >= _stun: _set_state(S.IDLE)\n'
        '\t# Execute buffered inputs after state transitions as well as before them.\n'
        '\t# Skills take priority over an attack buffered during ranged rest.\n'
        '\t_try_queued_skill()\n'
        '\t_try_queued_light(dt)\n'
        '\t_move(dt)',
        "tick post-state input execution",
    )
    old_attack = '''func _read_attack(dt: float) -> void:
	var on := in_attack
	var pressed := on and not _atk_prev
	var released := not on and _atk_prev
	_atk_prev = on
	if state in [S.HITSTUN, S.STAGGER, S.KO, S.WIN]:
		_holding = false; return
	if pressed and atk_lock > 0.0: return
	if pressed: _holding = true; _hold_t = 0.0
	if _holding:
		_hold_t += dt
		if _hold_t >= HOLD_T and state == S.IDLE and not in_block: _set_state(S.CHARGE)
	if released and _holding:
		_holding = false
		if state == S.CHARGE: _start_attack("heavy")
		elif _hold_t < HOLD_T: _request_light()
'''
    new_attack = '''func _read_attack(dt: float) -> void:
	var on := in_attack
	var pressed := on and not _atk_prev
	var released := not on and _atk_prev
	_atk_prev = on
	if state in [S.HITSTUN, S.STAGGER, S.KO, S.WIN]:
		_holding = false
		return
	# Record a tap even during ranged attack rest; whether it executes is
	# decided when the input is released, not when the button goes down.
	if pressed:
		_holding = true
		_hold_t = 0.0
	if _holding:
		_hold_t += dt
		if _hold_t >= HOLD_T and state == S.IDLE and atk_lock <= 0.0 and not in_block:
			_set_state(S.CHARGE)
	if released and _holding:
		_holding = false
		if state == S.CHARGE:
			_start_attack("heavy")
		elif _hold_t < HOLD_T:
			_request_light()
'''
    s = replace_exact(s, old_attack, new_attack, "light/charge input handling")

    old_skills = '''func _read_skill() -> void:
	var k := in_skill
	if k == "" or cooldowns.get(k, 1.0) > 0.0: return
	var free: bool = state in [S.IDLE, S.BLOCK, S.CHARGE] or (state == S.ATTACK and atk_phase == 2)
	if not free: return
	_holding = false
	cooldowns[k] = float(attacks[k].cd) * cd_mult
	_start_attack(k)

func _request_light() -> void:
	if state == S.IDLE or state == S.BLOCK:
		_start_attack(_combo_next if _combo_timer > 0.0 else "l1")
	elif state == S.ATTACK and not atk.is_empty() and atk.next != "":
		_buffered = true
'''
    new_skills = '''func _read_skill(dt: float) -> void:
	# A press during the wind-up or active phase is buffered briefly rather
	# than silently lost. A cooldown begins ONLY when the ability actually starts.
	if state in [S.HITSTUN, S.STAGGER, S.KO, S.WIN]:
		_queued_skill = ""
		_queued_skill_t = 0.0
		return
	if in_skill != "":
		var key: String = in_skill
		if attacks.has(key) and float(cooldowns.get(key, 1.0)) <= 0.0:
			_queued_skill = key
			_queued_skill_t = SKILL_BUFFER_SECONDS
	elif _queued_skill_t > 0.0:
		_queued_skill_t = maxf(_queued_skill_t - dt, 0.0)
		if _queued_skill_t <= 0.0:
			_queued_skill = ""
	_try_queued_skill()

func _try_queued_skill() -> void:
	if _queued_skill == "" or _queued_skill_t <= 0.0:
		return
	var key: String = _queued_skill
	if not attacks.has(key) or float(cooldowns.get(key, 1.0)) > 0.0:
		_queued_skill = ""
		_queued_skill_t = 0.0
		return
	var free: bool = state in [S.IDLE, S.BLOCK, S.CHARGE] or (state == S.ATTACK and atk_phase == 2)
	if not free:
		return
	_queued_skill = ""
	_queued_skill_t = 0.0
	_holding = false
	_buffered = false
	_combo_next = "l1"
	_combo_timer = 0.0
	cooldowns[key] = float(attacks[key].cd) * cd_mult
	_start_attack(key)

func _try_queued_light(dt: float) -> void:
	if _queued_light_t <= 0.0:
		return
	_queued_light_t = maxf(_queued_light_t - dt, 0.0)
	if _queued_light_t <= 0.0:
		return
	if state == S.IDLE and atk_lock <= 0.0 and not in_block and _queued_skill == "":
		_queued_light_t = 0.0
		_start_attack(_combo_next if _combo_timer > 0.0 else "l1")

func _request_light() -> void:
	if state == S.IDLE or state == S.BLOCK:
		if atk_lock > 0.0:
			_queued_light_t = LIGHT_BUFFER_SECONDS
		else:
			_start_attack(_combo_next if _combo_timer > 0.0 else "l1")
	elif state == S.ATTACK and not atk.is_empty() and atk.next != "":
		# One buffered follow-up per swing; cannot multiply damage or skip frames.
		_buffered = true
'''
    s = replace_exact(s, old_skills, new_skills, "skill buffering and light combo queue")
    s = replace_exact(
        s,
        '\t_buffered = false\n\tswing_serial += 1',
        '\t_buffered = false\n\t_queued_light_t = 0.0\n\tswing_serial += 1',
        "clear consumed queued light on attack start",
    )
    s = replace_exact(
        s,
        '''func _interrupt_attack() -> void:
	# A hit or clash cancels pending combo inputs; the next tap starts from l1.
	_holding = false
	_buffered = false
	_combo_next = "l1"
	_combo_timer = 0.0''',
        '''func _interrupt_attack() -> void:
	# Stuns, clashes, and guard breaks cancel EVERY queued action.
	_holding = false
	_buffered = false
	_queued_skill = ""
	_queued_skill_t = 0.0
	_queued_light_t = 0.0
	_combo_next = "l1"
	_combo_timer = 0.0''',
        "reset queue on interruption",
    )
    return s


def make_report(root: Path) -> str:
    attacks_path = root / "data/attacks.json"
    try:
        attacks = json.loads(attacks_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise RuntimeError(f"Cannot validate data/attacks.json: {e}") from e
    if not isinstance(attacks, dict):
        raise RuntimeError("data/attacks.json must be a JSON object")
    missing = {}
    chains = {}
    skill_count = 0
    for name, kit in attacks.items():
        if not isinstance(kit, dict):
            raise RuntimeError(f"Character {name} has an invalid attack table")
        absent = [k for k in ("l1", "heavy", "z", "x", "c", "v") if k not in kit]
        if absent:
            missing[name] = absent
        chain = []
        cur, seen = "l1", set()
        while cur and cur not in seen and cur in kit:
            seen.add(cur)
            chain.append(cur)
            item = kit[cur]
            if not isinstance(item, dict):
                raise RuntimeError(f"{name}.{cur}: malformed move object")
            cur = str(item.get("next", ""))
        if cur and cur not in kit:
            raise RuntimeError(f"{name}: light combo references missing move {cur!r}")
        chains[name] = " -> ".join(chain)
        skill_count += sum(1 for slot in ("z", "x", "c", "v") if slot in kit)
    if missing:
        raise RuntimeError("Incomplete attack tables: " + str(missing))
    text = [
        "FIGHT ROYALE GODOT | UPDATE 09 - SKILLS AND COMBOS",
        "",
        "Changes:",
        "- Skill presses made during attack wind-up/active frames buffer up to 0.45 seconds.",
        "- Buffered skills execute at the next legal recovery/idle opportunity.",
        "- Cooldown is applied only when a skill actually begins.",
        "- Short attack taps during ranged attack rest buffer for up to 0.24 seconds.",
        "- Light follow-ups retain their original 'next' links and combo duration.",
        "- Taking a hit, clash, or guard break clears queued commands.",
        "- Original damage, guard damage, skill cooldowns and poses are unchanged.",
        "",
        f"Characters with attack data: {len(attacks)}",
        f"Defined Z/X/C/V skills: {skill_count}",
        "",
        "Existing light-attack chains:",
    ]
    for name in sorted(chains):
        text.append(f"  {name}: {chains[name]}")
    text.extend([
        "",
        "Game modes: Duel vs CPU, CPU vs CPU only. No shop changes.",
        "Godot note: opening the project in the editor imports new .vrm files before play.",
        "To test: attack tap during a combo, Z/X/C during wind-up and during recovery,",
        "then verify each skill casts once and its cooldown starts on cast.",
        "This report statically validates attack data; it is not an engine gameplay test.",
        "",
    ])
    return "\n".join(text)


def safe_write(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_name(dest.name + ".frg09_" + uuid.uuid4().hex[:8] + ".tmp")
    try:
        temp.write_bytes(data)
        temp.replace(dest)
    finally:
        temp.unlink(missing_ok=True)


def build_changes(root: Path) -> dict[str, bytes]:
    source = root / FIGHTER
    if not (root / "project.godot").is_file() or not source.is_file():
        raise RuntimeError("Run from the Godot project folder containing project.godot and scripts/fighter.gd")
    old = source.read_text(encoding="utf-8")
    new = patch_fighter(old)
    result = {}
    if new != old:
        result[FIGHTER] = new.encode("utf-8")
    report = make_report(root).encode("utf-8")
    if not (root / REPORT).is_file() or (root / REPORT).read_bytes() != report:
        result[REPORT] = report
    return result


def install(root: Path, changes: dict[str, bytes], dry: bool) -> Path | None:
    if not changes:
        print("Already installed. No changes needed.")
        return None
    print("Files to update:")
    for rel in changes:
        print(" ", rel)
    if dry:
        print("Dry run: nothing written.")
        return None
    backup = root.parent / (root.name + "_backups") / (
        "skills_09_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    )
    backup.mkdir(parents=True, exist_ok=False)
    meta = {"version": VERSION, "project": str(root.resolve()), "files": {}}
    for rel, contents in changes.items():
        prev = (root / rel).read_bytes() if (root / rel).exists() else None
        meta["files"][rel] = {"old": sha(prev), "new": sha(contents)}
        if prev is not None:
            dest = backup / "originals" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(prev)
    (backup / "manifest.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    applied = []
    try:
        for rel, data in changes.items():
            safe_write(root / rel, data)
            applied.append(rel)
    except Exception:
        for rel in reversed(applied):
            original = backup / "originals" / rel
            dest = root / rel
            if original.is_file():
                safe_write(dest, original.read_bytes())
            else:
                dest.unlink(missing_ok=True)
        raise
    print("Backup:", backup)
    return backup


def restore(root: Path, folder: str) -> None:
    backup = Path(folder).expanduser().resolve()
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest.get("project", "")).resolve() != root.resolve():
        raise RuntimeError("This is not an Update 09 backup for the current project")
    entries = manifest["files"]
    for rel, info in entries.items():
        p = Path(rel)
        if p.is_absolute() or ".." in p.parts:
            raise RuntimeError(f"Unsafe backup entry {rel}")
        current = root / rel
        if not current.is_file() or sha(current.read_bytes()) != info["new"]:
            raise RuntimeError(f"{rel} has changed since installation; refusing overwrite")
        if info["old"] is not None:
            original = backup / "originals" / rel
            if not original.is_file() or sha(original.read_bytes()) != info["old"]:
                raise RuntimeError(f"Damaged original backup for {rel}")
    for rel, info in entries.items():
        if info["old"] is None:
            (root / rel).unlink(missing_ok=True)
        else:
            safe_write(root / rel, (backup / "originals" / rel).read_bytes())
        print("Restored:", rel)
    print("Update 09 restored.")


def check_godot(root: Path, selected: str | None) -> int:
    exe = None
    if selected:
        exe = str(Path(selected).expanduser().resolve()) if Path(selected).is_file() else shutil.which(selected)
    if not exe:
        exe = next((p for cmd in ("godot", "godot4", "godot.exe") if (p := shutil.which(cmd))), None)
    if not exe:
        print("Godot executable not on PATH. Open project in Godot editor and inspect Debugger > Errors.")
        return 0
    try:
        cp = subprocess.run([exe, "--headless", "--editor", "--path", str(root), "--quit"],
                            capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as error:
        print("Godot validation failed:", error)
        return 2
    output = (cp.stdout + "\n" + cp.stderr)[-10000:]
    print(output)
    if cp.returncode or re.search(r"(?:SCRIPT ERROR|Parse Error|Failed to load script)", output, re.I):
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fight Royale Godot - Update 09 Skills and Combos")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", metavar="BACKUP_FOLDER")
    parser.add_argument("--check-godot", action="store_true")
    parser.add_argument("--godot", help="Custom Godot executable path, requires --check-godot")
    args = parser.parse_args()
    root = Path.cwd().resolve()
    print("FIGHT ROYALE GODOT | UPDATE 09 - SKILLS AND COMBOS\nProject:", root)
    if args.restore:
        restore(root, args.restore)
        return 0
    changes = build_changes(root)
    install(root, changes, args.dry_run)
    if not args.dry_run:
        print("Done. See reports/skills_combos_09.txt for chain validation and testing steps.")
    if args.check_godot and not args.dry_run:
        return check_godot(root, args.godot)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError, UnicodeError, json.JSONDecodeError) as error:
        print("ERROR:", error, file=sys.stderr)
        raise SystemExit(1)
