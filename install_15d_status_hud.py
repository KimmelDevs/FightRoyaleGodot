#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot — Update 15D: status-effect HUD with timers and stacks.

From the Godot project directory:
    python install_15d_status_hud.py

Requires 15A-15C. Safe to repeat. Optional --dry-run, --check-godot,
--project PATH, and --restore BACKUP_DIR.
Does not edit character rigs, game balance, or assign any new passive.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

VERSION = "15D.1"
FLAG = "# FRG15D - status HUD and countdown indicators"
REPORT = """FIGHT ROYALE — UPDATE 15D — STATUS HUD

For Duel vs CPU and CPU vs CPU:
- Displays up to three active status labels below each fighter's HP/guard bars.
- Displays remaining seconds, stacks and buff/debuff colors.
- Additional effects are summarized as +N to prevent HUD overflow.
- Statuses are listed in stable alphabetical order to prevent jumpy labels.
- Existing guard-fatigue information remains beside the name.
- HUD reflects actual status-runtime state. It does not create statuses.
- Preserves skill cooldowns, models, combat and cameras.

Requires Updates 15A, 15B, 15C. Actual Godot runtime testing required.
"""


def one(s: str, old: str, new: str, label: str) -> str:
    n = s.count(old)
    if n != 1:
        raise ValueError(f"{label}: expected one unambiguous anchor; found {n}. No files changed")
    return s.replace(old, new, 1)


def patch_runtime(s: str) -> str:
    if FLAG in s:
        if 'func hud_effects() -> Array[Dictionary]:' in s:
            return s
        raise ValueError("Incomplete 15D runtime patch")
    if "FRG15C - damage/healing/cleanse status support" not in s:
        raise ValueError("Install Update 15C first (scripts/combat_status.gd)")
    needle = '''func short_label() -> String:
'''
    addition = '''# FRG15D - status HUD and countdown indicators
func hud_effects() -> Array[Dictionary]:
	# Provide immutable snapshots for HUD; never expose the mutable effects dictionary.
	var result: Array[Dictionary] = []
	for effect_id in _effects.keys():
		var effect: Dictionary = _effects.get(effect_id, {})
		var count: int = int(effect.get("stacks", 0))
		var seconds: float = maxf(float(effect.get("left", 0.0)), 0.0)
		if count <= 0 or seconds <= 0.0:
			continue
		var rule: Dictionary = _rules.get(effect_id, {})
		result.append({
			"id": String(effect_id),
			"label": String(rule.get("label", effect_id)),
			"stacks": count,
			"left": seconds,
			"category": String(rule.get("category", "neutral"))
		})
	# Stable visual order during refreshes; never sort the underlying runtime effects.
	result.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return String(a.get("id", "")) < String(b.get("id", "")))
	return result

'''
    return one(s, needle, addition + needle, "runtime snapshot API")


def patch_fighter(s: str) -> str:
    if FLAG in s:
        if "func status_details() -> Array[Dictionary]:" in s:
            return s
        raise ValueError("Incomplete 15D fighter patch")
    if "FRG15C - damage/healing/cleanse status support" not in s:
        raise ValueError("Install Update 15C first (scripts/fighter.gd)")
    needle = '''func status_summary() -> String:
	return status_runtime.short_label() if status_runtime != null else ""
'''
    addition = '''
# FRG15D - status HUD and countdown indicators
func status_details() -> Array[Dictionary]:
	if status_runtime == null:
		return []
	return status_runtime.hud_effects()
'''
    return one(s, needle, needle + addition, "fighter status bridge")


def patch_match(s: str) -> str:
    if FLAG in s:
        if '"status_effects": f.status_details()' in s:
            return s
        raise ValueError("Incomplete 15D match patch")
    if "FRG15A - status and passive runtime" not in s:
        raise ValueError("Missing status runtime; install Update 15A")
    needle = '''"fatigue": f.guard_fatigue, "status": f.status_summary()}'''
    new = '''"fatigue": f.guard_fatigue, "status": f.status_summary(), "status_effects": f.status_details()}'''
    s = one(s, needle, new, "match HUD fighter info")
    # Keep the marker outside of the expression so Godot parse remains unchanged.
    return one(s, '# --- HUD feed ------------------------------------------------------------------------------',
               FLAG + '\n# --- HUD feed ------------------------------------------------------------------------------', 'match version marker')


