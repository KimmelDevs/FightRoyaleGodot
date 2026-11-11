#!/usr/bin/env python3
"""Fight Royale Godot 17B — smooth, dual-layer weapon trails (GL compatible).

Run inside the existing Godot project:
    python install_17b_weapon_trails.py

Options:
    python install_17b_weapon_trails.py --dry-run
    python install_17b_weapon_trails.py --restore PATH_TO_BACKUP

Visual effects only: no changes to hitboxes, cooldowns, combat, or animations.
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

VERSION = "17B.1"
TAG = "# FRG17B - twin-layer weapon trails"
TRAIL = "scripts/trail.gd"
MATCH = "scripts/match.gd"
REPORT = "reports/weapon_trails_17b.txt"

TRAIL_SCRIPT = r'''class_name Trail
extends MeshInstance3D
## FRG17B - twin-layer weapon trails
## Bright core plus softly fading edge; samples interpolate through quick swings.
## Compatibility: Trail.new(base, tip, color), .emitting and .tick(dt).
## No hit detection is performed here. This node only draws a ribbon.

const SAMPLES := 26
const MAX_INTERPOLATION := 5

var base: Node3D
var tip: Node3D
var emitting := false
var _pts: Array = [] # [blade_base, blade_tip, age_seconds, intensity]
var _im := ImmediateMesh.new()
var _color: Color = Color.WHITE
var _life := 0.22
var _spread := 1.22
var _brightness := 1.0
var _previous_base := Vector3.ZERO
var _previous_tip := Vector3.ZERO
var _has_previous := false

func _init(b: Node3D, t: Node3D, color: Color) -> void:
    base = b
    tip = t
    _color = color
    mesh = _im
    var material := StandardMaterial3D.new()
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.vertex_color_use_as_albedo = true
    material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
    material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
    material.cull_mode = BaseMaterial3D.CULL_DISABLED
    material.albedo_color = Color.WHITE
    material_override = material
    top_level = true

## Changes VFX character, not weapon grip, attacks, or the humanoid rig.
func configure(kit: String, element: String) -> void:
    match kit:
        "greatsword":
            _life = 0.28
            _spread = 1.34
            _brightness = 1.12
        "katana", "assassin":
            _life = 0.18
            _spread = 1.13
            _brightness = 1.08
        "knuckles", "kicks":
            _life = 0.14
            _spread = 1.10
            _brightness = 0.80
        "mage", "bow":
            _life = 0.20
            _spread = 1.16
            _brightness = 0.72
        _:
            _life = 0.22
            _spread = 1.22
            _brightness = 1.0
    if element in ["light", "lightning", "electric", "ice"]:
        _brightness *= 1.12

func _sample(a: Vector3, b: Vector3, intensity: float) -> void:
    if a.distance_squared_to(b) < 0.0009:
        return
    _pts.append([a, b, 0.0, intensity])
    while _pts.size() > SAMPLES:
        _pts.pop_front()

func tick(dt: float) -> void:
    var step := maxf(0.0, dt)
    for sample in _pts:
        sample[2] = float(sample[2]) + step
    while not _pts.is_empty() and float(_pts[0][2]) >= _life:
        _pts.pop_front()
    # A paused game must not generate new frames of a swing.
    if emitting and step > 0.0 and is_instance_valid(base) and is_instance_valid(tip):
        var a := base.global_position
        var b := tip.global_position
        if _has_previous:
            var distance := maxf(a.distance_to(_previous_base), b.distance_to(_previous_tip))
            if distance > 3.5:
                # Teleports and forced repositioning should not draw across an arena.
                _pts.clear()
                _sample(a, b, 0.8)
            elif distance > 0.012:
                var subdivisions := clampi(ceili(distance / 0.18), 1, MAX_INTERPOLATION)
                var speed := distance / maxf(step, 0.008)
                var energy := clampf(0.65 + speed * 0.042, 0.70, 1.30)
                for j in range(1, subdivisions + 1):
                    var t := float(j) / float(subdivisions)
                    _sample(_previous_base.lerp(a, t), _previous_tip.lerp(b, t), energy)
        else:
            _sample(a, b, 0.9)
        _previous_base = a
        _previous_tip = b
        _has_previous = true
    elif not emitting:
        _has_previous = false
    _im.clear_surfaces()
    if _pts.size() < 2:
        return
    _draw_layer(true)
    _draw_layer(false)

func _draw_layer(outer: bool) -> void:
    _im.surface_begin(Mesh.PRIMITIVE_TRIANGLE_STRIP)
    var n := _pts.size()
    for i in range(n):
        var sample: Array = _pts[i]
        var a: Vector3 = sample[0]
        var b: Vector3 = sample[1]
        var age: float = float(sample[2])
        var energy: float = float(sample[3])
        var life_fraction := clampf(1.0 - age / maxf(_life, 0.01), 0.0, 1.0)
        var leading_edge := pow(float(i + 1) / float(n), 0.6)
        var opacity := life_fraction * life_fraction * leading_edge * energy * _brightness
        # The outer ribbon is wider and translucent. The inner one is narrow
        # and bright, giving clear contours without any postprocessing blur.
        var center := (a + b) * 0.5
        var width := _spread if outer else 0.66
        var left := center + (a - center) * width
        var right := center + (b - center) * width
        var tint := _color if outer else _color.lerp(Color.WHITE, 0.60)
        var alpha := clampf(opacity * (0.26 if outer else 0.87), 0.0, 0.95)
        var color := Color(tint.r, tint.g, tint.b, alpha)
        _im.surface_set_color(color)
        _im.surface_add_vertex(left)
        _im.surface_set_color(color)
        _im.surface_add_vertex(right)
    _im.surface_end()
'''

BEFORE_MATCH = '''\t\tvar tr := Trail.new(f.model.blade_base, f.model.blade_tip, Color(f.look.glow))
\t\tadd_child(tr)
\t\t_trails[f] = tr'''
AFTER_MATCH = '''\t\tvar tr := Trail.new(f.model.blade_base, f.model.blade_tip, Color(f.look.glow))
\t\t# FRG17B: visual styling uses the existing character kit / element.
\t\ttr.configure(String(f.kit), String(f.look.get("element", "")))
\t\tadd_child(tr)
\t\t_trails[f] = tr'''


def digest(contents: bytes | None) -> str | None:
    return hashlib.sha256(contents).hexdigest() if contents is not None else None


def atomic_write(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".frg17b-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build_changes(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise RuntimeError("Open PowerShell in the Godot project directory (project.godot is missing).")
    trail_file, match_file = root / TRAIL, root / MATCH
    if not trail_file.is_file() or not match_file.is_file():
        raise RuntimeError("Required scripts/trail.gd and scripts/match.gd not found.")
    current_trail = trail_file.read_text(encoding="utf-8-sig")
    current_match = match_file.read_text(encoding="utf-8-sig")
    if TAG in current_trail or "# FRG17B: visual styling" in current_match:
        if TAG in current_trail and "# FRG17B: visual styling" in current_match:
            print("Update 17B already installed. No changes needed.")
            return {}
        raise RuntimeError("Partial 17B install detected; files left untouched. Inspect previous backups.")
    # Refuse unexpected versions rather than silently clobbering custom edits.
    necessary = ["class_name Trail", "extends MeshInstance3D", "func _init(", "func tick(dt: float)", "_im.surface_begin(Mesh.PRIMITIVE_TRIANGLE_STRIP)"]
    if not all(needle in current_trail for needle in necessary):
        raise RuntimeError("Unknown trail.gd layout — refusing to replace custom code.")
    if BEFORE_MATCH not in current_match or current_match.count(BEFORE_MATCH) != 1:
        raise RuntimeError("Fighter trail mount anchor changed; no changes made. Send scripts/match.gd for a compatible patch.")
    if TAG in current_match:
        raise RuntimeError("Unexpected 17B marker in match.gd; no changes made.")
    # Require the prior VFX update so installers remain in their planned order.
    if "# FRG17A - combat impact VFX" not in current_match:
        raise RuntimeError("Install Update 17A first (its marker is missing from match.gd).")
    updated_match = current_match.replace(BEFORE_MATCH, AFTER_MATCH, 1)
    report = "Fight Royale Godot — Update 17B: Weapon Trails\n\n"
    report += """- Dual-layer transparent-additive ribbons: broad colored edge and crisp white-tinted core.\n- Interpolated samples on quick swings reduce visual gaps at variable frame rates.\n- Shorter trails for fast fighters; longer trails for heavy weapons.\n- Fighter glow color follows the existing roster data.\n- Pauses do not advance trail ages or generate samples.\n- Teleports will not draw streaks across the arena.\n- GL Compatibility renderer; no shader or third-party dependencies.\n- No changes to attack mechanics, hitboxes, passives, AI, or cooldowns.\n\nOpen the Godot editor after installation to load updated scripts.\n"""
    return {TRAIL: TRAIL_SCRIPT.encode("utf-8"), MATCH: updated_match.encode("utf-8"), REPORT: report.encode("utf-8")}


def install(root: Path, modifications: dict[str, bytes], dry_run: bool) -> Path | None:
    if not modifications:
        return None
    for relative in modifications:
        print("Update:", relative)
    if dry_run:
        print("DRY RUN — no files written.")
        return None
    backup_dir = root.parent / (root.name + "_backups") / (
        "weapon_trails_17b_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    )
    backup_dir.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for relative, contents in modifications.items():
        target = root / relative
        before = target.read_bytes() if target.is_file() else None
        manifest["files"][relative] = {"before": digest(before), "after": digest(contents)}
        if before is not None:
            saved = backup_dir / "originals" / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(before)
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    completed = []
    try:
        for relative, contents in modifications.items():
            atomic_write(root / relative, contents)
            completed.append(relative)
    except Exception:
        for relative in reversed(completed):
            saved = backup_dir / "originals" / relative
            if saved.is_file():
                atomic_write(root / relative, saved.read_bytes())
            else:
                (root / relative).unlink(missing_ok=True)
        raise
    print("Installed Update 17B. Backup:", backup_dir)
    return backup_dir


def restore(root: Path, folder: str) -> None:
    backup_dir = Path(folder).expanduser().resolve()
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest.get("project", "")).resolve() != root:
        raise RuntimeError("This is not a 17B backup for this project.")
    for relative, hashes in manifest["files"].items():
        current_file = root / relative
        current = current_file.read_bytes() if current_file.is_file() else None
        if digest(current) != hashes["after"]:
            raise RuntimeError("Cannot restore: file changed since Update 17B: " + relative)
        saved = backup_dir / "originals" / relative
        if hashes["before"] is not None and (not saved.is_file() or digest(saved.read_bytes()) != hashes["before"]):
            raise RuntimeError("Backup missing or corrupt for " + relative)
    for relative in manifest["files"]:
        saved = backup_dir / "originals" / relative
        if saved.is_file():
            atomic_write(root / relative, saved.read_bytes())
        else:
            (root / relative).unlink(missing_ok=True)
    print("Restored Update 17B successfully.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fight Royale Update 17B - smooth weapon trails")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", metavar="BACKUP_DIR")
    args = parser.parse_args()
    project = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(project, args.restore)
        else:
            install(project, build_changes(project), args.dry_run)
        return 0
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
