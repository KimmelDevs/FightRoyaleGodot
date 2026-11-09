#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot — Update 10: Duel vs CPU match completion.

Run in the Godot project folder:
    python install_10_duel_vs_cpu.py

Optional:
    python install_10_duel_vs_cpu.py --dry-run
    python install_10_duel_vs_cpu.py --check-godot
    python install_10_duel_vs_cpu.py --restore PATH_TO_BACKUP

Works after the Fight Royale 01-09 series, including optional 09b third-person
camera. Adds duel round timers, time-limit winner decisions, reliable READY/FIGHT
HUD startup, rematch/character-reselect controls, and guarded player inputs.
Does not change fighter skills, VRMs, SFX, or underlying AI balance.
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

VERSION = "10.0"
MARKER = "# FRG10 - complete Duel vs CPU match flow"
FILES = ("scripts/main.gd", "scripts/match.gd", "scripts/hud.gd")
REPORT = "reports/duel_vs_cpu_10.txt"


def replace_once(s: str, old: str, new: str, label: str) -> str:
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {n}; no files changed. "
                           "Provide current scripts/main.gd, match.gd and hud.gd for a compatible installer.")
    return s.replace(old, new, 1)


def replace_func(s: str, name: str, changed, required=()) -> str:
    pattern = re.compile(rf"(?m)^func {re.escape(name)}\([^\n]*\)(?:\s*->\s*\w+)?:\n")
    matches = list(pattern.finditer(s))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one function {name}, found {len(matches)}; no files changed")
    a = matches[0].start()
    following = re.search(r"(?m)^func [A-Za-z_][A-Za-z_0-9]*\(", s[matches[0].end():])
    b = matches[0].end() + following.start() if following else len(s)
    previous = s[a:b]
    for string in required:
        if string not in previous:
            raise RuntimeError(f"Function {name} is not the expected version (missing {string!r})")
    updated = changed(previous)
    return s[:a] + updated + s[b:]


def patch_main(s: str) -> str:
    if MARKER in s:
        if all(v in s for v in ("_choose_duel_time", "_back_to_character_select", '"round_seconds": _duel_seconds')):
            return s
        raise RuntimeError("Partial Update 10 main.gd detected; refusing to patch")
    if "FIGHT_ROYALE_MODES_V02" not in s or "func show_prepare() -> void:" not in s:
        raise RuntimeError("This main.gd isn't the two-mode version installed by Update 02")
    s = replace_once(s, 'var _mode := "duel"\n',
                     'var _mode := "duel"\n' + MARKER + '\nvar _duel_seconds := 120\n', 'duel state')
    def prepare(fn: str) -> str:
        old = '\t_title(v, "AI Difficulty", 23)\n'
        addition = '''\tif _mode == "duel":
		var time_row := HBoxContainer.new()
		time_row.add_theme_constant_override("separation", 12)
		v.add_child(time_row)
		_text(time_row, "Round limit:", 18)
		var timer := OptionButton.new()
		timer.custom_minimum_size = Vector2(180, 36)
		var durations := [60, 120, 180, 0]
		for option_index in durations.size():
			var caption := "Unlimited" if durations[option_index] == 0 else "%d minutes" % int(durations[option_index] / 60)
			timer.add_item(caption)
		timer.select(maxi(durations.find(_duel_seconds), 0))
		timer.item_selected.connect(_choose_duel_time)
		time_row.add_child(timer)
'''
        if old not in fn:
            raise RuntimeError('Missing AI Difficulty heading in show_prepare')
        return fn.replace(old, addition + old, 1)
    s = replace_func(s, 'show_prepare', prepare, ('_skill_picker(v, 0)', '_skill_picker(v, 1)'))
    s = replace_once(s, 'func _choose_difficulty(index: int) -> void:\n',
                     'func _choose_duel_time(index: int) -> void:\n'
                     '\t_duel_seconds = [60, 120, 180, 0][clampi(index, 0, 3)]\n\n'
                     'func _choose_difficulty(index: int) -> void:\n', 'time selection callback')
    s = replace_once(s, '"difficulty": _difficulty, "spectator": spectator}',
                     '"difficulty": _difficulty, "spectator": spectator, "round_seconds": _duel_seconds}',
                     'match configuration')
    s = replace_once(s, '\t_hud.quit_to_menu.connect(show_menu)\n\tadd_child(_hud)',
                     '\t_hud.quit_to_menu.connect(show_menu)\n'
                     '\t_hud.change_fighters.connect(_back_to_character_select)\n'
                     '\tadd_child(_hud)', 'HUD signal hookup')
    s = replace_once(s, 'func _end_match() -> void:\n',
                     'func _back_to_character_select() -> void:\n'
                     '\t_end_match()\n'
                     '\tshow_select()\n\n'
                     'func _end_match() -> void:\n', 'fighter reselection function')
    return s


