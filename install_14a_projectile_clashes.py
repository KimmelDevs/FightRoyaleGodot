#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot Update 14A — projectile-vs-projectile clashes and pause safety.

Run from your Godot project root:
    python install_14a_projectile_clashes.py

Options: --dry-run, --check-godot, --project PATH, --restore BACKUP_DIR.
Only changes scripts/match.gd and its own update report. Existing assets untouched.
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

VERSION = "14A.1"
MATCH_PATH = "scripts/match.gd"
REPORT_PATH = "reports/projectile_14a.txt"
MARKER = "# FRG14A - swept projectile versus projectile clashes"

PROJECTILE_HELPERS = '''# FRG14A - swept projectile versus projectile clashes
# Only ordinary non-piercing enemy projectiles can cancel each other.
# Explosive and piercing attacks continue through their normal impact rules.
func _projectile_can_clash(p: Dictionary) -> bool:
\tif bool(p.get("pierce", false)):
\t\treturn false
\tvar style: String = String(p.atk.get("style", ""))
\treturn not (style in ["explosion", "bomb", "meteor", "grenade", "rocket"])

func _resolve_projectile_duels(dt: float) -> void:
\t# Compare trajectories over this frame so fast bolts crossing between
\t# discrete positions can still collide, even at lower frame rates.
\tif dt <= 0.0 or _projectiles.size() < 2:
\t\treturn
\tvar claimed: Dictionary = {}
\tvar destroyed: Array = []
\tfor i in range(_projectiles.size()):
\t\tvar a: Dictionary = _projectiles[i]
\t\tif claimed.has(a.id) or not _projectile_can_clash(a):
\t\t\tcontinue
\t\tif not is_instance_valid(a.node):
\t\t\tcontinue
\t\tfor j in range(i + 1, _projectiles.size()):
\t\t\tvar b: Dictionary = _projectiles[j]
\t\t\tif claimed.has(b.id) or int(a.team) == int(b.team) or not _projectile_can_clash(b):
\t\t\t\tcontinue
\t\t\tif not is_instance_valid(b.node):
\t\t\t\tcontinue
\t\t\tvar relative_position: Vector3 = a.node.global_position - b.node.global_position
\t\t\tvar relative_velocity: Vector3 = a.vel - b.vel
\t\t\tvar relative_speed_sq: float = relative_velocity.length_squared()
\t\t\tvar hit_t: float = 0.0
\t\t\tif relative_speed_sq > 0.000001:
\t\t\t\thit_t = clampf(-relative_position.dot(relative_velocity) / relative_speed_sq, 0.0, dt)
\t\t\tvar a_at: Vector3 = a.node.global_position + a.vel * hit_t
\t\t\tvar b_at: Vector3 = b.node.global_position + b.vel * hit_t
\t\t\t# Projectile meshes use a 0.14*size sphere. Slight tolerance
\t\t\t# accounts for narrow arrow meshes and near-miss visual contact.
\t\t\tvar hit_radius: float = 0.18 * (maxf(float(a.size), 0.3) + maxf(float(b.size), 0.3))
\t\t\tif a_at.distance_squared_to(b_at) > hit_radius * hit_radius:
\t\t\t\tcontinue
\t\t\tvar impact: Vector3 = (a_at + b_at) * 0.5
\t\t\tfx.sparks(impact, Color("#fff1bd"), 24, 6.0)
\t\t\tfx.ring(impact, Color("#f6d78c"), 0.9, 0.20, 0.75)
\t\t\tfx.number(impact + Vector3(0.0, 0.3, 0.0), "CLASH!", Color("#ffe6a0"), 0.65)
\t\t\tclaimed[a.id] = true
\t\t\tclaimed[b.id] = true
\t\t\tdestroyed.append(a)
\t\t\tdestroyed.append(b)
\t\t\tbreak
\tfor p in destroyed:
\t\tif is_instance_valid(p.node):
\t\t\tp.node.queue_free()
\t\t_projectiles.erase(p)

'''

REPORT = """FIGHT ROYALE GODOT — UPDATE 14A: PROJECTILE CLASHES

What changed:
- Enemy non-piercing, non-explosive projectiles can cancel when their
  trajectories intersect during the same update frame.
- Each projectile can clash only once per frame; friendly fire is excluded.
- Existing projectile-to-fighter and melee-to-projectile logic is preserved.
- Paused or finished matches no longer process projectile hits.
- Old projectile nodes are freed on rematch instead of being left in the scene.

No changes to character skills, cooldowns, projectile damage, VRMs, SFX,
menus, shops or game modes. No engine-side test was performed by the installer
unless --check-godot is requested and Godot is on PATH.
"""


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected 1 anchor, found {count}; not installing partial update")
    return source.replace(old, new, 1)


