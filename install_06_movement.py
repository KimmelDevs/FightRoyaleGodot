#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot Update 06: movement + grounded procedural footwork.

Run from your Godot project directory:
  python install_06_movement.py

Optional:
  python install_06_movement.py --dry-run
  python install_06_movement.py --check-godot
  python install_06_movement.py --restore "<backup folder printed during installation>"

Requires Update 05. Makes no changes to VRMs, sound files or animation libraries.
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

VERSION = "06.0"
MARKER = "# FRG06 - locomotion and procedural footwork"
FILES = (
    "scripts/keys.gd",
    "scripts/player_brain.gd",
    "scripts/fighter.gd",
    "scripts/fighter_model.gd",
    "scripts/motion_layer.gd",
)


def rep_once(data: str, before: str, after: str, part: str) -> str:
    count = data.count(before)
    if count != 1:
        raise RuntimeError(f"Unsafe to modify {part}: expected 1 matching anchor, found {count}: {before[:85]!r}")
    return data.replace(before, after, 1)


def patch_keys(src: str) -> str:
    if MARKER in src:
        require = ('"sprint"', '"dodge"', 'KEY_SHIFT', 'KEY_Q')
        if all(v in src for v in require):
            return src
        raise RuntimeError("Update 06 marker exists in keys.gd but expected actions are missing")
    src = rep_once(src,
        '\t["jump", "Jump"], ["attack", "Attack (tap) / charged attack (hold)"], ["block", "Block / shield"],',
        '\t["jump", "Jump"], ["attack", "Attack (tap) / charged attack (hold)"], ["block", "Block / shield"],\n'
        '\t["sprint", "Sprint (hold)"], ["dodge", "Dodge (tap)"],  # FRG06 - locomotion and procedural footwork',
        'keys.gd actions')
    src = rep_once(src,
        '\t"jump": ["k:%d" % KEY_SPACE, ""], "attack": ["m:%d" % MOUSE_BUTTON_LEFT, ""], "block": ["m:%d" % MOUSE_BUTTON_RIGHT, ""],',
        '\t"jump": ["k:%d" % KEY_SPACE, ""], "attack": ["m:%d" % MOUSE_BUTTON_LEFT, ""], "block": ["m:%d" % MOUSE_BUTTON_RIGHT, ""],\n'
        '\t"sprint": ["k:%d" % KEY_SHIFT, ""], "dodge": ["k:%d" % KEY_Q, ""],',
        'keys.gd default binds')
    return src


def patch_player(src: str) -> str:
    if MARKER in src:
        if all(v in src for v in ('_dodge_pending', 'in_sprint', 'in_dodge')):
            return src
        raise RuntimeError("Partial Update 06 detected in player_brain.gd")
    src = rep_once(src, 'var _prev := {}',
        'var _prev := {}\nvar _dodge_pending := false  # FRG06 - locomotion and procedural footwork',
        'player_brain.gd variables')
    src = rep_once(src,
        '\tif e is InputEventKey and e.pressed and not e.echo:\n\t\tfor pair in',
        '\tif e is InputEventKey and e.pressed and not e.echo:\n'
        '\t\tif Keys.matches("dodge", e): _dodge_pending = true\n'
        '\t\tfor pair in',
        'player_brain.gd event handling')
    src = rep_once(src,
        '\tif x != 0 or y != 0: f.in_move = (right * x + fwd * y).normalized()\n\tf.in_attack',
        '\tif x != 0 or y != 0: f.in_move = (right * x + fwd * y).normalized()\n'
        '\tf.in_sprint = Keys.held("sprint")\n'
        '\tif _dodge_pending:\n'
        '\t\t# A stationary dodge retreats from the opponent; moving dodge follows input.\n'
        '\t\tf.in_dodge = f.in_move if f.in_move.length_squared() > 0.01 else -f.forward()\n'
        '\t\t_dodge_pending = false\n'
        '\tf.in_attack',
        'player_brain.gd think inputs')
    return src


