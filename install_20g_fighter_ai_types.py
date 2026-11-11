#!/usr/bin/env python3
"""Fight Royale Godot — Patch 20G: explicit GDScript variable types.

Run from the Godot project directory:
    python install_20g_fighter_ai_types.py

Repairs exactly two type inference errors:
    scripts/fighter.gd: var speed := ...  -> var speed: float = ...
    scripts/ai_brain.gd: var vulnerable := ... -> var vulnerable: bool = ...
The code expressions and behavior remain unchanged. No ZIP or manual editing.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

RULES = (
    (
        "scripts/fighter.gd",
        "speed",
        "float",
        ("move_speed", "status_runtime.movement_multiplier()"),
    ),
    (
        "scripts/ai_brain.gd",
        "vulnerable",
        "bool",
        ("o.state", "Fighter.S.HITSTUN", "Fighter.S.STAGGER"),
    ),
)


def patch_one(path: Path, name: str, typename: str, markers: tuple[str, ...]):
    raw = path.read_bytes()
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    text = raw[len(bom):].decode("utf-8")
    pattern = re.compile(
        rf"(?m)^([ \t]*)var {re.escape(name)}(?:(: {re.escape(typename)} =)|(\s*:=))([^\r\n]*)(\r?\n|$)"
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError(
            f"{path.name}: expected exactly one '{name}' declaration, found {len(matches)}; no files changed"
        )
    hit = matches[0]
    expr = hit.group(4)
    if not all(marker in expr for marker in markers):
        raise ValueError(
            f"{path.name}: unexpected expression for {name!r}: {expr.strip()!r}; no files changed"
        )
    if hit.group(2) is not None:
        return raw, None
    start, end = hit.span()
    replacement = hit.group(1) + f"var {name}: {typename} =" + expr + hit.group(5)
    modified = text[:start] + replacement + text[end:]
    output = bom + modified.encode("utf-8")
    return output, (hit.group().rstrip("\r\n"), replacement.rstrip("\r\n"))


def main() -> int:
    project = Path.cwd().resolve()
    print("FIGHT ROYALE — PATCH 20G: FIGHTER + AI TYPES", flush=True)
    print(f"Project: {project}", flush=True)
    if not (project / "project.godot").is_file():
        print("ERROR: project.godot not found. Run this installer from your Godot project folder.")
        return 2

    plans = []
    try:
        # Preflight ALL targets before modifying ANY file.
        for relative, name, typename, markers in RULES:
            file = project / relative
            if not file.is_file():
                raise FileNotFoundError(f"Missing file: {file}")
            updated, change = patch_one(file, name, typename, markers)
            plans.append((file, updated, change))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", flush=True)
        return 2

    needed = [t for t in plans if t[2] is not None]
    if not needed:
        print("Already fixed: both variables are explicitly typed.", flush=True)
        print("RESULT: PASS (no changes necessary)", flush=True)
        return 0

    backup_dir = project.parent / (project.name + "_backups") / (
        "patch_20g_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    )
    try:
        backup_dir.mkdir(parents=True, exist_ok=False)
        for file, output, change in needed:
            backup = backup_dir / file.name
            shutil.copy2(file, backup)
            print(f"Backup: {backup}", flush=True)

        for file, output, change in needed:
            before, after = change
            file.write_bytes(output)
            if file.read_bytes() != output:
                raise OSError(f"Disk verification failed: {file}")
            print(f"Fixed: {file.relative_to(project)}", flush=True)
            print(f"  BEFORE: {before.strip()}", flush=True)
            print(f"  AFTER : {after.strip()}", flush=True)

        for relative, name, typename, markers in RULES:
            file = project / relative
            saved, change = patch_one(file, name, typename, markers)
            if change is not None or saved != file.read_bytes():
                raise OSError(f"Validation failed for {file}")
            print(f"Verified: {relative}", flush=True)

        print("RESULT: PASS — both scripts have explicit types.", flush=True)
        print("Close Godot completely, reopen the project, and review any new errors.", flush=True)
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", flush=True)
        print("Attempting to restore all modified files from backups...", flush=True)
        for file, output, change in needed:
            backup = backup_dir / file.name
            if backup.is_file():
                try:
                    shutil.copy2(backup, file)
                except OSError as restore_error:
                    print(f"RESTORE ERROR {file}: {restore_error}", flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
