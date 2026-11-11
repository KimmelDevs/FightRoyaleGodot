#!/usr/bin/env python3
"""Fight Royale Godot — Update 16D: Animation Lab playback controls.

Run from the Godot project directory:
    python install_16d_animation_preview.py

Requires 16C. Adds timeline scrubbing, playback speed, pause, stepping, and loop
controls to the Animation Lab. Does not modify fighters' combat timing, rigs,
VRMs, existing pose profiles, or weapon attachments.

Options: --dry-run, --project PATH, --restore BACKUP_DIR.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone

VERSION = "16D.1"
TAG = "# FRG16D - animation lab preview timeline"
PATH_LAB = "scripts/animation_lab.gd"
PATH_MODEL = "scripts/fighter_model.gd"
PATH_REPORT = "reports/animation_lab_16d.txt"

VARS_BEFORE = '''var _gait_running := true
# FRG16C - animation lab pose tools'''
VARS_AFTER = '''var _gait_running := true
# FRG16D - animation lab preview timeline
var _frg16d_elapsed := 0.0
var _frg16d_duration := 1.10
var _frg16d_playing := true
var _frg16d_loop := true
var _frg16d_speed := 1.0
var _frg16d_bar: HSlider
var _frg16d_label: Label
var _frg16d_play_button: Button
var _frg16d_loop_button: Button
var _frg16d_speed_select: OptionButton
# FRG16C - animation lab pose tools'''

UI_BEFORE = '''\t_button(tools, "Play / Pause Walk", func(): _gait_running = not _gait_running)
\t_style_text(right, "Preview combat states, rotate bones and Save Fighter. Edits also apply in battles.", 13)'''
UI_AFTER = '''\t# FRG16D: timeline controls are preview-only; no profile writes or undo history.
\tvar playback := HBoxContainer.new()
\tright.add_child(playback)
\t_frg16d_play_button = _button(playback, "Pause", _frg16d_toggle)
\t_button(playback, "◀ Frame", func(): _frg16d_step(-1))
\t_button(playback, "Frame ▶", func(): _frg16d_step(1))
\t_frg16d_loop_button = _button(playback, "Loop: ON", _frg16d_toggle_loop)
\t_frg16d_speed_select = OptionButton.new()
\tplayback.add_child(_frg16d_speed_select)
\tfor caption in ["0.25x", "0.5x", "1x", "1.5x", "2x"]:
\t\t_frg16d_speed_select.add_item(caption)
\t_frg16d_speed_select.select(2)
\t_frg16d_speed_select.item_selected.connect(_frg16d_set_speed)
\t_frg16d_label = _style_text(right, "0.00s / 1.10s (0%)", 13, Color("#a8d9ff"))
\t_frg16d_bar = HSlider.new()
\t_frg16d_bar.min_value = 0.0
\t_frg16d_bar.max_value = 1.0
\t_frg16d_bar.step = 0.005
\t_frg16d_bar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
\tright.add_child(_frg16d_bar)
\t_frg16d_bar.value_changed.connect(_frg16d_scrub_to)
\t_style_text(right, "Preview walk/run or combat motion; drag the timeline to inspect joint positions. Editing remains on the left.", 13)'''

STATE_BEFORE = '''\t_selected_state = MODES[clampi(index, 0, MODES.size() - 1)]
\t_refresh_sliders()
\t_apply_live()'''
STATE_AFTER = '''\t_selected_state = MODES[clampi(index, 0, MODES.size() - 1)]
\t_frg16d_elapsed = 0.0
\t_frg16d_sync_ui()
\t_refresh_sliders()
\t_apply_live()'''

PROCESS_BEFORE = '''\t_model.rotation_degrees.y = _yaw
\tif not _gait_running:
\t\t_model.lab_paused = true
\telse:
\t\t_model.lab_paused = false
\t_model.walk = 1.0 if _selected_state in ["walk", "run"] else 0.0
\t_model.run = 1.0 if _selected_state == "run" else 0.0
\t_model.choreo_state = _selected_state if _selected_state not in ["idle", "walk", "run"] else "idle"
\t_model.choreo_weight = 0.0 if _selected_state in ["idle", "walk", "run"] else 1.0
\t_model.choreo_progress = fmod(float(Time.get_ticks_msec()) / 1100.0, 1.0) if _gait_running else 0.45
\t_model.play_pose(_frg16b_preview_pose(), 18.0)'''
PROCESS_AFTER = '''\t_model.rotation_degrees.y = _yaw
\tif _frg16d_playing:
\t\t_frg16d_elapsed += maxf(dt, 0.0) * _frg16d_speed
\t\tif _frg16d_elapsed >= _frg16d_duration:
\t\t\tif _frg16d_loop:
\t\t\t\t_frg16d_elapsed = fmod(_frg16d_elapsed, _frg16d_duration)
\t\t\telse:
\t\t\t\t_frg16d_elapsed = _frg16d_duration
\t\t\t\t_frg16d_playing = false
\tvar phase: float = clampf(_frg16d_elapsed / _frg16d_duration, 0.0, 1.0)
\t# Only the Animation Lab enables these preview overrides.
\t_model.lab_preview_override = true
\t_model.lab_preview_phase = phase * TAU
\t_model.lab_preview_time = _frg16d_elapsed
\t_model.lab_paused = true
\t_model.walk = 1.0 if _selected_state in ["walk", "run"] else 0.0
\t_model.run = 1.0 if _selected_state == "run" else 0.0
\t_model.choreo_state = _selected_state if _selected_state not in ["idle", "walk", "run"] else "idle"
\t_model.choreo_weight = 0.0 if _selected_state in ["idle", "walk", "run"] else 1.0
\t_model.choreo_progress = phase
\t_model.play_pose(_frg16b_preview_pose(), 18.0)
\t_frg16d_sync_ui()'''

HELPERS = '''# FRG16D: preview controls do not affect saved fighter poses or in-match animations.
func _frg16d_toggle() -> void:
\t_frg16d_playing = not _frg16d_playing
\tif _frg16d_playing and _frg16d_elapsed >= _frg16d_duration:
\t\t_frg16d_elapsed = 0.0
\t_frg16d_sync_ui()

func _frg16d_toggle_loop() -> void:
\t_frg16d_loop = not _frg16d_loop
\t_frg16d_sync_ui()

func _frg16d_step(direction: int) -> void:
\t_frg16d_playing = false
\t_frg16d_elapsed = clampf(_frg16d_elapsed + float(direction) / 30.0, 0.0, _frg16d_duration)
\t_frg16d_sync_ui()

func _frg16d_scrub_to(value: float) -> void:
\t_frg16d_playing = false
\t_frg16d_elapsed = clampf(value, 0.0, 1.0) * _frg16d_duration
\t_frg16d_sync_ui()

func _frg16d_set_speed(index: int) -> void:
\tvar speeds := [0.25, 0.5, 1.0, 1.5, 2.0]
\tif index < 0 or index >= speeds.size():
\t\treturn
\t_frg16d_speed = float(speeds[index])

func _frg16d_sync_ui() -> void:
\tif is_instance_valid(_frg16d_bar):
\t\tvar alpha: float = clampf(_frg16d_elapsed / _frg16d_duration, 0.0, 1.0)
\t\t_frg16d_bar.set_value_no_signal(alpha)
\tif is_instance_valid(_frg16d_label):
\t\t_frg16d_label.text = "%.2fs / %.2fs (%d%%)" % [_frg16d_elapsed, _frg16d_duration, int(round(100.0 * _frg16d_elapsed / _frg16d_duration))]
\tif is_instance_valid(_frg16d_play_button):
\t\t_frg16d_play_button.text = "Pause" if _frg16d_playing else "Play"
\tif is_instance_valid(_frg16d_loop_button):
\t\t_frg16d_loop_button.text = "Loop: ON" if _frg16d_loop else "Loop: OFF"

'''

MODEL_VARS_BEFORE = '''var lab_paused := false
# FRG16B - combat choreography'''
MODEL_VARS_AFTER = '''var lab_paused := false
# FRG16D - Animation Lab playback overrides (never set by combat scenes)
var lab_preview_override := false
var lab_preview_phase := 0.0
var lab_preview_time := 0.0
# FRG16B - combat choreography'''
MODEL_PROCESS_BEFORE = '''func _process(dt: float) -> void:
\t_t += dt
\tif not lab_paused:
\t\t_phase += dt * (10.0 + 6.0 * run) * walk
\tif motion == null: return'''
MODEL_PROCESS_AFTER = '''func _process(dt: float) -> void:
\tif lab_preview_override:
\t\t_t = lab_preview_time
\t\t_phase = lab_preview_phase
\telse:
\t\t_t += dt
\t\tif not lab_paused:
\t\t\t_phase += dt * (10.0 + 6.0 * run) * walk
\tif motion == null: return'''


def once(text: str, original: str, replacement: str, label: str) -> str:
    n = text.count(original)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly 1 anchor, found {n}. No changes written.")
    return text.replace(original, replacement, 1)


def digest(content: bytes | None) -> str | None:
    return None if content is None else hashlib.sha256(content).hexdigest()


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".frg16d-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def changes_for(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise RuntimeError("project.godot missing; run from the Godot project folder.")
    lab = root / PATH_LAB
    model = root / PATH_MODEL
    if not lab.is_file() or not model.is_file():
        raise RuntimeError("Update 16C files missing. Install 16A, 16B and 16C first.")
    lab_text = lab.read_text(encoding="utf-8-sig")
    model_text = model.read_text(encoding="utf-8-sig")
    lab_patched = TAG in lab_text
    model_patched = TAG in model_text
    if lab_patched != model_patched:
        raise RuntimeError("Partial 16D installation detected. Restore its backup before retrying.")
    if lab_patched:
        print("Update 16D is already installed; no files changed.")
        return {}
    if "# FRG16C - animation lab pose tools" not in lab_text or "# FRG16B - combat choreography" not in model_text:
        raise RuntimeError("Update 16C / 16B dependencies not found. Do not apply to an older project.")
    lab_text = once(lab_text, VARS_BEFORE, VARS_AFTER, "Animation Lab variables")
    lab_text = once(lab_text, UI_BEFORE, UI_AFTER, "Animation Lab UI controls")
    lab_text = once(lab_text, STATE_BEFORE, STATE_AFTER, "Animation Lab selected-state handler")
    lab_text = once(lab_text, PROCESS_BEFORE, PROCESS_AFTER, "Animation Lab frame update")
    lab_text = once(lab_text, "func _back() -> void:\n", HELPERS + "func _back() -> void:\n", "Animation Lab preview methods")
    model_text = once(model_text, MODEL_VARS_BEFORE, MODEL_VARS_AFTER, "FighterModel preview variables")
    model_text = once(model_text, MODEL_PROCESS_BEFORE, MODEL_PROCESS_AFTER, "FighterModel preview phase")
    lab_text += "\n" + TAG + "\n"
    model_text += "\n" + TAG + "\n"
    report = """Fight Royale Godot - Update 16D: Animation Lab Preview Timeline

