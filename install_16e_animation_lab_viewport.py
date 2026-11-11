#!/usr/bin/env python3
"""Fight Royale Godot — Update 16E: Animation Lab camera and bone inspector.

From the Godot project directory:
    python install_16e_animation_lab_viewport.py

Requires Update 16D. Adds right-drag camera orbit, mouse-wheel zoom,
reset view, bone-marker and bone-label toggles while preserving pose data.
Options: --dry-run, --project PATH, --restore BACKUP_DIRECTORY.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

VERSION = "16E.1"
TAG = "# FRG16E - animation lab viewport inspector"
LAB_PATH = "scripts/animation_lab.gd"
REPORT_PATH = "reports/animation_lab_16e.txt"

VARS_BEFORE = '''var _frg16d_speed_select: OptionButton
# FRG16C - animation lab pose tools'''
VARS_AFTER = '''var _frg16d_speed_select: OptionButton
# FRG16E - animation lab viewport inspector
var _frg16e_orbit_yaw := 0.0
var _frg16e_orbit_pitch := 8.0
var _frg16e_distance := 4.2
var _frg16e_target := Vector3(0.0, 1.12, 0.0)
var _frg16e_dragging := false
var _frg16e_markers_visible := true
var _frg16e_labels_visible := false
var _frg16e_markers_button: Button
var _frg16e_labels_button: Button
# FRG16C - animation lab pose tools'''

CAMERA_BEFORE = '''	_camera.make_current()
	_camera.look_at(Vector3(0, 1.1, 0), Vector3.UP)
	var light := DirectionalLight3D.new()'''
CAMERA_AFTER = '''	_camera.make_current()
	_frg16e_update_camera()
	var light := DirectionalLight3D.new()'''

CONTROLS_BEFORE = '''	_button(tools, "Front", func(): _yaw = 0.0)
	_button(tools, "Side", func(): _yaw = 90.0)
	_button(tools, "Back", func(): _yaw = 180.0)
	# FRG16D: timeline controls are preview-only; no profile writes or undo history.'''
CONTROLS_AFTER = '''	_button(tools, "Front", func(): _yaw = 0.0)
	_button(tools, "Side", func(): _yaw = 90.0)
	_button(tools, "Back", func(): _yaw = 180.0)
	_button(tools, "Reset View", _frg16e_reset_view)
	var inspector_tools := HBoxContainer.new()
	right.add_child(inspector_tools)
	_frg16e_markers_button = _button(inspector_tools, "Joints: ON", _frg16e_toggle_markers)
	_frg16e_labels_button = _button(inspector_tools, "Names: OFF", _frg16e_toggle_names)
	_style_text(right, "Preview: right-drag to orbit, mouse wheel to zoom, left-click a joint to edit.", 13)
	# FRG16D: timeline controls are preview-only; no profile writes or undo history.'''

MARKER_BEFORE = '''	point.material_override = material
	_world.add_child(point)
	_marker_nodes[role] = point'''
MARKER_AFTER = '''	point.material_override = material
	var name_label := Label3D.new()
	name_label.text = role
	name_label.font_size = 18
	name_label.pixel_size = 0.0025
	name_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	name_label.no_depth_test = true
	name_label.position = Vector3(0.08, 0.035, 0.0)
	name_label.visible = _frg16e_labels_visible
	point.add_child(name_label)
	_world.add_child(point)
	_marker_nodes[role] = point'''

INPUT_BEFORE = '''func _viewport_input(event: InputEvent) -> void:
	if not (event is InputEventMouseButton):
		return
	var click := event as InputEventMouseButton
	if not click.pressed or click.button_index != MOUSE_BUTTON_LEFT:
		return
	if _model == null or _model.skeleton == null:
		return
	var ratio := _view_box.size / Vector2(_view.size)
	var nearest := 28.0
	var chosen := ""
	for role in _marker_nodes:
		var node: MeshInstance3D = _marker_nodes[role]
		if not node.visible:
			continue
		var pixel: Vector2 = _camera.unproject_position(node.global_position) * ratio
		var dist: float = pixel.distance_to(event.position)
		if dist < nearest:
			nearest = dist
			chosen = role
	if chosen != "":
		var index := _joint_roles.find(chosen)
		if index >= 0:
			_bone.select(index)
			_change_bone(index)
		accept_event()
'''
INPUT_AFTER = '''func _viewport_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		if not _frg16e_dragging:
			return
		var motion := event as InputEventMouseMotion
		_frg16e_orbit_yaw -= motion.relative.x * 0.38
		_frg16e_orbit_pitch = clampf(_frg16e_orbit_pitch - motion.relative.y * 0.28, -45.0, 65.0)
		_frg16e_update_camera()
		accept_event()
		return
	if not (event is InputEventMouseButton):
		return
	var click := event as InputEventMouseButton
	if click.button_index == MOUSE_BUTTON_RIGHT:
		_frg16e_dragging = click.pressed
		accept_event()
		return
	if not click.pressed:
		return
	if click.button_index == MOUSE_BUTTON_WHEEL_UP:
		_frg16e_distance = clampf(_frg16e_distance * 0.90, 1.3, 12.0)
		_frg16e_update_camera()
		accept_event()
		return
	if click.button_index == MOUSE_BUTTON_WHEEL_DOWN:
		_frg16e_distance = clampf(_frg16e_distance * 1.10, 1.3, 12.0)
		_frg16e_update_camera()
		accept_event()
		return
	if click.button_index != MOUSE_BUTTON_LEFT or not _frg16e_markers_visible:
		return
	if _model == null or _model.skeleton == null:
		return
	var ratio := _view_box.size / Vector2(_view.size)
	var nearest := 28.0
	var chosen := ""
	for role in _marker_nodes:
		var node: MeshInstance3D = _marker_nodes[role]
		if not node.visible or _camera.is_position_behind(node.global_position):
			continue
		var pixel: Vector2 = _camera.unproject_position(node.global_position) * ratio
		var dist: float = pixel.distance_to(click.position)
		if dist < nearest:
			nearest = dist
			chosen = role
	if chosen != "":
		var index := _joint_roles.find(chosen)
		if index >= 0:
			_bone.select(index)
			_change_bone(index)
		accept_event()
'''

PROCESS_BEFORE = '''		marker.visible = bone_id >= 0
		if bone_id < 0:
			continue
		marker.global_position = _model.skeleton.global_transform * _model.skeleton.get_bone_global_pose(bone_id).origin
		var material: StandardMaterial3D = marker.material_override
		material.albedo_color = Color("#ffda72") if role == _selected_bone else Color("#60d2ff")'''
PROCESS_AFTER = '''		marker.visible = bone_id >= 0 and _frg16e_markers_visible
		if bone_id < 0:
			continue
		marker.global_position = _model.skeleton.global_transform * _model.skeleton.get_bone_global_pose(bone_id).origin
		var name_label := marker.get_child(0) as Label3D
		if is_instance_valid(name_label):
			name_label.visible = _frg16e_labels_visible
		var material: StandardMaterial3D = marker.material_override
		material.albedo_color = Color("#ffda72") if role == _selected_bone else Color("#60d2ff")'''

HELPERS = '''# FRG16E: viewport controls never alter FighterModel bones, profiles, or combat timing.
func _frg16e_update_camera() -> void:
	if not is_instance_valid(_camera):
		return
	var yaw := deg_to_rad(_frg16e_orbit_yaw)
	var pitch := deg_to_rad(_frg16e_orbit_pitch)
	var forward := Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch))
	_camera.position = _frg16e_target + forward * _frg16e_distance
	_camera.look_at(_frg16e_target, Vector3.UP)

func _frg16e_reset_view() -> void:
	_frg16e_dragging = false
	_frg16e_orbit_yaw = 0.0
	_frg16e_orbit_pitch = 8.0
	_frg16e_distance = 4.2
	_frg16e_update_camera()
	_yaw = 18.0

func _frg16e_toggle_markers() -> void:
	_frg16e_markers_visible = not _frg16e_markers_visible
	if is_instance_valid(_frg16e_markers_button):
		_frg16e_markers_button.text = "Joints: ON" if _frg16e_markers_visible else "Joints: OFF"

func _frg16e_toggle_names() -> void:
	_frg16e_labels_visible = not _frg16e_labels_visible
	if is_instance_valid(_frg16e_labels_button):
		_frg16e_labels_button.text = "Names: ON" if _frg16e_labels_visible else "Names: OFF"

'''


def replace_once(body: str, before: str, after: str, label: str) -> str:
    n = body.count(before)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {n}; no files modified")
    return body.replace(before, after, 1)


def hexdigest(content: bytes | None) -> str | None:
    return hashlib.sha256(content).hexdigest() if content is not None else None


def atomic_write(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".frg16e-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contents)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def modifications(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise RuntimeError("Run this inside the Godot project folder (project.godot not found).")
    lab_path = root / LAB_PATH
    if not lab_path.is_file():
        raise RuntimeError("Animation Lab is missing. Install 16A through 16D first.")
    lab = lab_path.read_text(encoding="utf-8-sig")
    if TAG in lab:
        print("Update 16E already installed. No changes needed.")
        return {}
    if "# FRG16D - animation lab preview timeline" not in lab:
        raise RuntimeError("Update 16D is required before installing 16E.")
    for label, before, after in [
        ("variables", VARS_BEFORE, VARS_AFTER),
        ("camera", CAMERA_BEFORE, CAMERA_AFTER),
        ("UI", CONTROLS_BEFORE, CONTROLS_AFTER),
        ("markers", MARKER_BEFORE, MARKER_AFTER),
        ("viewport input", INPUT_BEFORE, INPUT_AFTER),
        ("marker visibility", PROCESS_BEFORE, PROCESS_AFTER),
        ("view controls", "func _back() -> void:\n", HELPERS + "func _back() -> void:\n"),
    ]:
        lab = replace_once(lab, before, after, label)
    report = """Fight Royale Godot — Update 16E: Animation Lab Viewport Inspector

