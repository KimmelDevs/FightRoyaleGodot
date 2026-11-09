#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot — Update 14C: projectile spin and environment impact visuals.

Run from the Godot project directory:
    python install_14c_projectile_impacts.py

Options: --dry-run, --check-godot, --project PATH, --restore BACKUP_DIR.
Requires Update 14B; preserves character stats, cooldowns, damage and hitboxes.
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

VERSION = "14C.1"
MATCH_FILE = "scripts/match.gd"
REPORT_FILE = "reports/projectile_impacts_14c.txt"
MARKER = "# FRG14C - projectile spin and environment impacts"

HELPERS = '''# FRG14C - projectile spin and environment impacts
# Visual-only: projectile velocity, damage, collisions and cooldowns unchanged.
func _projectile_visual_update(p: Dictionary, dt: float) -> void:
	var node: MeshInstance3D = p.node
	if not is_instance_valid(node):
		return
	var style: String = String(p.atk.get("style", ""))
	# Shuriken spin about flight axis while their world travel stays untouched.
	if style == "shuriken":
		node.rotate_object_local(Vector3.FORWARD, dt * 15.0)

func _projectile_world_visual(p: Dictionary, at: Vector3, is_world: bool) -> void:
	# Cosmetic only. Do not call apply_hit or spawn area damage here.
	var col: Color = p.color
	var scale: float = clampf(float(p.size), 0.35, 2.0)
	if not is_world:
		# Timeouts should quietly dissipate to avoid fake impact cues.
		fx.flash(at, col, 0.12 * scale, 0.11, 0.32)
		return
	var style: String = String(p.atk.get("style", ""))
	if style in ["explosion", "bomb", "meteor", "grenade", "rocket"]:
		# A MISS is cosmetic only, even when the projectile style is explosive.
		fx.flash(at, col, 0.45 * scale, 0.17, 0.65)
		fx.ring(at, col, 0.65 * scale, 0.22, 0.55)
	else:
		fx.sparks(at, col, 9, 3.0)
		fx.flash(at, col, 0.22 * scale, 0.12, 0.50)
		if at.y < 0.12:
			fx.ring(at, col, 0.40 * scale, 0.20, 0.4)

'''

REPORT = """FIGHT ROYALE GODOT — UPDATE 14C: PROJECTILE IMPACT READABILITY

- Shurikens spin around their flight axis as they move.
- Missed projectiles make a small visual effect on ground/arena boundaries.
- Timed-out projectiles quietly dissipate rather than vanish instantly.
- Existing hit effects, damage, knockback, clashes, hitboxes and AI are unchanged.
- Requires Update 14B. Tested as a Python file patch; validate in Godot.
"""



def replace_once(source: str, old: str, new: str, label: str) -> str:
    found = source.count(old)
    if found != 1:
        raise ValueError(f"{label}: expected one matching section, found {found}; no files modified")
    return source.replace(old, new, 1)


def patch(source: str) -> str:
    if MARKER in source:
        required = ("_projectile_visual_update(p, dt)", "_projectile_world_visual(p, visual_pos, world_end)")
        if all(x in source for x in required):
            return source
        raise ValueError("Partially installed 14C detected; refusing unsafe re-patch")
    if "# FRG14B - readable projectile silhouettes and ribbon trails" not in source:
        raise ValueError("Install Update 14B before 14C")
    source = replace_once(
        source,
        "func _update_projectiles(dt: float) -> void:",
        HELPERS + "func _update_projectiles(dt: float) -> void:",
        "projectile visual helpers",
    )
    source = replace_once(
        source,
        "\t\tnode.global_position += p.vel * dt\n\t\t_update_projectile_trail(p)\n\t\tp.life -= dt\n",
        "\t\tnode.global_position += p.vel * dt\n\t\t_update_projectile_trail(p)\n\t\tp.life -= dt\n\t\t_projectile_visual_update(p, dt)\n",
        "projectile rotation during travel",
    )
    source = replace_once(
        source,
        '''		var gp := node.global_position
		if p.life <= 0 or gp.y < 0.05 or Vector2(gp.x, gp.z).length() > 16: done = true
		if done:
			node.queue_free()
			_projectiles.erase(p)
''',
        '''		var gp := node.global_position
		if not done:
			var world_end: bool = gp.y < 0.05 or Vector2(gp.x, gp.z).length() > 16
			if world_end or p.life <= 0.0:
				var visual_pos: Vector3 = gp
				if visual_pos.y < 0.05:
					visual_pos.y = 0.05
				_projectile_world_visual(p, visual_pos, world_end)
				done = true
		if done:
			node.queue_free()
			_projectiles.erase(p)
''',
        "projectile world/timeout visuals",
    )
    return source


def digest(blob: bytes | None) -> str | None:
    return hashlib.sha256(blob).hexdigest() if blob is not None else None


def write_atomic(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp_14c_" + uuid.uuid4().hex[:8])
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
        print("Update 14C already installed; no changes.")
        return
    print("Update 14C files:")
    for rel in changes:
        print(" -", rel)
    if dry_run:
        print("Dry run: no files modified")
        return
    folder = root.parent / (root.name + "_backups") / (
        "projectiles_14c_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
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
    print("Installed 14C. Backup:", folder)


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
    ap = argparse.ArgumentParser(description="Fight Royale Godot Update 14C — Projectile Impacts")
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
