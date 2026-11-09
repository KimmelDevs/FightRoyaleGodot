#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot — Update 14B: projectile silhouette and trail visibility.

Run from the Godot project directory:
    python install_14b_projectile_visuals.py

Options: --dry-run, --check-godot, --project PATH, --restore BACKUP_DIR.
Requires Update 14A; leaves character stats, cooldowns, damage and hitboxes intact.
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

VERSION = "14B.1"
MATCH_FILE = "scripts/match.gd"
REPORT_FILE = "reports/projectile_visuals_14b.txt"
MARKER = "# FRG14B - readable projectile silhouettes and ribbon trails"

HELPERS = '''# FRG14B - readable projectile silhouettes and ribbon trails
# Visual-only change: projectile hitboxes, speed, damage and clash rules stay unchanged.
const PROJECTILE_TRAIL_SAMPLES := 8

func _projectile_shape(style: String, size: float) -> Mesh:
\tmatch style:
\t\t"arrow":
\t\t\tvar arrow := BoxMesh.new()
\t\t\tarrow.size = Vector3(0.05, 0.05, 0.70) * size
\t\t\treturn arrow
\t\t"wave":
\t\t\tvar wave := BoxMesh.new()
\t\t\twave.size = Vector3(0.95, 0.14, 0.14) * size
\t\t\treturn wave
\t\t"shuriken":
\t\t\tvar star := BoxMesh.new()
\t\t\tstar.size = Vector3(0.34, 0.34, 0.055) * size
\t\t\treturn star
\t\t"shock":
\t\t\tvar pulse := SphereMesh.new()
\t\t\tpulse.radius = 0.20 * size
\t\t\tpulse.height = 0.40 * size
\t\t\treturn pulse
\t\t_:
\t\t\tvar bolt := SphereMesh.new()
\t\t\tbolt.radius = 0.14 * size
\t\t\tbolt.height = 0.28 * size
\t\t\treturn bolt

func _attach_projectile_trail(p: Dictionary) -> void:
\tvar node: MeshInstance3D = p.node
\tvar ribbon := MeshInstance3D.new()
\tribbon.name = "ProjectileTrail"
\tvar immediate := ImmediateMesh.new()
\tribbon.mesh = immediate
\tvar mat := StandardMaterial3D.new()
\tmat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
\tmat.vertex_color_use_as_albedo = true
\tmat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
\tmat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
\tmat.cull_mode = BaseMaterial3D.CULL_DISABLED
\tribbon.material_override = mat
\tnode.add_child(ribbon)
\tp["trail_mesh"] = immediate
\tp["trail_points"] = [node.global_position]

func _update_projectile_trail(p: Dictionary) -> void:
\tvar node: MeshInstance3D = p.node
\tif not is_instance_valid(node):
\t\treturn
\tvar points: Array = p.get("trail_points", [])
\tpoints.append(node.global_position)
\twhile points.size() > PROJECTILE_TRAIL_SAMPLES:
\t\tpoints.pop_front()
\tvar ribbon: ImmediateMesh = p.get("trail_mesh")
\tif ribbon == null:
\t\treturn
\tribbon.clear_surfaces()
\tif points.size() < 2:
\t\treturn
\tribbon.surface_begin(Mesh.PRIMITIVE_TRIANGLE_STRIP)
\tfor i in range(points.size()):
\t\tvar before: Vector3 = points[maxi(i - 1, 0)]
\t\tvar after: Vector3 = points[mini(i + 1, points.size() - 1)]
\t\tvar side: Vector3 = (after - before).cross(Vector3.UP)
\t\tif side.length_squared() < 0.00001:
\t\t\tside = Vector3.RIGHT
\t\tside = side.normalized() * (0.065 * float(p.size))
\t\tvar alpha: float = 0.72 * float(i) / float(points.size() - 1)
\t\tvar here: Vector3 = points[i]
\t\tribbon.surface_set_color(Color(p.color, alpha))
\t\tribbon.surface_add_vertex(node.to_local(here - side))
\t\tribbon.surface_set_color(Color(p.color, alpha))
\t\tribbon.surface_add_vertex(node.to_local(here + side))
\tribbon.surface_end()

'''

REPORT = """FIGHT ROYALE GODOT — UPDATE 14B — PROJECTILE VISUALS

Changes to scripts/match.gd:
- Makes arrows, waves, shurikens and shock projectiles visually distinct.
- Adds short fading ribbons to projectiles, automatically freed with the projectile.
- Keeps the 14A projectile-vs-projectile clash rules unchanged.
- Does not modify damage, hitboxes, speed, cooldowns or game modes.

This is a cosmetic update, not full character-specific projectile artwork.
Open the project in Godot to import scripts and test the rendered result.
"""


def replace_once(source: str, old: str, new: str, label: str) -> str:
    found = source.count(old)
    if found != 1:
        raise ValueError(f"{label}: expected one matching section, found {found}; no files modified")
    return source.replace(old, new, 1)


