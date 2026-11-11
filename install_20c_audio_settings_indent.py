#!/usr/bin/env python3
"""Fight Royale Godot 20C — targeted main.gd audio UI indentation repair.

From an open CMD window in the project folder:
    python install_20c_audio_settings_indent.py

Corrects ONLY the leading whitespace in the two audio-related functions
introduced by 18B. Preserves all code, other lines, and line endings.
Creates a backup outside the Git repository and verifies the saved result.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from datetime import datetime


FUNC_1 = "func _set_audio_level(percent: float, channel: String) -> void:"
FUNC_2 = "func _audio_settings_section(parent: VBoxContainer) -> void:"
NEXT_FUNC = "func _begin_rebind(action: String, slot: int, button: Button) -> void:"
INDENT = re.compile(r"^([ \t]*)(.*)$")


def repair(content: str) -> tuple[str, list[tuple[int, str, str]]]:
    # Split with kept endings to preserve CRLF, LF, or unusual mixed endings.
    lines = content.splitlines(keepends=True)
    raw_lines = [line.rstrip("\r\n") for line in lines]
    for marker in (FUNC_1, FUNC_2, NEXT_FUNC):
        if raw_lines.count(marker) != 1:
            raise ValueError(f"Expected exactly one '{marker}', found {raw_lines.count(marker)}. No edits made.")
    i1, i2, i3 = (raw_lines.index(x) for x in (FUNC_1, FUNC_2, NEXT_FUNC))
    if not (i1 < i2 < i3):
        raise ValueError("Audio functions are in unexpected order; refusing to guess.")
    first_block = "\n".join(raw_lines[i1:i2])
    second_block = "\n".join(raw_lines[i2:i3])
    if "AudioSettings.set_level(channel, percent / 100.0)" not in first_block:
        raise ValueError("Audio volume assignment missing; refusing to modify file.")
    if "for item in [[\"master\"" not in second_block or "audio_grid" not in second_block:
        raise ValueError("Audio settings form differs from expected 18B layout; refusing to modify file.")
    changes = []
    for idx in range(i1 + 1, i3):
        if idx == i2:  # Second function declaration is correctly at column zero.
            continue
        line = lines[idx]
        original = raw_lines[idx]
        if not original.strip() or original.lstrip().startswith("#"):
            continue
        match = INDENT.match(original)
        if not match:
            continue
        old_prefix, code = match.groups()
        if not old_prefix:
            # All code within these functions must be indented. Refuse
            # silently altering structure, including unexpected new functions.
            raise ValueError(f"Unexpected unindented line {idx + 1}: {code[:90]}")
        if " " not in old_prefix:
            continue
        columns = len(old_prefix.expandtabs(4))
        if columns % 4 != 0:
            raise ValueError(f"Non-multiple-of-four indentation on line {idx + 1}: {old_prefix!r}")
        new_prefix = "\t" * (columns // 4)
        lines[idx] = new_prefix + line[len(old_prefix):]
        changes.append((idx + 1, old_prefix, new_prefix))
    output = "".join(lines)
    # Check all lines within the two affected functions; no mixed indentation.
    for idx, line in enumerate(output.splitlines(), 1):
        if i1 + 1 <= idx <= i3 and idx != i2 + 1 and line.strip() and not line.lstrip().startswith("#"):
            prefix = line[:len(line) - len(line.lstrip(" \t"))]
            if " " in prefix:
                raise ValueError(f"Line {idx} still uses spaces in indentation")
    # Apart from indentation, this script cannot alter any code line.
    if [x.lstrip(" \t") for x in content.splitlines()] != [x.lstrip(" \t") for x in output.splitlines()]:
        raise ValueError("Non-indentation changes detected; refusing to write file.")
    return output, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".", help="Directory containing project.godot")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()
    root = Path(args.project).expanduser().resolve()
    target = root / "scripts" / "main.gd"
    print("FIGHT ROYALE - PATCH 20C - AUDIO INDENTATION REPAIR")
    print("PROJECT:", root)
    print("SCRIPT: ", target)
    if not (root / "project.godot").is_file() or not target.is_file():
        print("ERROR: Run from the Godot project folder (project.godot and scripts/main.gd must exist).")
        return 2
    original = target.read_bytes()
    bom = b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b""
    try:
        source = original[len(bom):].decode("utf-8")
        fixed, changed = repair(source)
    except (UnicodeError, ValueError) as exc:
        print("ERROR:", exc)
        return 2
    print("Indentation lines to repair:", len(changed))
    for line_no, old, new in changed:
        print(f"  line {line_no}: {old!r} -> {new!r}")
    if not changed:
        print("Already fixed. If Godot still reports line 395, confirm you're running THIS project and restart the editor.")
        return 0
    if args.dry_run:
        print("DRY RUN ONLY; no file written.")
        return 0
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = root.parent / (root.name + "_backups") / ("main_audio_indent_20c_" + stamp)
    try:
        backup.mkdir(parents=True, exist_ok=False)
        shutil.copy2(target, backup / "main.gd")
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".frg20c_", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(bom + fixed.encode("utf-8"))
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        saved = target.read_bytes()
        if saved != bom + fixed.encode("utf-8"):
            raise RuntimeError("Saved bytes did not match repaired bytes")
        # Explicit post-write verification for the ORIGINAL reported error.
        check_content = saved[len(bom):].decode("utf-8")
        _, residual_changes = repair(check_content)
        if residual_changes:
            raise RuntimeError("Post-write check found space indentation remains")
        print("SUCCESS: main.gd audio settings indentation fixed and verified.")
        print("SHA256:", hashlib.sha256(saved).hexdigest())
        print("BACKUP:", backup / "main.gd")
        print("Next: fully close/reopen Godot, run the project, and inspect new errors if any.")
        return 0
    except Exception as exc:
        print("ERROR during save/verification:", exc)
        try:
            shutil.copy2(backup / "main.gd", target)
            print("Original main.gd restored from backup.")
        except Exception as restore_exc:
            print("CRITICAL: restore failed:", restore_exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