def patch(source: str) -> str:
    if MARKER in source:
        required = ("_resolve_projectile_duels(dt)", "if dt <= 0.0 or round_over:", "for p in _projectiles:\n\t\tif is_instance_valid(p.node):")
        if all(x in source for x in required):
            return source
        raise ValueError("Partial Update 14A detected; refusing to modify")
    for prereq in ("# FRG12B", "# FRG07", "func _update_projectiles(dt: float) -> void:"):
        if prereq not in source:
            raise ValueError("Expected previous projectile update not found: " + prereq)
    source = replace_once(source,
        "func start_round() -> void:\n\tfor f in fighters: f.queue_free()",
        "func start_round() -> void:\n\t# FRG14A: free effects from the preceding round before clearing arrays.\n\tfor p in _projectiles:\n\t\tif is_instance_valid(p.node):\n\t\t\tp.node.queue_free()\n\tfor f in fighters: f.queue_free()",
        "round cleanup")
    source = replace_once(source,
        "func _update_projectiles(dt: float) -> void:\n\tfor p in _projectiles.duplicate():",
        "func _update_projectiles(dt: float) -> void:\n\t# Never let paused / concluded duels advance or apply projectile damage.\n\tif dt <= 0.0 or round_over:\n\t\treturn\n\t_resolve_projectile_duels(dt)\n\tfor p in _projectiles.duplicate():",
        "projectile frame")
    source = replace_once(source,
        "func _update_projectiles(dt: float) -> void:",
        PROJECTILE_HELPERS + "func _update_projectiles(dt: float) -> void:",
        "insert projectile clash implementation")
    return source


def digest(b: bytes | None) -> str | None:
    return hashlib.sha256(b).hexdigest() if b is not None else None


def write_atomic(path: Path, blob: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp_14a_" + uuid.uuid4().hex[:8])
    try:
        tmp.write_bytes(blob)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def plan(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise ValueError("Run from your Godot project directory (project.godot missing)")
    path = root / MATCH_PATH
    if not path.is_file():
        raise ValueError("Missing " + MATCH_PATH)
    current = path.read_text(encoding="utf-8-sig")
    updated = patch(current)
    changes = {}
    if current != updated:
        changes[MATCH_PATH] = updated.encode("utf-8")
    if not (root / REPORT_PATH).is_file() or (root / REPORT_PATH).read_text(encoding="utf-8") != REPORT:
        changes[REPORT_PATH] = REPORT.encode("utf-8")
    return changes


def install(root: Path, changes: dict[str, bytes], dry_run: bool) -> None:
    if not changes:
        print("Update 14A already installed; no changes.")
        return
    print("Update 14A files:")
    for name in changes:
        print(" -", name)
    if dry_run:
        print("Dry run: nothing written.")
        return
    folder = root.parent / (root.name + "_backups") / (
        "projectiles_14a_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    )
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for rel, blob in changes.items():
        old = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest["files"][rel] = {"before": digest(old), "after": digest(blob)}
        if old is not None:
            out = folder / "originals" / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(old)
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    completed = []
    try:
        for rel, blob in changes.items():
            write_atomic(root / rel, blob)
            completed.append(rel)
    except Exception:
        for rel in reversed(completed):
            original = folder / "originals" / rel
            if original.is_file():
                write_atomic(root / rel, original.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print("Installed Update 14A. Backup:", folder)


def restore(root: Path, source: str) -> None:
    backup = Path(source).expanduser().resolve()
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest.get("project", "")).resolve() != root:
        raise ValueError("Backup does not belong to this update and project")
    for rel, info in manifest["files"].items():
        actual = (root / rel).read_bytes() if (root / rel).is_file() else None
        if digest(actual) != info["after"]:
            raise ValueError("Refusing to overwrite file modified since Update 14A: " + rel)
        orig = backup / "originals" / rel
        if info["before"] is not None and (not orig.is_file() or digest(orig.read_bytes()) != info["before"]):
            raise ValueError("Backup corrupted: " + rel)
    for rel in manifest["files"]:
        orig = backup / "originals" / rel
        if orig.is_file():
            write_atomic(root / rel, orig.read_bytes())
        else:
            (root / rel).unlink(missing_ok=True)
    print("Restored:", backup)


def check_godot(root: Path) -> None:
    exe = shutil.which("godot") or shutil.which("godot4")
    if not exe:
        print("Godot not found on PATH. Open project in Godot to validate GDScript.")
        return
    r = subprocess.run([exe, "--headless", "--editor", "--path", str(root), "--quit"],
                       text=True, capture_output=True, timeout=150)
    print((r.stdout + "\n" + r.stderr)[-14000:])
    if r.returncode != 0:
        raise RuntimeError("Godot headless validation failed (" + str(r.returncode) + ")")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fight Royale Godot 14A — Projectile clashes")
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
