#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fight Royale Godot — Update 15A: data-driven statuses and passive event hooks.

Run inside the Godot project directory:
    python install_15a_status_foundation.py

Optional: --dry-run, --check-godot, --project PATH, --restore BACKUP_DIR
Backs up modified files and refuses ambiguous patch anchors.
Does not automatically activate new passives on existing fighters; future character
installers populate data/passive_profiles_15a.json after roster reconciliation.
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

VERSION = "15A.1"
FLAG = "# FRG15A - status and passive runtime"
RUNTIME_PATH = "scripts/combat_status.gd"
RULES_PATH = "data/status_rules_15a.json"
PROFILES_PATH = "data/passive_profiles_15a.json"
REPORT_PATH = "reports/status_foundation_15a.txt"

RUNTIME = r'''extends Node
## FRG15A - status and passive runtime
## Generic status effects and event-triggered passives, with *no* default character passives.
## Character installers can add triggers to data/passive_profiles_15a.json.

const RULES_FILE := "res://data/status_rules_15a.json"
const PROFILES_FILE := "res://data/passive_profiles_15a.json"

var _host = null
var _char_id := ""
var _rules: Dictionary = {}
var _triggers: Dictionary = {}
var _effects: Dictionary = {} # name -> {stacks:int, left:float}
var _event_ready: Dictionary = {} # per-event cooldown deadlines
var _clock := 0.0
var _dot_bank := 0.0

func bind_host(host: Node, fighter_id: String) -> void:
	_host = host
	_char_id = fighter_id
	var rules_data: Variant = _read_json(RULES_FILE)
	if rules_data is Dictionary:
		_rules = rules_data.get("effects", {})
	var profiles_data: Variant = _read_json(PROFILES_FILE)
	if profiles_data is Dictionary:
		var profiles: Dictionary = profiles_data.get("profiles", {})
		var entry: Variant = profiles.get(_char_id, {})
		if entry is Dictionary:
			_triggers = entry.get("triggers", {})

func _read_json(path: String) -> Variant:
	if not FileAccess.file_exists(path):
		push_warning("Fight Royale: missing status configuration " + path)
		return {}
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not (value is Dictionary):
		push_warning("Fight Royale: invalid status configuration " + path)
		return {}
	return value

func apply_effect(effect_id: String, stacks: int = 1, seconds: float = -1.0) -> bool:
	if _host == null or not _rules.has(effect_id) or stacks <= 0:
		return false
	if _host.is_down():
		return false
	var rule: Dictionary = _rules[effect_id]
	var cap: int = maxi(int(rule.get("max_stacks", 1)), 1)
	var duration: float = seconds if seconds > 0.0 else float(rule.get("duration", 3.0))
	if duration <= 0.0:
		return false
	var previous: Dictionary = _effects.get(effect_id, {})
	_effects[effect_id] = {
		"stacks": mini(int(previous.get("stacks", 0)) + stacks, cap),
		"left": maxf(float(previous.get("left", 0.0)), duration)
	}
	return true

func clear_effect(effect_id: String) -> void:
	_effects.erase(effect_id)

func clear_all() -> void:
	_effects.clear()
	_event_ready.clear()
	_dot_bank = 0.0

func stacks_of(effect_id: String) -> int:
	return int(_effects.get(effect_id, {}).get("stacks", 0))

func modify(stat_id: String) -> float:
	var total := 0.0
	for effect_id in _effects:
		var rule: Dictionary = _rules.get(effect_id, {})
		var mods: Dictionary = rule.get("modifiers", {})
		total += float(mods.get(stat_id, 0.0)) * stacks_of(effect_id)
	return clampf(total, -0.75, 1.5)

func movement_multiplier() -> float:
	return clampf(1.0 + modify("movement"), 0.25, 2.5)

func attack_time_multiplier() -> float:
	return 1.0 / clampf(1.0 + modify("attack_speed"), 0.3, 2.5)

func guard_regen_multiplier() -> float:
	return clampf(1.0 + modify("guard_regen"), 0.0, 3.0)

func outgoing_multiplier() -> float:
	return clampf(1.0 + modify("outgoing_damage"), 0.25, 2.5)

func incoming_multiplier() -> float:
	return clampf(1.0 + modify("incoming_damage"), 0.25, 2.5)

func short_label() -> String:
	var labels: Array[String] = []
	for effect_id in _effects:
		var rule: Dictionary = _rules.get(effect_id, {})
		var stack_count := stacks_of(effect_id)
		var label: String = String(rule.get("label", effect_id))
		labels.append(label + ("x%d" % stack_count if stack_count > 1 else ""))
		if labels.size() == 2:
			break
	return ", ".join(PackedStringArray(labels))

func step(dt: float) -> void:
	if dt <= 0.0 or _host == null:
		return
	_clock += dt
	if _host.is_down():
		clear_all()
		return
	for effect_id in _effects.keys():
		var info: Dictionary = _effects[effect_id]
		info["left"] = float(info.get("left", 0.0)) - dt
		if float(info["left"]) <= 0.0:
			_effects.erase(effect_id)
		else:
			_effects[effect_id] = info
	_dot_bank += dt
	while _dot_bank >= 0.25:
		_dot_bank -= 0.25
		var damage := 0.0
		for effect_id in _effects:
			var rule: Dictionary = _rules.get(effect_id, {})
			damage += float(rule.get("dot_hp_fraction_per_second", 0.0)) * stacks_of(effect_id) * 0.25 * float(_host.max_hp)
		if damage > 0.0:
			_host.receive_status_damage(damage)
			if _host.is_down():
				clear_all()
				break

func on_event(event_id: String, other: Node = null) -> void:
	if _host == null or _host.is_down():
		return
	var entries: Variant = _triggers.get(event_id, [])
	if not (entries is Array):
		return
	for idx in range(entries.size()):
		var item: Variant = entries[idx]
		if not (item is Dictionary):
			continue
		var effect_id: String = String(item.get("effect", ""))
		if not _rules.has(effect_id):
			continue
		var token := event_id + ":" + str(idx)
		if _clock < float(_event_ready.get(token, -1.0)):
			continue
		if randf() > clampf(float(item.get("chance", 1.0)), 0.0, 1.0):
			continue
		var target: Node = other if String(item.get("target", "self")) == "opponent" else _host
		if not is_instance_valid(target) or not target.has_method("add_status"):
			continue
		var count: int = maxi(int(item.get("stacks", 1)), 1)
		var duration: float = float(item.get("duration", -1.0))
		if bool(target.call("add_status", effect_id, count, duration)):
			_event_ready[token] = _clock + maxf(float(item.get("cooldown", 0.0)), 0.0)
'''