def patch_fighter(src: str) -> str:
    if MARKER in src:
        if all(v in src for v in ('_read_dodge()', '_steer_vel', 'model.run', 'DODGE_SPEED')):
            return src
        raise RuntimeError("Partial Update 06 detected in fighter.gd")
    src = rep_once(src, 'const DASH_SPEED := 14.0',
        'const DASH_SPEED := 14.0\n'
        'const DODGE_SPEED := 10.0  # FRG06 - locomotion and procedural footwork\n'
        'const DODGE_DURATION := 0.20\n'
        'const DODGE_COOLDOWN := 1.4\n'
        'const SPRINT_MULT := 1.45\n'
        'const GROUND_ACCEL := 19.0\n'
        'const GROUND_BRAKE := 25.0\n'
        'const AIR_CONTROL := 0.45',
        'fighter.gd constants')
    src = rep_once(src, 'var in_dash := Vector3.ZERO',
        'var in_dash := Vector3.ZERO\nvar in_dodge := Vector3.ZERO\nvar in_sprint := false',
        'fighter.gd input declarations')
    src = rep_once(src, 'var _dash_dir := Vector3.ZERO',
        'var _dash_dir := Vector3.ZERO\n'
        'var _dodge_t := 0.0\nvar _dodge_cd := 0.0\nvar _dodge_dir := Vector3.ZERO\n'
        'var _steer_vel := Vector3.ZERO',
        'fighter.gd movement state')
    src = rep_once(src,
        'in_attack = false; in_block = false; in_jump = false; in_skill = ""; in_move = Vector3.ZERO; in_dash = Vector3.ZERO',
        'in_attack = false; in_block = false; in_jump = false; in_skill = ""; in_move = Vector3.ZERO; in_dash = Vector3.ZERO\n'
        '\tin_dodge = Vector3.ZERO; in_sprint = false',
        'fighter.gd input reset')
    src = rep_once(src, '\t_dash_t = maxf(_dash_t - dt, 0.0)',
        '\t_dash_t = maxf(_dash_t - dt, 0.0)\n'
        '\t_dodge_t = maxf(_dodge_t - dt, 0.0)\n'
        '\t_dodge_cd = maxf(_dodge_cd - dt, 0.0)',
        'fighter.gd duration timers')
    src = rep_once(src, '\t_read_dash()\n\t_read_attack(dt)',
        '\t_read_dash()\n\t_read_dodge()\n\t_read_attack(dt)',
        'fighter.gd action sequence')
    src = rep_once(src,
        'func _read_attack(dt: float) -> void:',
        '''func _read_dodge() -> void:
\t# Short evasive sidestep, independent of the double-tap dash cooldown.
\tif in_dodge.length_squared() < 0.01 or _dodge_cd > 0.0 or _dash_t > 0.0:
\t\treturn
\tif state != S.IDLE and state != S.BLOCK:
\t\treturn
\t_dodge_dir = Vector3(in_dodge.x, 0.0, in_dodge.z).normalized()
\tif _dodge_dir.length_squared() < 0.01:
\t\treturn
\t_steer_vel = Vector3.ZERO
\t_dodge_t = DODGE_DURATION
\t_dodge_cd = DODGE_COOLDOWN
\tinvuln_t = maxf(invuln_t, 0.14)
\tif state == S.BLOCK:
\t\t_set_state(S.IDLE)
\tdashed.emit(self)

func _read_attack(dt: float) -> void:''',
        'fighter.gd dodge method')
    # Whole locomotion method is updated, preserving charge, lunge, pushback, arena limits and auto approach.
    before = src[src.index('func _move(dt: float) -> void:'):src.index('\nfunc _vertical(dt: float) -> void:')]
    if not all(x in before for x in ('_leap_vel', '_knock', 'model.walk', 'auto_approach')):
        raise RuntimeError('Unexpected fighter.gd _move implementation; refusing to replace custom movement')
    after = '''func _move(dt: float) -> void:
\tvar pos := position
\tvar o = opponent
\tvar dir := forward()
\tvar dist := 99.0
\tif o and not o.is_down():
\t\tvar to: Vector3 = o.position - pos
\t\tto.y = 0.0
\t\tdist = to.length()
\t\tdir = to / maxf(dist, 0.001)
\telif in_move.length_squared() > 0.01:
\t\tdir = in_move.normalized()
\tif state != S.KO:
\t\tvar target := atan2(dir.x, dir.z)
\t\trotation.y += wrapf(target - rotation.y, -PI, PI) * (1.0 - exp(-12.0 * dt))

\tvar walking := false
\tvar running := false
\tvar burst := false
\tif state == S.ATTACK and atk.get("mode", "") == "leap" and atk_phase == 1:
\t\tpos += _leap_vel * dt
\t\t_steer_vel = Vector3.ZERO
\telif _dash_t > 0.0:
\t\tpos += _dash_dir * DASH_SPEED * dt
\t\t_steer_vel = Vector3.ZERO
\t\tburst = true
\t\twalking = on_ground
\t\t_running = false
\telif _dodge_t > 0.0:
\t\tpos += _dodge_dir * DODGE_SPEED * dt
\t\t_steer_vel = Vector3.ZERO
\t\tburst = true
\t\twalking = on_ground
\telse:
\t\tvar v := 0.0
\t\tif state == S.IDLE and auto_approach and brain != null and o and not o.is_down() and dist > ENGAGE:
\t\t\tv = walk_speed
\t\t\twalking = on_ground
\t\tif state == S.ATTACK and not atk.is_empty() and atk_phase <= 1 and dist > MIN_DIST + 0.15:
\t\t\tv += float(atk.lunge)
\t\t_knock = maxf(_knock - 14.0 * dt, 0.0)
\t\tv -= _knock
\t\tif dist < MIN_DIST and v > 0.0:
\t\t\tv = 0.0
\t\tpos += dir * v * dt

\t\tvar steer := 1.0 if state == S.IDLE else 0.5 if state == S.BLOCK else 0.4 if state == S.CHARGE else 0.0
\t\tvar requested := Vector3.ZERO
\t\tif steer > 0.0 and in_move.length_squared() > 0.0001:
\t\t\tvar sprint_now := in_sprint and state == S.IDLE and on_ground
\t\t\tvar speed := move_speed * (SPRINT_MULT if sprint_now else 1.0)
\t\t\trequested = in_move.normalized() * speed * steer
\t\t\trunning = sprint_now
\t\tvar response := GROUND_ACCEL if requested.length_squared() > 0.01 else GROUND_BRAKE
\t\tvar air_factor := 1.0 if on_ground else AIR_CONTROL
\t\t_steer_vel = _steer_vel.move_toward(requested, response * air_factor * dt)
\t\tvar travel := _steer_vel * dt
\t\tif dist < MIN_DIST and travel.dot(dir) > 0.0:
\t\t\ttravel -= dir * travel.dot(dir)
\t\tpos += travel
\t\twalking = walking or (on_ground and _steer_vel.length_squared() > 0.04)
\t\tif dist < MIN_DIST * 0.9:
\t\t\tpos -= dir * (MIN_DIST * 0.9 - dist) * 0.5
\tvar flat := Vector2(pos.x, pos.z).length()
\tif flat > arena_radius:
\t\tpos.x *= arena_radius / flat
\t\tpos.z *= arena_radius / flat
\tposition = pos

\t# The motion modifier controls gait AFTER the animation library poses.
\tvar w := 1.0 if walking else 0.0
\tmodel.walk = clampf(lerpf(model.walk, w, 1.0 - exp(-9.0 * dt)), 0.0, 1.0)
\tmodel.run = lerpf(model.run, 1.0 if running else 0.0, 1.0 - exp(-7.0 * dt))
\tvar side := Vector3(cos(rotation.y), 0.0, -sin(rotation.y))
\tvar side_value := clampf(_steer_vel.dot(side) / maxf(move_speed, 0.01), -1.0, 1.0)
\tmodel.strafe = lerpf(model.strafe, side_value, 1.0 - exp(-9.0 * dt))
\tmodel.airborne = not on_ground
\tmodel.burst = lerpf(model.burst, 1.0 if burst else 0.0, 1.0 - exp(-15.0 * dt))
'''
    # Avoid a fake variable: running is already declared above.
    after = after.replace('\t\t_running = false\n', '')
    src = src.replace(before, after, 1)
    return src