def patch_match(s: str) -> str:
    if MARKER in s:
        checks = ('func _tick_duel_clock(dt: float)', 'func _finish_duel(winner: Fighter',
                  '"seconds_left": _duel_seconds_left', 'start_round.call_deferred()')
        if all(x in s for x in checks):
            return s
        raise RuntimeError("Partial Update 10 match.gd detected; refusing to patch")
    if 'class_name Match' not in s or '# FRG08' not in s:
        raise RuntimeError('Match needs the Update 08 combat foundation')
    s = replace_once(s, 'var paused := false\n',
                     'var paused := false\n\n' + MARKER + '\n'
                     'var _duel_seconds_left := 120.0\n'
                     'var _duel_clock_running := false\n', 'match clock state')
    # Defer the first spawn and READY event so Hud._ready has connected to ui_event.
    s = replace_once(s, '\tstart_round()\n', '\tstart_round.call_deferred()\n', 'deferred first round')
    s = replace_once(s,
                     'fighters.clear(); _trails.clear(); _melee_hits.clear(); _projectiles.clear(); _strike_marks.clear(); _timers.clear()',
                     'fighters.clear(); _trails.clear(); _melee_hits.clear(); _projectiles.clear(); _strike_marks.clear(); _timers.clear()\n'
                     '\t_duel_seconds_left = float(cfg.get("round_seconds", 120))\n'
                     '\t_duel_clock_running = false',
                     'round clock reset')
    s = replace_once(s, '\t\tfor f in fs: f.brain = _brain_for(f)',
                     '\t\t_duel_clock_running = cfg.mode == "duel"\n'
                     '\t\tfor f in fs: f.brain = _brain_for(f)', 'clock begins at FIGHT')
    def patch_input(fn: str) -> str:
        signature = 'func _unhandled_input(e: InputEvent) -> void:\n'
        if '\tif paused:\n' in fn:
            return fn.replace('\tif paused:\n', '\tif paused or round_over or not _duel_clock_running:\n', 1)
        if '\tif not bool(cfg.get("spectator", false)):' in fn:
            return fn.replace(signature, signature + '\tif paused or round_over or not _duel_clock_running:\n\t\treturn\n', 1)
        raise RuntimeError('Unrecognized player input handler')
    s = replace_func(s, '_unhandled_input', patch_input, ('_player_brain.on_event(e)',))
    s = replace_once(s, '\t_time += dt\n',
                     '\t_time += dt\n\t_tick_duel_clock(dt)\n', 'match clock tick')

    def replace_ko(fn: str) -> str:
        start = fn.index('\tif cfg.mode == "duel":')
        end = fn.index('\telif cfg.mode == "team":', start)
        duel = '''\tif cfg.mode == "duel":
		if round_over:
			return
		var survivor: Fighter = null
		for candidate in fighters:
			if candidate != f and not candidate.is_down():
				survivor = candidate
				break
		_finish_duel(survivor)
'''
        return fn[:start] + duel + fn[end:]
    s = replace_func(s, '_on_ko', replace_ko, ('elif cfg.mode == "team":', 'ui_event.emit'))

    new_functions = '''# --- FRG10: complete duel clock and end-of-round handling ----------------------------------

func _tick_duel_clock(dt: float) -> void:
	if cfg.mode != "duel" or round_over or not _duel_clock_running or dt <= 0.0:
		return
	if float(cfg.get("round_seconds", 120)) <= 0.0:
		return  # Unlimited mode
	_duel_seconds_left = maxf(_duel_seconds_left - dt, 0.0)
	if _duel_seconds_left > 0.0 or fighters.size() < 2:
		return
	# Remaining HP percentage determines the result. Exact ties are draws.
	var a: Fighter = fighters[0]
	var b: Fighter = fighters[1]
	var a_ratio: float = a.hp / maxf(a.max_hp, 1.0)
	var b_ratio: float = b.hp / maxf(b.max_hp, 1.0)
	var winner: Fighter = null
	if a_ratio > b_ratio + 0.0001:
		winner = a
	elif b_ratio > a_ratio + 0.0001:
		winner = b
	_finish_duel(winner, true)

func _finish_duel(winner: Fighter, by_time: bool = false) -> void:
	if round_over:
		return
	round_over = true
	_duel_clock_running = false
	for f in fighters:
		f.brain = null
	add_trauma(0.65)
	hit_stop(0.35)
	later(0.35, func():
		if not is_instance_valid(self):
			return
		if is_instance_valid(winner):
			winner.win()
		var spectator_mode: bool = bool(cfg.get("spectator", false))
		var draw: bool = winner == null
		var player_wins: bool = winner != null and winner == local
		var result_text: String = "DRAW"
		if not draw:
			if spectator_mode:
				result_text = "%s WINS!" % winner.look.name
			else:
				result_text = "VICTORY" if player_wins else "DEFEAT"
		var result_color: Color = Color("#d2e7ff") if draw else (Color("#ffe08a") if spectator_mode or player_wins else Color("#ff7b7b"))
		var detail: String = "Time limit reached" if by_time else "Knockout"
		ui_event.emit({"type": "over", "text": result_text, "sub": detail + "  |  R to rematch", "color": result_color})
		can_restart = true)

'''
    s = replace_once(s, '# --- camera --------------------------------------------------------------------------------',
                     new_functions + '# --- camera --------------------------------------------------------------------------------', 'duel win/timeout logic')

    # Dynamic HUD feed: inserts clock fields without replacing 09b's camera changes.
    s = replace_once(s,
                     '\t\t"can_restart": can_restart,\n',
                     '\t\t"seconds_left": _duel_seconds_left,\n'
                     '\t\t"time_limit": float(cfg.get("round_seconds", 120)),\n'
                     '\t\t"clock_running": _duel_clock_running,\n'
                     '\t\t"spectator": bool(cfg.get("spectator", false)),\n'
                     '\t\t"can_restart": can_restart,\n', 'HUD duel clock data')
    return s


