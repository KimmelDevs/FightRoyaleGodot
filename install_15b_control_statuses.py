#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot - Update 15B: control statuses (freeze, root, silence, paralyze).

Run from inside the Godot project folder:
    python install_15b_control_statuses.py

Requires Update 15A. No characters receive these statuses until their kits/passives
explicitly apply them. This installer preserves custom rules/passive profiles.
Optional: --dry-run, --check-godot, --restore PATH, --project PATH
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

VERSION = "15B.1"
FLAG = "# FRG15B - control status protections"
RUNTIME_FILE = "scripts/combat_status.gd"
FIGHTER_FILE = "scripts/fighter.gd"
RULES_FILE = "data/status_rules_15a.json"
REPORT_FILE = "reports/control_statuses_15b.txt"

ADDED_RULES = {
    "freeze": {
        "label": "Frozen", "max_stacks": 1, "duration": 2.0,
        "control": "freeze", "immunity_after": 4.0, "modifiers": {}
    },
    "paralyze": {
        "label": "Paralyzed", "max_stacks": 1, "duration": 1.0,
        "control": "freeze", "immunity_after": 2.5, "modifiers": {}
    },
    "root": {
        "label": "Rooted", "max_stacks": 1, "duration": 1.6,
        "control": "root", "immunity_after": 1.5, "modifiers": {}
    },
    "silence": {
        "label": "Silenced", "max_stacks": 1, "duration": 2.2,
        "control": "silence", "immunity_after": 1.0, "modifiers": {}
    },
}

REPORT = """FIGHT ROYALE - UPDATE 15B: CONTROL STATUS MECHANICS

Adds four optional, data-driven effects to the 15A status runtime:
- freeze: 2.0 seconds; prevents movement/attack/block/skills; 4s refreeze immunity.
- paralyze: 1.0 second full-action lock; 2.5s repeat immunity.
- root: 1.6 seconds; prevents movement, sprint, jump and dash; can still attack.
- silence: 2.2 seconds; prevents skills, but basic attack and block remain.

Status effects appear in the existing HP HUD's status label.
All crowd-control immunities begin when the respective effect expires.
Characters do NOT receive these effects by default. Later fighter kits explicitly
apply them through add_status(effect_id, stacks, duration) or attack metadata.
No changes to damage, cooldowns, AI, skills, or existing passive assignments.
No changes to models or sound effects. Existing custom status rules are preserved.

Godot editor validation remains required before considering this runtime verified.
"""


def replace_one(source: str, old: str, new: str, label: str) -> str:
    n = source.count(old)
    if n != 1:
        raise ValueError(f"{label}: expected 1 unambiguous anchor, found {n}; no files changed")
    return source.replace(old, new, 1)


def patch_runtime(s: str) -> str:
    if FLAG in s:
        needed = ("func control_blocks(action: String)", "_control_ready", "immunity_after", "func has_effect(")
        if all(x in s for x in needed):
            return s
        raise ValueError("Incomplete 15B status runtime; refusing blind re-patch")
    if "FRG15A - status and passive runtime" not in s:
        raise ValueError("Update 15A status runtime is required before Update 15B")
    s = replace_one(s,
        "var _event_ready: Dictionary = {} # per-event cooldown deadlines\n",
        "var _event_ready: Dictionary = {} # per-event cooldown deadlines\n"
        + FLAG + "\nvar _control_ready: Dictionary = {} # next legal application time for control statuses\n",
        "immunity dictionary")
    s = replace_one(s,
        '''\tif duration <= 0.0:
\t\treturn false
\tvar previous: Dictionary = _effects.get(effect_id, {})
''',
        '''\tif duration <= 0.0:
\t\treturn false
\tvar control_id: String = String(rule.get("control", ""))
\tif control_id != "" and _clock < float(_control_ready.get(effect_id, -1.0)):
\t\treturn false
\tvar previous: Dictionary = _effects.get(effect_id, {})
''',
        "control immunity entry")
    s = replace_one(s,
        '''\t\t"left": maxf(float(previous.get("left", 0.0)), duration)
\t}
\treturn true
''',
        '''\t\t"left": maxf(float(previous.get("left", 0.0)), duration)
\t}
\tif control_id != "":
\t\t# Cooldown begins after the *applied* effect has elapsed.
\t\t_control_ready[effect_id] = _clock + duration + maxf(float(rule.get("immunity_after", 0.0)), 0.0)
\treturn true
''',
        "control cooldown after application")
    s = replace_one(s,
        '''\t_effects.clear()
\t_event_ready.clear()
\t_dot_bank = 0.0
''',
        '''\t_effects.clear()
\t_event_ready.clear()
\t_control_ready.clear()
\t_dot_bank = 0.0
''',
        "reset control state")
    s = replace_one(s,
        '''func stacks_of(effect_id: String) -> int:
\treturn int(_effects.get(effect_id, {}).get("stacks", 0))
''',
        '''func has_effect(effect_id: String) -> bool:
\treturn _effects.has(effect_id) and int(_effects[effect_id].get("stacks", 0)) > 0

func control_blocks(action: String) -> bool:
\t# Called after brain input is set but before actions are processed.
\tfor effect_id in _effects:
\t\tvar rule: Dictionary = _rules.get(effect_id, {})
\t\tvar kind: String = String(rule.get("control", ""))
\t\tif kind == "freeze":
\t\t\treturn true
\t\tif kind == "root" and action == "movement":
\t\t\treturn true
\t\tif kind == "silence" and action == "skill":
\t\t\treturn true
\treturn false

func stacks_of(effect_id: String) -> int:
\treturn int(_effects.get(effect_id, {}).get("stacks", 0))
''',
        "control query API")
    return s


