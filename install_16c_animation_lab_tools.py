#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot — Update 16C: Animation Lab workflow tools.

Run from your Godot project folder:
    python install_16c_animation_lab_tools.py

Requires Update 16B. Adds undo/redo, pose copy/paste (also across fighters),
left/right mirroring, selected-joint reset and grouped slider drag history.
Existing saved character poses, rigs, VRMs, combat, and models are untouched.

Options: --dry-run, --check-godot, --restore BACKUP_DIRECTORY, --project PATH
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

VERSION = "16C.1"
TAG = "# FRG16C - animation lab pose tools"
FILE = "scripts/animation_lab.gd"


def replace_one(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one anchor, found {count}; no changes written")
    return source.replace(old, new, 1)


VARS = '''# FRG16C: temporary history in the editor; only Save Fighter writes to disk.
const FRG16C_HISTORY_LIMIT := 48
var _frg16c_undo_history: Array[Dictionary] = []
var _frg16c_redo_history: Array[Dictionary] = []
var _frg16c_clipboard: Dictionary = {}
var _frg16c_clipboard_valid := false
var _frg16c_clipboard_source := ""
var _frg16c_drag_active := false
var _frg16c_drag_recorded := false
'''

UI = '''\t# FRG16C: editing tools work with ALL 16B animation states, not just walk/run.
\t_style_text(panel, "Pose tools (Ctrl+Z / Ctrl+Y)", 15, Color("#ffe6a6"))
\tvar history_tools := HBoxContainer.new()
\tpanel.add_child(history_tools)
\t_button(history_tools, "Undo", _frg16c_undo)
\t_button(history_tools, "Redo", _frg16c_redo)
\tvar clipboard_tools := HBoxContainer.new()
\tpanel.add_child(clipboard_tools)
\t_button(clipboard_tools, "Copy Pose", _frg16c_copy_pose)
\t_button(clipboard_tools, "Paste Pose", _frg16c_paste_pose)
\tvar mirror_tools := HBoxContainer.new()
\tpanel.add_child(mirror_tools)
\t_button(mirror_tools, "Mirror L/R", _frg16c_mirror_pose)
\t_button(mirror_tools, "Reset Joint", _frg16c_reset_joint)
'''

HELPERS = '''# FRG16C: animation editing helpers; no skeleton rest pose or joint hierarchy changes.
func _frg16c_reset_history() -> void:
\t_frg16c_undo_history.clear()
\t_frg16c_redo_history.clear()
\t_frg16c_drag_active = false
\t_frg16c_drag_recorded = false

func _frg16c_snapshot() -> Dictionary:
\treturn {"profile": _profile.duplicate(true), "dirty": _dirty}

func _frg16c_drag_start() -> void:
\t_frg16c_drag_active = true
\t_frg16c_drag_recorded = false

func _frg16c_drag_end(_value_changed: bool) -> void:
\t_frg16c_drag_active = false
\t_frg16c_drag_recorded = false

func _frg16c_record_change() -> void:
\t# A continuous slider drag counts as ONE undo step, not hundreds.
\tif _frg16c_drag_active and _frg16c_drag_recorded:
\t\treturn
\t_frg16c_undo_history.append(_frg16c_snapshot())
\tif _frg16c_undo_history.size() > FRG16C_HISTORY_LIMIT:
\t\t_frg16c_undo_history.pop_front()
\t_frg16c_redo_history.clear()
\tif _frg16c_drag_active:
\t\t_frg16c_drag_recorded = true

func _frg16c_restore_snapshot(snapshot: Dictionary, message: String) -> void:
\tvar restored: Variant = snapshot.get("profile", {})
\tif not (restored is Dictionary):
\t\treturn
\t_profile = (restored as Dictionary).duplicate(true)
\t_dirty = bool(snapshot.get("dirty", true))
\t_frg16c_drag_active = false
\t_frg16c_drag_recorded = false
\t_refresh_sliders()
\t_refresh_gait()
\t_apply_live()
\t_info.text = message + " · Press Save Fighter to keep these edits."

func _frg16c_undo() -> void:
\tif _frg16c_undo_history.is_empty():
\t\t_info.text = "Nothing to undo."
\t\treturn
\tvar previous: Dictionary = _frg16c_undo_history.pop_back()
\t_frg16c_redo_history.append(_frg16c_snapshot())
\t_frg16c_restore_snapshot(previous, "Undid change")

func _frg16c_redo() -> void:
\tif _frg16c_redo_history.is_empty():
\t\t_info.text = "Nothing to redo."
\t\treturn
\tvar next_pose: Dictionary = _frg16c_redo_history.pop_back()
\t_frg16c_undo_history.append(_frg16c_snapshot())
\t_frg16c_restore_snapshot(next_pose, "Redid change")

func _frg16c_copy_pose() -> void:
\tvar poses: Dictionary = _profile.get("poses", {})
\tvar current: Variant = poses.get(_selected_state, {})
\tif not (current is Dictionary):
\t\t_info.text = "Selected pose has invalid data."
\t\treturn
\t_frg16c_clipboard = (current as Dictionary).duplicate(true)
\t_frg16c_clipboard_valid = true
\t_frg16c_clipboard_source = _selected_char + "/" + _selected_state
\t_info.text = "Copied " + _frg16c_clipboard_source + " · Change state or fighter and Paste Pose."

func _frg16c_paste_pose() -> void:
\tif not _frg16c_clipboard_valid:
\t\t_info.text = "Copy a pose first."
\t\treturn
\tvar poses: Dictionary = _profile.get("poses", {})
\tvar current: Dictionary = poses.get(_selected_state, {})
\tif current == _frg16c_clipboard:
\t\t_info.text = "Destination pose already matches the copied pose."
\t\treturn
\t_frg16c_record_change()
\tposes[_selected_state] = _frg16c_clipboard.duplicate(true)
\t_profile["poses"] = poses
\t_refresh_sliders()
\t_mark_dirty()
\t_info.text = "Pasted " + _frg16c_clipboard_source + " into " + _selected_char + "/" + _selected_state + ". Save Fighter to keep it."

func _frg16c_mirror_pose() -> void:
\tvar poses: Dictionary = _profile.get("poses", {})
\tvar current: Dictionary = poses.get(_selected_state, {})
\tif current.is_empty():
\t\t_info.text = "This pose has no joint offsets to mirror."
\t\treturn
\tvar mirrored: Dictionary = {}
\tfor key in current.keys():
\t\tvar bone: String = String(key)
\t\tvar dest: String = bone
\t\tif bone.begins_with("Left"):
\t\t\tdest = "Right" + bone.substr(4)
\t\telif bone.begins_with("Right"):
\t\t\tdest = "Left" + bone.substr(5)
\t\tvar raw: Variant = current[key]
\t\tif not (raw is Array) or raw.size() != 3:
\t\t\tcontinue
\t\t# Mirror in local bone Euler coordinates: pitch stays, yaw/roll invert.
\t\tmirrored[dest] = [float(raw[0]), -float(raw[1]), -float(raw[2])]
\tif mirrored == current:
\t\t_info.text = "Pose is already symmetrical."
\t\treturn
\t_frg16c_record_change()
\tposes[_selected_state] = mirrored
\t_profile["poses"] = poses
\t_refresh_sliders()
\t_mark_dirty()
\t_info.text = "Mirrored Left/Right joint offsets for " + _selected_state + ". Save Fighter to keep it."

func _frg16c_reset_joint() -> void:
\tif _selected_bone.is_empty():
\t\t_info.text = "Select a joint first."
\t\treturn
\tif Profiles.get_angles(_profile, _selected_state, _selected_bone).length_squared() < 0.00001:
\t\t_info.text = "This joint is already reset."
\t\treturn
\t_frg16c_record_change()
\tProfiles.put_angles(_profile, _selected_state, _selected_bone, Vector3.ZERO)
\t_refresh_sliders()
\t_mark_dirty()

func _unhandled_key_input(event: InputEvent) -> void:
\tif not (event is InputEventKey):
\t\treturn
\tvar key_event := event as InputEventKey
\tif not key_event.pressed or key_event.echo or not key_event.ctrl_pressed:
\t\treturn
\tif key_event.keycode == KEY_Z:
\t\t_frg16c_undo()
\t\tget_viewport().set_input_as_handled()
\telif key_event.keycode == KEY_Y:
\t\t_frg16c_redo()
\t\tget_viewport().set_input_as_handled()

'''

REPORT = '''Fight Royale Godot — Update 16C: Animation Lab Pose Tools

Requires 16B. Open Main Menu > Animation Lab.
New controls:
  - Undo / Redo; Ctrl+Z and Ctrl+Y (up to 48 undo steps).
  - Copy Pose / Paste Pose between animation states AND fighters.
  - Mirror L/R (mirrors stored joint offsets; does not retarget whole animations).
  - Reset Joint without clearing the full state.
  - Slider drags are grouped into one history entry.

Changes remain in the preview until you press Save Fighter.
The clipboard is only in memory for the current Animation Lab session.
Existing saved profiles, VRM meshes, rig hierarchies, animation resources,
combat logic and AI are not modified.
Mirroring assumes ordinary left/right VRM humanoid conventions. Certain rigs
may need manual joint offset adjustments after mirroring.
'''


def patch_animation_lab(s: str) -> str:
    if TAG in s:
        indicators = ["func _frg16c_mirror_pose()", "func _frg16c_undo()", '"Paste Pose"', "_frg16c_record_change()"]
        if all(x in s for x in indicators):
            return s
        raise ValueError("Incomplete 16C patch detected; restore prior backup first")
    if "# FRG16B - combat choreography" not in s or "func _frg16b_preview_pose()" not in s:
        raise ValueError("Update 16B required before installing 16C (animation_lab.gd)")
    s = replace_one(s, 'var _gait_running := true\n',
                    'var _gait_running := true\n' + TAG + '\n' + VARS,
                    "16C state declarations")
    s = replace_one(s, '\t_info = _style_text(panel, "Changes are previews until Save Fighter is pressed.",',
                    UI + '\t_info = _style_text(panel, "Changes are previews until Save Fighter is pressed.",',
                    "Animation Lab controls")
    s = replace_one(s, '\t\tslider.value_changed.connect(_on_axis.bind(axis))\n',
                    '\t\tslider.value_changed.connect(_on_axis.bind(axis))\n'
                    '\t\tslider.drag_started.connect(_frg16c_drag_start)\n'
                    '\t\tslider.drag_ended.connect(_frg16c_drag_end)\n',
                    "Bone slider undo grouping")
    s = replace_one(s, '\t\tslider.value_changed.connect(_on_gait.bind(field))\n',
                    '\t\tslider.value_changed.connect(_on_gait.bind(field))\n'
                    '\t\tslider.drag_started.connect(_frg16c_drag_start)\n'
                    '\t\tslider.drag_ended.connect(_frg16c_drag_end)\n',
                    "Gait slider undo grouping")
    s = replace_one(s, '\t_profile = Profiles.load_for(_selected_char)\n',
                    '\t_profile = Profiles.load_for(_selected_char)\n\t_frg16c_reset_history()\n',
                    "Character switch history reset")
    s = replace_one(s, '''\tvar angles := Profiles.get_angles(_profile, _selected_state, _selected_bone)
\tangles[axis] = value
''',
        '''\tvar angles := Profiles.get_angles(_profile, _selected_state, _selected_bone)
\t_frg16c_record_change()
\tangles[axis] = value
''', "Bone edit history")
    s = replace_one(s, '''\tvar settings: Dictionary = _profile.get("gait", {})
\tsettings[field] = value
''',
        '''\t_frg16c_record_change()
\tvar settings: Dictionary = _profile.get("gait", {})
\tsettings[field] = value
''', "Gait edit history")
    s = replace_one(s, '''func _reset_state() -> void:
\tvar poses: Dictionary = _profile.get("poses", {})
''',
        '''func _reset_state() -> void:
\t_frg16c_record_change()
\tvar poses: Dictionary = _profile.get("poses", {})
''', "Reset state undo")
    s = replace_one(s, '''func _reset_all() -> void:
\t_profile = Profiles.new_profile()
''',
        '''func _reset_all() -> void:
\t_frg16c_record_change()
\t_profile = Profiles.new_profile()
''', "Reset all undo")
    s = replace_one(s, 'func _back() -> void:\n', HELPERS + 'func _back() -> void:\n',
                    "Pose utility functions")
    return s


def digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def build_changes(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise ValueError("project.godot missing; run the installer from your Godot project directory")
    target = root / FILE
    if not target.is_file():
        raise ValueError("Missing scripts/animation_lab.gd; install 16A and 16B first")
    original = target.read_text(encoding="utf-8-sig")
    updated = patch_animation_lab(original)
    changes: dict[str, bytes] = {}
    if updated != original:
        changes[FILE] = updated.encode("utf-8")
    report = "reports/animation_lab_16c.txt"
    if not (root / report).is_file() or (root / report).read_text(encoding="utf-8") != REPORT:
        changes[report] = REPORT.encode("utf-8")
    return changes


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp16c_" + uuid.uuid4().hex[:8])
    try:
        tmp.write_bytes(content)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def install(root: Path, changes: dict[str, bytes], dry_run: bool) -> Path | None:
    if not changes:
        print("Update 16C already installed; no changes needed.")
        return None
    print("Update 16C changes:")
    for name in changes:
        print(" -", name)
    if dry_run:
        print("Dry run OK; nothing written.")
        return None
    backup = (root.parent / (root.name + "_backups") /
              ("animation_lab_16c_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]))
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "root": str(root), "files": {}}
    for name, content in changes.items():
        dest = root / name
        previous = dest.read_bytes() if dest.is_file() else None
        manifest["files"][name] = {"before": digest(previous), "after": digest(content)}
        if previous is not None:
            saved = backup / "originals" / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(previous)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    written: list[str] = []
    try:
        for name, content in changes.items():
            atomic_write(root / name, content)
            written.append(name)
    except Exception:
        for name in reversed(written):
            saved = backup / "originals" / name
            if saved.is_file():
                atomic_write(root / name, saved.read_bytes())
            else:
                (root / name).unlink(missing_ok=True)
        raise
    print("Installed Update 16C. Backup:", backup)
    return backup


def restore(root: Path, backup_dir: str) -> None:
    backup = Path(backup_dir).expanduser().resolve()
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest.get("root", "")).resolve() != root:
        raise ValueError("Backup does not match this project and Update 16C")
    for name, hashes in manifest["files"].items():
        dest = root / name
        content = dest.read_bytes() if dest.is_file() else None
        if digest(content) != hashes["after"]:
            raise ValueError("Cannot restore: file changed since installation: " + name)
        saved = backup / "originals" / name
        if hashes["before"] is not None and (not saved.is_file() or digest(saved.read_bytes()) != hashes["before"]):
            raise ValueError("Missing or invalid backup: " + name)
    for name in manifest["files"]:
        saved = backup / "originals" / name
        if saved.is_file():
            atomic_write(root / name, saved.read_bytes())
        else:
            (root / name).unlink(missing_ok=True)
    print("Restored:", backup)


def validate_godot(root: Path) -> None:
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary:
        print("Godot executable not found in PATH; open project in Godot Editor to validate.")
        return
    result = subprocess.run([binary, "--headless", "--editor", "--path", str(root), "--quit"],
                            text=True, capture_output=True, timeout=120)
    print((result.stdout + "\n" + result.stderr)[-12000:])
    if result.returncode:
        raise RuntimeError("Godot validation failed with exit code " + str(result.returncode))


def main() -> int:
    parser = argparse.ArgumentParser(description="Fight Royale Godot Update 16C — Animation Lab Tools")
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
            install(root, build_changes(root), args.dry_run)
            if args.check_godot and not args.dry_run:
                validate_godot(root)
        return 0
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
