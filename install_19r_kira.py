#!/usr/bin/env python3
"""Fight Royale Godot Update 19R — Kira: Tempest Kicker.

Run from the Godot project folder: python install_19r_kira.py
Optional: --dry-run or --restore <backup-folder>

Requires Update 19Q. Updates the EXISTING Kira, never adds a duplicate.
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

VERSION = "19R.1"
MARKER = "FRG19R"


def json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def require_swap(text: str, old: str, new: str, path: str):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected 1 patch anchor, found {count}: {old[:85]!r}; no changes made")
    return text.replace(old, new, 1)


def load_json(root, rel):
    try:
        return json.loads((root / rel).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise RuntimeError(f"Cannot read {rel}: {e}") from e


def build(root: Path):
    if not (root / "project.godot").is_file():
        raise RuntimeError("Run from your Godot project directory (project.godot missing).")
    if not (root / "data/browser_nyx_19q.json").is_file():
        raise RuntimeError("Install Update 19Q before Update 19R.")
    roster = load_json(root, "data/roster.json")
    kira = [f for f in roster if f.get("id") == "kira"]
    if len(kira) != 1 or kira[0].get("look", {}).get("kit") != "kicks":
        raise RuntimeError("Expected exactly one existing Kira (kicks) entry; no changes made")
    if not (root / "animations/kicks.tres").is_file():
        raise RuntimeError("Missing animations/kicks.tres; install skeleton/animation updates first.")
    attacks = load_json(root, "data/attacks.json")
    kit = attacks.get("kira")
    if not isinstance(kit, dict) or any(k not in kit for k in ("l1", "l2", "l3", "l4", "heavy", "z", "x", "c", "v")):
        raise RuntimeError("Kira's existing attack table is missing required moves")
    if kit["z"].get("name") != "Cyclone Kick" or kit["x"].get("name") != "Crescent Gale":
        raise RuntimeError("Unrecognized Kira kit; refusing blind overwrite")
    if kit["c"].get("name") not in ("Hundred Kicks", "Phantom Step") or kit["v"].get("name") not in ("Dragon Ascent", "Hundred Kicks"):
        raise RuntimeError("Kira C/V do not match the expected legacy or browser version")
    if any(k in kit for k in ("air_l1", "air_l2", "air_l3")):
        raise RuntimeError("Kira air attacks already present without 19R manifest; manual audit required")

    # Current browser source: Cyclone Kick, Crescent Gale, Phantom Step (C), Hundred Kicks (V).
    kit["z"].update(type="strike", at="self", style="cyclone_kick_v2", cd=6,
        wind=0.18, active=0.57, recover=0.4, delay=0.03, repeat=3, interval=0.19,
        radius=2.0, dmg=65, guard=20, knock=3, stun=0.3,
        pose_w="cy1_w", pose_s="cy1_s",
        desc="Three rotating heel kicks with alternating legs; each can be guarded or parried.")
    kit["c"].update(name="Phantom Step", type="phantom", style="kira_phantom",
        desc="Teleport behind the opponent for three separate kicks. First landed kick stuns.",
        cd=16, wind=0.12, active=0.05, recover=1.35, dmg=115, guard=30,
        knock=1.2, stun=2.0, stagger=True, heavy=True, repeat=3, interval=0.5,
        pose_w="kk1_w", pose_s="kk3_s", no_parry=True)
    kit["v"].update(name="Hundred Kicks", type="strike", at="target", style="kira_hundred",
        desc="Six rapid stationary phantom kicks; Kira remains vulnerable throughout.",
        cd=10, wind=0.1125, active=0.06, recover=0.45, dmg=30, guard=10,
        knock=0.8, stun=0.3, delay=0.15, radius=1.5, repeat=6, interval=0.045,
        self_jump=0, pose_w="kk1_w", pose_s="kk1_s")
    for n, damage, nxt, knock, wind_pose, strike_pose in [
        (1, 28, "air_l2", 0.8, "kk2_w", "fly_s"),
        (2, 32, "air_l3", 1.0, "kk2_w", "kk2_s"),
        (3, 42, "", 4.0, "kk3_w", "kk3_s"),
    ]:
        entry = dict(kit["l1"])
        entry.update(id=f"air_l{n}", name=f"Air Kick {n}", next=nxt,
                     wind=0.09, active=0.09, recover=0.37 if n == 3 else 0.23,
                     dmg=damage, guard=18 if n == 3 else 12,
                     stun=0.34 if n == 3 else 0.21, knock=knock, lunge=0,
                     reach=1.95, pose_w=wind_pose, pose_s=strike_pose)
        kit[f"air_l{n}"] = entry
    changes = {"data/attacks.json": json_bytes(attacks)}

    rel = "scripts/fighter.gd"
    src = (root / rel).read_text(encoding="utf-8")
    src = require_swap(src,
        "var nyx_air_strikes := 0\n",
        "var nyx_air_strikes := 0\n# FRG19R — three aerial kicks per jump; resets upon landing.\nvar kira_air_strikes := 0\n", rel)
    src = require_swap(src,
        '\tif kit == "assassin":\n\t\tvar ambush_text:',
        '\t# FRG19R: Kira can make three distinct airborne kicks per jump.\n'
        '\tif kit == "kicks":\n'
        '\t\tvar kick_text: String = "AIR KICKS %d/3" % kira_air_strikes\n'
        '\t\treturn kick_text if summary.is_empty() else kick_text + ", " + summary\n'
        '\tif kit == "assassin":\n\t\tvar ambush_text:', rel)
    src = require_swap(src,
        '\tif kit == "assassin" and on_ground and nyx_air_strikes != 0:\n',
        '\t# FRG19R: air combo cannot be resumed once Kira touches the ground.\n'
        '\tif kit == "kicks" and on_ground and kira_air_strikes != 0:\n'
        '\t\tkira_air_strikes = 0\n'
        '\t\t_combo_next = "l1"\n'
        '\t\t_combo_timer = 0.0\n'
        '\t\tif atk_id in ["air_l1", "air_l2", "air_l3"]:\n'
        '\t\t\t_buffered = false\n'
        '\t\t\tatk["next"] = ""\n'
        '\tif kit == "assassin" and on_ground and nyx_air_strikes != 0:\n', rel)
    src = require_swap(src,
        '\t\tif kit == "assassin" and not on_ground:\n\t\t\tif nyx_air_strikes < 2: _start_attack("air_l%d" % (nyx_air_strikes + 1))\n',
        '\t\tif kit == "kicks" and not on_ground:\n'
        '\t\t\tif kira_air_strikes < 3: _start_attack("air_l%d" % (kira_air_strikes + 1))\n'
        '\t\telif kit == "assassin" and not on_ground:\n'
        '\t\t\tif nyx_air_strikes < 2: _start_attack("air_l%d" % (nyx_air_strikes + 1))\n', rel)
    src = require_swap(src,
        'func _request_light() -> void:\n\t# FRG19Q',
        'func _request_light() -> void:\n'
        '\t# FRG19R — Kira: three real airborne kick contacts, not an unlimited loop.\n'
        '\tif kit == "kicks" and not on_ground:\n'
        '\t\tif kira_air_strikes >= 3: return\n'
        '\t\tif state in [S.IDLE, S.BLOCK]:\n'
        '\t\t\tif atk_lock <= 0.0: _start_attack("air_l%d" % (kira_air_strikes + 1))\n'
        '\t\t\telse: _queued_light_t = LIGHT_BUFFER_SECONDS\n'
        '\t\telif state == S.ATTACK and atk_id in ["air_l1", "air_l2"]:\n'
        '\t\t\t_buffered = true\n'
        '\t\treturn\n'
        '\t# FRG19Q', rel)
    src = require_swap(src,
        '\tif kit == "assassin" and aid in ["air_l1", "air_l2"] and on_ground: return\n',
        '\tif kit == "kicks" and aid in ["air_l1", "air_l2", "air_l3"] and on_ground: return # FRG19R\n'
        '\tif kit == "assassin" and aid in ["air_l1", "air_l2"] and on_ground: return\n', rel)
    src = require_swap(src,
        '\tatk = attacks[aid].duplicate(true)\n\t# FRG19Q',
        '\tatk = attacks[aid].duplicate(true)\n'
        '\t# FRG19R — each Kira air kick advances once, including buffered chains.\n'
        '\tif kit == "kicks" and aid in ["air_l1", "air_l2", "air_l3"]:\n'
        '\t\tkira_air_strikes = int(aid.right(1))\n'
        '\t# FRG19Q', rel)
    src = require_swap(src,
        'else 0.63 if kit == "assassin" and not on_ground and state == S.ATTACK',
        'else 0.65 if kit == "kicks" and not on_ground and state == S.ATTACK and atk_id in ["air_l1", "air_l2", "air_l3"] else 0.63 if kit == "assassin" and not on_ground and state == S.ATTACK', rel)
    changes[rel] = src.encode("utf-8")

    rel = "scripts/match.gd"
    src = (root / rel).read_text(encoding="utf-8")
    src = require_swap(src,
        '\tif f.kit == "tristaff" and String(a.get("type", "")) == "melee":\n\t\t_zephyr_schedule_beats(f, a)\n\tmatch a.type:',
        '\tif f.kit == "tristaff" and String(a.get("type", "")) == "melee":\n'
        '\t\t_zephyr_schedule_beats(f, a)\n'
        '\t# FRG19R — Kira Phantom Step resolves as three true hits, never a fake melee.\n'
        '\tif f.kit == "kicks" and String(a.get("style", "")) == "kira_phantom":\n'
        '\t\t_kira_phantom_step(f, a)\n'
        '\t\treturn\n'
        '\tmatch a.type:', rel)
    src = require_swap(src,
        '## Area attack(s) at the target (or around the caster) after a telegraphed delay.\n',
        '''# FRG19R — Phantom Step: staggerable, 3 independent timed kicks.
# Each strike repositions Kira behind her CURRENT opponent, but an interrupted
# cast cannot continue after knockdown, KO, or a new attack; no guaranteed damage.
func _kira_phantom_step(f: Fighter, a: Dictionary) -> void:
    if f.opponent == null or f.is_down(): return
    var serial: int = f.swing_serial
    var original_round: int = _round
    var original_target: Fighter = f.opponent
    for beat in range(3):
        var beat_index: int = beat
        later(float(beat_index) * float(a.get("interval", 0.5)), func():
            if original_round != _round or round_over or not is_instance_valid(f) or f.is_down(): return
            if f.swing_serial != serial or f.state in [Fighter.S.HITSTUN, Fighter.S.STAGGER, Fighter.S.KO]: return
            if not is_instance_valid(original_target) or original_target.is_down(): return
            var target: Fighter = original_target
            var delta: Vector3 = target.position - f.position
            delta.y = 0.0
            if delta.length_squared() < 0.05: delta = f.forward()
            var behind: Vector3 = target.position + delta.normalized() * 1.10
            behind.y = f.position.y
            f.teleport(behind)
            var kick: Dictionary = a.duplicate(true)
            kick["type"] = "melee"
            kick["stun"] = 2.0 if beat_index == 0 else 0.30
            kick["stagger"] = beat_index == 0
            kick["knock"] = 1.2 if beat_index < 2 else 3.0
            fx.ring(target.position, Color("#5ae4d6"), 0.95, 0.18, 0.60)
            var difference: Vector3 = target.position - f.position
            difference.y = 0.0
            if difference.length() <= 2.15 + target.radius:
                apply_hit(f, target, kick, f.atk_power, target.chest(), difference.normalized(), false)
        )

## Area attack(s) at the target (or around the caster) after a telegraphed delay.
''', rel)
    # Kira skill effects use impacts, not sword slash particles.
    src = require_swap(src,
        '\t\t"spin":\n\t\t\tfx.ring(g + Vector3(0, 1.0, 0), color, radius, 0.2, 0.9)\n',
        '\t\t"spin":\n\t\t\tfx.ring(g + Vector3(0, 1.0, 0), color, radius, 0.2, 0.9)\n'
        '\t\t"cyclone_kick_v2", "kira_hundred": # FRG19R — blunt foot impacts, never blade slashes.\n'
        '\t\t\tfx.ring(g + Vector3(0, 0.65, 0), Color("#6cffd7"), radius * 0.82, 0.19, 0.80)\n'
        '\t\t\tfx.flash(g + Vector3(0, 1.05, 0), Color("#dafff1"), 0.30, 0.11, 0.72)\n', rel)
    changes[rel] = src.encode("utf-8")
    changes["data/browser_kira_19r.json"] = json_bytes({
        "version": VERSION, "id": "kira", "character": "Kira / Tempest Kicker",
        "source": "https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts",
        "state": "FIRST PLAYABLE REFINEMENT",
        "completed": ["Preserved existing Kira roster ID, VRM and four light kicks",
                      "Cyclone Kick: three area pulses", "Crescent Gale retained",
                      "Phantom Step: three real teleport kicks with stagger on first contact",
                      "Hundred Kicks ultimate: six fast impacts and no invulnerability",
                      "Three aerial combo kicks per jump with air steering; grounded reset",
                      "HUD air-kick counter"],
        "pending": ["Pose-specific alternate-leg choreography", "Exact Godot visual alignment", "Full engine playtest"]})
    changes["reports/kira_19r.txt"] = (
        "19R — Kira / Tempest Kicker\n"
        "Ported browser C Phantom Step (3 timed real kicks), V Hundred Kicks (6 beats),\n"
        "and three aerial kick contacts per jump. Existing fighter roster entry preserved.\n"
        "Requires Update 19Q; no shop or game mode changes.\n"
        "Python dry-run tested; engine runtime test still needed.\n").encode("utf-8")
    return changes


def digest(blob):
    return hashlib.sha256(blob).hexdigest() if blob is not None else None


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".frg19r-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fp:
            fp.write(data)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def install(root: Path, dry_run: bool):
    if (root / "data/browser_kira_19r.json").exists():
        print("Update 19R already installed; no changes.")
        return
    changes = build(root)
    changed = {name: blob for name, blob in changes.items()
               if not (root / name).exists() or (root / name).read_bytes() != blob}
    for name in changed:
        print("Update:", name)
    if dry_run:
        print("19R dry-run passed; no project files changed.")
        return
    backup = root.parent / (root.name + "_backups") / ("kira_19r_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for rel, blob in changed.items():
        old = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest["files"][rel] = {"before": digest(old), "after": digest(blob)}
        if old is not None:
            saved = backup / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(old)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    complete = []
    try:
        for rel, blob in changed.items():
            atomic_write(root / rel, blob)
            complete.append(rel)
    except BaseException:
        for rel in reversed(complete):
            saved = backup / rel
            if saved.exists():
                atomic_write(root / rel, saved.read_bytes())
            else:
                (root / rel).unlink(missing_ok=True)
        raise
    print("Update 19R installed. Backup:", backup)


def restore(root: Path, backup: Path):
    manifest = load_json(backup, "manifest.json")
    if manifest.get("project") != str(root):
        raise RuntimeError("Backup belongs to a different project")
    for rel, hashes in manifest["files"].items():
        cur = (root / rel).read_bytes() if (root / rel).is_file() else None
        if digest(cur) != hashes["after"]:
            raise RuntimeError("Restore refused: file changed after installing 19R: " + rel)
    for rel, hashes in manifest["files"].items():
        saved = backup / rel
        if hashes["before"] is None:
            (root / rel).unlink(missing_ok=True)
        else:
            atomic_write(root / rel, saved.read_bytes())
    print("Restored:", backup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    try:
        if args.restore:
            restore(root, args.restore.resolve())
        else:
            install(root, args.dry_run)
    except Exception as error:
        print("ERROR:", error, file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
