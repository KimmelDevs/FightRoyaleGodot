#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot — Update 08: Defense + visible-fighter recovery.

Run from the project directory:
    python install_08_defense.py

Options:
    python install_08_defense.py --dry-run
    python install_08_defense.py --check-godot
    python install_08_defense.py --restore <backup-folder>

Requires Update 07. Uses standard Python only; never rewrites VRMs or SFX.
If Godot cannot load a VRM, fighters now display a colored procedural placeholder
instead of disappearing/crashing; an audit gives import troubleshooting steps.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

VERSION = "08.0"
MARKER_MODEL = "# FRG08 - safe VRM loading and visible avatar fallback"
MARKER_FIGHTER = "# FRG08 - defense and guard fatigue"
MARKER_MATCH = "# FRG08 - defense integration and visible fighter checks"
MARKER_MAIN = "# FRG08 - character preview camera"
FILES = ("scripts/fighter_model.gd", "scripts/fighter.gd", "scripts/match.gd", "scripts/hud.gd", "scripts/main.gd")


def replace_once(src: str, old: str, new: str, reason: str) -> str:
    count = src.count(old)
    if count != 1:
        raise RuntimeError(f"{reason}: expected one source anchor, found {count}. "
                           "No source file was changed. Send your current scripts for a tailored patch.")
    return src.replace(old, new, 1)


