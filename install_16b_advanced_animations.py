#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot — Update 16B: combat choreography and Animation Lab states.

Run from the Godot project folder:
    python install_16b_advanced_animations.py

Requires 16A. Safe backups, idempotence, --dry-run, --restore BACKUP_DIR,
optional --check-godot. Does not modify .vrm assets or original animation libraries.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

VERSION = "16B.1"
TAG = "# FRG16B - combat choreography"
STATES = ["idle", "walk", "run", "attack", "charge", "block", "hit", "stagger", "dodge", "jump", "win"]


def change_once(s: str, before: str, after: str, where: str) -> str:
    n = s.count(before)
    if n != 1:
        raise ValueError(f"{where}: expected one anchor, found {n}. Project unchanged.")
    return s.replace(before, after, 1)


COMBAT_HELPER = '''# FRG16B: small, ADDITIVE secondary motion on top of authored kit poses.
# Degrees are intentionally subtle so VRM grips and weapon attachments remain stable.
func _frg16b_secondary(role: String, action: String, progress: float) -> Vector3:
    var p: float = clampf(progress, 0.0, 1.0)
    var wave: float = sin(p * PI)
    var heavy_factor: float = 1.25 if heavy or combat_kit in ["greatsword", "knight"] else 0.85
    if action == "attack":
        if role in ["Spine", "Chest", "UpperChest"]:
            return Vector3(-2.5 * wave * heavy_factor, 4.0 * (p - 0.5) * heavy_factor, 1.5 * wave)
        if role == "RightShoulder":
            return Vector3(-2.5 * wave, 0.0, -3.0 * wave)
        if role == "RightLowerArm":
            return Vector3(2.0 * wave, 0.0, 0.0)
        if role == "LeftShoulder":
            return Vector3(1.5 * wave, 0.0, 2.0 * wave)
        if role == "Head":
            return Vector3(1.0 * wave, -1.5 * (p - 0.5), 0.0)
    elif action == "charge":
        if role in ["Chest", "UpperChest"]:
            return Vector3(5.0 * wave, -2.0 * wave, 0.0)
        if role in ["LeftUpperLeg", "RightUpperLeg"]:
            return Vector3(3.0, 0.0, 0.0)
        if role == "RightLowerArm":
            return Vector3(-4.0, 0.0, 0.0)
    elif action == "block":
        if role in ["Chest", "UpperChest"]:
            return Vector3(3.0, 0.0, -2.0)
        if role == "LeftShoulder":
            return Vector3(-3.0, 0.0, 4.0)
        if role == "LeftLowerArm":
            return Vector3(-3.0, 0.0, 0.0)
        if role == "Head":
            return Vector3(3.0, 0.0, 0.0)
    elif action in ["hit", "stagger"]:
        var strength: float = 1.5 if action == "stagger" else 1.0
        if role in ["Spine", "Chest", "UpperChest"]:
            return Vector3(-7.0 * strength * wave, 0.0, 3.0 * wave)
        if role == "Head":
            return Vector3(-4.0 * strength * wave, 0.0, 0.0)
        if role == "RightShoulder":
            return Vector3(3.0 * wave, 0.0, -3.0 * wave)
        if role == "LeftShoulder":
            return Vector3(3.0 * wave, 0.0, 3.0 * wave)
    elif action == "dodge":
        if role in ["Chest", "UpperChest"]:
            return Vector3(8.0 * wave, 0.0, 2.0 * wave)
        if role in ["LeftUpperLeg", "RightUpperLeg"]:
            return Vector3(6.0 * wave, 0.0, 0.0)
        if role == "Head":
            return Vector3(-2.0 * wave, 0.0, 0.0)
    elif action == "jump":
        if role in ["LeftLowerLeg", "RightLowerLeg"]:
            return Vector3(6.0, 0.0, 0.0)
        if role in ["Chest", "UpperChest"]:
            return Vector3(-2.0, 0.0, 0.0)
    elif action == "win":
        if role in ["Chest", "UpperChest"]:
            return Vector3(-3.0, 0.0, 0.0)
        if role == "Head":
            return Vector3(-2.0, 0.0, 0.0)
    return Vector3.ZERO

'''