def patch_hud(s: str) -> str:
    if MARKER in s:
        if all(x in s for x in ('signal change_fighters', '_clock_label.text', '"Change Fighters"')):
            return s
        raise RuntimeError('Partial Update 10 hud.gd detected; refusing to patch')
    if 'class_name Hud' not in s or 'func _on_event' not in s:
        raise RuntimeError('Unrecognized scripts/hud.gd')
    s = replace_once(s, 'signal quit_to_menu\n',
                     'signal quit_to_menu\nsignal change_fighters\n\n' + MARKER + '\n', 'HUD change-fighters signal')
    s = replace_once(s, 'var _pause: PanelContainer\n',
                     'var _pause: PanelContainer\nvar _clock_label: Label\nvar _controls_hint: Label\n',
                     'HUD clock and controls label state')
    s = replace_once(s, '\t_other_bar = _bar_block(root, true)\n',
                     '''\t_other_bar = _bar_block(root, true)
	_clock_label = _label(root, 25, Color("#ffe9a8"))
	_clock_label.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_clock_label.position = Vector2(-100, 45)
	_clock_label.size = Vector2(200, 36)
	_controls_hint = _label(root, 15, Color("#f1f4ff"))
	_controls_hint.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_controls_hint.position = Vector2(-440, -25)
	_controls_hint.size = Vector2(880, 24)
	_controls_hint.text = "WASD move  |  LMB attack/hold charge  |  RMB block  |  Z X C skills  |  Space jump  |  Shift sprint  |  Q dodge"
	_controls_hint.visible = not bool(match_node.cfg.get("spectator", false))
''', 'HUD clock rendering nodes')
    s = replace_once(s,
                     '\tov.add_child(_button("Rematch (R)", func(): rematch.emit()))\n\tov.add_child(_button("Main menu", func(): quit_to_menu.emit()))',
                     '\tov.add_child(_button("Rematch (R)", func(): rematch.emit()))\n'
                     '\tov.add_child(_button("Change Fighters", func(): change_fighters.emit()))\n'
                     '\tov.add_child(_button("Main menu", func(): quit_to_menu.emit()))',
                     'victory screen navigation')
    s = replace_once(s,
                     '\tpv.add_child(_button("Restart", func(): set_paused(false); rematch.emit()))\n',
                     '\tpv.add_child(_button("Restart", func(): set_paused(false); rematch.emit()))\n'
                     '\tpv.add_child(_button("Change Fighters", func(): set_paused(false); change_fighters.emit()))\n',
                     'pause screen navigation')
    s = replace_once(s, '\tvar h := match_node.hud()\n',
                     '''\tvar h := match_node.hud()
	if _clock_label != null:
		var seconds: int = maxi(int(ceil(float(h.get("seconds_left", 0.0)))), 0)
		var unlimited: bool = float(h.get("time_limit", 0.0)) <= 0.0
		_clock_label.text = "DUEL  |  --:--" if unlimited else ("DUEL  |  %02d:%02d" % [int(seconds / 60), seconds % 60])
		_clock_label.visible = not bool(h.get("spectator", false))
''', 'HUD ticking clock')
    return s