Preview controls:
- Play/Pause preview
- Frame step backward or forward (1/30-second increments)
- Timeline scrub 0 to 100 percent
- Playback speed 0.25x, 0.5x, 1x, 1.5x, 2x
- Optional looping
- State changes reset preview position

For walk/run, preview scrubbing drives the procedural leg/arm swing cycle.
For combat states, preview controls drive secondary-motion progress.
The existing AnimationLibrary poses remain separate static poses; this update does
not create per-bone keyframes or a reusable animation timeline.

Important: this updates only preview behavior. It does not change fighters'
combat timings, skill damage, AI, or VRM skeleton files.
"""
    return {PATH_LAB: lab_text.encode(), PATH_MODEL: model_text.encode(), PATH_REPORT: report.encode()}


def install(root: Path, changes: dict[str, bytes], dry_run: bool) -> None:
    if not changes:
        return
    print("16D files:", ", ".join(changes))
    if dry_run:
        print("Dry run completed. No changes written.")
        return
    backup = root.parent / (root.name + "_backups") / ("animation_preview_16d_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "root": str(root), "files": {}}
    for rel, data in changes.items():
        original = (root / rel).read_bytes() if (root / rel).exists() else None
        manifest["files"][rel] = {"before": digest(original), "after": digest(data)}
        if original is not None:
            target = backup / "originals" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    modified = []
    try:
        for rel, data in changes.items():
            atomic_write(root / rel, data)
            modified.append(rel)
    except Exception:
        for rel in reversed(modified):
            original = backup / "originals" / rel
            if original.exists():
                atomic_write(root / rel, original.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print("Installed Update 16D. Backup:", backup)


def restore(root: Path, backup_name: str) -> None:
    backup = Path(backup_name).expanduser().resolve()
    data = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if data.get("version") != VERSION or Path(data.get("root", "")).resolve() != root:
        raise RuntimeError("Invalid 16D backup for this project.")
    for rel, meta in data["files"].items():
        target = root / rel
        current = target.read_bytes() if target.exists() else None
        if digest(current) != meta["after"]:
            raise RuntimeError("Cannot restore because file changed since installation: " + rel)
        if meta["before"] is not None:
            saved = backup / "originals" / rel
            if not saved.is_file() or digest(saved.read_bytes()) != meta["before"]:
                raise RuntimeError("Backup is incomplete: " + rel)
    for rel in data["files"]:
        target = root / rel
        saved = backup / "originals" / rel
        if saved.exists():
            atomic_write(target, saved.read_bytes())
        else:
            target.unlink(missing_ok=True)
    print("Restored Update 16D files from", backup)


def main() -> int:
    ap = argparse.ArgumentParser(description="Fight Royale Godot Update 16D — Animation Preview")
    ap.add_argument("--project", type=Path, default=Path.cwd())
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore", metavar="BACKUP_DIRECTORY")
    args = ap.parse_args()
    root = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(root, args.restore)
        else:
            install(root, changes_for(root), args.dry_run)
        return 0
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