MODEL_SETUP = r'''func setup(look_data: Dictionary) -> void:
	look = look_data
	kit = str(look.get("kit", "knight"))
	fallback_used = false
	fallback_reason = ""
	# Missing/unimported VRMs must never make the entire fighter invisible.
	var requested: String = str(look.get("vrm", ""))
	var candidate_ids: Array[String] = []
	if not requested.is_empty():
		candidate_ids.append(requested)
	var standin: String = str(FALLBACK.get(look.get("body", "f"), "ember"))
	if not candidate_ids.has(standin):
		candidate_ids.append(standin)
	for candidate in candidate_ids:
		var resource_path := "res://models/%s.vrm" % candidate
		if not ResourceLoader.exists(resource_path):
			continue
		var resource: Resource = ResourceLoader.load(resource_path)
		if not (resource is PackedScene):
			continue
		var instance: Node = (resource as PackedScene).instantiate()
		if not (instance is Node3D):
			instance.queue_free()
			continue
		vrm = instance as Node3D
		add_child(vrm)
		skeleton = FighterRig.find_skeleton(vrm)
		if skeleton != null and vrm.find_children("*", "MeshInstance3D", true, false).size() > 0:
			loaded_model_id = candidate
			break
		skeleton = null
		vrm.queue_free()
		vrm = null
	if skeleton == null:
		fallback_used = true
		fallback_reason = "No importable VRM with a Skeleton3D for " + str(look.get("name", "fighter"))
		push_warning("Fight Royale Update 08: " + fallback_reason + ". Using visible placeholder; check Godot's Import / Errors tabs.")
		_build_fallback_avatar()
		return
	rig_profile = FighterRig.profile_for(loaded_model_id)
	player = AnimationPlayer.new()
	player.name = "Poses"
	vrm.add_child(player)
	player.root_node = NodePath("..")
	var animation_resource: Resource = ResourceLoader.load("res://animations/%s.tres" % kit)
	if animation_resource is AnimationLibrary:
		player.add_animation_library("", animation_resource as AnimationLibrary)
	else:
		push_warning("Fight Royale: animation library for " + kit + " unavailable; model stays visible")
	motion = MotionLayer.new()
	motion.heavy = look.get("body", "f") == "m"
	motion.bone_map = FighterRig.runtime_bone_map(skeleton, rig_profile)
	skeleton.add_child(motion)
	for m in vrm.find_children("*", "MeshInstance3D", true, false):
		_meshes.append(m)
	_flash_mat = StandardMaterial3D.new()
	_flash_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_flash_mat.albedo_color = Color(1, 1, 1, 0.85)
	_flash_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_build_weapons()
	play_pose("idle", 10)

func _fallback_piece(parent: Node3D, dimensions: Vector3, center: Vector3, color: Color) -> MeshInstance3D:
	var mesh := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = dimensions
	mesh.mesh = box
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.8
	mesh.material_override = material
	mesh.position = center
	parent.add_child(mesh)
	_meshes.append(mesh)
	return mesh

func _build_fallback_avatar() -> void:
	# Intentionally simple, but always drawn even if .vrm import is broken.
	vrm = Node3D.new()
	vrm.name = "VisibleFallback08"
	add_child(vrm)
	var armor := Color(str(look.get("tunic", "#5579bb")))
	var limbs := Color(str(look.get("metal", "#c5d3e7")))
	var skin := Color("#e8c4a1")
	_fallback_piece(vrm, Vector3(0.56, 0.78, 0.33), Vector3(0, 1.12, 0), armor)
	_fallback_piece(vrm, Vector3(0.34, 0.35, 0.33), Vector3(0, 1.73, 0), skin)
	_fallback_piece(vrm, Vector3(0.22, 0.71, 0.24), Vector3(-0.41, 1.14, 0), limbs)
	_fallback_piece(vrm, Vector3(0.22, 0.71, 0.24), Vector3(0.41, 1.14, 0), limbs)
	_fallback_piece(vrm, Vector3(0.23, 0.75, 0.26), Vector3(-0.16, 0.39, 0), armor.darkened(0.25))
	_fallback_piece(vrm, Vector3(0.23, 0.75, 0.26), Vector3(0.16, 0.39, 0), armor.darkened(0.25))
	# Keep blade/trail and projectile anchors safe even without humanoid bones.
	var sword := Node3D.new()
	sword.position = Vector3(0.52, 1.02, 0)
	vrm.add_child(sword)
	_fallback_piece(sword, Vector3(0.07, 0.66, 0.07), Vector3(0, 0.37, 0), Color("#e2ecff"))
	blade_base = Node3D.new()
	blade_base.position = Vector3(0, 0.06, 0)
	sword.add_child(blade_base)
	blade_tip = Node3D.new()
	blade_tip.position = Vector3(0, 0.7, 0)
	sword.add_child(blade_tip)
	cast_point = blade_tip
	shield_node = Node3D.new()
	shield_node.position = Vector3(-0.48, 1.2, 0)
	vrm.add_child(shield_node)
	var warning := Label3D.new()
	warning.text = "VRM IMPORT NEEDED"
	warning.position = Vector3(0, 2.16, 0)
	warning.modulate = Color("#ffe08a")
	warning.pixel_size = 0.004
	warning.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	vrm.add_child(warning)

'''


def patch_model(src: str) -> str:
    if MARKER_MODEL in src:
        if all(k in src for k in ("func _build_fallback_avatar()", "fallback_used", "func _fallback_piece(")):
            return src
        raise RuntimeError("Update 08 partial model patch detected")
    if "FighterRig.find_skeleton" not in src or "WeaponMount.profile_for" not in src:
        raise RuntimeError("Updates 04 and 05 required for fighter_model.gd")
    src = replace_once(src, "var loaded_model_id := \"\" # FRG05 - automatic weapon profile mounts",
        'var loaded_model_id := "" # FRG05 - automatic weapon profile mounts\n' + MARKER_MODEL +
        '\nvar fallback_used := false\nvar fallback_reason := ""', "model fallback state")
    before = src.index("func setup(look_data: Dictionary) -> void:")
    after = src.index("## Blend to a pose;", before)
    src = src[:before] + MODEL_SETUP + src[after:]
    src = replace_once(src,
        "\tif pose_name == _pose or not player.has_animation(pose_name):\n\t\treturn",
        "\tif player == null or pose_name == _pose or not player.has_animation(pose_name):\n\t\treturn",
        "fallback-safe pose player")
    return src


