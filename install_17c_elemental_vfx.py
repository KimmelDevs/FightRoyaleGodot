#!/usr/bin/env python3
"""Fight Royale Godot — 17C Elemental VFX (visual only).

From the directory containing project.godot:
    python install_17c_elemental_vfx.py

Optional:
    python install_17c_elemental_vfx.py --dry-run
    python install_17c_elemental_vfx.py --restore PATH_TO_BACKUP

Requires installed 17A and 17B; does not change damage, skills, hitboxes or AI.
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

VERSION = "17C.1"
MARKER = "# FRG17C - elemental hit and skill VFX"
FX_PATH = "scripts/fx.gd"
MATCH_PATH = "scripts/match.gd"
TRAIL_PATH = "scripts/trail.gd"
REPORT_PATH = "reports/elemental_vfx_17c.txt"

FX_FUNCTIONS = r'''
# FRG17C - elemental hit and skill VFX
# Cosmetic only: all damage, status, guard, projectile and AI calculations are unchanged.
# Lightweight MultiMesh bursts, with fewer particles on non-heavy strikes.
func elemental_hit_17c(at: Vector3, element: String, tint: Color, heavy: bool) -> void:
	var n := 11 if heavy else 5
	var color_key := element.to_lower()
	match color_key:
		"fire", "flame":
			var ember := BoxMesh.new()
			ember.size = Vector3(0.055, 0.10, 0.035)
			burst(at, ember, unlit(Color("#ff8b3d"), 0.95, true), n, 3.9, Vector3.UP, 1.0, -1.8, 0.42, 1.0)
			if heavy: flash(at, Color("#ffba54"), 0.35, 0.16, 0.5)
		"electric", "lightning":
			var spark := BoxMesh.new()
			spark.size = Vector3(0.025, 0.025, 0.19)
			burst(at, spark, unlit(Color("#d3f0ff"), 0.95, true), n + 3, 6.0, Vector3.ZERO, 1.0, 4.0, 0.20, 1.0)
			if heavy: ring(at, Color("#83d4ff"), 0.85, 0.17, 0.65)
		"water":
			var droplet := SphereMesh.new()
			droplet.radius = 0.045
			droplet.height = 0.09
			droplet.radial_segments = 6
			droplet.rings = 3
			burst(at, droplet, unlit(Color("#7bd7ff"), 0.75, true), n, 3.3, Vector3.UP, 1.2, 7.0, 0.36, 1.0)
			if heavy: ring(at, Color("#4caaff"), 0.8, 0.2, 0.45)
		"shadow", "moon", "blood":
			var dark_tint := Color("#b17bef") if color_key != "blood" else Color("#e44869")
			sparks(at, dark_tint, n + 2, 3.3)
			if heavy: flash(at, dark_tint, 0.45, 0.2, 0.42)
		"light", "blossom", "nature":
			motes(at, tint, n)
			if heavy: ring(at, tint, 0.7, 0.17, 0.46)
		"chi", "force":
			if heavy: ring(at, tint, 1.05, 0.22, 0.62)
		# Earth already emits rocks in Match; no duplicate burst here.
		_:
			pass

func elemental_skill_17c(at: Vector3, element: String, style: String, tint: Color, radius: float) -> void:
	var r := clampf(radius, 0.35, 5.0)
	match style:
		"lightning":
			var ray := BoxMesh.new()
			ray.size = Vector3(0.035, 0.25, 0.035)
			burst(at + Vector3.UP * 0.5, ray, unlit(Color("#d7f4ff"), 0.9, true), 15, 7.5, Vector3.UP, 0.85, 0.0, 0.27, 1.1)
		"meteor", "explosion":
			var coal := BoxMesh.new()
			coal.size = Vector3(0.08, 0.08, 0.08)
			burst(at + Vector3.UP * 0.25, coal, unlit(Color("#ff9d5b"), 0.85, true), 15, 4.2, Vector3.UP, 1.0, 12.0, 0.50, 1.0)
		"spin":
			motes(at + Vector3.UP * 0.65, tint, 10)
		"slam", "cleave":
			# 17A provides the ground crack and directional burst; add a small dust bloom.
			motes(at + Vector3.UP * 0.25, Color("#dac2a2"), 6)
		_:
			match element.to_lower():
				"water":
					ring(at, Color("#83d7ff"), r * 0.7, 0.21, 0.47)
				"moon", "shadow", "blood":
					flash(at + Vector3.UP * 0.4, tint, r * 0.28, 0.19, 0.3)
				"nature", "blossom", "light":
					motes(at + Vector3.UP * 0.4, tint, 7)
				_:
					pass
'''

HIT_ANCHOR = "\t\t\tfx.combat_hit(hit_pos, glow, dir, heavy)"
HIT_NEW = HIT_ANCHOR + (
    "\n\t\t\t# FRG17C: cosmetic accent only after a landed hit."
    "\n\t\t\tif attacker is Fighter:"
    "\n\t\t\t\tfx.elemental_hit_17c(hit_pos, String(attacker.look.element), glow, heavy)"
)
IMPACT_ANCHOR = (
    "\t\t_:\n"
    "\t\t\tfx.sparks(pos, color, 14, 5.0)\n\n"
    "func _buff(f: Fighter, a: Dictionary) -> void:"
)
IMPACT_NEW = (
    "\t\t_:\n"
    "\t\t\tfx.sparks(pos, color, 14, 5.0)\n"
    "\t# FRG17C: visual-only elemental accent for skill impact events.\n"
    "\tfx.elemental_skill_17c(g, String(a.get(\"element\", \"\")), String(a.get(\"style\", \"\")), color, radius)\n\n"
    "func _buff(f: Fighter, a: Dictionary) -> void:"
)


def checksum(value: bytes | None) -> str | None:
    return hashlib.sha256(value).hexdigest() if value is not None else None


def safe_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, scratch = tempfile.mkstemp(prefix=".frg17c-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(scratch, path)
    finally:
        if os.path.exists(scratch):
            os.unlink(scratch)


def replace_exact_once(text: str, old: str, new: str, description: str) -> str:
    found = text.count(old)
    if found != 1:
        raise RuntimeError(f"{description}: expected exactly 1 code anchor, found {found}; no changes made.")
    return text.replace(old, new, 1)


def plan(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise RuntimeError("Run this from your Godot project folder (project.godot missing).")
    for relative in (FX_PATH, MATCH_PATH, TRAIL_PATH):
        if not (root / relative).is_file():
            raise RuntimeError(f"Required source missing: {relative}")
    fx = (root / FX_PATH).read_text(encoding="utf-8-sig")
    match = (root / MATCH_PATH).read_text(encoding="utf-8-sig")
    trail = (root / TRAIL_PATH).read_text(encoding="utf-8-sig")

    marked = (MARKER in fx, MARKER in match)
    if all(marked):
        print("17C already installed; no files changed.")
        return {}
    if any(marked):
        raise RuntimeError("Partial Update 17C detected; leaving project unchanged.")
    if "# FRG17A - combat impact VFX" not in fx or "# FRG17A - combat impact VFX" not in match:
        raise RuntimeError("Update 17A is required before 17C.")
    if "# FRG17B - twin-layer weapon trails" not in trail or "# FRG17B: visual styling" not in match:
        raise RuntimeError("Update 17B is required before 17C.")
    if "func elemental_hit_17c" in fx or "elemental_hit_17c(" in match:
        raise RuntimeError("Conflicting elemental VFX patch detected; no files changed.")

    fx = fx.rstrip() + "\n\n" + FX_FUNCTIONS.lstrip("\n")
    match = replace_exact_once(match, HIT_ANCHOR, HIT_NEW, "Land-hit hook")
    match = replace_exact_once(match, IMPACT_ANCHOR, IMPACT_NEW, "Skill-impact hook")
    match = replace_exact_once(match, "class_name Match\n", "class_name Match\n" + MARKER + "\n", "Match header")
    report = """Fight Royale Godot - Update 17C (Elemental Hit and Skill VFX)