def patch_fighter(s: str) -> str:
    if FLAG in s:
        needed = ('status_runtime.control_blocks("movement")', 'status_runtime.control_blocks("attack")', 'status_runtime.control_blocks("skill")')
        if all(x in s for x in needed):
            return s
        raise ValueError("Incomplete 15B fighter patch; refusing blind re-patch")
    if "FRG15A - status and passive runtime" not in s:
        raise ValueError("Update 15A fighter status runtime required before Update 15B")
    s = replace_one(s,
        '''func add_status(effect_id: String, stacks: int = 1, seconds: float = -1.0) -> bool:
\treturn status_runtime.apply_effect(effect_id, stacks, seconds) if status_runtime != null else false
''',
        '''func add_status(effect_id: String, stacks: int = 1, seconds: float = -1.0) -> bool:
\tif status_runtime == null:
\t\treturn false
\tvar applied: bool = status_runtime.apply_effect(effect_id, stacks, seconds)
\tif applied and model != null:
\t\tif effect_id in ["freeze", "paralyze"]:
\t\t\tmodel.flash(Color("#8acfff"), 0.25)
\t\telif effect_id == "root":
\t\t\tmodel.flash(Color("#a6a2ff"), 0.15)
\t\telif effect_id == "silence":
\t\t\tmodel.flash(Color("#d89bf0"), 0.15)
\treturn applied
''',
        "status application visual feedback")
    s = replace_one(s,
        '''\tif status_runtime != null:
\t\tstatus_runtime.step(dt)
\tif guard_fatigue > 0 and dt > 0.0:
''',
        '''\tif status_runtime != null:
\t\tstatus_runtime.step(dt)
\t\t# FRG15B - Apply CC to both player and AI inputs; no editor setup needed.
\t\tif status_runtime.control_blocks("movement"):
\t\t\tin_move = Vector3.ZERO
\t\t\tin_dash = Vector3.ZERO
\t\t\tin_dodge = Vector3.ZERO
\t\t\tin_sprint = false
\t\t\tin_jump = false
\t\t\t_steer_vel = Vector3.ZERO
\t\t\t_dash_t = 0.0
\t\t\t_dodge_t = 0.0
\t\tif status_runtime.control_blocks("attack"):
\t\t\tin_attack = false
\t\t\t_atk_prev = false
\t\t\t_holding = false
\t\t\tif state in [S.ATTACK, S.CHARGE]:
\t\t\t\t_interrupt_attack()
\t\t\t\t_set_state(S.IDLE)
\t\tif status_runtime.control_blocks("skill"):
\t\t\tin_skill = ""
\t\t\t_queued_skill = ""
\t\t\t_queued_skill_t = 0.0
\t\tif status_runtime.control_blocks("defense"):
\t\t\tin_block = false
\t\t\tif state == S.BLOCK:
\t\t\t\t_set_state(S.IDLE)
\tif guard_fatigue > 0 and dt > 0.0:
''',
        "enforce status action restrictions")
    # Control states do not get combat recovery exploits. A root-only fighter can
    # still attack; a silenced fighter can still block and perform basic attacks.
    s = replace_one(s,
        '''class_name Fighter
extends Node3D
# FRG15A - status and passive runtime
''',
        '''class_name Fighter
extends Node3D
# FRG15A - status and passive runtime
''' + FLAG + "\n",
        "fighter marker")
    return s