def patch_fighter(src: str) -> str:
    if MARKER_FIGHTER in src:
        if all(x in src for x in ("guard_fatigue", "add_guard_fatigue", "attack_time_multiplier")):
            return src
        raise RuntimeError("Partial Update 08 defense changes in fighter.gd")
    if "func active_melee()" not in src or "KNOCK_DAMPING" not in src:
        raise RuntimeError("Install Update 07 before Update 08")
    src = replace_once(src, "const GUARD_REGEN := 30.0", "const GUARD_REGEN := 30.0\n" + MARKER_FIGHTER +
        "\nconst FATIGUE_CAP := 10\nconst FATIGUE_DECAY_SECONDS := 3.0", "guard fatigue constants")
    src = replace_once(src, "var guard := 100.0", "var guard := 100.0\nvar guard_fatigue := 0\nvar _fatigue_decay := 3.0", "guard fatigue state")
    src = replace_once(src, "\thp = max_hp; guard = max_guard", "\thp = max_hp; guard = max_guard\n\tguard_fatigue = 0; _fatigue_decay = FATIGUE_DECAY_SECONDS", "guard fatigue round reset")
    src = replace_once(src,
        "\tstate_t += dt\n\t_clock += dt",
        "\tstate_t += dt\n\t_clock += dt\n"
        "\tif guard_fatigue > 0 and dt > 0.0:\n"
        "\t\t_fatigue_decay -= dt\n"
        "\t\tif _fatigue_decay <= 0.0:\n"
        "\t\t\tguard_fatigue -= 1\n"
        "\t\t\t_fatigue_decay = FATIGUE_DECAY_SECONDS\n",
        "fatigue decay")
    src = replace_once(src, "## True throughout the *entire* damaging window, not just on the first active frame.",
        '''func add_guard_fatigue() -> void:
	guard_fatigue = mini(guard_fatigue + 1, FATIGUE_CAP)
	_fatigue_decay = FATIGUE_DECAY_SECONDS

func attack_time_multiplier() -> float:
	# Each stack makes attack/skill execution 2% slower; maximum 10 stacks.
	return 1.0 / maxf(1.0 - 0.02 * float(guard_fatigue), 0.5)

## True throughout the *entire* damaging window, not just on the first active frame.''',
        "fatigue methods")
    src = replace_once(src,
        'and atk_phase == 1 and state_t <= float(atk.wind) + float(atk.active) + 0.0001',
        'and atk_phase == 1 and state_t <= (float(atk.wind) + float(atk.active)) * attack_time_multiplier() + 0.0001',
        "active melee fatigue timing")
    src = replace_once(src,
        'return atk_phase == 1 or (atk_phase == 0 and state_t > atk.wind * 0.6) or (atk_phase == 2 and state_t < atk.wind + atk.active + 0.05)',
        'return atk_phase == 1 or (atk_phase == 0 and state_t > float(atk.wind) * attack_time_multiplier() * 0.6) or (atk_phase == 2 and state_t < (float(atk.wind) + float(atk.active)) * attack_time_multiplier() + 0.05)',
        "trail fatigue timing")
    src = replace_once(src, 'var w: float = atk.wind\n\tvar ac: float = atk.active\n\tvar r: float = atk.recover',
        'var w: float = float(atk.wind) * attack_time_multiplier()\n\tvar ac: float = float(atk.active) * attack_time_multiplier()\n\tvar r: float = float(atk.recover) * attack_time_multiplier()',
        'windup/active/recovery fatigue timing')
    src = replace_once(src,
        'guard = minf(guard + 20.0, max_guard)',
        'guard = minf(guard + max_guard * 0.10, max_guard)',
        "parry guard recovery (10%)")
    return src