def patch_model(src: str) -> str:
    if MARKER in src:
        if all(v in src for v in ('motion.run', 'motion.strafe', 'motion.airborne', 'motion.burst')):
            return src
        raise RuntimeError("Partial Update 06 detected in fighter_model.gd")
    src = rep_once(src, 'var walk := 0.0',
        'var walk := 0.0\nvar run := 0.0  # FRG06 - locomotion and procedural footwork\nvar strafe := 0.0\nvar airborne := false\nvar burst := 0.0',
        'fighter_model.gd data')
    src = rep_once(src,
        '\t_phase += dt * 11.0 * walk\n\tmotion.t = _t\n\tmotion.walk = walk\n\tmotion.phase = _phase',
        '\t_phase += dt * (10.0 + 6.0 * run) * walk\n'
        '\tif motion == null: return\n'
        '\tmotion.t = _t\n\tmotion.walk = walk\n\tmotion.run = run\n\tmotion.strafe = strafe\n\tmotion.airborne = airborne\n\tmotion.burst = burst\n\tmotion.phase = _phase',
        'fighter_model.gd movement parameters')
    return src


def patch_motion(src: str) -> str:
    if MARKER in src:
        if all(v in src for v in ('_knees', '_feet', 'strafe', 'airborne', 'burst')):
            return src
        raise RuntimeError("Partial Update 06 detected in motion_layer.gd")
    src = rep_once(src, 'var heavy := false',
        'var heavy := false\n'
        'var run := 0.0  # FRG06 - locomotion and procedural footwork\n'
        'var strafe := 0.0\nvar airborne := false\nvar burst := 0.0',
        'motion_layer.gd controls')
    src = rep_once(src, 'var _legs := [-1, -1]',
        'var _legs := [-1, -1]\nvar _knees := [-1, -1]\nvar _feet := [-1, -1]\nvar _arms := [-1, -1]',
        'motion_layer.gd bone caches')
    src = rep_once(src,
        '\t_legs = [_bone_name(sk, "LeftUpperLeg"), _bone_name(sk, "RightUpperLeg")]',
        '\t_legs = [_bone_name(sk, "LeftUpperLeg"), _bone_name(sk, "RightUpperLeg")]\n'
        '\t_knees = [_bone_name(sk, "LeftLowerLeg"), _bone_name(sk, "RightLowerLeg")]\n'
        '\t_feet = [_bone_name(sk, "LeftFoot"), _bone_name(sk, "RightFoot")]\n'
        '\t_arms = [_bone_name(sk, "LeftUpperArm"), _bone_name(sk, "RightUpperArm")]',
        'motion_layer.gd bone setup')
    start = src.index('func _process_modification() -> void:')
    old = src[start:]
    if not all(v in old for v in ('set_bone_pose_position', 'set_bone_pose_rotation', 'breath')) or '\nfunc ' in old[5:]:
        raise RuntimeError('Unknown motion_layer.gd modifier; refusing to replace custom modifier')
    new = '''func _rotate_local(sk: Skeleton3D, bone: int, axis: Vector3, amount: float) -> void:
\tif bone < 0 or absf(amount) < 0.00001:
\t\treturn
\tvar q := Quaternion(axis, amount)
\tsk.set_bone_pose_rotation(bone, (sk.get_bone_pose_rotation(bone) * q).normalized())

func _process_modification() -> void:
\tvar sk := get_skeleton()
\tif sk == null or _hips < 0:
\t\treturn
\tvar idle := 1.0 - clampf(walk, 0.0, 1.0)
\tvar sprint := clampf(run, 0.0, 1.0)
\tvar grounded := 0.0 if airborne else 1.0
\tvar gait := clampf(walk, 0.0, 1.0) * grounded * (1.0 - clampf(burst, 0.0, 1.0) * 0.75)
\tvar s := sin(phase)
\tvar breath := sin(t * TAU / (3.6 if not heavy else 4.2))
\tvar stride := (0.48 + 0.22 * sprint) * gait

\t# Keep authored crouch/pose height; add light heel-to-toe bob only while moving.
\tvar bob := absf(s) * (0.025 + 0.018 * sprint) * gait
\tvar shift := 0.016 * strafe * gait
\tvar pos := _hip_rest + Vector3(shift, hips_offset * _scale + bob + breath * 0.004 * idle, 0.0)
\tsk.set_bone_pose_position(_hips, pos)
\t# Thighs, knees, and ankles are animated as a unit, rather than stiff scissor legs.
\tfor i in 2:
\t\tvar sign := 1.0 if i == 0 else -1.0
\t\tvar stepping := s * sign
\t\t_rotate_local(sk, _legs[i], Vector3.RIGHT, stepping * stride)
\t\t_rotate_local(sk, _knees[i], Vector3.RIGHT, maxf(0.0, -stepping) * 0.42 * gait + (0.16 if airborne else 0.0))
\t\t_rotate_local(sk, _feet[i], Vector3.RIGHT, -stepping * (0.16 + 0.06 * sprint) * gait)
\t\t# Opposing arm counter-swing; reduced to preserve the kit's guard stance.
\t\t_rotate_local(sk, _arms[i], Vector3.RIGHT, -stepping * 0.10 * gait * (0.7 if heavy else 1.0))
\t# Dodge / dash reads as a brief forward lean, not running in place.
\t_rotate_local(sk, _chest, Vector3.RIGHT, -0.13 * clampf(burst, 0.0, 1.0))
\t_rotate_local(sk, _chest, Vector3.FORWARD, -0.045 * strafe * gait)
\t# Minimal idle breathing to keep heavy knights grounded.
\t_rotate_local(sk, _chest, Vector3.RIGHT, -breath * deg_to_rad(1.6 if not heavy else 0.8) * idle)
'''
    return src[:start] + new


