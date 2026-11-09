#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot - Update 05: automatic weapon attachments.

From the Godot project directory:
    python install_05_weapon_attachments.py

Optional:
    python install_05_weapon_attachments.py --dry-run
    python install_05_weapon_attachments.py --check-godot
    python install_05_weapon_attachments.py --restore "PATH_FROM_BACKUP_MESSAGE"

Requires Update 04 (FighterRig). Uses procedural weapons already present in
fighter_model.gd. Adds per-kit/per-character/per-model corrections without editing
VRM bones or requiring scene-editor work. Does not touch SFX or unrelated files.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

VERSION = "05.0"
MODEL_REL = "scripts/fighter_model.gd"
MOUNT_REL = "scripts/weapon_mount.gd"
PROFILE_REL = "data/weapon_profiles.json"
AUDIT_REL = "reports/weapon_audit_05.txt"
CHECK_REL = "tools/check_weapon_mounts_05.gd"

KITS = ("knight", "greatsword", "katana", "mage", "bow", "assassin", "knuckles", "kicks")

# 0 offsets are deliberate: the original Godot geometry already assumes a +Y
# weapon axis. The VRM-local grip basis comes from Update 04. Non-zero values
# should only be chosen after in-engine visualization of a particular fighter.
def default_adjust():
    return {"position": [0.0, 0.0, 0.0], "rotation_deg": [0.0, 0.0, 0.0], "scale": 1.0}


def default_kit():
    return {"right": default_adjust(), "left": default_adjust(), "shield": default_adjust()}