def patch_match(src: str) -> str:
    if MARKER_MATCH in src:
        if all(s in src for s in ("f.model.fallback_used", "attacker.add_guard_fatigue()", "camera.make_current()")):
            return src
        raise RuntimeError("Partial Update 08 match patch detected")
    if "_active_melee_contact" not in src or "_melee_hits" not in src:
        raise RuntimeError("Install Update 07 first; match.gd is not compatible")
    src = replace_once(src, 'class_name Match\nextends Node3D',
        'class_name Match\nextends Node3D\n' + MARKER_MATCH, "match marker")
    src = replace_once(src, '\tadd_child(camera)\n\tcamera.position = Vector3(0, 6, 10)',
        '\tadd_child(camera)\n\tcamera.make_current()\n\tcamera.position = Vector3(0, 6, 10)',
        "make match camera active")
    src = replace_once(src,
        '\tf.setup(int(slot.char), slot.get("loadout", ["z", "x", "c"]), slot.get("emblem", {}))',
        '\tf.setup(int(slot.char), slot.get("loadout", ["z", "x", "c"]), slot.get("emblem", {}))\n'
        '\tif f.model != null and f.model.fallback_used:\n'
        '\t\tpush_warning("Fight Royale: " + f.look.name + " uses a visible fallback. Open the VRM import errors in Godot.")',
        "report runtime placeholder")
    src = replace_once(src,
        '\t\t"blocked":\n\t\t\tfx.sparks(',
        '\t\t"blocked":\n\t\t\tif attacker is Fighter: attacker.add_guard_fatigue()\n\t\t\tfx.sparks(',
        "fatigue blocked")
    src = replace_once(src,
        '\t\t"parry":\n\t\t\tif not ranged and attacker is Fighter: attacker.stagger(0.95)',
        '\t\t"parry":\n\t\t\tif attacker is Fighter: attacker.add_guard_fatigue()\n'
        '\t\t\t# Parry delays attacks with hit-stop, not a full stun.',
        "fatigue parry and nonstun")
    src = replace_once(src,
        '"down": f.is_down(), "glow": f.look.glow}',
        '"down": f.is_down(), "glow": f.look.glow, "fatigue": f.guard_fatigue}',
        "fatigue HUD feed")
    return src


def patch_hud(src: str) -> str:
    marker = "# FRG08 - defense HUD fatigue counter"
    if marker in src:
        return src
    src = replace_once(src,
        '\t(box.get_node("Name") as Label).text = "%s  %d / %d" % [info.name, int(ceil(info.hp)), int(info.max_hp)]',
        '\t# FRG08 - defense HUD fatigue counter\n'
        '\tvar penalty := int(info.get("fatigue", 0))\n'
        '\tvar suffix := "  FATIGUE %d/10" % penalty if penalty > 0 else ""\n'
        '\t(box.get_node("Name") as Label).text = "%s  %d / %d%s" % [info.name, int(ceil(info.hp)), int(info.max_hp), suffix]',
        "HUD fatigue display")
    return src


def patch_main(src: str) -> str:
    if MARKER_MAIN in src:
        if "camera.make_current()" in src and "viewport.render_target_update_mode" in src:
            return src
        raise RuntimeError("Partial preview camera repair detected")
    src = replace_once(src,
        '\tviewport.transparent_bg = true\n\tbox.add_child(viewport)',
        '\tviewport.transparent_bg = true\n\tviewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS\n\tbox.add_child(viewport)',
        "ensure preview rendered")
    src = replace_once(src,
        '\tviewport.add_child(camera)\n\tvar light := DirectionalLight3D.new()',
        '\tviewport.add_child(camera)\n\t' + MARKER_MAIN +
        '\n\tcamera.make_current()\n\tcamera.look_at(Vector3(0, 1.0, 0), Vector3.UP)\n'
        '\tvar light := DirectionalLight3D.new()',
        "preview camera setup")
    return src


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resolve_root(selected: str | None) -> Path:
    root = Path(selected).expanduser().resolve() if selected else Path.cwd().resolve()
    if not (root / 'project.godot').is_file():
        raise RuntimeError(f"No project.godot in {root}. Run from your Godot project folder.")
    for name in FILES:
        if not (root / name).is_file():
            raise RuntimeError(f"Missing {name}; use the project with Updates 01–07 already installed.")
    return root


