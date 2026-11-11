#!/usr/bin/env python3
"""Fight Royale Godot - Patch 20A, safe GDScript parse repair.

Usage (CMD, already inside the Godot project):
    python install_20a_gdscript_parse_repair.py

Options:
    --dry-run             Show proposed changes without writing
    --project DIRECTORY   Point to a Godot project directory (defaults to current dir)

Only whitespace and three targeted declarations are changed. No kit data,
combat logic, or Godot scenes are regenerated. Original files are backed up
outside the project before replacement.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re
import shutil
import sys
import tempfile

REPAIRS = {
    "scripts/ai_brain.gd": [
        (
            "AI bool type",
            re.compile(r"(?m)^([ \t]*)var vulnerable\s*:=\s*o\.state\s+in\s+\[Fighter\.S\.HITSTUN,\s*Fighter\.S\.STAGGER\](?=\s*(?:#.*)?$)"),
            r"\1var vulnerable: bool = o.state in [Fighter.S.HITSTUN, Fighter.S.STAGGER]",
            "var vulnerable: bool =",
        )
    ],
    "scripts/fighter.gd": [
        (
            "Fighter movement speed type",
            re.compile(r"(?m)^([ \t]*)var speed\s*:=\s*move_speed\s*\*\s*\(SPRINT_MULT if sprint_now else 1\.0\)\s*\*\s*status_runtime\.movement_multiplier\(\)(?=\s*(?:#.*)?$)"),
            r"\1var speed: float = float(move_speed) * (SPRINT_MULT if sprint_now else 1.0) * float(status_runtime.movement_multiplier())",
            "var speed: float =",
        )
    ],
    "scripts/hud.gd": [
        (
            "HUD dictionary type",
            re.compile(r"(?m)^([ \t]*)var h\s*:=\s*match_node\.hud\(\)(?=\s*(?:#.*)?$)"),
            r"\1var h: Dictionary = match_node.hud()",
            "var h: Dictionary = match_node.hud()",
        )
    ],
}


def convert_indent_to_tabs(content: str) -> tuple[str, int, list[int]]:
    """Replace only indentation with exactly 4-space visual columns.

    Four spaces are one Godot tab (the repository uses one tab per code level).
    Indents with partial columns are left untouched and flagged for inspection,
    rather than guessing and accidentally changing program structure.
    """
    rewritten: list[str] = []
    count = 0
    partial: list[int] = []
    for lineno, line in enumerate(content.splitlines(keepends=True), 1):
        match = re.match(r"^([ \t]+)([^\r\n]*)", line)
        if not match or not match.group(2).strip():
            rewritten.append(line)
            continue
        prefix = match.group(1)
        if " " not in prefix:
            rewritten.append(line)
            continue
        columns = len(prefix.expandtabs(4))
        if columns % 4:
            partial.append(lineno)
            rewritten.append(line)
            continue
        tabs = "\t" * (columns // 4)
        if prefix != tabs:
            count += 1
            line = tabs + line[len(prefix):]
        rewritten.append(line)
    return "".join(rewritten), count, partial


def apply_targeted(content: str, relative_path: str) -> tuple[str, list[str]]:
    reports: list[str] = []
    for name, pattern, replacement, already_fixed in REPAIRS.get(relative_path, []):
        changed, hits = pattern.subn(replacement, content)
        if hits == 1:
            content = changed
            reports.append(f"  + {name}")
        elif hits == 0 and already_fixed in content:
            reports.append(f"  = Already fixed: {name}")
        elif hits == 0:
            reports.append(f"  ! Target not found: {name}; skipped rather than guessing")
        else:
            raise ValueError(f"{relative_path}: {name} matched {hits} times; refusing unsafe replacement")
    return content, reports


def write_exact(path: Path, data: bytes) -> None:
    # Create temp in same folder so os.replace is atomic on Windows/OneDrive.
    handle, temp_name = tempfile.mkstemp(prefix=".frg20a_", suffix=".tmp", dir=path.parent)
    try:
        with open(handle, "wb", closefd=True) as out:
            out.write(data)
        Path(temp_name).replace(path)
    finally:
        if Path(temp_name).exists():
            Path(temp_name).unlink()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--project", default=".", help="Godot project folder (defaults to current dir)")
    args = p.parse_args()
    project = Path(args.project).expanduser().resolve()
    scripts = project / "scripts"
    if not (project / "project.godot").is_file() or not scripts.is_dir():
        print("ERROR: Run this from the Fight Royale Godot project folder containing project.godot and scripts/.")
        return 2

    files = sorted(scripts.rglob("*.gd"))
    required = [project / relative for relative in REPAIRS]
    missing = [x for x in required if not x.is_file()]
    if missing:
        print("ERROR: Required script(s) missing; nothing has been changed:")
        for x in missing:
            print("  -", x.relative_to(project))
        return 2

    changes: dict[Path, tuple[bytes, bytes]] = {}
    msgs: list[str] = []
    for path in files:
        relative = path.relative_to(project).as_posix()
        original = path.read_bytes()
        bom = b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b""
        try:
            source = original[len(bom):].decode("utf-8")
        except UnicodeDecodeError:
            print("ERROR: Non-UTF-8 script; stopping:", relative)
            return 2
        fixed, normalized, partial = convert_indent_to_tabs(source)
        fixed, descriptions = apply_targeted(fixed, relative)
        updated = bom + fixed.encode("utf-8")
        if updated != original:
            changes[path] = (original, updated)
            msgs.append(f"{relative}: {normalized} indentation lines normalized")
            msgs.extend(descriptions)
        elif descriptions:
            msgs.append(f"{relative}: unchanged")
            msgs.extend(descriptions)
        if partial:
            msgs.append(f"  ! Non-4-column indentation left alone at lines: {', '.join(map(str, partial[:15]))}")

    print("FIGHT ROYALE - 20A GDScript Parser Repair")
    print(f"Project: {project}")
    print(f"Examined: {len(files)} .gd files | Modified: {len(changes)}")
    for msg in msgs:
        print(msg)
    if not changes:
        print("No changes needed. The repair may have been installed already.")
        return 0
    if args.dry_run:
        print("DRY RUN - no files changed")
        return 0

    backup_root = project.parent / (project.name + "_backups")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = backup_root / ("gdscript_parser_20a_" + stamp)
    try:
        # Make a complete backup of all touched files before writing anything.
        for path in changes:
            dest = backup / path.relative_to(project)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
    except OSError as exc:
        print("ERROR: Could not create backups; no project files were modified:", exc)
        return 2

    written: list[Path] = []
    try:
        for path, (_, updated) in changes.items():
            write_exact(path, updated)
            written.append(path)
    except OSError as exc:
        for path in reversed(written):
            try:
                write_exact(path, changes[path][0])
            except OSError as rollback_error:
                print("CRITICAL: rollback failed for", path, rollback_error)
        print("ERROR: Repair failed; rollback attempted:", exc)
        print("Backups are at:", backup)
        return 2

    print("\nRepair installed successfully. Backups:", backup)
    print("Restart the Godot editor (or reload the project) and check Debugger > Errors.")
    print("If another parse error appears, capture its script name, line, and message.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