MOUNT_GD = r'''# Fight Royale Godot - Update 05 | automatic procedural weapon mounts.
class_name WeaponMount
extends RefCounted

## All positions are meters in bone-grip local coordinates. Rotations are XYZ
## Euler degrees in that same local space; scale changes all built geometry
## including trail and projectile pivots, keeping the gameplay anchors aligned.
## Missing or invalid entries always use neutral/default transformations.
const SETTINGS := "res://data/weapon_profiles.json"

static func _vec3(raw: Variant, fallback: Vector3 = Vector3.ZERO) -> Vector3:
    if not (raw is Array) or raw.size() != 3:
        return fallback
    for value in raw:
        if not (value is int or value is float):
            return fallback
        if is_nan(float(value)) or is_inf(float(value)):
            return fallback
    return Vector3(float(raw[0]), float(raw[1]), float(raw[2]))

static func _apply(target: Node3D, correction: Dictionary) -> Node3D:
    if target == null:
        return target
    var pos: Vector3 = _vec3(correction.get("position", []))
    var degrees: Vector3 = _vec3(correction.get("rotation_deg", []))
    var amount: float = float(correction.get("scale", 1.0))
    if is_nan(amount) or is_inf(amount) or amount < 0.1 or amount > 5.0:
        amount = 1.0
    var local_offset := Transform3D(Basis.from_euler(Vector3(deg_to_rad(degrees.x), deg_to_rad(degrees.y), deg_to_rad(degrees.z))), pos)
    target.transform = target.transform * local_offset
    target.scale = target.scale * (Vector3.ONE * amount)
    return target

static func _merge_settings(dst: Dictionary, entry: Variant) -> void:
    if not (entry is Dictionary):
        return
    for key in ["right", "left", "shield"]:
        var item: Variant = entry.get(key, {})
        if not (item is Dictionary):
            continue
        var data: Dictionary = dst.get(key, {}).duplicate(true)
        for field in ["position", "rotation_deg", "scale"]:
            if item.has(field):
                data[field] = item[field]
        dst[key] = data

static func profile_for(look: Dictionary, resolved_model_id: String) -> Dictionary:
    var neutral := {"position": [0.0, 0.0, 0.0], "rotation_deg": [0.0, 0.0, 0.0], "scale": 1.0}
    var result := {"right": neutral.duplicate(true), "left": neutral.duplicate(true), "shield": neutral.duplicate(true)}
    if not FileAccess.file_exists(SETTINGS):
        return result
    var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(SETTINGS))
    if not (parsed is Dictionary):
        return result
    var kit_key: String = str(look.get("kit", "")).to_lower()
    var model_key: String = resolved_model_id.to_lower()
    var id_key: String = str(look.get("name", "")).to_lower()
    var kits: Variant = parsed.get("kits", {})
    var models: Variant = parsed.get("models", {})
    var fighters: Variant = parsed.get("fighters", {})
    if kits is Dictionary:
        _merge_settings(result, kits.get(kit_key, {}))
    if models is Dictionary:
        _merge_settings(result, models.get(model_key, {}))
    if fighters is Dictionary:
        _merge_settings(result, fighters.get(id_key, {}))
    return result

static func configure_grip(grip: Node3D, profile: Dictionary, side: String) -> Node3D:
    if grip == null:
        return grip
    var key: String = side.to_lower()
    var entry: Variant = profile.get(key, {})
    if entry is Dictionary:
        _apply(grip, entry)
    return grip

## Mount a shield on the left FOREARM, not on the hand's wrist rotation.
## Copy the hand-grip's REST position into forearm coordinates, preserving the
## shield's position when standing still. If there's no usable forearm, keep
## the original hand-grip mount instead of attaching to a missing bone.
static func forearm_shield_mount(sk: Skeleton3D, rig: Dictionary, left_grip: Node3D) -> Node3D:
    if sk == null or left_grip == null:
        return left_grip
    var forearm_name: String = FighterRig.name_for(sk, "LeftLowerArm", rig)
    var hand_name: String = FighterRig.name_for(sk, "LeftHand", rig)
    var forearm_index: int = sk.find_bone(forearm_name)
    var hand_index: int = sk.find_bone(hand_name)
    if forearm_index < 0 or hand_index < 0:
        push_warning("Fight Royale: no forearm mount; shield will follow hand")
        return left_grip
    var forearm_rest: Transform3D = sk.get_bone_global_rest(forearm_index)
    var hand_rest: Transform3D = sk.get_bone_global_rest(hand_index)
    if absf(forearm_rest.basis.determinant()) < 0.00001:
        return left_grip
    var attachment := BoneAttachment3D.new()
    attachment.name = "LeftShieldForearmAttachment05"
    attachment.bone_name = forearm_name
    sk.add_child(attachment)
    var local_mount := Node3D.new()
    local_mount.name = "ShieldMount05"
    attachment.add_child(local_mount)
    local_mount.transform = forearm_rest.affine_inverse() * hand_rest * left_grip.transform
    return local_mount

static func configure_shield(pivot: Node3D, profile: Dictionary) -> void:
    var entry: Variant = profile.get("shield", {})
    if pivot != null and entry is Dictionary:
        _apply(pivot, entry)
'''

# Use simple static source patching with explicit anchors and version marker;
# refusing incompatible projects is safer than editing an unknown version.