def build_report(root: Path) -> str:
    roster = json.loads((root / 'data/roster.json').read_text(encoding='utf-8'))
    models = root / 'models'
    found = {p.stem.casefold(): p for p in models.rglob('*.vrm')} if models.exists() else {}
    lines = ["FIGHT ROYALE GODOT - MODEL VISIBILITY CHECK / UPDATE 08", "",
             "This is a static file audit, NOT proof Godot successfully imported a VRM.",
             "The old model loader could stop character creation if the resource was unavailable.",
             "Update 08 replaces invisible / failed characters with visible temporary figures.", "",
             f"Project: {root}", f"Found VRM files: {len(found)}", f"Roster entries: {len(roster)}", ""]
    for c in roster:
        if not isinstance(c, dict):
            continue
        look = c.get('look', {})
        requested = str(look.get('vrm', ''))
        fid = c.get('id', '?')
        exists = requested.lower() in found
        lines.append(f"{fid}: {'VRM PRESENT' if exists else 'NO DEDICATED VRM / fallback expected'} ({requested or 'unspecified'})")
    lines.extend(["", "WHEN CHARACTERS DO NOT APPEAR:",
                  "1. Open the project in the Godot EDITOR (not just the exported game).",
                  "2. Allow .vrm assets to import; check the Import and Errors tabs.",
                  "3. Confirm addons/vrm/plugin.cfg and addons/Godot-MToon-Shader/plugin.cfg are enabled.",
                  "4. Start Duel vs CPU and choose fighters; placeholder humanoids will appear if VRMs cannot load.",
                  "5. For errors, copy the first red Godot error and send it for a precise fix.",
                  "6. If models are placed in subfolders of models/, their names will be listed here but the existing loader expects models/<id>.vrm.",
                  "", "UPDATE 08 DEFENSE:",
                  "- Parry recovers 10% of max guard and uses hit-stop instead of attacker stun.",
                  "- Blocking/parrying adds +1 fatigue to the attacker (maximum 10).",
                  "- Each fatigue stack slows attack phases by 2% (maximum 20%).",
                  "- Fatigue decreases one stack per 3 seconds without another block/parry.",
                  "- Fatigue counter shown on each fighter's name/HP area.", ""])
    return '\n'.join(lines)


def changes_for(root: Path) -> dict[str, bytes]:
    ops = {'scripts/fighter_model.gd': patch_model, 'scripts/fighter.gd': patch_fighter,
           'scripts/match.gd': patch_match, 'scripts/hud.gd': patch_hud,
           'scripts/main.gd': patch_main}
    results = {}
    for rel, patch in ops.items():
        f = root / rel
        old = f.read_text(encoding='utf-8')
        new = patch(old)
        if new != old:
            results[rel] = new.encode('utf-8')
    report_rel = 'reports/model_visibility_08.txt'
    report = build_report(root).encode('utf-8')
    if not (root / report_rel).is_file() or (root / report_rel).read_bytes() != report:
        results[report_rel] = report
    return results


def safe_write(target: Path, contents: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + '.' + uuid.uuid4().hex[:8] + '.tmp')
    try:
        tmp.write_bytes(contents)
        tmp.replace(target)
    finally:
        if tmp.exists():
            tmp.unlink()