In Animation Lab:
- Right mouse drag: orbit the preview camera around the fighter
- Mouse wheel: zoom in/out within safe limits
- Front/Side/Back: rotate the preview model
- Reset View: restore the default camera and model orientation
- Joints toggle: show/hide selectable humanoid bone markers
- Names toggle: show/hide bone names beside their markers
- Left mouse click a joint to select it for editing with X/Y/Z sliders

This update does NOT edit a saved pose, modify a rig or VRM, or change combat timing.
It requires Update 16D. Open Godot once after installation to import scripts.
"""
    return {LAB_PATH: lab.encode("utf-8"), REPORT_PATH: report.encode("utf-8")}


def install(root: Path, files: dict[str, bytes], dry_run: bool) -> None:
    if not files:
        return
    for rel in files:
        print("Update:", rel)
    if dry_run:
        print("DRY RUN: no files changed")
        return
    backup = root.parent / (root.name + "_backups") / (
        "animation_lab_16e_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    )
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "root": str(root), "files": {}}
    for rel, content in files.items():
        original = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest["files"][rel] = {"before": hexdigest(original), "after": hexdigest(content)}
        if original is not None:
            dest = backup / "originals" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(original)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    written = []
    try:
        for rel, content in files.items():
            atomic_write(root / rel, content)
            written.append(rel)
    except Exception:
        for rel in reversed(written):
            previous = backup / "originals" / rel
            if previous.is_file():
                atomic_write(root / rel, previous.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print("Installed 16E successfully. Backup:", backup)


def restore(root: Path, directory: str) -> None:
    backup = Path(directory).expanduser().resolve()
    metadata = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if metadata.get("version") != VERSION or Path(metadata.get("root", "")).resolve() != root:
        raise RuntimeError("Backup does not belong to Update 16E on this project.")
    for rel, checksums in metadata["files"].items():
        target = root / rel
        current = target.read_bytes() if target.is_file() else None
        if hexdigest(current) != checksums["after"]:
            raise RuntimeError("File modified after installing 16E; refusing unsafe restore: " + rel)
        saved = backup / "originals" / rel
        before = checksums["before"]
        if before is not None and (not saved.is_file() or hexdigest(saved.read_bytes()) != before):
            raise RuntimeError("Backup original missing or corrupt: " + rel)
    for rel in metadata["files"]:
        original = backup / "originals" / rel
        if original.is_file():
            atomic_write(root / rel, original.read_bytes())
        else:
            (root / rel).unlink(missing_ok=True)
    print("Restored Update 16E successfully.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fight Royale Update 16E — Animation Lab viewport")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", metavar="BACKUP_DIRECTORY")
    args = parser.parse_args()
    project = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(project, args.restore)
        else:
            install(project, modifications(project), args.dry_run)
        return 0
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