def patch_model(original: str) -> str:
    marker = "# FRG05 - automatic weapon profile mounts"
    if marker in original:
        for needle in ("WeaponMount.profile_for", "WeaponMount.configure_grip", "WeaponMount.forearm_shield_mount", "WeaponMount.configure_shield"):
            if needle not in original:
                raise RuntimeError("Update 05 marker exists but method missing: " + needle)
        return original
    if "FighterRig.make_grip" not in original or "FighterRig.profile_for" not in original:
        raise RuntimeError("Update 04 must be installed first: FighterRig integration not found")

    def rep(s: str, needle: str, replacement: str, reason: str) -> str:
        count = s.count(needle)
        if count != 1:
            raise RuntimeError("Cannot safely locate " + reason + " in fighter_model.gd (found " + str(count) + ")")
        return s.replace(needle, replacement, 1)

    s = original
    s = rep(s, "var rig_profile: Dictionary = {} # FRG04 - rig mapper integrated\n",
            "var rig_profile: Dictionary = {} # FRG04 - rig mapper integrated\n"
            "var loaded_model_id := \"\" # FRG05 - automatic weapon profile mounts\n",
            "Update 04 rig declaration")
    s = rep(s, "\trig_profile = FighterRig.profile_for(id)\n",
            "\trig_profile = FighterRig.profile_for(id)\n"
            "\tloaded_model_id = id\n", "profile initialization")
    s = rep(s, "\tvar r := _grip(\"Right\")\n\tvar l := _grip(\"Left\")\n",
            "\tvar mount_profile: Dictionary = WeaponMount.profile_for(look, loaded_model_id)\n"
            "\tvar r: Node3D = WeaponMount.configure_grip(_grip(\"Right\"), mount_profile, \"right\")\n"
            "\tvar l: Node3D = WeaponMount.configure_grip(_grip(\"Left\"), mount_profile, \"left\")\n",
            "weapon grip initialization")
    s = rep(s, "\t\t\tshield_node = _pivot(l, Vector3(0, 0, -0.06))\n",
            "\t\t\tvar forearm_mount: Node3D = WeaponMount.forearm_shield_mount(skeleton, rig_profile, l)\n"
            "\t\t\tshield_node = _pivot(forearm_mount, Vector3(0, 0, -0.06))\n"
            "\t\t\tWeaponMount.configure_shield(shield_node, mount_profile)\n",
            "knight shield")
    return s


CHECK_GD = r'''extends SceneTree
## Optional runtime sanity check with --check-godot. Does not require user input.
func _init() -> void:
    call_deferred("_verify")

func _verify() -> void:
    var roster: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/roster.json"))
    if not (roster is Array):
        printerr("MOUNT05 ERROR: missing roster")
        quit(2)
        return
    var failures: int = 0
    var checked: int = 0
    for fighter in roster:
        if not (fighter is Dictionary):
            continue
        var look: Dictionary = fighter.get("look", {})
        var id: String = str(fighter.get("id", "unknown"))
        var requested: String = str(look.get("vrm", ""))
        var model_id: String = requested
        if not ResourceLoader.exists("res://models/%s.vrm" % model_id):
            model_id = "rook" if str(look.get("body", "f")) == "m" else "ember"
        if not ResourceLoader.exists("res://models/%s.vrm" % model_id):
            print("MOUNT05 SKIP ", id, ": missing model and fallback")
            continue
        var body := FighterModel.new()
        root.add_child(body)
        body.setup(look)
        var valid: bool = body.skeleton != null and body.blade_base != null and body.blade_tip != null and body.shield_node != null
        if valid:
            valid = body.blade_base.global_transform.origin.is_finite() and body.blade_tip.global_transform.origin.is_finite()
        if valid:
            checked += 1
            print("MOUNT05 OK ", id, " kit=", str(look.get("kit", "")), " rig=", body.loaded_model_id)
        else:
            failures += 1
            printerr("MOUNT05 FAIL ", id, " missing weapon or skeleton anchor")
        body.free()
    print("MOUNT05 result: checked=", checked, " failed=", failures)
    quit(0 if failures == 0 and checked > 0 else 2)
'''


def json_bytes(value) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def root_dir(value: str | None) -> Path:
    root = (Path(value).expanduser() if value else Path.cwd()).resolve()
    requirements = ["project.godot", MODEL_REL, "scripts/rig_mapper.gd", "data/roster.json"]
    missing = [r for r in requirements if not (root / r).is_file()]
    if missing:
        raise RuntimeError("Run from your Godot folder after Update 04; missing: " + ", ".join(missing))
    return root


def _safe_dict(x) -> dict:
    return x if isinstance(x, dict) else {}