RULES = {
  "schema_version": 1,
  "description": "Statuses available to later Fight Royale character packs; no effects are enabled on characters by this installer.",
  "effects": {
    "haste": {"label": "Haste", "max_stacks": 5, "duration": 5.0, "modifiers": {"attack_speed": 0.05}},
    "slow": {"label": "Slow", "max_stacks": 5, "duration": 4.0, "modifiers": {"movement": -0.08}},
    "weaken": {"label": "Weaken", "max_stacks": 3, "duration": 7.0, "modifiers": {"outgoing_damage": -0.06}},
    "brittle": {"label": "Brittle", "max_stacks": 3, "duration": 7.0, "modifiers": {"incoming_damage": 0.05}},
    "fortify": {"label": "Fortify", "max_stacks": 3, "duration": 6.0, "modifiers": {"incoming_damage": -0.06}},
    "focus": {"label": "Focus", "max_stacks": 3, "duration": 5.0, "modifiers": {"outgoing_damage": 0.05}},
    "resolve": {"label": "Resolve", "max_stacks": 3, "duration": 8.0, "modifiers": {"movement": 0.07}},
    "guard_flow": {"label": "Guard Flow", "max_stacks": 3, "duration": 5.0, "modifiers": {"guard_regen": 0.12}},
    "scorch": {"label": "Scorch", "max_stacks": 5, "duration": 4.0, "modifiers": {}, "dot_hp_fraction_per_second": 0.002},
    "bleed": {"label": "Bleed", "max_stacks": 3, "duration": 6.0, "modifiers": {}, "dot_hp_fraction_per_second": 0.0015}
  }
}
PROFILES = {
  "schema_version": 1,
  "description": "No passives auto-enabled. Later installers add entries for retained browser fighters after roster verification.",
  "supported_events": ["attack_started", "skill_started", "landed_hit", "received_hit", "blocked_attack", "blocked", "was_parried", "parried", "guard_broken", "clashed", "projectile_destroyed"],
  "profiles": {}
}
REPORT = """FIGHT ROYALE — UPDATE 15A: PASSIVE / STATUS FOUNDATION

- Adds a separate, round-scoped status runtime for each fighter.
- Supports timed and capped stack effects: haste, slow, weaken, brittle,
  fortify, focus, resolve, guard_flow, scorch, bleed.
- Hooks attack starts, blocks, parries, landed hits, guard breaks, clashes,
  and projectile destruction into configurable character passive events.
- Attack definitions may optionally include:
    \"apply_status\": \"scorch\", \"status_chance\": 0.4,
    \"status_stacks\": 1, \"status_duration\": 4.0
- Future character installers configure reactions in data/passive_profiles_15a.json:
    \"profiles\": {\"fighter_id\": {\"triggers\": {\"parried\": [
      {\"effect\": \"haste\", \"target\": \"self\", \"stacks\": 1,
       \"duration\": 3.0, \"cooldown\": 1.0}
    ]}}}
- No status or passive is applied automatically to the current roster.
- No changes to existing skill damage, cooldowns or weapon attacks.
- Status state resets with each new Fighter instance; no shop/economy involved.
- This is a Python patch validation only; import project in Godot for runtime checks.
"""