def patch_hud(s: str) -> str:
    if FLAG in s:
        if all(x in s for x in ('StatusRow', 'status_effects', 'Effect%d')):
            return s
        raise ValueError("Incomplete 15D HUD patch")
    if "FRG15A - status and passive runtime" not in s:
        raise ValueError("Missing status HUD base; install Update 15A")
    s = one(s,
        '''	var gd := _progress(Color("#7fc4ff"), 8); gd.name = "Guard"; box.add_child(gd)
	if right:
''',
        '''	var gd := _progress(Color("#7fc4ff"), 8); gd.name = "Guard"; box.add_child(gd)
	# FRG15D - status HUD and countdown indicators
	var status_row := HBoxContainer.new()
	status_row.name = "StatusRow"
	status_row.add_theme_constant_override("separation", 7)
	status_row.alignment = BoxContainer.ALIGNMENT_END if right else BoxContainer.ALIGNMENT_BEGIN
	for slot in range(3):
		var effect_label := _label(status_row, 13, Color("#ebefff"))
		effect_label.name = "Effect%d" % slot
		effect_label.visible = false
	status_row.visible = false
	box.add_child(status_row)
	if right:
''',
        'HUD status row creation')
    s = one(s,
        '''	var status_text: String = String(info.get("status", ""))
	if status_text != "":
		suffix += "  [%s]" % status_text
	(box.get_node("Name") as Label).text = "%s  %d / %d%s" % [info.name, int(ceil(info.hp)), int(info.max_hp), suffix]
	var hp: ProgressBar = box.get_node("Hp"); hp.max_value = info.max_hp; hp.value = info.hp
	var gd: ProgressBar = box.get_node("Guard"); gd.max_value = info.max_guard; gd.value = info.guard
''',
        '''	(box.get_node("Name") as Label).text = "%s  %d / %d%s" % [info.name, int(ceil(info.hp)), int(info.max_hp), suffix]
	var hp: ProgressBar = box.get_node("Hp"); hp.max_value = info.max_hp; hp.value = info.hp
	var gd: ProgressBar = box.get_node("Guard"); gd.max_value = info.max_guard; gd.value = info.guard
	# Active buffs/debuffs are shown as small timed labels, not in the fighter name.
	var row: HBoxContainer = box.get_node("StatusRow")
	var effects: Array = info.get("status_effects", [])
	row.visible = not effects.is_empty()
	for i in range(3):
		var cell: Label = row.get_node("Effect%d" % i)
		cell.visible = i < effects.size()
		if not cell.visible:
			continue
		if i == 2 and effects.size() > 3:
			cell.text = "+%d more" % (effects.size() - 2)
			cell.add_theme_color_override("font_color", Color("#c9d3e6"))
			continue
		var effect: Dictionary = effects[i]
		var label: String = String(effect.get("label", effect.get("id", "?")))
		var stacks: int = int(effect.get("stacks", 1))
		var left: float = maxf(float(effect.get("left", 0.0)), 0.0)
		cell.text = "%s%s %.1fs" % [label, ("x%d" % stacks if stacks > 1 else ""), left]
		var kind: String = String(effect.get("category", "neutral"))
		var tint := Color("#84e1b4") if kind == "buff" else (Color("#ffaaa3") if kind == "debuff" else Color("#e1d1ff"))
		cell.add_theme_color_override("font_color", tint)
''',
        'HUD timed statuses')
    return s


def digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def build(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise ValueError("project.godot not found; run from the Godot project directory")
    changes: dict[str, bytes] = {}
    for name, patch in [
        ("scripts/combat_status.gd", patch_runtime),
        ("scripts/fighter.gd", patch_fighter),
        ("scripts/match.gd", patch_match),
        ("scripts/hud.gd", patch_hud),
    ]:
        path = root / name
        if not path.is_file():
            raise ValueError(f"Missing file: {name}")
        original = path.read_text(encoding="utf-8-sig")
        result = patch(original)
        if result != original:
            changes[name] = result.encode("utf-8")
    path = root / "reports/status_hud_15d.txt"
    if not path.is_file() or path.read_text(encoding="utf-8-sig") != REPORT:
        changes["reports/status_hud_15d.txt"] = REPORT.encode("utf-8")
    return changes


def atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp15d_" + uuid.uuid4().hex[:8])
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def install(root: Path, changes: dict[str, bytes], dry: bool) -> None:
    if not changes:
        print("Update 15D already installed. No changes needed.")
        return
    print("Update 15D modifications:")
    for name in changes:
        print(" -", name)
    if dry:
        print("Dry run only; nothing changed")
        return
    folder = root.parent / (root.name + "_backups") / ("status_15d_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for name, after in changes.items():
        current = root / name
        before = current.read_bytes() if current.is_file() else None
        manifest["files"][name] = {"before": digest(before), "after": digest(after)}
        if before is not None:
            target = folder / "originals" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(before)
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    applied: list[str] = []
    try:
        for name, data in changes.items():
            atomic(root / name, data)
            applied.append(name)
    except Exception:
        for name in reversed(applied):
            original = folder / "originals" / name
            if original.is_file():
                atomic(root / name, original.read_bytes())
            else:
                (root / name).unlink(missing_ok=True)
        raise
    print("Installed Update 15D. Backup:", folder)


def restore(root: Path, backup_folder: str) -> None:
    folder = Path(backup_folder).expanduser().resolve()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest.get("project", "")).resolve() != root:
        raise ValueError("Backup belongs to another project or installer version")
    for name, hashes in manifest["files"].items():
        current = root / name
        now = current.read_bytes() if current.is_file() else None
        if digest(now) != hashes["after"]:
            raise ValueError(f"Refusing rollback: {name} was edited since installation")
        before_file = folder / "originals" / name
        if hashes["before"] is not None:
            if not before_file.is_file() or digest(before_file.read_bytes()) != hashes["before"]:
                raise ValueError(f"Backup corrupt for {name}")
    for name in manifest["files"]:
        previous = folder / "originals" / name
        if previous.is_file():
            atomic(root / name, previous.read_bytes())
        else:
            (root / name).unlink(missing_ok=True)
    print("Restored:", folder)


def godot_check(root: Path) -> None:
    executable = shutil.which("godot") or shutil.which("godot4")
    if not executable:
        print("Godot not found in PATH. Open Godot editor to verify the project.")
        return
    run = subprocess.run([executable, "--headless", "--editor", "--path", str(root), "--quit"],
                         capture_output=True, text=True, timeout=120)
    print((run.stdout + "\n" + run.stderr)[-8000:])
    if run.returncode:
        raise RuntimeError(f"Godot reported errors: exit code {run.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fight Royale Godot Update 15D — active status HUD")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-godot", action="store_true")
    parser.add_argument("--restore", metavar="BACKUP_DIR")
    args = parser.parse_args()
    root = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(root, args.restore)
        else:
            install(root, build(root), args.dry_run)
            if args.check_godot and not args.dry_run:
                godot_check(root)
        return 0
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
