#!/usr/bin/env python3
"""Fight Royale Godot — Update 17D: VFX quality presets and effect budgets.

From your Godot project directory:
    python install_17d_vfx_quality.py
    python install_17d_vfx_quality.py --preset eco
    python install_17d_vfx_quality.py --preset ultra
    python install_17d_vfx_quality.py --dry-run
    python install_17d_vfx_quality.py --restore BACKUP_FOLDER

Requires Update 17C. Visuals only; no gameplay, damage, physics, AI, or rigs changed.
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

VERSION = "17D.1"
TAG = "# FRG17D - VFX quality and performance"
FX_FILE = "scripts/fx.gd"
TRAIL_FILE = "scripts/trail.gd"
CONFIG_FILE = "data/vfx_quality.json"
REPORT_FILE = "reports/vfx_quality_17d.txt"
PRESETS = {
    "eco": {"max_active_effects": 65, "max_burst_particles": 20, "particle_scale": 0.55},
    "balanced": {"max_active_effects": 120, "max_burst_particles": 36, "particle_scale": 0.82},
    "ultra": {"max_active_effects": 200, "max_burst_particles": 64, "particle_scale": 1.0},
}

FX_SETUP = '''# FRG17D - VFX quality and performance
# Purely cosmetic. Read presets at startup from res://data/vfx_quality.json.
# When the settings file is absent or invalid, use balanced defaults.
var _vfx17d_max_active: int = 120
var _vfx17d_max_particles: int = 36
var _vfx17d_particle_scale: float = 0.82

func _ready() -> void:
	var preset := "balanced"
	var cfg_path := "res://data/vfx_quality.json"
	if FileAccess.file_exists(cfg_path):
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(cfg_path))
		if parsed is Dictionary:
			preset = String(parsed.get("preset", "balanced"))
	match preset:
		"eco":
			_vfx17d_max_active = 65
			_vfx17d_max_particles = 20
			_vfx17d_particle_scale = 0.55
		"ultra":
			_vfx17d_max_active = 200
			_vfx17d_max_particles = 64
			_vfx17d_particle_scale = 1.0
		_:
			_vfx17d_max_active = 120
			_vfx17d_max_particles = 36
			_vfx17d_particle_scale = 0.82

func active_effect_count_17d() -> int:
	return _items.size()

'''

OLD_ADD = '''func _add(n: Node3D, upd: Callable) -> void:
	add_child(n)
	_items.append([n, upd])'''
NEW_ADD = '''func _add(n: Node3D, upd: Callable) -> void:
	# FRG17D: retire the oldest visual if the budget is full. Never block a new hit.
	if _items.size() >= _vfx17d_max_active:
		var oldest: Array = _items.pop_front()
		if is_instance_valid(oldest[0]):
			oldest[0].queue_free()
	add_child(n)
	_items.append([n, upd])'''

BURST_HEAD = '''func burst(pos: Vector3, mesh: Mesh, mat: Material, amount: int, speed: float, dir := Vector3.ZERO, spread := 1.0, gravity := 9.0, life := 0.4, size := 1.0) -> void:
	var mm := MultiMesh.new()'''
BURST_HEAD_NEW = '''func burst(pos: Vector3, mesh: Mesh, mat: Material, amount: int, speed: float, dir := Vector3.ZERO, spread := 1.0, gravity := 9.0, life := 0.4, size := 1.0) -> void:
	# FRG17D: reduce MultiMesh instance work while preserving effect shapes/timing.
	var actual_amount: int = clampi(roundi(float(amount) * _vfx17d_particle_scale), 0, _vfx17d_max_particles)
	var mm := MultiMesh.new()'''


def digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".frg17d-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def exactly_once(source: str, before: str, after: str, what: str) -> str:
    count = source.count(before)
    if count != 1:
        raise RuntimeError(f"{what}: expected exactly one anchor, found {count}; no changes applied.")
    return source.replace(before, after, 1)


def patch_fx(source: str) -> str:
    # Use the Update 17C effect script as the stable baseline.
    if TAG in source:
        return source
    if "# FRG17C - elemental hit and skill VFX" not in source:
        raise RuntimeError("Install Update 17C before 17D. No files changed.")
    source = exactly_once(source, "var _items: Array = []  # [node, updater Callable(dt) -> bool alive]", "var _items: Array = []  # [node, updater Callable(dt) -> bool alive]\n\n" + FX_SETUP.rstrip(), "Fx settings insertion")
    source = exactly_once(source, OLD_ADD, NEW_ADD, "Visual effect allocation")
    source = exactly_once(source, BURST_HEAD, BURST_HEAD_NEW, "MultiMesh burst initialization")
    head, delimiter, tail = source.partition("func sparks(")
    if not delimiter:
        raise RuntimeError("Can't locate end of MultiMesh burst routine.")
    head = exactly_once(head, "mm.instance_count = amount", "mm.instance_count = actual_amount", "Burst instance count")
    if head.count("for i in amount:") != 2:
        raise RuntimeError("Unexpected burst iteration count; refusing to modify source.")
    head = head.replace("for i in amount:", "for i in actual_amount:")
    return head + delimiter + tail


def changes_for(root: Path, preset: str) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise RuntimeError("Run this inside your Godot project folder (project.godot not found).")
    if not (root / FX_FILE).is_file() or not (root / TRAIL_FILE).is_file():
        raise RuntimeError("Missing scripts/fx.gd or scripts/trail.gd.")
    original = (root / FX_FILE).read_text(encoding="utf-8-sig")
    trail = (root / TRAIL_FILE).read_text(encoding="utf-8-sig")
    if "# FRG17A - combat impact VFX" not in original or "# FRG17B - twin-layer weapon trails" not in trail:
        raise RuntimeError("Updates 17A and 17B must be installed before 17D.")
    if "# FRG17C - elemental hit and skill VFX" not in original:
        raise RuntimeError("Update 17C must be installed before 17D.")
    patched = patch_fx(original)
    config = {
        "version": VERSION,
        "preset": preset,
        "visual_effects_only": True,
        "budget": PRESETS[preset],
        "note": "Change the preset by rerunning install_17d_vfx_quality.py --preset eco|balanced|ultra",
    }
    report = f"""Fight Royale Godot — Update 17D: VFX Quality and Performance\n\nPreset: {preset}\nMax concurrent temporary effects: {PRESETS[preset]['max_active_effects']}\nMaximum particles per MultiMesh burst: {PRESETS[preset]['max_burst_particles']}\nBurst density scale: {PRESETS[preset]['particle_scale']}\n\n- Limits temporary visual nodes and MultiMesh instances, prioritizing recent impacts.\n- Oldest visual is retired when at the active-effect limit.\n- Changes affect sparks, motes, rings, flashes and visual bursts only.\n- No changes to attacks, hitboxes, damage, status, AI, animations, or rigs.\n- GL Compatibility renderer stays unchanged.\n- Open Godot editor after installing and test Duel vs CPU / CPU vs CPU.\n"""
    wanted = {
        FX_FILE: patched.encode("utf-8"),
        CONFIG_FILE: (json.dumps(config, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
        REPORT_FILE: report.encode("utf-8"),
    }
    actual: dict[str, bytes] = {}
    for relative, data in wanted.items():
        file = root / relative
        if not file.is_file() or file.read_bytes() != data:
            actual[relative] = data
    return actual


def install(root: Path, updates: dict[str, bytes], dry_run: bool) -> None:
    if not updates:
        print("Update 17D is already installed with the selected preset. No changes needed.")
        return
    for relative in updates:
        print("Update:", relative)
    if dry_run:
        print("DRY RUN: no files modified.")
        return
    backup_dir = root.parent / (root.name + "_backups") / (
        "vfx_quality_17d_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    )
    backup_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict = {"version": VERSION, "project": str(root), "files": {}}
    for relative, contents in updates.items():
        target = root / relative
        original = target.read_bytes() if target.is_file() else None
        manifest["files"][relative] = {"before": digest(original), "after": digest(contents)}
        if original is not None:
            saved = backup_dir / "originals" / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(original)
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    finished = []
    try:
        for relative, contents in updates.items():
            atomic_write(root / relative, contents)
            finished.append(relative)
    except Exception:
        for relative in reversed(finished):
            original = backup_dir / "originals" / relative
            if original.is_file():
                atomic_write(root / relative, original.read_bytes())
            else:
                (root / relative).unlink(missing_ok=True)
        raise
    print("Update 17D installed; backup:", backup_dir)


def restore(root: Path, folder: str) -> None:
    backup = Path(folder).expanduser().resolve()
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest.get("project", "")).resolve() != root:
        raise RuntimeError("Backup was not made by Update 17D for this project.")
    for relative, entry in manifest["files"].items():
        target = root / relative
        current = target.read_bytes() if target.is_file() else None
        if digest(current) != entry["after"]:
            raise RuntimeError("Modified since installation; refusing to overwrite: " + relative)
        saved = backup / "originals" / relative
        if entry["before"] is not None and (not saved.is_file() or digest(saved.read_bytes()) != entry["before"]):
            raise RuntimeError("Original backup missing/damaged: " + relative)
    for relative in manifest["files"]:
        saved = backup / "originals" / relative
        if saved.is_file():
            atomic_write(root / relative, saved.read_bytes())
        else:
            (root / relative).unlink(missing_ok=True)
    print("Update 17D restored.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fight Royale Godot — Update 17D: VFX Quality Presets")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--preset", choices=list(PRESETS), default="balanced")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", metavar="BACKUP_FOLDER")
    args = parser.parse_args()
    root = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(root, args.restore)
        else:
            install(root, changes_for(root, args.preset), args.dry_run)
        return 0
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
