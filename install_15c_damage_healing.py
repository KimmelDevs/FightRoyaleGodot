#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot — Update 15C: DoT, regeneration, and debuff cleansing.

From the Godot project directory:
    python install_15c_damage_healing.py

Requires 15A + 15B. Supports --dry-run, --project PATH,
--check-godot, and --restore BACKUP_DIR.

This installs status primitives only: character kits are NOT modified.
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

VERSION = "15C.1"
FLAG = "# FRG15C - damage/healing/cleanse status support"
RUNTIME_FILE = "scripts/combat_status.gd"
FIGHTER_FILE = "scripts/fighter.gd"
RULES_FILE = "data/status_rules_15a.json"
REPORT_FILE = "reports/damage_healing_15c.txt"

NEW_RULES = {
    "poison": {
        "label": "Poison", "max_stacks": 3, "duration": 5.0,
        "category": "debuff", "modifiers": {},
        "dot_hp_fraction_per_second": 0.0018,
    },
    "regeneration": {
        "label": "Regeneration", "max_stacks": 3, "duration": 5.0,
        "category": "buff", "modifiers": {},
        "hot_hp_fraction_per_second": 0.0025,
    },
}

# Classify only default statuses; keep any user-defined classifications intact.
DEFAULT_CATEGORIES = {
    "haste": "buff", "focus": "buff", "fortify": "buff", "resolve": "buff",
    "guard_flow": "buff", "slow": "debuff", "weaken": "debuff",
    "brittle": "debuff", "scorch": "debuff", "bleed": "debuff",
    "freeze": "debuff", "paralyze": "debuff", "root": "debuff",
    "silence": "debuff", "poison": "debuff", "regeneration": "buff",
}

REPORT = """FIGHT ROYALE — UPDATE 15C: DAMAGE / HEALING / CLEANSE

Requires Update 15A and Update 15B.

Adds optional data-driven effects:
 - poison: 3 stacks maximum; 5-second duration; each stack deals 0.18%
   of maximum HP per second, at the existing 0.25-second status tick.
 - regeneration: 3 stacks maximum; 5-second duration; each stack heals
   0.25% of maximum HP per second, capped at maximum HP.

Existing scorch and bleed continue to work. Periodic damage resolves before
periodic healing; lethal status damage cannot be undone by regeneration.

New runtime method: status_runtime.cleanse_negative(max_count=-1) -> int.
New fighter method: cleanse_debuffs(max_count=-1) -> int.
New fighter method: remove_status(effect_id) -> void.

Classifies the original statuses as buffs or debuffs, preserving any existing
custom category values. Effect parameters are not overwritten.

No character automatically receives these effects. Their application comes
later in character kits and passive profiles, which can call
fighter.add_status(effect_id, stacks, seconds).

No changes to game modes, shop, stats, VRM assets, or combat audio.

Godot editor runtime testing is still required.
"""