def one(source: str, old: str, new: str, name: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"{name}: expected one anchor, found {count}; refusing to modify the project")
    return source.replace(old, new, 1)


def patch_fighter(s: str) -> str:
    if FLAG in s:
        if all(x in s for x in ("status_runtime.step(dt)", "notify_passive_event(", "status_runtime.incoming_multiplier()")):
            return s
        raise ValueError("Incomplete 15A fighter patch; refusing to overwrite")
    s = one(s, 'class_name Fighter\nextends Node3D\n', 'class_name Fighter\nextends Node3D\n' + FLAG + '\nconst STATUS_SCRIPT = preload("res://scripts/combat_status.gd")\n', "fighter status preload")
    s = one(s, 'var model: FighterModel\n', 'var model: FighterModel\nvar status_runtime\n', "status instance")
    s = one(s, '''	model = FighterModel.new()
	add_child(model)
	model.setup(look)
''', '''	model = FighterModel.new()
	add_child(model)
	model.setup(look)
	status_runtime = STATUS_SCRIPT.new()
	add_child(status_runtime)
	status_runtime.bind_host(self, String(c.id))
''', "attach status to fighter")
    s = one(s, '''	_clock += dt
	if guard_fatigue > 0 and dt > 0.0:
''', '''	_clock += dt
	if status_runtime != null:
		status_runtime.step(dt)
	if guard_fatigue > 0 and dt > 0.0:
''', "status tick")
    s = one(s, '\t\tif _guard_delay <= 0.0: guard = minf(guard + GUARD_REGEN * dt, max_guard)\n', '\t\tif _guard_delay <= 0.0: guard = minf(guard + GUARD_REGEN * dt * status_runtime.guard_regen_multiplier(), max_guard)\n', "guard regen status")
    s = one(s, '''	return 1.0 / maxf(1.0 - 0.02 * float(guard_fatigue), 0.5)
''', '''	return (1.0 / maxf(1.0 - 0.02 * float(guard_fatigue), 0.5)) * status_runtime.attack_time_multiplier()
''', "attack speed status")
    s = one(s, '''	if aid == "heavy" and state == S.CHARGE: atk_power = 1.0 + 0.5 * minf(state_t / CHARGE_MAX, 1.0)
	atk_power *= dmg_mult * (RAGE_MULT if rage_t > 0.0 else 1.0)
''', '''	if aid == "heavy" and state == S.CHARGE: atk_power = 1.0 + 0.5 * minf(state_t / CHARGE_MAX, 1.0)
	atk_power *= dmg_mult * (RAGE_MULT if rage_t > 0.0 else 1.0) * status_runtime.outgoing_multiplier()
''', "outgoing status damage")
    s = one(s, '''		v = walk_speed
''', '''		v = walk_speed * status_runtime.movement_multiplier()
''', "auto approach status")
    s = one(s, '''			var speed := move_speed * (SPRINT_MULT if sprint_now else 1.0)
''', '''			var speed := move_speed * (SPRINT_MULT if sprint_now else 1.0) * status_runtime.movement_multiplier()
''', "player/AI movement status")
    s = one(s, '''	var dmg: float = float(a.dmg) * power
''', '''	var dmg: float = float(a.dmg) * power * status_runtime.incoming_multiplier()
''', "incoming status damage")
    s = one(s, '''	_set_state(S.ATTACK)

func _attack_step() -> void:
''', '''	_set_state(S.ATTACK)
	notify_passive_event("attack_started", opponent)
	if aid in ["z", "x", "c", "v"]:
		notify_passive_event("skill_started", opponent)

func _attack_step() -> void:
''', "attack start passive hook")
    s = one(s, '''func is_down() -> bool: return state == S.KO
''', '''# Status API used by later character installers and ability definitions.
func add_status(effect_id: String, stacks: int = 1, seconds: float = -1.0) -> bool:
	return status_runtime.apply_effect(effect_id, stacks, seconds) if status_runtime != null else false

func notify_passive_event(event_id: String, other: Node = null) -> void:
	if status_runtime != null:
		status_runtime.on_event(event_id, other)

func status_summary() -> String:
	return status_runtime.short_label() if status_runtime != null else ""

func receive_status_damage(amount: float) -> void:
	if state == S.KO or amount <= 0.0:
		return
	hp = maxf(hp - amount, 0.0)
	if hp <= 0.0:
		_ko()

func is_down() -> bool: return state == S.KO
''', "status/public passive interface")
    return s