def build_profile(root: Path) -> tuple[dict, int]:
    roster = json.loads((root / "data/roster.json").read_text(encoding="utf-8-sig"))
    if not isinstance(roster, list):
        raise RuntimeError("data/roster.json should contain a JSON list")
    path = root / PROFILE_REL
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise RuntimeError("Existing weapon_profiles.json is not a JSON object; refusing overwrite")
        if data.get("schema") != 1:
            raise RuntimeError("Unrecognized weapon_profiles.json schema; refusing overwrite")
    else:
        data = {"schema": 1, "update": VERSION, "notes": (
            "Transform corrections are local to the rig's grip. +Y is the weapon/blade axis. "
            "Adjust per fighter later using numeric values; no skeleton editing required."),
            "kits": {}, "models": {}, "fighters": {}}
    kits, models, fighters = (_safe_dict(data.get(k)) for k in ("kits", "models", "fighters"))
    for kit in KITS:
        kits.setdefault(kit, default_kit())
    for file in sorted((root / "models").glob("*.vrm")) if (root / "models").exists() else []:
        models.setdefault(file.stem.lower(), {})
    for entry in roster:
        if not isinstance(entry, dict):
            continue
        look = _safe_dict(entry.get("look"))
        name = str(look.get("name") or entry.get("id") or "").lower()
        if name:
            fighters.setdefault(name, {})
    data["kits"], data["models"], data["fighters"] = kits, models, fighters
    return data, len(roster)