def json_bytes(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def changes_for(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise ValueError("Run from the Godot project directory (project.godot must exist)")
    output: dict[str, bytes] = {}
    for rel, patch in [(RUNTIME_FILE, patch_runtime), (FIGHTER_FILE, patch_fighter)]:
        path = root / rel
        if not path.is_file():
            raise ValueError(f"Missing {rel}. Install Update 15A first")
        original = path.read_text(encoding="utf-8-sig")
        changed = patch(original)
        if changed != original:
            output[rel] = changed.encode("utf-8")

    p = root / RULES_FILE
    if not p.is_file():
        raise ValueError("Missing 15A status rules. Install Update 15A first")
    rules = json.loads(p.read_text(encoding="utf-8-sig"))
    if not isinstance(rules, dict) or not isinstance(rules.get("effects"), dict):
        raise ValueError("Invalid 15A status rules configuration")
    new = json.loads(json.dumps(rules))
    for effect_id, value in ADDED_RULES.items():
        if effect_id not in new["effects"]:
            new["effects"][effect_id] = value
        elif not isinstance(new["effects"][effect_id], dict):
            raise ValueError(f"Effect {effect_id} has invalid type")
        elif new["effects"][effect_id].get("control", "") != value["control"]:
            raise ValueError(f"Effect {effect_id} already exists with incompatible control type")
    if rules != new:
        output[RULES_FILE] = json_bytes(new)

    p = root / REPORT_FILE
    if not p.exists() or p.read_text(encoding="utf-8-sig") != REPORT:
        output[REPORT_FILE] = REPORT.encode("utf-8")
    return output


def digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp_15b_" + uuid.uuid4().hex[:10])
    try:
        tmp.write_bytes(data)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def install(root: Path, changes: dict[str, bytes], dry_run: bool) -> None:
    if not changes:
        print("Update 15B already installed; no changes")
        return
    print("Update 15B changes:")
    for rel in changes:
        print(" - " + rel)
    if dry_run:
        print("Dry run: no files changed")
        return
    backup = root.parent / (root.name + "_backups") / (
        "status_15b_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    )
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for rel, after in changes.items():
        old = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest["files"][rel] = {"before": digest(old), "after": digest(after)}
        if old is not None:
            target = backup / "originals" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(old)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    applied = []
    try:
        for rel, after in changes.items():
            atomic_write(root / rel, after)
            applied.append(rel)
    except Exception:
        for rel in reversed(applied):
            previous = backup / "originals" / rel
            if previous.is_file():
                atomic_write(root / rel, previous.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print("Installed 15B. Backup:", backup)


def restore(root: Path, folder: str) -> None:
    backup = Path(folder).expanduser().resolve()
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest.get("project", "")).resolve() != root:
        raise ValueError("Wrong project or backup version")
    for rel, info in manifest["files"].items():
        existing = (root / rel).read_bytes() if (root / rel).is_file() else None
        if digest(existing) != info["after"]:
            raise ValueError("File changed after install, refusing rollback: " + rel)
        original = backup / "originals" / rel
        if info["before"] is not None and (not original.is_file() or digest(original.read_bytes()) != info["before"]):
            raise ValueError("Damaged backup: " + rel)
    for rel in manifest["files"]:
        original = backup / "originals" / rel
        if original.is_file():
            atomic_write(root / rel, original.read_bytes())
        else:
            (root / rel).unlink(missing_ok=True)
    print("Restored", backup)


def check_godot(root: Path) -> None:
    exe = shutil.which("godot") or shutil.which("godot4")
    if not exe:
        print("Godot not on PATH; open the project in editor to verify imported assets and scripts")
        return
    p = subprocess.run([exe, "--headless", "--editor", "--path", str(root), "--quit"],
                       capture_output=True, text=True, timeout=120)
    print((p.stdout + "\n" + p.stderr)[-10000:])
    if p.returncode != 0:
        raise RuntimeError("Godot validation failed with exit status " + str(p.returncode))


def main() -> int:
    ap = argparse.ArgumentParser(description="Fight Royale Godot Update 15B - Crowd-control status mechanics")
    ap.add_argument("--project", type=Path, default=Path.cwd())
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore", metavar="BACKUP_DIR")
    ap.add_argument("--check-godot", action="store_true")
    args = ap.parse_args()
    root = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(root, args.restore)
        else:
            install(root, changes_for(root), args.dry_run)
            if args.check_godot and not args.dry_run:
                check_godot(root)
        return 0
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