def patch_match(s: str) -> str:
    if FLAG in s:
        if all(x in s for x in ("notify_passive_event(\"parried\"", "notify_passive_event(\"clashed\"", "status_summary()")):
            return s
        raise ValueError("Incomplete 15A match patch; refusing unsafe reinstall")
    s = one(s, 'class_name Match\nextends Node3D\n', 'class_name Match\nextends Node3D\n' + FLAG + '\n', "match marker")
    # Status triggering only on successful damaging hits, never blocks, parries, misses.
    s = one(s, '''	var result := d.receive_hit(attacker, a, power)
	var glow := Color(attacker.look.glow) if attacker is Fighter else Color.WHITE
''', '''	var result := d.receive_hit(attacker, a, power)
	if result in ["hit", "crit", "ko"]:
		d.notify_passive_event("received_hit", attacker if attacker is Fighter else null)
		if attacker is Fighter:
			attacker.notify_passive_event("landed_hit", d)
		var effect_id: String = String(a.get("apply_status", ""))
		if effect_id != "" and randf() <= clampf(float(a.get("status_chance", 1.0)), 0.0, 1.0):
			d.add_status(effect_id, maxi(int(a.get("status_stacks", 1)), 1), float(a.get("status_duration", -1.0)))
	elif result == "blocked":
		d.notify_passive_event("blocked", attacker if attacker is Fighter else null)
		if attacker is Fighter:
			attacker.notify_passive_event("blocked_attack", d)
	elif result == "parry":
		d.notify_passive_event("parried", attacker if attacker is Fighter else null)
		if attacker is Fighter:
			attacker.notify_passive_event("was_parried", d)
	elif result == "guard_break":
		d.notify_passive_event("guard_broken", attacker if attacker is Fighter else null)
	var glow := Color(attacker.look.glow) if attacker is Fighter else Color.WHITE
''', "on hit passive hooks")
    s = one(s, '''func _clash(a: Fighter, b: Fighter, pos: Vector3) -> void:
	a.clash_recoil(); b.clash_recoil()
''', '''func _clash(a: Fighter, b: Fighter, pos: Vector3) -> void:
	a.clash_recoil(); b.clash_recoil()
	a.notify_passive_event("clashed", b)
	b.notify_passive_event("clashed", a)
''', "clash passive hooks")
    s = one(s, '''				done = true
				break
		if done:
			node.queue_free()
''', '''				defender.notify_passive_event("projectile_destroyed", p.shooter if p.shooter is Fighter else null)
				done = true
				break
		if done:
			node.queue_free()
''', "melee projectile destruction hook")
    s = one(s, '''			claimed[a.id] = true
			claimed[b.id] = true
			destroyed.append(a)
''', '''			claimed[a.id] = true
			claimed[b.id] = true
			if a.shooter is Fighter:
				a.shooter.notify_passive_event("projectile_destroyed", b.shooter if b.shooter is Fighter else null)
			if b.shooter is Fighter:
				b.shooter.notify_passive_event("projectile_destroyed", a.shooter if a.shooter is Fighter else null)
			destroyed.append(a)
''', "projectile duel hook")
    s = one(s, '''"glow": f.look.glow, "fatigue": f.guard_fatigue}''', '''"glow": f.look.glow, "fatigue": f.guard_fatigue, "status": f.status_summary()}''', "HUD status feed")
    return s


def patch_hud(s: str) -> str:
    if FLAG in s:
        if 'info.get("status", "")' in s:
            return s
        raise ValueError("Incomplete 15A HUD patch")
    s = one(s, 'class_name Hud\nextends CanvasLayer\n', 'class_name Hud\nextends CanvasLayer\n' + FLAG + '\n', "HUD marker")
    s = one(s, '''	var suffix := "  FATIGUE %d/10" % penalty if penalty > 0 else ""
	(box.get_node("Name") as Label).text = "%s  %d / %d%s" % [info.name, int(ceil(info.hp)), int(info.max_hp), suffix]
''', '''	var suffix := "  FATIGUE %d/10" % penalty if penalty > 0 else ""
	var status_text: String = String(info.get("status", ""))
	if status_text != "":
		suffix += "  [%s]" % status_text
	(box.get_node("Name") as Label).text = "%s  %d / %d%s" % [info.name, int(ceil(info.hp)), int(info.max_hp), suffix]
''', "HUD status label")
    return s