def with_tabs(code: str) -> str:
    # Match the source project's tab indents; Godot rejects mixed indent styles.
    return re.sub(r"^(?: {4})+", lambda m: "\t" * (len(m.group()) // 4), code, flags=re.MULTILINE)


def patch_motion(s: str) -> str:
    if TAG in s:
        if "func _frg16b_secondary" in s and 'var combat_state := "idle"' in s:
            return s
        raise ValueError("Incomplete 16B motion layer; restore previous backup first.")
    if "# FRG16A - interactive animation lab" not in s:
        raise ValueError("Update 16A is required (motion_layer.gd not patched).")
    s = change_once(s,
        "var lab_profile: Dictionary = {}  # per-fighter, persisted locomotion settings",
        "var lab_profile: Dictionary = {}  # per-fighter, persisted locomotion settings\n" + TAG +
        "\nvar combat_state := \"idle\"\nvar combat_progress := 0.0\nvar combat_weight := 0.0\nvar combat_kit := \"\"",
        "MotionLayer combat channel")
    s = change_once(s, "func _process_modification() -> void:", with_tabs(COMBAT_HELPER) + "func _process_modification() -> void:", "MotionLayer helper")
    old = '''\t\tvar euler: Vector3 = _lab_offsets(idle_offsets, role).lerp(_lab_offsets(walk_offsets, role), blend_walk)
\t\teuler = euler.lerp(_lab_offsets(run_offsets, role), blend_run)
\t\tif euler.length_squared() < 0.000001:
'''
    new = '''\t\tvar euler: Vector3 = _lab_offsets(idle_offsets, role).lerp(_lab_offsets(walk_offsets, role), blend_walk)
\t\teuler = euler.lerp(_lab_offsets(run_offsets, role), blend_run)
\t\t# FRG16B: combat offsets edited in Animation Lab are applied in-game.
\t\t# Smooth blend avoids a snap between walking and attacking or reacting.
\t\tvar blend_combat: float = clampf(combat_weight, 0.0, 1.0)
\t\tif blend_combat > 0.0001 and combat_state != "idle":
\t\t\tvar active_offsets: Dictionary = pose_states.get(combat_state, {})
\t\t\tvar user_offset: Vector3 = _lab_offsets(active_offsets, role)
\t\t\teuler = euler.lerp(user_offset, blend_combat)
\t\t\teuler += _frg16b_secondary(role, combat_state, combat_progress) * blend_combat
\t\tif euler.length_squared() < 0.000001:
'''
    return change_once(s, old, new, "MotionLayer action blending")


def patch_model(s: str) -> str:
    if TAG in s:
        if "motion.combat_state = choreo_state" in s:
            return s
        raise ValueError("Incomplete 16B fighter_model.gd patch.")
    if "# FRG16A - interactive animation lab" not in s:
        raise ValueError("Update 16A is required (fighter_model.gd not patched).")
    s = change_once(s, "var lab_paused := false", "var lab_paused := false\n"+TAG+'''
var choreo_state := "idle"
var choreo_progress := 0.0
var choreo_weight := 0.0''', "Model choreography properties")
    s = change_once(s, "motion.lab_profile = LAB_PROFILES.load_for(character_id if not character_id.is_empty() else String(look.get(\"vrm\", \"\")))",
        'motion.lab_profile = LAB_PROFILES.load_for(character_id if not character_id.is_empty() else String(look.get("vrm", "")))\n\tmotion.combat_kit = kit',
        "Model kit profile")
    s = change_once(s, "\tmotion.phase = _phase\n", '''\tmotion.phase = _phase
\tmotion.combat_state = choreo_state
\tmotion.combat_progress = clampf(choreo_progress, 0.0, 1.0)
\tmotion.combat_weight = lerpf(motion.combat_weight, clampf(choreo_weight, 0.0, 1.0), 1.0 - exp(-15.0 * dt))
''', "Model runtime motion synchronization")
    return s


FIGHTER_HELPER = '''# FRG16B - combat choreography
# Sync combat state to additive skeleton motion; combat stats are unchanged.
func _frg16b_update_choreography() -> void:
    if model == null:
        return
    var action := "idle"
    if state == S.KO:
        action = "hit"
    elif state == S.WIN:
        action = "win"
    elif state == S.HITSTUN:
        action = "hit"
    elif state == S.STAGGER:
        action = "stagger"
    elif state == S.ATTACK:
        action = "attack"
    elif state == S.CHARGE:
        action = "charge"
    elif state == S.BLOCK:
        action = "block"
    elif _dodge_t > 0.0 or _dash_t > 0.0:
        action = "dodge"
    elif not on_ground:
        action = "jump"
    model.choreo_state = action
    model.choreo_weight = 0.0 if action == "idle" else 1.0
    if action == "attack" and not atk.is_empty():
        var total: float = maxf(0.01, (float(atk.get("wind", 0.0)) + float(atk.get("active", 0.0)) + float(atk.get("recover", 0.0))) * attack_time_multiplier())
        model.choreo_progress = clampf(state_t / total, 0.0, 1.0)
    elif action == "dodge":
        model.choreo_progress = 0.5
    elif action == "win":
        model.choreo_progress = 0.5
    else:
        model.choreo_progress = clampf(state_t / 0.45, 0.0, 1.0)

'''


def patch_fighter(s: str) -> str:
    if TAG in s:
        if "func _frg16b_update_choreography" in s:
            return s
        raise ValueError("Incomplete 16B fighter.gd patch.")
    if "# FRG16A - interactive animation lab" not in s:
        raise ValueError("Update 16A required (fighter.gd not patched).")
    s = change_once(s, "\tmodel.play_pose(pose_name, pose_speed)\n", "\tmodel.play_pose(pose_name, pose_speed)\n\t_frg16b_update_choreography()\n", "Fighter update hook")
    return change_once(s, "func _compute_pose() -> void:\n", with_tabs(FIGHTER_HELPER) + "func _compute_pose() -> void:\n", "Fighter choreography helper")


def patch_lab(s: str) -> str:
    if TAG in s:
        if "func _frg16b_preview_pose" in s and "choreo_weight" in s:
            return s
        raise ValueError("Incomplete 16B animation_lab.gd patch.")
    if "Update 16A - visual humanoid joint inspector" not in s:
        raise ValueError("Update 16A required (animation_lab.gd not found).")
    s = change_once(s, 'const MODES := ["idle", "walk", "run"]',
       TAG + '\nconst MODES := ' + json.dumps(STATES), 'Lab combat state selector')
    s = change_once(s,
       '"Edit humanoid joint rotations. Walk/run offsets are applied on top of existing combat poses."',
       '"Edit joints for locomotion AND combat. Actions use additive offsets over kit animations."',
       'Lab description')
    s = change_once(s,
       '"Select Idle, Walk or Run, adjust joints, then Save Fighter. Settings also apply in duels."',
       '"Preview combat states, rotate bones and Save Fighter. Edits also apply in battles."',
       'Lab instructions')
    helper = '''# FRG16B: preview the actual kit pose underneath editable joint offsets.
func _frg16b_preview_pose() -> String:
    match _selected_state:
        "attack":
            var attacks: Dictionary = Data.attacks_for(_selected_char)
            var basic: Dictionary = attacks.get("l1", {})
            return String(basic.get("pose_s", "idle"))
        "charge":
            var attacks: Dictionary = Data.attacks_for(_selected_char)
            var charged: Dictionary = attacks.get("heavy", {})
            return String(charged.get("pose_w", "idle"))
        "block": return "block"
        "hit": return "hit"
        "stagger": return "stagger"
        "jump": return "jump"
        "win": return "win"
        "dodge": return "idle"
        _: return "idle"

'''
    s = change_once(s, 'func _process(dt: float) -> void:\n', with_tabs(helper) + 'func _process(dt: float) -> void:\n', 'Lab preview helper')
    s = change_once(s,
        '\t_model.walk = 0.0 if _selected_state == "idle" else 1.0\n',
        '\t_model.walk = 1.0 if _selected_state in ["walk", "run"] else 0.0\n',
        'Lab no walking during combat previews')
    s = change_once(s,
        '\t_model.run = 1.0 if _selected_state == "run" else 0.0\n',
        '''\t_model.run = 1.0 if _selected_state == "run" else 0.0
\t_model.choreo_state = _selected_state if _selected_state not in ["idle", "walk", "run"] else "idle"
\t_model.choreo_weight = 0.0 if _selected_state in ["idle", "walk", "run"] else 1.0
\t_model.choreo_progress = fmod(float(Time.get_ticks_msec()) / 1100.0, 1.0) if _gait_running else 0.45
\t_model.play_pose(_frg16b_preview_pose(), 18.0)
''', 'Lab runtime combat preview')
    return s


def patch_profiles(s: str) -> str:
    if TAG in s:
        if '"attack"' in s and '"block"' in s:
            return s
        raise ValueError("Incomplete 16B animation_lab_profiles.gd patch.")
    if "## Update 16A" not in s:
        raise ValueError("Update 16A required (animation_lab_profiles.gd not found).")
    s = change_once(s, 'const STATES := ["idle", "walk", "run"]', TAG + '\nconst STATES := ' + json.dumps(STATES), 'Profile state schema')
    # Legacy profiles remain valid; only defaults for NEW fighter profiles change.
    s = change_once(s, '"poses": {"idle": {}, "walk": {}, "run": {}}',
        '"poses": {"idle": {}, "walk": {}, "run": {}, "attack": {}, "charge": {}, "block": {}, "hit": {}, "stagger": {}, "dodge": {}, "jump": {}, "win": {}}',
        'Default new profile actions')
    return s


PATCHES = {
    "scripts/motion_layer.gd": patch_motion,
    "scripts/fighter_model.gd": patch_model,
    "scripts/fighter.gd": patch_fighter,
    "scripts/animation_lab.gd": patch_lab,
    "scripts/animation_lab_profiles.gd": patch_profiles,
}

REPORT = '''Fight Royale — Update 16B: Combat Animation Lab & Choreography

Open Main Menu > Animation Lab; animation states now include Attack, Charge,
Block, Hit, Stagger, Dodge, Jump and Win, in addition to Idle, Walk and Run.
Select a fighter, change an action state, edit joint X/Y/Z rotations and Save Fighter.
Per-character edits apply in Duel vs CPU and CPU vs CPU.

Runtime effects: subtle additive torso, shoulder, forearm and leg motion during
combat, smoothly blended on top of existing kit AnimationPlayer poses. Weapon
bone attachments, VRM files, hitboxes, damage, AI, SFX and cooldowns are unchanged.
This is a joint-offset pose editor, not a keyframe timeline or automatic IK solver.
Models require successful VRM imports in the Godot editor.

If your project already has custom gameplay edits conflicting with an expected
patch anchor, the installer stops without writing any changes.
'''


def hash_data(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def build_changes(root: Path) -> dict[str, bytes]:
    if not (root / 'project.godot').is_file():
        raise ValueError('project.godot missing; run from Godot project directory.')
    changes: dict[str, bytes] = {}
    for rel, patch in PATCHES.items():
        target = root / rel
        if not target.is_file():
            raise ValueError(f'Missing {rel}; install 16A first.')
        original = target.read_text(encoding='utf-8-sig')
        modified = patch(original)
        if modified != original:
            changes[rel] = modified.encode('utf-8')
    target = root / 'reports/animation_lab_16b.txt'
    if not target.is_file() or target.read_bytes() != REPORT.encode('utf-8'):
        changes['reports/animation_lab_16b.txt'] = REPORT.encode('utf-8')
    return changes


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp16b_' + uuid.uuid4().hex[:8])
    try:
        temp.write_bytes(data)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def install(root: Path, changes: dict[str, bytes], dry_run: bool) -> None:
    if not changes:
        print('Update 16B already installed; no changes needed.')
        return
    print('Update 16B changes:')
    for rel in changes:
        print(' -', rel)
    if dry_run:
        print('Dry run OK; nothing written.')
        return
    backup = (root.parent / (root.name + '_backups') /
              ('advanced_animations_16b_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6]))
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {'version': VERSION, 'root': str(root), 'files': {}}
    for rel, data in changes.items():
        target = root / rel
        original = target.read_bytes() if target.is_file() else None
        manifest['files'][rel] = {'before': hash_data(original), 'after': hash_data(data)}
        if original is not None:
            saved = backup / 'originals' / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(original)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    committed: list[str] = []
    try:
        for rel, data in changes.items():
            atomic_write(root / rel, data)
            committed.append(rel)
    except Exception:
        for rel in reversed(committed):
            old = backup / 'originals' / rel
            if old.is_file():
                atomic_write(root / rel, old.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print('Installed 16B. Backup:', backup)
    print('Open Godot > Animation Lab > choose Attack/Block/Hit/Dodge/Jump/Win to edit joints.')


def restore(root: Path, backup_dir: str) -> None:
    backup = Path(backup_dir).expanduser().resolve()
    manifest = json.loads((backup / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('version') != VERSION or Path(manifest.get('root', '')).resolve() != root:
        raise ValueError('This backup does not belong to this project and installer.')
    for rel, meta in manifest['files'].items():
        target = root / rel
        actual = target.read_bytes() if target.is_file() else None
        if hash_data(actual) != meta['after']:
            raise ValueError('Cannot restore modified file: ' + rel)
        if meta['before'] is not None:
            source = backup / 'originals' / rel
            if not source.is_file() or hash_data(source.read_bytes()) != meta['before']:
                raise ValueError('Backup is missing or corrupted: ' + rel)
    for rel in manifest['files']:
        source = backup / 'originals' / rel
        if source.is_file():
            atomic_write(root / rel, source.read_bytes())
        else:
            (root / rel).unlink(missing_ok=True)
    print('Restored:', backup)


def check_godot(root: Path) -> None:
    executable = shutil.which('godot') or shutil.which('godot4')
    if not executable:
        print('Godot not on PATH; open your project in Godot Editor to validate.')
        return
    result = subprocess.run([executable, '--headless', '--editor', '--path', str(root), '--quit'],
                            capture_output=True, text=True, timeout=120)
    output = (result.stdout + '\n' + result.stderr)[-12000:]
    print(output)
    if result.returncode:
        raise RuntimeError('Godot validation failed with exit code ' + str(result.returncode))


def main() -> int:
    parser = argparse.ArgumentParser(description='Fight Royale Godot Update 16B — Advanced Animations')
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--restore', metavar='BACKUP_DIR')
    parser.add_argument('--check-godot', action='store_true')
    args = parser.parse_args()
    root = args.project.expanduser().resolve()
    try:
        if args.restore:
            restore(root, args.restore)
        else:
            install(root, build_changes(root), args.dry_run)
            if args.check_godot and not args.dry_run:
                check_godot(root)
        return 0
    except Exception as exc:
        print('ERROR:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