def patch(source: str) -> str:
    if MARKER in source:
        for need in ("_projectile_shape(", "_attach_projectile_trail(", "_update_projectile_trail(p)"):
            if need not in source:
                raise ValueError("Partial 14B update found, refusing to modify: " + need)
        return source
    if "# FRG14A - swept projectile versus projectile clashes" not in source:
        raise ValueError("Install Update 14A before 14B")
    # Separate methods are deliberately inserted adjacent to existing projectile helpers,
    # avoiding changes to class names, global autoloads or animation systems.
    source = replace_once(source,
        "func _spawn_projectile(shooter, a: Dictionary, power: float, pos: Vector3, vel: Vector3, color: Color, target) -> void:",
        HELPERS + "func _spawn_projectile(shooter, a: Dictionary, power: float, pos: Vector3, vel: Vector3, color: Color, target) -> void:",
        "projectile helpers")
    old_shape = '''\tvar node := MeshInstance3D.new()
\tvar size: float = float(a.size)
\tif a.style == "arrow":
\t\tvar b := BoxMesh.new(); b.size = Vector3(0.02, 0.02, 0.7) * size; node.mesh = b
\telse:
\t\tvar s := SphereMesh.new(); s.radius = 0.14 * size; s.height = 0.28 * size; node.mesh = s
'''
    new_shape = '''\tvar node := MeshInstance3D.new()
\tvar size: float = float(a.size)
\tnode.mesh = _projectile_shape(String(a.get("style", "bolt")), size)
'''
    source = replace_once(source, old_shape, new_shape, "projectile shape selection")
    old_spawn_tail = '''\t\t"atk": a, "power": power, "pierce": bool(a.pierce), "hit": {}, "target": target, "color": color, "size": size})
\t_next_id += 1
'''
    new_spawn_tail = '''\t\t"atk": a, "power": power, "pierce": bool(a.pierce), "hit": {}, "target": target, "color": color, "size": size})
\t_attach_projectile_trail(_projectiles[_projectiles.size() - 1])
\t_next_id += 1
'''
    source = replace_once(source, old_spawn_tail, new_spawn_tail, "trail attach on spawn")
    source = replace_once(source,
        '''\t\tnode.global_position += p.vel * dt
\t\tp.life -= dt
''',
        '''\t\tnode.global_position += p.vel * dt
\t\t_update_projectile_trail(p)
\t\tp.life -= dt
''',
        "trail update on movement")
    return source


def digest(blob: bytes | None) -> str | None:
    return hashlib.sha256(blob).hexdigest() if blob is not None else None


def write_atomic(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp_14b_" + uuid.uuid4().hex[:8])
    try:
        tmp.write_bytes(contents)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def plan(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise ValueError("Run this from the Godot project folder containing project.godot")
    path = root / MATCH_FILE
    if not path.is_file():
        raise ValueError("Missing scripts/match.gd")
    before = path.read_text(encoding="utf-8-sig")
    after = patch(before)
    out: dict[str, bytes] = {}
    if before != after:
        out[MATCH_FILE] = after.encode("utf-8")
    if not (root / REPORT_FILE).is_file() or (root / REPORT_FILE).read_text(encoding="utf-8") != REPORT:
        out[REPORT_FILE] = REPORT.encode("utf-8")
    return out


def install(root: Path, changes: dict[str, bytes], dry_run: bool) -> None:
    if not changes:
        print("Update 14B already installed; no changes.")
        return
    print("Update 14B files:")
    for rel in changes:
        print(" -", rel)
    if dry_run:
        print("Dry run: no files modified")
        return
    folder = root.parent / (root.name + "_backups") / (
        "projectiles_14b_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    )
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for rel, blob in changes.items():
        old = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest["files"][rel] = {"before": digest(old), "after": digest(blob)}
        if old is not None:
            backup = folder / "originals" / rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(old)
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    applied = []
    try:
        for rel, blob in changes.items():
            write_atomic(root / rel, blob)
            applied.append(rel)
    except Exception:
        for rel in reversed(applied):
            backup = folder / "originals" / rel
            if backup.is_file():
                write_atomic(root / rel, backup.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print("Installed 14B. Backup:", folder)


def restore(root: Path, source: str) -> None:
    backup = Path(source).expanduser().resolve()
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest.get("project", "")).resolve() != root:
        raise ValueError("Wrong backup or project")
    for rel, info in manifest["files"].items():
        cur = (root / rel).read_bytes() if (root / rel).is_file() else None
        if digest(cur) != info["after"]:
            raise ValueError("File changed since 14B; not overwriting: " + rel)
        old = backup / "originals" / rel
        if info["before"] is not None and (not old.is_file() or digest(old.read_bytes()) != info["before"]):
            raise ValueError("Corrupt backup: " + rel)
    for rel in manifest["files"]:
        old = backup / "originals" / rel
        if old.is_file():
            write_atomic(root / rel, old.read_bytes())
        else:
            (root / rel).unlink(missing_ok=True)
    print("Restored:", backup)


def check_godot(root: Path) -> None:
    exe = shutil.which("godot") or shutil.which("godot4")
    if not exe:
        print("Godot executable not on PATH. Open the project in the Godot editor to validate")
        return
    proc = subprocess.run([exe, "--headless", "--editor", "--path", str(root), "--quit"],
                          text=True, capture_output=True, timeout=150)
    print((proc.stdout + "\n" + proc.stderr)[-16000:])
    if proc.returncode != 0:
        raise RuntimeError(f"Godot validation exit code {proc.returncode}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fight Royale Godot Update 14B — Projectile Visuals")
    ap.add_argument("--project", type=Path, default=Path.cwd())
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check-godot", action="store_true")
    ap.add_argument("--restore", metavar="BACKUP_DIR")
    args = ap.parse_args()
    root = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(root, args.restore)
        else:
            install(root, plan(root), args.dry_run)
            if args.check_godot and not args.dry_run:
                check_godot(root)
        return 0
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