def changes_for(root: Path) -> dict[str, bytes]:
    if not (root / 'project.godot').is_file():
        raise RuntimeError('Run this installer inside your Fight Royale Godot directory, beside project.godot.')
    results = {}
    for rel, patcher in zip(FILES, (patch_main, patch_match, patch_hud)):
        file = root / rel
        if not file.is_file():
            raise RuntimeError(f'Missing {rel}; refusing to create guessed game code')
        before = file.read_text(encoding='utf-8-sig')
        after = patcher(before)
        if after != before:
            results[rel] = after.encode('utf-8')
    report = '''FIGHT ROYALE GODOT | UPDATE 10 - DUEL VS CPU

Improves existing Duel vs CPU selection, match and HUD:
* Configurable 1-, 2-, 3-minute or unlimited round timer (default 2 min).
* READY/FIGHT banner now emits after HUD has connected.
* Clock begins when the fighters become controllable.
* Knockout or time expiry ends the duel. Time winner is highest remaining HP %.
* Ties at timeout are reported as draws.
* Rematch (R), Change Fighters, and Main Menu from results/pause UI.
* Paused/READY/finished duels do not forward player input to PlayerBrain.
* Bottom-row duel input guide; 09b third-person F6/Tab camera unaffected.
* CPU vs CPU remains selectable; this update does not complete spectator features.
* No shop, currency, multiplayer, or new asset requirements.

Validation: Python file patching and backup / restore can be tested here.
Godot import, parsing, visuals and gameplay must be checked inside your editor.
'''.encode('utf-8')
    if not (root / REPORT).is_file() or (root / REPORT).read_bytes() != report:
        results[REPORT] = report
    return results