def blob_json(value: dict) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def plan(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise ValueError("Run from the folder containing project.godot")
    changes: dict[str, bytes] = {}
    for rel, func in [("scripts/fighter.gd", patch_fighter), ("scripts/match.gd", patch_match), ("scripts/hud.gd", patch_hud)]:
        path = root / rel
        if not path.is_file():
            raise ValueError("Missing " + rel)
        before = path.read_text(encoding="utf-8-sig")
        after = func(before)
        if after != before:
            changes[rel] = after.encode("utf-8")
    for rel, content in [(RUNTIME_PATH, RUNTIME.encode("utf-8")), (RULES_PATH, blob_json(RULES)), (PROFILES_PATH, blob_json(PROFILES)), (REPORT_PATH, REPORT.encode("utf-8"))]:
        path = root / rel
        if not path.is_file():
            changes[rel] = content
        elif rel == RUNTIME_PATH and path.read_bytes() != content:
            if "FRG15A - status and passive runtime" in path.read_text(encoding="utf-8-sig"):
                # Keep user changes to the runtime unless they explicitly restore it.
                continue
            raise ValueError("Status runtime already exists and differs; refusing overwrite: " + rel)
        elif rel == REPORT_PATH and path.read_bytes() != content:
            changes[rel] = content
        elif rel in (RULES_PATH, PROFILES_PATH):
            try:
                current = json.loads(path.read_text(encoding="utf-8-sig"))
                expected_key = "effects" if rel == RULES_PATH else "profiles"
                if not isinstance(current, dict) or expected_key not in current:
                    raise ValueError("Invalid configuration shape")
            except (ValueError, UnicodeError) as exc:
                raise ValueError(f"Invalid existing configuration {rel}: {exc}") from exc
            # Always keep previously installed/edited status rules and profiles.
    return changes


def digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp_15a_" + uuid.uuid4().hex[:8])
    try:
        temp.write_bytes(data)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def install(root: Path, changes: dict[str, bytes], dry_run: bool) -> None:
    if not changes:
        print("Update 15A already installed; no changes.")
        return
    print("Update 15A files:")
    for rel in changes:
        print(" -", rel)
    if dry_run:
        print("Dry run: no files modified")
        return
    folder = root.parent / (root.name + "_backups") / (
        "status_15a_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    )
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for rel, content in changes.items():
        old = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest["files"][rel] = {"before": digest(old), "after": digest(content)}
        if old is not None:
            target = folder / "originals" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(old)
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    applied: list[str] = []
    try:
        for rel, content in changes.items():
            write_atomic(root / rel, content)
            applied.append(rel)
    except Exception:
        for rel in reversed(applied):
            backup = folder / "originals" / rel
            if backup.is_file():
                write_atomic(root / rel, backup.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print("Installed Update 15A. Backup:", folder)


def restore(root: Path, source: str) -> None:
    folder = Path(source).expanduser().resolve()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION or Path(manifest.get("project", "")).resolve() != root:
        raise ValueError("Wrong backup or project")
    for rel, info in manifest["files"].items():
        current = (root / rel).read_bytes() if (root / rel).is_file() else None
        if digest(current) != info["after"]:
            raise ValueError("File changed since Update 15A; refusing overwrite: " + rel)
        backup = folder / "originals" / rel
        if info["before"] is not None and (not backup.is_file() or digest(backup.read_bytes()) != info["before"]):
            raise ValueError("Corrupt backup: " + rel)
    for rel in manifest["files"]:
        backup = folder / "originals" / rel
        if backup.is_file():
            write_atomic(root / rel, backup.read_bytes())
        else:
            (root / rel).unlink(missing_ok=True)
    print("Restored:", folder)


def check_godot(root: Path) -> None:
    exe = shutil.which("godot") or shutil.which("godot4")
    if not exe:
        print("Godot executable not on PATH; open project in editor for import and script validation")
        return
    p = subprocess.run([exe, "--headless", "--editor", "--path", str(root), "--quit"], text=True, capture_output=True, timeout=150)
    print((p.stdout + "\n" + p.stderr)[-14000:])
    if p.returncode != 0:
        raise RuntimeError(f"Godot exit status {p.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fight Royale Godot Update 15A — Status and Passives Foundation")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-godot", action="store_true")
    parser.add_argument("--restore", metavar="BACKUP_DIR")
    args = parser.parse_args()
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
