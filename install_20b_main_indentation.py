#!/usr/bin/env python3
"""Fight Royale Godot - Patch 20B: finish main.gd indentation repair.

Run in the Godot project folder (CMD or PowerShell):
    python install_20b_main_indentation.py

This ONLY changes leading whitespace in scripts/main.gd, never gameplay code.
It is intended for the surviving Godot 4.7 indentation error on line 395
following Patch 20A. Creates a timestamped backup outside the repository.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile


INDENT = re.compile(r"^([\t ]+)([^\r\n]*)")


def read_prefix(line: str) -> tuple[str, str]:
    match = INDENT.match(line)
    return (match.group(1), line[len(match.group(1)):]) if match else ("", line)


def width(prefix: str) -> int:
    return len(prefix.expandtabs(4))


def significant_neighbor(lines: list[str], start: int, direction: int) -> tuple[int | None, str]:
    idx = start + direction
    while 0 <= idx < len(lines):
        prefix, body = read_prefix(lines[idx])
        code = body.strip()
        if code and not code.startswith("#"):
            return width(prefix) // 4, code
        idx += direction
    return None, ""


def choose_tabs(cols: int, lines: list[str], at: int) -> int:
    """Map a malformed indentation width to likely tab depth.

    Use nearest 4-column depth; when equidistant, use block context.
    Never dedent an originally indented line to column 0.
    """
    floor_depth = max(1, cols // 4)
    ceil_depth = max(1, (cols + 3) // 4)
    if floor_depth == ceil_depth:
        return floor_depth
    lo_error = abs(cols - floor_depth * 4)
    hi_error = abs(cols - ceil_depth * 4)
    if lo_error < hi_error:
        return floor_depth
    if hi_error < lo_error:
        return ceil_depth
    before_depth, before_text = significant_neighbor(lines, at, -1)
    after_depth, _ = significant_neighbor(lines, at, 1)
    if before_depth is not None and before_text.endswith(":"):
        expected = before_depth + 1
        if expected in (floor_depth, ceil_depth):
            return expected
    if before_depth in (floor_depth, ceil_depth) and before_depth == after_depth:
        return before_depth
    if after_depth in (floor_depth, ceil_depth):
        return after_depth
    if before_depth in (floor_depth, ceil_depth):
        return before_depth
    return ceil_depth


def fix(source: str) -> tuple[str, list[tuple[int, str, str]], list[str]]:
    lines = source.splitlines(keepends=True)
    new_lines = []
    edits = []
    diagnostics = []
    for i, line in enumerate(lines):
        prefix, body = read_prefix(line)
        if not prefix or not body.strip() or " " not in prefix:
            new_lines.append(line)
            continue
        cols = width(prefix)
        if cols % 4 == 0:
            depth = cols // 4
        else:
            depth = choose_tabs(cols, lines, i)
        changed = "\t" * depth
        if changed != prefix:
            new_lines.append(changed + body)
            edits.append((i + 1, repr(prefix), repr(changed)))
        else:
            new_lines.append(line)
    for at in (393, 394, 395, 396, 397):
        if at <= len(lines):
            old_prefix, old_body = read_prefix(lines[at - 1])
            new_prefix, new_body = read_prefix(new_lines[at - 1])
            if at == 395:
                diagnostics.append(f"Line 395 before: {repr(old_prefix)}; after: {repr(new_prefix)}; text: {new_body.strip()[:95]}")
            elif old_prefix != new_prefix:
                diagnostics.append(f"Line {at}: {repr(old_prefix)} -> {repr(new_prefix)}")
    return "".join(new_lines), edits, diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview edits only")
    parser.add_argument("--project", default=".", help="Godot project directory (default: current directory)")
    args = parser.parse_args()
    root = Path(args.project).resolve()
    target = root / "scripts" / "main.gd"
    if not (root / "project.godot").is_file() or not target.is_file():
        print("ERROR: Run inside the Godot project folder containing project.godot and scripts/main.gd")
        return 2
    original = target.read_bytes()
    bom = b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b""
    try:
        source = original[len(bom):].decode("utf-8")
    except UnicodeDecodeError as exc:
        print("ERROR: main.gd is not UTF-8:", exc)
        return 2
    output, changes, diagnostics = fix(source)
    print("FIGHT ROYALE - PATCH 20B - main.gd remaining indentation")
    print("Target:", target)
    for item in diagnostics:
        print(item)
    print("Lines with space-based indentation converted:", len(changes))
    for line_no, old, new in changes[:30]:
        print(f"  {line_no}: {old} -> {new}")
    if len(changes) > 30:
        print(f"  ...and {len(changes) - 30} more")
    if not changes:
        print("Nothing to modify. If Godot still reports line 395, close/reopen the editor and recheck the saved file.")
        print("If the error persists, share scripts/main.gd so the actual source can be inspected.")
        return 0
    if args.dry_run:
        print("DRY RUN - no file changed")
        return 0

    backup_dir = root.parent / (root.name + "_backups") / ("main_indent_20b_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    backup_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(target, backup_dir / "main.gd")
    new_bytes = bom + output.encode("utf-8")
    fd, temp_name = tempfile.mkstemp(prefix=".20b_", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(new_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except OSError as exc:
        try:
            shutil.copy2(backup_dir / "main.gd", target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        print("ERROR: write failed, original restored:", exc)
        return 2
    print("Saved main.gd. Backup:", backup_dir)
    print("Restart Godot and check the Debugger error list before committing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
