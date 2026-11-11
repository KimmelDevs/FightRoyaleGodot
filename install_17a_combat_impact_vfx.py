#!/usr/bin/env python3
"""Fight Royale Godot — Update 17A: clearer combat impact VFX.

Usage (PowerShell in your Godot project folder):
    python install_17a_combat_impact_vfx.py
    python install_17a_combat_impact_vfx.py --dry-run
    python install_17a_combat_impact_vfx.py --restore PATH_TO_BACKUP

Visual-only changes: attacks, damage, hit-stun, cooldowns, projectiles and AI are unchanged.
Works with the existing GL Compatibility renderer and programmatically generated weapons.
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

VERSION = "17A.1"
TAG = "# FRG17A - combat impact VFX"
FX_FILE = "scripts/fx.gd"
MATCH_FILE = "scripts/match.gd"
REPORT_FILE = "reports/combat_vfx_17a.txt"

FX_ADDITION = '''
# FRG17A - combat impact VFX
# Cosmetic only: no damage, collisions, hit-stop or combat timings are changed.
# Each ray burst is one MultiMesh, not a node for each spark.
func _vfx17a_rays(pos: Vector3, color: Color, direction: Vector3, amount: int, reach: float, duration: float) -> void:
	var rays := BoxMesh.new()
	rays.size = Vector3(0.025, 0.025, 1.0)
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = rays
	mm.instance_count = amount
	var node := MultiMeshInstance3D.new()
	node.multimesh = mm
	node.material_override = unlit(color, 0.94, true)
	var orientations: Array[Vector3] = []
	var distances: Array[float] = []
	var heading := direction.normalized() if direction.length_squared() > 0.0001 else Vector3.UP
	for i in range(amount):
		var jitter := Vector3(randf_range(-1.0, 1.0), randf_range(-1.0, 1.0), randf_range(-1.0, 1.0))
		var ray := (heading * 0.60 + jitter).normalized()
		if ray.length_squared() < 0.0001:
			ray = Vector3.UP
		orientations.append(ray)
		distances.append(reach * randf_range(0.65, 1.10))
	var elapsed := [0.0]
	_add(node, func(dt: float) -> bool:
		elapsed[0] += dt
		var progress: float = clampf(elapsed[0] / maxf(duration, 0.01), 0.0, 1.0)
		for i in range(amount):
			var ray: Vector3 = orientations[i]
			var up: Vector3 = Vector3.UP if absf(ray.dot(Vector3.UP)) < 0.92 else Vector3.FORWARD
			var basis := Basis.looking_at(ray, up)
			var visible_length: float = maxf(0.001, distances[i] * 0.28 * (1.0 - progress))
			var center: Vector3 = pos + ray * (0.1 + distances[i] * progress * 0.60)
			mm.set_instance_transform(i, Transform3D(basis.scaled(Vector3(1.0, 1.0, visible_length)), center))
		return elapsed[0] < duration)

# A shield-facing translucent disk; oriented toward the incoming strike.
func _vfx17a_shield_disk(pos: Vector3, color: Color, incoming: Vector3, radius: float, duration: float) -> void:
	var disk := MeshInstance3D.new()
	var sphere := SphereMesh.new()
	sphere.radius = 1.0
	sphere.height = 2.0
	sphere.radial_segments = 20
	sphere.rings = 8
	disk.mesh = sphere
	var mat := unlit(color, 0.38, true)
	disk.material_override = mat
	disk.position = pos
	var normal := incoming.normalized() if incoming.length_squared() > 0.0001 else Vector3.FORWARD
	var up := Vector3.UP if absf(normal.dot(Vector3.UP)) < 0.92 else Vector3.FORWARD
	disk.basis = Basis.looking_at(normal, up)
	var elapsed := [0.0]
	_add(disk, func(dt: float) -> bool:
		elapsed[0] += dt
		var progress: float = clampf(elapsed[0] / maxf(duration, 0.01), 0.0, 1.0)
		var grow: float = radius * (0.65 + progress * 0.55)
		disk.scale = Vector3(grow, grow, 0.035)
		mat.albedo_color.a = 0.38 * (1.0 - progress)
		return elapsed[0] < duration)

func combat_hit(pos: Vector3, color: Color, normal: Vector3, heavy: bool = false) -> void:
	var intensity: float = 1.0 if heavy else 0.65
	flash(pos, Color.WHITE.lerp(color, 0.35), 0.25 + 0.24 * intensity, 0.13, 0.85)
	sparks(pos, color, 24 if heavy else 13, 7.5 if heavy else 5.0, normal)
	_vfx17a_rays(pos, color, normal, 14 if heavy else 8, 1.25 if heavy else 0.72, 0.22 if heavy else 0.16)
	if heavy:
		ring(pos, color, 1.35, 0.22, 0.65)

func combat_guard(pos: Vector3, incoming: Vector3, perfect: bool = false) -> void:
	var tint := Color("#a8ecff") if perfect else Color("#ffc971")
	_vfx17a_shield_disk(pos, tint, incoming, 0.95 if perfect else 0.65, 0.27 if perfect else 0.17)
	sparks(pos, tint, 31 if perfect else 13, 8.0 if perfect else 4.5, -incoming)
	_vfx17a_rays(pos, tint, -incoming, 13 if perfect else 6, 0.95 if perfect else 0.48, 0.21 if perfect else 0.14)
	if perfect:
		flash(pos, Color("#e4fbff"), 0.40, 0.12, 0.8)
		ring(pos, tint, 1.5, 0.30, 0.85)

func combat_guard_break(pos: Vector3) -> void:
	var tint := Color("#ffad49")
	flash(pos, Color("#fff4c2"), 0.78, 0.17, 0.95)
	sparks(pos, tint, 36, 8.5)
	_vfx17a_rays(pos, tint, Vector3.UP, 20, 1.65, 0.27)
	ring(pos, tint, 1.75, 0.32, 0.84)

func combat_clash(pos: Vector3) -> void:
	var tint := Color("#ffe5a2")
	flash(pos, Color.WHITE, 0.75, 0.16, 0.92)
	sparks(pos, tint, 38, 9.0)
	_vfx17a_rays(pos, tint, Vector3.UP, 22, 1.55, 0.23)
	ring(pos, tint, 2.45, 0.35, 0.87)
'''

MATCH_REPLACEMENTS = [
    (
        'fx.sparks(hit_pos, glow, 30 if heavy else 18, 8.0 if heavy else 6.0, dir)\n\t\t\tfx.flash(hit_pos, glow, 0.45 if heavy else 0.3, 0.14, 0.8)\n\t\t\tif a.heavy: fx.ring(hit_pos, glow, 2.2, 0.35, 0.9)',
        'fx.combat_hit(hit_pos, glow, dir, heavy)',
        "melee impacts",
    ),
    (
        'fx.sparks(shield_pos, Color("#ffd27a"), 16, 5.0, -dir + Vector3(0, 0.3, 0))',
        'fx.combat_guard(shield_pos, dir, false)',
        "blocks",
    ),
    (
        'fx.sparks(shield_pos, Color("#aee9ff"), 40, 9.0)\n\t\t\tfx.ring(shield_pos, Color("#b3f2ff"), 1.6, 0.35, 0.9)',
        'fx.combat_guard(shield_pos, dir, true)',
        "parries",
    ),
    (
        'fx.sparks(hit_pos, Color("#ffb347"), 40, 9.0)',
        'fx.combat_guard_break(hit_pos)',
        "guard breaks",
    ),
    (
        'fx.sparks(pos, Color("#fff2c0"), 50, 10.0)\n\tfx.ring(pos, Color("#ffe699"), 3.0, 0.45, 0.9)',
        'fx.combat_clash(pos)',
        "weapon clashes",
    ),
]


def sha256(contents: bytes | None) -> str | None:
    return hashlib.sha256(contents).hexdigest() if contents is not None else None


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".frg17a-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as writer:
            writer.write(data)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def replace_once(contents: str, before: str, after: str, label: str) -> str:
    count = contents.count(before)
    if count != 1:
        raise RuntimeError(f"{label}: expected one code anchor, found {count}. No files changed.")
    return contents.replace(before, after, 1)


def updates(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise RuntimeError("project.godot not found. Open PowerShell in your Godot project folder.")
    fx_path, match_path = root / FX_FILE, root / MATCH_FILE
    if not fx_path.is_file() or not match_path.is_file():
        raise RuntimeError("Missing scripts/fx.gd or scripts/match.gd — do not continue.")
    fx_code = fx_path.read_text(encoding="utf-8-sig")
    match_code = match_path.read_text(encoding="utf-8-sig")
    if TAG in fx_code or TAG in match_code:
        if TAG in fx_code and TAG in match_code:
            print("Update 17A is already installed; no changes required.")
            return {}
        raise RuntimeError("Only part of Update 17A appears installed; refusing mixed changes.")
    if "class_name Fx" not in fx_code or "func combat_hit(" in fx_code:
        raise RuntimeError("Unexpected Fx script version; inspect before installing.")
    if "func apply_hit(" not in match_code or "func _clash(" not in match_code:
        raise RuntimeError("Unexpected Match script version; inspect before installing.")
    fx_code = fx_code.rstrip() + "\n\n" + FX_ADDITION.lstrip()
    for before, after, label in MATCH_REPLACEMENTS:
        match_code = replace_once(match_code, before, after, label)
    match_code = match_code.replace('class_name Match\n', 'class_name Match\n' + TAG + '\n', 1)
    report = 'Fight Royale Godot - Update 17A (Combat Impact VFX)\n\n'
    report += '''- Distinctive directional hit streaks for light/heavy attacks.
- Shield-facing disks for blocks; larger blue pulse for perfect parries.
- Golden radial burst on clashes; orange shockwave on guard breaks.
- MultiMesh streak implementation reduces per-burst scene nodes.
- No gameplay changes: damage, hit-stun, AI, hitboxes, cooldowns unchanged.
- All visuals use built-in Godot mesh/material types; no imported textures required.
- Open Godot Editor once to let it parse and import modified scripts.
- Visual results are not verified by the Python installer; test in both game modes.
'''
    return {
        FX_FILE: fx_code.encode("utf-8"),
        MATCH_FILE: match_code.encode("utf-8"),
        REPORT_FILE: report.encode("utf-8"),
    }


def apply(root: Path, changes: dict[str, bytes], dry_run: bool) -> Path | None:
    if not changes:
        return None
    for relative in changes:
        print("Update:", relative)
    if dry_run:
        print("DRY RUN: no files modified")
        return None
    backup_dir = root.parent / (root.name + "_backups") / (
        "combat_vfx_17a_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    )
    backup_dir.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for relative, new_data in changes.items():
        target = root / relative
        old_data = target.read_bytes() if target.is_file() else None
        manifest["files"][relative] = {"before": sha256(old_data), "after": sha256(new_data)}
        if old_data is not None:
            saved = backup_dir / "originals" / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(old_data)
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    done: list[str] = []
    try:
        for relative, content in changes.items():
            atomic_write(root / relative, content)
            done.append(relative)
    except Exception:
        for relative in reversed(done):
            previous = backup_dir / "originals" / relative
            if previous.is_file():
                atomic_write(root / relative, previous.read_bytes())
            else:
                (root / relative).unlink(missing_ok=True)
        raise
    print("Installed Update 17A successfully. Backup:", backup_dir)
    return backup_dir


def restore(root: Path, folder: str) -> None:
    savedir = Path(folder).expanduser().resolve()
    manifest = json.loads((savedir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest.get("project", "")).resolve() != root:
        raise RuntimeError("This backup does not belong to Update 17A on this project.")
    for relative, states in manifest["files"].items():
        current = (root / relative).read_bytes() if (root / relative).is_file() else None
        if sha256(current) != states["after"]:
            raise RuntimeError("Cannot restore file modified since 17A: " + relative)
        old_file = savedir / "originals" / relative
        if states["before"] is not None and (not old_file.is_file() or sha256(old_file.read_bytes()) != states["before"]):
            raise RuntimeError("Missing or corrupt backup for " + relative)
    for relative in manifest["files"]:
        old_file = savedir / "originals" / relative
        if old_file.is_file():
            atomic_write(root / relative, old_file.read_bytes())
        else:
            (root / relative).unlink(missing_ok=True)
    print("Restored Update 17A successfully.")


def main() -> int:
    cli = argparse.ArgumentParser(description="Fight Royale Update 17A - combat impact visuals")
    cli.add_argument("--project", type=Path, default=Path.cwd())
    cli.add_argument("--dry-run", action="store_true")
    cli.add_argument("--restore", metavar="BACKUP_DIRECTORY")
    args = cli.parse_args()
    project = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(project, args.restore)
        else:
            apply(project, updates(project), args.dry_run)
        return 0
    except Exception as err:
        print("ERROR:", err, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
