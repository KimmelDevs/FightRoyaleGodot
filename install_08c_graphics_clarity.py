#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot — Update 08c: Graphics Clarity hotfix.

Run from the Godot project directory:
    python install_08c_graphics_clarity.py

Optional:
    python install_08c_graphics_clarity.py --preset balanced
    python install_08c_graphics_clarity.py --preset ultra
    python install_08c_graphics_clarity.py --resolution 1600x900
    python install_08c_graphics_clarity.py --dry-run
    python install_08c_graphics_clarity.py --restore FULL_BACKUP_FOLDER_PATH

Works with the GL Compatibility renderer and preserves VRMs, shader plugins, gameplay
scripts, models, SFX and your two game modes. Uses only the Python standard library.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid

VERSION = "08c.1"
MARKER_PREVIEW = "# FRG08C - render character previews at full displayed size with crisp 3D scaling"
MARKER_FOG = "# FRG08C - remove distance haze from the duel arena"
PRESETS = {
    "balanced": {"width": 1280, "height": 720, "scale": 1.0, "preview_scale": 1.0, "mip_bias": -0.05},
    "sharp": {"width": 1600, "height": 900, "scale": 1.15, "preview_scale": 1.2, "mip_bias": -0.18},
    "ultra": {"width": 1920, "height": 1080, "scale": 1.3, "preview_scale": 1.3, "mip_bias": -0.20},
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def screen_size() -> tuple[int, int] | None:
    if os.name != "nt":
        return None
    try:
        import ctypes
        user32 = ctypes.windll.user32
        # Avoid logical-pixel scaling on HiDPI displays where possible.
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
        w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        if w >= 640 and h >= 480:
            return (int(w), int(h))
    except Exception:
        pass
    return None


def resolution_for(preset: dict, custom: str | None) -> tuple[int, int, str]:
    if custom:
        match = re.fullmatch(r"(\d{3,5})[xX](\d{3,5})", custom)
        if not match:
            raise ValueError("--resolution must look like 1600x900")
        w, h = map(int, match.groups())
        if not (640 <= w <= 7680 and 360 <= h <= 4320):
            raise ValueError("Resolution must be between 640x360 and 7680x4320")
        return w, h, "manual override"

    w, h = preset["width"], preset["height"]
    display = screen_size()
    if display:
        # Fit inside the screen including window title bar and taskbar. 3D is
        # rendered at actual window pixels due to canvas_items stretch mode.
        max_w = max(640, int(display[0] * 0.90))
        max_h = max(360, int(display[1] * 0.86))
        ratio = min(1.0, max_w / w, max_h / h)
        if ratio < 1.0:
            w = max(640, int(w * ratio) // 16 * 16)
            h = max(360, int(round(w * 9.0 / 16.0)))
            return w, h, f"auto-fit to {display[0]}x{display[1]} display"
    return w, h, "preset"


def ini_set(text: str, section: str, key: str, value: str) -> str:
    """Patch one Godot project setting without rewriting unrelated sections."""
    header = re.compile(rf"(?m)^\[{re.escape(section)}\]\s*$")
    found = header.search(text)
    if found is None:
        if not text.endswith("\n"):
            text += "\n"
        return text + f"\n[{section}]\n{key}={value}\n"
    rest = re.search(r"(?m)^\[[^\n]+\]\s*$", text[found.end():])
    end = found.end() + rest.start() if rest else len(text)
    before, body, after = text[:found.end()], text[found.end():end], text[end:]
    line = re.compile(rf"(?m)^{re.escape(key)}\s*=.*$")
    if len(line.findall(body)) > 1:
        raise RuntimeError(f"Duplicate project setting [{section}] {key}; refusing unsafe edit")
    if line.search(body):
        body = line.sub(lambda _m: f"{key}={value}", body, count=1)
    else:
        body = body.rstrip("\n") + f"\n{key}={value}\n\n"
    return before + body + after


def preview_patch(src: str, preview_scale: float) -> str:
    # Limit changes to the preview function. Do not alter fighter cameras,
    # user controls, selection menus or actual animation/model imports.
    start = src.find("func _preview_box()")
    if start < 0:
        raise RuntimeError("scripts/main.gd: _preview_box() not found")
    end = src.find("\nfunc ", start + 5)
    if end < 0:
        raise RuntimeError("scripts/main.gd: cannot determine preview function end")
    before, block, after = src[:start], src[start:end], src[end:]
    if MARKER_PREVIEW in block:
        block = re.sub(r"(?m)^\tviewport\.scaling_3d_scale\s*=.*$", f"\tviewport.scaling_3d_scale = {preview_scale:.2f}", block, count=1)
        return before + block + after
    replacements = (
        (r"(?m)^\tbox\.stretch = true$", "\tbox.stretch = true\n\t" + MARKER_PREVIEW + "\n\tbox.stretch_shrink = 1"),
        (r"(?m)^\tbox\.custom_minimum_size = Vector2\(320, 240\)$", "\tbox.custom_minimum_size = Vector2(400, 300)"),
        (r"(?m)^\tviewport\.size = Vector2i\(400, 320\)$", f"\tviewport.size = Vector2i(800, 600)\n\tviewport.scaling_3d_scale = {preview_scale:.2f}"),
    )
    for pattern, replacement in replacements:
        block, count = re.subn(pattern, lambda _m, val=replacement: val, block)
        if count != 1:
            raise RuntimeError(f"scripts/main.gd: preview anchor mismatch ({pattern}), found {count}; no files changed")
    # Godot resizes the viewport to its display size when stretch=true. The
    # higher 3D scaling factor supplies supersampling, not the 800x600 alone.
    return before + block + after


def match_patch(src: str) -> str:
    if MARKER_FOG in src:
        return src
    pattern = r"(?m)^(\t)env\.environment\.fog_enabled\s*=\s*true\s*$"
    result, count = re.subn(pattern, lambda m: f"{m.group(1)}{MARKER_FOG}\n{m.group(1)}env.environment.fog_enabled = false", src, count=1)
    if count != 1:
        # Fog is optional; a modified scene may already disable it.
        if re.search(r"(?m)^\tenv\.environment\.fog_enabled\s*=\s*false\s*$", src):
            return src
        raise RuntimeError("scripts/match.gd: expected arena fog setting not found; no files changed")
    return result


def build(root: Path, preset_name: str, manual_resolution: str | None):
    required = ["project.godot", "scripts/main.gd", "scripts/match.gd"]
    for rel in required:
        if not (root / rel).is_file():
            raise RuntimeError(f"Missing {rel}. Run from your Fight Royale Godot project directory.")
    cfg = read(root / "project.godot")
    main = read(root / "scripts/main.gd")
    match = read(root / "scripts/match.gd")
    p = PRESETS[preset_name]
    w, h, note = resolution_for(p, manual_resolution)
    # Keep the 1280x720 logical UI, but render the 3D arena at the actual window
    # resolution using canvas_items, not low-resolution viewport stretch.
    changes = [
        ("display", "window/size/viewport_width", "1280"),
        ("display", "window/size/viewport_height", "720"),
        ("display", "window/size/window_width_override", str(w)),
        ("display", "window/size/window_height_override", str(h)),
        ("display", "window/stretch/mode", '"canvas_items"'),
        ("rendering", "scaling_3d/mode", "0"),  # bilinear, supports SSAA in GL
        ("rendering", "scaling_3d/scale", str(p["scale"])),
        ("rendering", "anti_aliasing/quality/screen_space_aa", "0"),  # FXAA can blur textures
        ("rendering", "textures/default_filters/texture_mipmap_bias", str(p["mip_bias"])),
    ]
    for section, key, value in changes:
        cfg = ini_set(cfg, section, key, value)
    # We explicitly do NOT change renderer/rendering_method or renderer features.
    main = preview_patch(main, p["preview_scale"])
    match = match_patch(match)
    report = {
        "update": VERSION,
        "preset": preset_name,
        "window_pixels": [w, h],
        "resolution_selection": note,
        "logical_ui_base": [1280, 720],
        "3d_supersample_scale": p["scale"],
        "preview_supersample_scale": p["preview_scale"],
        "texture_lod_bias": p["mip_bias"],
        "fog": "disabled",
        "renderer": "unchanged; keeps GL Compatibility",
        "note": "This does not increase native VRM texture detail or modify source assets.",
    }
    return {
        "project.godot": cfg.encode("utf-8"),
        "scripts/main.gd": main.encode("utf-8"),
        "scripts/match.gd": match.encode("utf-8"),
        "reports/graphics_clarity_08c.json": (json.dumps(report, indent=2) + "\n").encode("utf-8"),
    }, report


def safe_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".frg08c_" + uuid.uuid4().hex[:8] + ".tmp")
    try:
        temp.write_bytes(content)
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def install(root: Path, payload: dict[str, bytes], dry_run: bool) -> Path | None:
    changed = {}
    for rel, new in payload.items():
        target = root / rel
        old = target.read_bytes() if target.exists() else None
        if old != new:
            changed[rel] = (old, new)
    if not changed:
        print("Already installed: no files need changing.")
        return None
    print("Files to update:")
    for rel in changed:
        print("  ", rel)
    if dry_run:
        print("Dry-run complete. No files were written.")
        return None
    backup = (root.parent / f"{root.name}_backups" /
              ("graphics_08c_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]))
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "root": str(root.resolve()), "files": {}}
    for rel, (old, new) in changed.items():
        if old is not None:
            original = backup / "originals" / rel
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(old)
        manifest["files"][rel] = {"old": sha(old) if old is not None else None, "new": sha(new)}
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    done = []
    try:
        for rel, (old, new) in changed.items():
            safe_write(root / rel, new)
            done.append(rel)
    except Exception:
        for rel in reversed(done):
            old = changed[rel][0]
            target = root / rel
            if old is None:
                target.unlink(missing_ok=True)
            else:
                safe_write(target, old)
        raise
    print("Backup:", backup)
    return backup


def restore(root: Path, folder_arg: str) -> None:
    folder = Path(folder_arg).expanduser().resolve()
    manifest_path = folder / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("Backup folder has no manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not str(manifest.get("version", "")).startswith("08c.") or Path(manifest.get("root", "")).resolve() != root.resolve():
        raise RuntimeError("This backup is not for Update 08c and this Godot project")
    files = manifest["files"]
    # Verify every target before making ANY modifications.
    for rel, info in files.items():
        name = Path(rel)
        if name.is_absolute() or ".." in name.parts:
            raise RuntimeError(f"Unsafe backup path: {rel}")
        dest = root / name
        if not dest.is_file() or sha(dest.read_bytes()) != info["new"]:
            raise RuntimeError(f"File changed after Update 08c; refusing to overwrite: {rel}")
        if info["old"] is not None:
            copy = folder / "originals" / name
            if not copy.is_file() or sha(copy.read_bytes()) != info["old"]:
                raise RuntimeError(f"Corrupt backup copy: {rel}")
    for rel, info in files.items():
        dest = root / rel
        if info["old"] is None:
            dest.unlink()
        else:
            safe_write(dest, (folder / "originals" / rel).read_bytes())
    print("Restored original files from", folder)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fight Royale Update 08c — sharper graphics, no renderer change")
    parser.add_argument("--preset", choices=list(PRESETS), default="sharp", help="Default: sharp; balanced for faster FPS, ultra for higher quality")
    parser.add_argument("--resolution", help="Optional custom window size, e.g. 1600x900")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", metavar="FULL_BACKUP_FOLDER_PATH")
    args = parser.parse_args()
    root = Path.cwd().resolve()
    print("Fight Royale Godot — Graphics Clarity 08c |", root)
    try:
        if args.restore:
            restore(root, args.restore)
            return 0
        payload, report = build(root, args.preset, args.resolution)
        print(f"Graphics preset: {report['preset']} — window {report['window_pixels'][0]}x{report['window_pixels'][1]}")
        print(f"3D scale {report['3d_supersample_scale']}x, GL Compatibility preserved")
        install(root, payload, args.dry_run)
        print("Done. Close any running game, reopen Godot or run the project to see the changes.")
        print("If FPS drops, run: python install_08c_graphics_clarity.py --preset balanced")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