def json_bytes(obj: dict) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')


def resolve_root(root_str: str | None) -> Path:
    root = Path(root_str or '.').expanduser().resolve()
    for rel in ("project.godot", *FILES):
        if not (root / rel).is_file():
            raise RuntimeError(f"Missing {rel}. Run inside the Godot project after Updates 01–05.")
    src = (root / "scripts/fighter_model.gd").read_text(encoding="utf-8-sig")
    if "WeaponMount.profile_for" not in src or "FighterRig.profile_for" not in src:
        raise RuntimeError("Updates 04 and 05 are required. Existing weapon/rig integration not found.")
    return root


def build_changes(root: Path) -> dict[str, bytes]:
    patchers = {"scripts/keys.gd": patch_keys, "scripts/player_brain.gd": patch_player,
                "scripts/fighter.gd": patch_fighter, "scripts/fighter_model.gd": patch_model,
                "scripts/motion_layer.gd": patch_motion}
    changes = {}
    for rel, patch in patchers.items():
        src = (root / rel).read_text(encoding='utf-8-sig')
        changes[rel] = patch(src).encode('utf-8')
    report = """FIGHT ROYALE GODOT - MOVEMENT UPDATE 06

ADDED
- Shift: sprint (1.45x existing character move speed while grounded and idle).
- Q: short directional dodge, or retreat when standing still; separate 1.4s cooldown.
- Double-tap WASD still activates the existing long dash.
- Horizontal movement now accelerates and brakes rather than snapping instantly.
- Air steering is reduced to 45% of ground response.
- Footwork adds knee bend, ankle movement, opposing arm swing, stride variation,
  hip bob, lateral weight shift, mild torso lean, and airborne leg tuck.
- Existing combat animation poses, attack lunges, knockback and auto-approach remain.
- No new animation assets needed; skeleton mapping from Update 04 is used.

CONTROLS
WASD / arrows: move | Shift: sprint | Q: dodge | double-tap direction: dash
Space: jump | left click: attack | right click: block | Z/X/C: skills
If custom controls already exist, the two new actions inherit defaults and can
be rebound from Settings. Other keybindings are preserved.

NOTE
Python patch testing cannot prove Godot visual correctness. Use --check-godot
if the Godot executable is available; otherwise open the project in the editor.
"""
    changes["reports/movement_audit_06.txt"] = report.encode('utf-8')
    return changes