def replace_one(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one unique anchor, found {count}; refusing modification")
    return source.replace(old, new, 1)


def patch_runtime(source: str) -> str:
    if FLAG in source:
        required = ("func cleanse_negative(", 'hot_hp_fraction_per_second',
                    'func clear_effect(', "func apply_effect(")
        if all(part in source for part in required):
            return source
        raise ValueError("Update 15C runtime marker found but implementation incomplete")
    if "FRG15B - control status protections" not in source:
        raise ValueError("Install Update 15B before 15C (status runtime)")
    source = replace_one(source,
        '## FRG15A - status and passive runtime\n',
        '## FRG15A - status and passive runtime\n' + FLAG + '\n',
        "runtime version marker")
    source = replace_one(source,
        '''func clear_effect(effect_id: String) -> void:
\t_effects.erase(effect_id)
''',
        '''func clear_effect(effect_id: String) -> void:
\t_effects.erase(effect_id)

func cleanse_negative(max_count: int = -1) -> int:
\t# -1 clears every debuff; positive values remove at most that many kinds.
\t# Return the number of distinct effects removed; immunity timers stay intact.
\tvar removed := 0
\tif max_count == 0:
\t\treturn 0
\tfor effect_id in _effects.keys():
\t\tvar rule: Dictionary = _rules.get(effect_id, {})
\t\tif String(rule.get("category", "")) != "debuff":
\t\t\tcontinue
\t\t_effects.erase(effect_id)
\t\tremoved += 1
\t\tif max_count > 0 and removed >= max_count:
\t\t\tbreak
\treturn removed
''',
        "cleanse API")
    source = replace_one(source,
        '''\t\tvar damage := 0.0
\t\tfor effect_id in _effects:
\t\t\tvar rule: Dictionary = _rules.get(effect_id, {})
\t\t\tdamage += float(rule.get("dot_hp_fraction_per_second", 0.0)) * stacks_of(effect_id) * 0.25 * float(_host.max_hp)
\t\tif damage > 0.0:
\t\t\t_host.receive_status_damage(damage)
\t\t\tif _host.is_down():
\t\t\t\tclear_all()
\t\t\t\tbreak
''',
        '''\t\tvar damage := 0.0
\t\tvar healing := 0.0
\t\tfor effect_id in _effects:
\t\t\tvar rule: Dictionary = _rules.get(effect_id, {})
\t\t\tvar stack_count: int = stacks_of(effect_id)
\t\t\tdamage += maxf(float(rule.get("dot_hp_fraction_per_second", 0.0)), 0.0) * stack_count * 0.25 * float(_host.max_hp)
\t\t\thealing += maxf(float(rule.get("hot_hp_fraction_per_second", 0.0)), 0.0) * stack_count * 0.25 * float(_host.max_hp)
\t\tif damage > 0.0:
\t\t\t_host.receive_status_damage(damage)
\t\t\tif _host.is_down():
\t\t\t\tclear_all()
\t\t\t\tbreak
\t\tif healing > 0.0 and _host.has_method("heal"):
\t\t\t_host.heal(healing)
''',
        "periodic healing and damage resolution")
    return source


def patch_fighter(source: str) -> str:
    if FLAG in source:
        if all(x in source for x in ("func cleanse_debuffs(", "func remove_status(", 'effect_id == "regeneration"')):
            return source
        raise ValueError("Update 15C fighter marker found but implementation incomplete")
    if "FRG15B - control status protections" not in source:
        raise ValueError("Install Update 15B before 15C (fighter code)")
    source = replace_one(source,
        '# FRG15B - control status protections\n',
        '# FRG15B - control status protections\n' + FLAG + '\n',
        "fighter version marker")
    source = replace_one(source,
        '''\t\telif effect_id == "silence":
\t\t\tmodel.flash(Color("#d89bf0"), 0.15)
\treturn applied
''',
        '''\t\telif effect_id == "silence":
\t\t\tmodel.flash(Color("#d89bf0"), 0.15)
\t\telif effect_id in ["scorch", "poison"]:
\t\t\tmodel.flash(Color("#ff9456") if effect_id == "scorch" else Color("#78c66a"), 0.16)
\t\telif effect_id == "bleed":
\t\t\tmodel.flash(Color("#d74c5a"), 0.16)
\t\telif effect_id == "regeneration":
\t\t\tmodel.flash(Color("#52db99"), 0.17)
\treturn applied

func cleanse_debuffs(max_count: int = -1) -> int:
\tif status_runtime == null:
\t\treturn 0
\treturn status_runtime.cleanse_negative(max_count)

func remove_status(effect_id: String) -> void:
\tif status_runtime != null:
\t\tstatus_runtime.clear_effect(effect_id)
''',
        "fighter heal and cleanse bridge")
    return source


def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def make_changes(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise ValueError("Run from the Godot project directory (project.godot missing)")
    changes: dict[str, bytes] = {}
    for rel, patcher in [(RUNTIME_FILE, patch_runtime), (FIGHTER_FILE, patch_fighter)]:
        file = root / rel
        if not file.is_file():
            raise ValueError(f"Missing {rel}; install Update 15A and 15B first")
        original = file.read_text(encoding="utf-8-sig")
        edited = patcher(original)
        if edited != original:
            changes[rel] = edited.encode("utf-8")

    rules_path = root / RULES_FILE
    if not rules_path.is_file():
        raise ValueError("Missing status_rules_15a.json; install 15A and 15B first")
    rules = json.loads(rules_path.read_text(encoding="utf-8-sig"))
    if not isinstance(rules, dict) or not isinstance(rules.get("effects"), dict):
        raise ValueError("Invalid status rules JSON")
    modified = json.loads(json.dumps(rules))
    effects = modified["effects"]
    for effect_id, value in NEW_RULES.items():
        if effect_id not in effects:
            effects[effect_id] = value
        elif not isinstance(effects[effect_id], dict):
            raise ValueError(f"Invalid rules for {effect_id}")
    for effect_id, category in DEFAULT_CATEGORIES.items():
        if effect_id in effects:
            if not isinstance(effects[effect_id], dict):
                raise ValueError(f"Invalid rules for {effect_id}")
            effects[effect_id].setdefault("category", category)
    if rules != modified:
        changes[RULES_FILE] = json_bytes(modified)

    report_path = root / REPORT_FILE
    if not report_path.exists() or report_path.read_text(encoding="utf-8-sig") != REPORT:
        changes[REPORT_FILE] = REPORT.encode("utf-8")
    return changes


def sha(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp15c_" + uuid.uuid4().hex[:8])
    try:
        tmp.write_bytes(data)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def install(root: Path, changes: dict[str, bytes], dry_run: bool) -> None:
    if not changes:
        print("Update 15C already installed; nothing to change")
        return
    print("Update 15C changes:")
    for rel in changes:
        print(" -", rel)
    if dry_run:
        print("Dry run — no files changed")
        return
    backup = root.parent / (root.name + "_backups") / (
        "status_15c_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    )
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for rel, after in changes.items():
        old_path = root / rel
        previous = old_path.read_bytes() if old_path.is_file() else None
        manifest["files"][rel] = {"before": sha(previous), "after": sha(after)}
        if previous is not None:
            dest = backup / "originals" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(previous)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    applied = []
    try:
        for rel, after in changes.items():
            atomic_write(root / rel, after)
            applied.append(rel)
    except Exception:
        for rel in reversed(applied):
            prior = backup / "originals" / rel
            if prior.is_file():
                atomic_write(root / rel, prior.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print("Installed Update 15C. Backup:", backup)


def restore(root: Path, folder: str) -> None:
    backup = Path(folder).expanduser().resolve()
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest.get("project", "")).resolve() != root:
        raise ValueError("Incorrect project or backup version")
    for rel, entry in manifest["files"].items():
        target = root / rel
        current = target.read_bytes() if target.is_file() else None
        if sha(current) != entry["after"]:
            raise ValueError(f"Refusing rollback: {rel} was modified after installation")
        prior = backup / "originals" / rel
        if entry["before"] is not None and (not prior.is_file() or sha(prior.read_bytes()) != entry["before"]):
            raise ValueError(f"Backup is damaged: {rel}")
    for rel in manifest["files"]:
        prior = backup / "originals" / rel
        if prior.is_file():
            atomic_write(root / rel, prior.read_bytes())
        else:
            (root / rel).unlink(missing_ok=True)
    print("Restored", backup)


def check_godot(root: Path) -> None:
    exe = shutil.which("godot") or shutil.which("godot4")
    if exe is None:
        print("Godot executable not on PATH; open the project in the editor to check scripts")
        return
    result = subprocess.run([exe, "--headless", "--editor", "--path", str(root), "--quit"],
                            capture_output=True, text=True, timeout=120)
    print((result.stdout + "\n" + result.stderr)[-10000:])
    if result.returncode:
        raise RuntimeError(f"Godot script validation failed: exit code {result.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fight Royale Godot 15C — damage/healing statuses")
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
            install(root, make_changes(root), args.dry_run)
            if args.check_godot and not args.dry_run:
                check_godot(root)
        return 0
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