def install(root: Path, changes: dict[str, bytes], dry_run: bool) -> Path | None:
    for rel in changes:
        print(f"  {'WOULD UPDATE' if dry_run else 'UPDATE'} {rel}")
    print(f"Files to change: {len(changes)}")
    if not changes or dry_run:
        return None
    backup = root.parent / f'{root.name}_backups' / ('defense_08_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {'version': VERSION, 'project': str(root), 'files': []}
    for rel, contents in changes.items():
        target = root / rel
        old = target.read_bytes() if target.is_file() else None
        if old is not None:
            copy = backup / 'originals' / rel
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(old)
        manifest['files'].append({'path': rel, 'existed': old is not None,
                                  'before': sha(old) if old is not None else None,
                                  'after': sha(contents)})
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    done = []
    try:
        for rel, contents in changes.items():
            safe_write(root / rel, contents)
            done.append(rel)
    except Exception:
        for rel in reversed(done):
            original = backup / 'originals' / rel
            target = root / rel
            if original.is_file():
                safe_write(target, original.read_bytes())
            elif target.is_file():
                target.unlink()
        raise
    print('Backup:', backup)
    return backup


def restore(root: Path, target: str) -> None:
    folder = Path(target).expanduser().resolve()
    meta = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if meta.get('version') != VERSION or Path(meta.get('project', '')).resolve() != root:
        raise RuntimeError('This backup is not for Update 08 and this project')
    for entry in meta['files']:
        rel = Path(entry['path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise RuntimeError('Unsafe backup entry')
        f = root / rel
        if f.is_file() and sha(f.read_bytes()) != entry['after']:
            raise RuntimeError(f'{rel} was edited after installation; refusing overwrite')
        if entry['existed'] and sha((folder / 'originals' / rel).read_bytes()) != entry['before']:
            raise RuntimeError(f'Corrupt original backup: {rel}')
    for entry in meta['files']:
        rel = Path(entry['path'])
        f = root / rel
        if entry['existed']:
            safe_write(f, (folder / 'originals' / rel).read_bytes())
        elif f.is_file():
            f.unlink()
        print('  restored', rel)
    print('Backup restored.')


def validate_godot(root: Path, chosen: str | None) -> int:
    exe = None
    if chosen:
        candidate = Path(chosen).expanduser()
        exe = str(candidate.resolve()) if candidate.is_file() else shutil.which(chosen)
    if not exe:
        exe = next((p for name in ('godot', 'godot4', 'godot.exe') if (p := shutil.which(name))), None)
    if not exe:
        print('Godot executable not on PATH. Open the project editor to import VRMs and see errors.')
        return 0
    for args in (['--headless', '--editor', '--path', str(root), '--quit'],
                 ['--headless', '--path', str(root), '--quit-after', '3']):
        try:
            completed = subprocess.run([exe, *args], capture_output=True, text=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as err:
            print('Godot verification error:', err)
            return 2
        output = completed.stdout + completed.stderr
        print(output[-9000:])
        if completed.returncode or re.search(r'(?:SCRIPT ERROR|Parse Error|Failed to load script)', output, re.I):
            print('Godot found errors: copy output above and send it for repair.')
            return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Fight Royale Godot — Update 08 defense + model visibility')
    parser.add_argument('--project', help='default current folder')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--check-godot', action='store_true')
    parser.add_argument('--godot', help='path to Godot executable')
    parser.add_argument('--restore', metavar='BACKUP_FOLDER')
    args = parser.parse_args()
    root = resolve_root(args.project)
    print('FIGHT ROYALE GODOT | UPDATE 08 — DEFENSE + CHARACTER VISIBILITY\nProject:', root)
    if args.restore:
        restore(root, args.restore)
        return 0
    changes = changes_for(root)
    install(root, changes, args.dry_run)
    if not args.dry_run:
        print('Done. Model report: reports/model_visibility_08.txt')
        print('If imported models still fail, fighters will appear as placeholder figures.')
    if args.check_godot and not args.dry_run:
        return validate_godot(root, args.godot)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, KeyError, UnicodeError, json.JSONDecodeError) as error:
        print('ERROR:', error, file=sys.stderr)
        sys.exit(1)