- Small elemental accents only on landed melee hits: fire, lightning, water,
  moon/shadow/blood, light/nature/blossom and chi/force.
- Elemental skill impact accents by style and element (meteor, lightning,
  spin, slam, cleave and water/shadow magic).
- Uses built-in MultiMesh particles/materials; compatible with GL renderer.
- Purely cosmetic: damage, status, AI, cooldowns, range and hitboxes unchanged.
- VRM rigging and Animation Lab saved profiles are untouched.
- No SFX paths are changed. Audio integration remains a later update.
- Test within Godot after script import, in both Duel vs CPU and CPU vs CPU.
"""
    return {FX_PATH: fx.encode("utf-8"), MATCH_PATH: match.encode("utf-8"), REPORT_PATH: report.encode("utf-8")}


def install(root: Path, changes: dict[str, bytes], dry_run: bool) -> Path | None:
    if not changes:
        return None
    for relative in changes:
        print("Update:", relative)
    if dry_run:
        print("DRY RUN — no files written")
        return None
    backups = root.parent / (root.name + "_backups") / (
        "elemental_vfx_17c_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    )
    backups.mkdir(parents=True, exist_ok=False)
    manifest: dict = {"version": VERSION, "project": str(root), "files": {}}
    for relative, new in changes.items():
        old = (root / relative).read_bytes() if (root / relative).is_file() else None
        manifest["files"][relative] = {"before": checksum(old), "after": checksum(new)}
        if old is not None:
            saved = backups / "originals" / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(old)
    (backups / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    modified: list[str] = []
    try:
        for relative, new in changes.items():
            safe_write(root / relative, new)
            modified.append(relative)
    except Exception:
        for relative in reversed(modified):
            saved = backups / "originals" / relative
            if saved.is_file():
                safe_write(root / relative, saved.read_bytes())
            else:
                (root / relative).unlink(missing_ok=True)
        raise
    print("Update 17C installed. Backup:", backups)
    return backups


def restore(root: Path, saved_folder: str) -> None:
    folder = Path(saved_folder).expanduser().resolve()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest.get("project", "")).resolve() != root:
        raise RuntimeError("Backup is not from 17C on this project.")
    for relative, states in manifest["files"].items():
        current = (root / relative).read_bytes() if (root / relative).is_file() else None
        if checksum(current) != states["after"]:
            raise RuntimeError("Cannot restore modified file: " + relative)
        original = folder / "originals" / relative
        if states["before"] is not None and (not original.is_file() or checksum(original.read_bytes()) != states["before"]):
            raise RuntimeError("Backup missing or damaged: " + relative)
    for relative in manifest["files"]:
        original = folder / "originals" / relative
        if original.is_file():
            safe_write(root / relative, original.read_bytes())
        else:
            (root / relative).unlink(missing_ok=True)
    print("Update 17C restored.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fight Royale — Elemental VFX Update 17C")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", metavar="BACKUP_FOLDER")
    args = parser.parse_args()
    root = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(root, args.restore)
        else:
            install(root, plan(root), args.dry_run)
        return 0
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