def build_changes(root: Path) -> tuple[dict[str, bytes], dict]:
    profile, n = build_profile(root)
    model = (root / MODEL_REL).read_text(encoding="utf-8-sig")
    new_model = patch_model(model)
    kits_used = {}
    for fighter in json.loads((root / "data/roster.json").read_text(encoding="utf-8-sig")):
        kit = str(_safe_dict(fighter.get("look")).get("kit", ""))
        kits_used[kit] = kits_used.get(kit, 0) + 1
    unmapped = [kit for kit in kits_used if kit not in KITS]
    report = ["FIGHT ROYALE - WEAPON ATTACHMENTS UPDATE 05", "",
              "Fighters in roster: " + str(n),
              "VRM models in models/: " + str(len(profile.get("models", {}))),
              "Kit types: " + ", ".join("%s=%d" % kv for kv in sorted(kits_used.items())),
              "Unknown kit types: " + (", ".join(unmapped) if unmapped else "none"),
              "", "INSTALLED BEHAVIOR",
              "- Keep original procedural weapons; align them to Update 04 humanoid grips.",
              "- Accept per-kit, per-model and per-fighter offsets in data/weapon_profiles.json.",
              "- Move knight shield attachment from the wrist to the left forearm.",
              "- Keep blade_base, blade_tip, cast_point and shield_node anchors intact.",
              "- Fallback to hand attachment when a forearm bone is unavailable.",
              "- No VRM bytes, model rigs, animation clips, or sound files changed.",
              "", "NOTES",
              "- Default offsets are neutral until actual gameplay screenshots can guide tuning.",
              "- A static scan cannot prove in-game weapon alignment; use --check-godot when available.",
              "- User changes to existing profile values are retained on reinstallation.",
              "- New fighter models or roster additions can be discovered by rerunning the installer."]
    changes = {MODEL_REL: new_model.encode("utf-8"), MOUNT_REL: MOUNT_GD.encode("utf-8"),
               PROFILE_REL: json_bytes(profile), CHECK_REL: CHECK_GD.encode("utf-8"),
               AUDIT_REL: ("\n".join(report) + "\n").encode("utf-8")}
    return changes, {"fighters": n, "models": len(profile.get("models", {})), "kits": kits_used}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp." + uuid.uuid4().hex[:8])
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def install(root: Path, changes: dict[str, bytes], dry_run: bool) -> Path | None:
    modified = {name: contents for name, contents in changes.items()
                if not (root / name).is_file() or (root / name).read_bytes() != contents}
    for name in changes:
        print("  %s  %s" % ("UPDATE   " if name in modified else "unchanged", name))
    print("Files to change:", len(modified))
    if dry_run:
        print("Dry run only: no changes written.")
        return None
    if not modified:
        print("Already installed; no files changed.")
        return None
    backup = (root.parent / (root.name + "_backups") /
              ("weapons_05_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]))
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": []}
    for rel, content in modified.items():
        path = root / rel
        exists = path.is_file()
        before = path.read_bytes() if exists else None
        if before is not None:
            original = backup / "originals" / rel
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(before)
        manifest["files"].append({"path": rel, "existed": exists,
                                   "before": sha(before) if exists else None,
                                   "after": sha(content)})
    (backup / "manifest.json").write_bytes(json_bytes(manifest))
    written = []
    try:
        for rel, contents in modified.items():
            safe_write(root / rel, contents)
            written.append(rel)
    except Exception:
        for rel in reversed(written):
            old = backup / "originals" / rel
            if old.is_file():
                safe_write(root / rel, old.read_bytes())
            elif (root / rel).exists():
                (root / rel).unlink()
        raise
    print("Backup created:", backup)
    return backup


def restore(root: Path, folder: str) -> None:
    backup = Path(folder).expanduser().resolve()
    meta = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if meta.get("version") != VERSION or Path(meta.get("project", "")).resolve() != root:
        raise RuntimeError("Backup doesn't match Update 05 for this project")
    records = meta.get("files", [])
    for item in records:
        path = Path(item["path"])
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeError("Unsafe backup path: " + str(path))
        if item["existed"]:
            prior = (backup / "originals" / path).read_bytes()
            if sha(prior) != item["before"]:
                raise RuntimeError("Backup checksum mismatch: " + str(path))
    # Do not undo subsequent user edits without being explicit.
    for item in records:
        dest = root / item["path"]
        if dest.is_file() and sha(dest.read_bytes()) != item["after"]:
            raise RuntimeError("File modified since installation; refusing automatic restore: " + str(dest))
    for item in records:
        dest = root / item["path"]
        if item["existed"]:
            safe_write(dest, (backup / "originals" / item["path"]).read_bytes())
        elif dest.exists():
            dest.unlink()
        print("  RESTORED", item["path"])
    print("Restoration complete")


def godot_check(root: Path, selected: str | None) -> int:
    exe = shutil.which(selected) if selected else None
    if not exe and selected and Path(selected).is_file():
        exe = str(Path(selected).resolve())
    if not exe:
        exe = next((p for name in ("godot", "godot4", "godot.exe", "Godot_v4.4-stable_win64_console.exe")
                    if (p := shutil.which(name))), None)
    if not exe:
        print("Godot not on PATH; open the project normally or provide --godot PATH_TO_EXE")
        return 0
    print("Checking Godot import...", exe)
    try:
        first = subprocess.run([exe, "--headless", "--path", str(root), "--editor", "--quit"],
                               text=True, capture_output=True, timeout=180)
        print((first.stdout + first.stderr)[-5000:])
        if first.returncode:
            return 2
        verify = subprocess.run([exe, "--headless", "--path", str(root),
                                 "--script", "res://tools/check_weapon_mounts_05.gd"],
                                text=True, capture_output=True, timeout=120)
        print((verify.stdout + verify.stderr)[-8000:])
        return 0 if verify.returncode == 0 else 2
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("Godot validation error:", exc)
        return 2


def main(argv=None) -> int:
    cli = argparse.ArgumentParser(description="Fight Royale Godot | Update 05 automatic weapon attachments")
    cli.add_argument("--project", help="Godot project directory, defaults to current directory")
    cli.add_argument("--dry-run", action="store_true")
    cli.add_argument("--restore", metavar="BACKUP_FOLDER")
    cli.add_argument("--check-godot", action="store_true")
    cli.add_argument("--godot", metavar="GODOT_EXE")
    args = cli.parse_args(argv)
    root = root_dir(args.project)
    print("FIGHT ROYALE GODOT - UPDATE 05 | WEAPON ATTACHMENTS\nProject:", root)
    if args.restore:
        restore(root, args.restore)
        return 0
    changes, data = build_changes(root)
    print("Fighters:", data["fighters"], "Models:", data["models"])
    install(root, changes, args.dry_run)
    if not args.dry_run:
        print("Report:", AUDIT_REL)
        print("DONE: Procedural weapon mounts and per-character profiles added; your VRMs are untouched.")
    if args.check_godot and not args.dry_run:
        return godot_check(root, args.godot)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, UnicodeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(1)