def sha(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def safe_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp.' + uuid.uuid4().hex[:8])
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        if tmp.exists(): tmp.unlink()


def install(root: Path, changes: dict[str, bytes], dry_run: bool) -> Path | None:
    modified = {rel: data for rel, data in changes.items() if not (root / rel).is_file() or (root / rel).read_bytes() != data}
    for rel in changes:
        print('  %-10s %s' % ('UPDATE' if rel in modified else 'unchanged', rel))
    print('Files to change:', len(modified))
    if dry_run:
        print('Dry run: no files written')
        return None
    if not modified:
        print('Already installed. No files changed.')
        return None
    folder = (root.parent / (root.name + '_backups') /
              ('movement_06_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6]))
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {'version': VERSION, 'project': str(root), 'files': []}
    for rel, data in modified.items():
        dest = root / rel
        exists = dest.is_file()
        original = dest.read_bytes() if exists else None
        if exists:
            stored = folder / 'originals' / rel
            stored.parent.mkdir(parents=True, exist_ok=True)
            stored.write_bytes(original)
        manifest['files'].append({'path': rel, 'existed': exists,
                                  'before': sha(original) if exists else None, 'after': sha(data)})
    (folder / 'manifest.json').write_bytes(json_bytes(manifest))
    completed = []
    try:
        for rel, data in modified.items():
            safe_write(root / rel, data)
            completed.append(rel)
    except Exception:
        for rel in reversed(completed):
            saved = folder / 'originals' / rel
            if saved.is_file(): safe_write(root / rel, saved.read_bytes())
            elif (root / rel).exists(): (root / rel).unlink()
        raise
    print('Backup:', folder)
    return folder


def restore(root: Path, source: str) -> None:
    folder = Path(source).expanduser().resolve()
    meta = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if meta.get('version') != VERSION or Path(meta.get('project', '')).resolve() != root:
        raise RuntimeError('Backup not created by Update 06 for this project')
    for row in meta.get('files', []):
        rel = Path(row['path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise RuntimeError('Invalid backup path')
        dest = root / rel
        if dest.is_file() and sha(dest.read_bytes()) != row['after']:
            raise RuntimeError('File changed since installation; restore aborted: ' + str(rel))
        if row['existed']:
            orig = (folder / 'originals' / rel).read_bytes()
            if sha(orig) != row['before']:
                raise RuntimeError('Original backup corrupted: ' + str(rel))
    for row in meta['files']:
        rel = Path(row['path'])
        dest = root / rel
        if row['existed']:
            safe_write(dest, (folder / 'originals' / rel).read_bytes())
        elif dest.is_file():
            dest.unlink()
        print('  restored', rel)
    print('Restored Update 06 backup.')


def check_godot(root: Path, selected: str | None) -> int:
    exe = None
    if selected and Path(selected).is_file():
        exe = str(Path(selected).resolve())
    elif selected: exe = shutil.which(selected)
    if not exe:
        exe = next((e for n in ('godot', 'godot4', 'godot.exe', 'Godot_v4.4-stable_win64_console.exe')
                    if (e := shutil.which(n))), None)
    if not exe:
        print('Godot executable not found. You can open the project normally or pass --godot PATH.')
        return 0
    for args in (['--headless', '--editor', '--path', str(root), '--quit'],
                 ['--headless', '--path', str(root), '--quit-after', '4']):
        try:
            p = subprocess.run([exe, *args], capture_output=True, text=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as err:
            print('Godot verification error:', err)
            return 2
        print((p.stdout + p.stderr)[-6000:])
        if p.returncode:
            print('Godot returned exit code', p.returncode)
            return 2
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Fight Royale Godot Update 06 — movement')
    parser.add_argument('--project', help='optional path to Godot project (default: current directory)')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--restore', metavar='BACKUP_FOLDER')
    parser.add_argument('--check-godot', action='store_true')
    parser.add_argument('--godot', metavar='EXE_PATH')
    args = parser.parse_args(argv)
    root = resolve_root(args.project)
    print('FIGHT ROYALE GODOT | UPDATE 06 — MOVEMENT\nProject:', root)
    if args.restore:
        restore(root, args.restore)
        return 0
    changes = build_changes(root)
    install(root, changes, args.dry_run)
    if not args.dry_run:
        print('Done. Keys: Shift=sprint, Q=dodge, double-tap WASD=dash.')
        print('Notes: reports/movement_audit_06.txt')
    if args.check_godot and not args.dry_run:
        return check_godot(root, args.godot)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, KeyError, UnicodeError, json.JSONDecodeError) as err:
        print('ERROR:', err, file=sys.stderr)
        sys.exit(1)