def sha(raw: bytes | None) -> str | None:
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.frg10_' + uuid.uuid4().hex[:10] + '.tmp')
    try:
        temp.write_bytes(content)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def install(root: Path, changes: dict[str, bytes], dry_run: bool = False) -> Path | None:
    if not changes:
        print('Already installed; no changes.')
        return None
    print('Files to update:')
    for rel in changes:
        print(' -', rel)
    if dry_run:
        print('Dry-run complete: nothing was written.')
        return None
    backup = root.parent / (root.name + '_backups') / ('duel_10_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {'version': VERSION, 'project': str(root), 'files': {}}
    for rel, data in changes.items():
        current = root / rel
        old = current.read_bytes() if current.exists() else None
        manifest['files'][rel] = {'old': sha(old), 'new': sha(data)}
        if old is not None:
            original = backup / 'originals' / rel
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(old)
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    applied = []
    try:
        for rel, data in changes.items():
            atomic_write(root / rel, data)
            applied.append(rel)
    except Exception:
        for rel in reversed(applied):
            original = backup / 'originals' / rel
            if original.is_file():
                atomic_write(root / rel, original.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print('Backup:', backup)
    return backup


def restore(root: Path, folder: str) -> None:
    backup = Path(folder).expanduser().resolve()
    meta = json.loads((backup / 'manifest.json').read_text(encoding='utf-8'))
    if meta.get('version') != VERSION or Path(meta.get('project', '')).resolve() != root:
        raise RuntimeError('Backup was not created by Update 10 for this folder')
    for rel, hashes in meta['files'].items():
        p = Path(rel)
        if p.is_absolute() or '..' in p.parts:
            raise RuntimeError('Unsafe backup filename ' + rel)
        current = root / p
        if not current.is_file() or sha(current.read_bytes()) != hashes['new']:
            raise RuntimeError('Refusing restore: file changed since install: ' + rel)
        original = backup / 'originals' / rel
        if hashes['old'] is not None and (not original.is_file() or sha(original.read_bytes()) != hashes['old']):
            raise RuntimeError('Original in backup is missing or damaged: ' + rel)
    for rel, hashes in meta['files'].items():
        path = root / rel
        if hashes['old'] is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write(path, (backup / 'originals' / rel).read_bytes())
        print('Restored:', rel)


def check_godot(root: Path, exe_arg: str | None) -> int:
    exe = None
    if exe_arg:
        exe = str(Path(exe_arg).expanduser().resolve()) if Path(exe_arg).is_file() else shutil.which(exe_arg)
    if not exe:
        exe = next((p for n in ('godot', 'godot4', 'godot.exe') if (p := shutil.which(n))), None)
    if not exe:
        print('No Godot executable found in PATH. Open Godot editor to check scripts and import assets.')
        return 0
    try:
        result = subprocess.run([exe, '--headless', '--editor', '--path', str(root), '--quit'],
                                capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print('Godot check could not finish:', exc)
        return 2
    text = (result.stdout + '\n' + result.stderr)[-14000:]
    print(text)
    if result.returncode or re.search(r'SCRIPT ERROR|Parse Error|Failed to load script', text, re.I):
        return 2
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description='Fight Royale Godot | Update 10 Duel vs CPU')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--restore', metavar='BACKUP_FOLDER')
    p.add_argument('--check-godot', action='store_true')
    p.add_argument('--godot', help='Godot executable for --check-godot')
    args = p.parse_args()
    root = Path.cwd().resolve()
    print('FIGHT ROYALE GODOT | UPDATE 10 - DUEL VS CPU\nProject:', root)
    if args.restore:
        restore(root, args.restore)
        return 0
    changes = changes_for(root)
    install(root, changes, args.dry_run)
    if not args.dry_run:
        print('\nGodot > Duel vs CPU > Choose Fighters > Start Fight.')
        print('Test READY/FIGHT, timer, skills, pause (Esc), KO and rematch (R).')
        print('Report:', REPORT)
    return check_godot(root, args.godot) if args.check_godot and not args.dry_run else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError, KeyError, UnicodeError, json.JSONDecodeError) as e:
        print('ERROR:', e, file=sys.stderr)
        raise SystemExit(1)
