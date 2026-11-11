#!/usr/bin/env python3
"""Fight Royale Godot — 19Q: Nyx, Shadow Blade (two aerial dagger strikes and Ambush).

Run from the Godot project directory:
    python install_19q_nyx.py
    python install_19q_nyx.py --dry-run
    python install_19q_nyx.py --restore <backup-directory>

Requires Update 19P. Does not touch other characters, models, sounds or saves.
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

VERSION = "19Q.1"
MARKER = "FRG19Q"


def read_json(root: Path, rel: str):
    try:
        return json.loads((root / rel).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise RuntimeError(f"{rel}: {e}") from e


def dump_json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def swap_once(source: str, old: str, new: str, rel: str) -> str:
    n = source.count(old)
    if n != 1:
        raise RuntimeError(f"{rel}: expected one exact patch anchor ({n} found): {old[:100]!r}. No files changed.")
    return source.replace(old, new, 1)


def build(root: Path) -> dict[str, bytes]:
    if not (root / "project.godot").is_file():
        raise RuntimeError("project.godot missing; run in Fight Royale Godot project folder")
    if not (root / "data/browser_marina_19p.json").is_file():
        raise RuntimeError("Install Update 19P first. No files were changed.")
    roster = read_json(root, "data/roster.json")
    found = [r for r in roster if r.get("id") == "nyx"]
    if len(found) != 1 or found[0].get("look", {}).get("kit") != "assassin":
        raise RuntimeError("Nyx assassin roster entry missing or duplicated")
    if not (root / "animations/assassin.tres").is_file():
        raise RuntimeError("Missing animation library animations/assassin.tres")
    attacks = read_json(root, "data/attacks.json")
    kit = attacks.get("nyx")
    required = ("l1", "l2", "l3", "l4", "heavy", "z", "x", "c", "v")
    if not isinstance(kit, dict) or any(k not in kit for k in required):
        raise RuntimeError("Nyx attack table incomplete")
    if [kit[k].get("name") for k in ("z", "x", "c", "v")] != ["Smoke Step", "Shuriken Fan", "Phantom Rush", "Venom Fan"]:
        raise RuntimeError("Unexpected Nyx skill kit version; avoiding blind overwrite")
    if "air_l1" in kit or "air_l2" in kit:
        raise RuntimeError("Nyx air skills already exist but 19Q marker is absent; manual audit required")

    # The browser kit already matches the inherited four-hit combo; preserve it.
    # Smoke Step is repositioning, not a damaging impact.
    kit["z"].update(dmg=0, guard=0, knock=0, stun=0, name="Smoke Step")
    # Venom Fan's description promises poison; existing status runtime supports it.
    kit["v"].update(apply_status="poison", status_duration=4.0,
                    status_chance=1.0, status_stacks=1)

    # Browser air-combat data: fast assassin two-stage aerial chain, not an unlimited combo.
    # Use EXISTING assassin animation poses until the next choreography refinement.
    one = dict(kit["l1"])
    one.update(id="air_l1", type="melee", name="Air Dagger One", next="air_l2",
               wind=0.09, active=0.09, recover=0.23, dmg=28,
               guard=12, reach=1.95, lunge=0, knock=0.8, stun=0.21,
               pose_w="as1_w", pose_s="as1_s", heavy=False)
    two = dict(kit["l2"])
    two.update(id="air_l2", type="melee", name="Air Dagger Two", next="",
               wind=0.09, active=0.09, recover=0.25, dmg=32,
               guard=12, reach=1.95, lunge=0, knock=1.0, stun=0.21,
               pose_w="as2_w", pose_s="as2_s", heavy=False)
    kit["air_l1"] = one
    kit["air_l2"] = two
    changes: dict[str, bytes] = {"data/attacks.json": dump_json(attacks)}

    rel = "scripts/fighter.gd"
    src = (root / rel).read_text(encoding="utf-8")
    src = swap_once(src,
        'var rook_combo_hits := 0\n',
        '# FRG19Q — Nyx: real Phantom Rush contacts boost ranged SKILLS only.\n'
        'var nyx_ambush_stacks := 0\n'
        'var nyx_air_strikes := 0\n'
        'var rook_combo_hits := 0\n', rel)
    src = swap_once(src,
        'func status_summary() -> String:\n\tvar summary: String = status_runtime.short_label() if status_runtime != null else ""\n',
        'func status_summary() -> String:\n\tvar summary: String = status_runtime.short_label() if status_runtime != null else ""\n'
        '\t# FRG19Q — Nyx HUD: +2% ranged skill damage per landed Phantom Rush.\n'
        '\tif kit == "assassin":\n'
        '\t\tvar ambush_text: String = "AMBUSH x%d (+%d%% RANGED SKILLS)" % [nyx_ambush_stacks, nyx_ambush_stacks * 2]\n'
        '\t\treturn ambush_text if summary.is_empty() else ambush_text + ", " + summary\n', rel)
    src = swap_once(src,
        'func _request_light() -> void:\n\tif state == S.IDLE or state == S.BLOCK:\n',
        'func _request_light() -> void:\n'
        '\t# FRG19Q — two independently damaging air dagger hits per jump.\n'
        '\tif kit == "assassin" and not on_ground:\n'
        '\t\tif nyx_air_strikes >= 2: return\n'
        '\t\tif state in [S.IDLE, S.BLOCK]:\n'
        '\t\t\tif atk_lock <= 0.0:\n'
        '\t\t\t\t_start_attack("air_l%d" % (nyx_air_strikes + 1))\n'
        '\t\t\telse: _queued_light_t = LIGHT_BUFFER_SECONDS\n'
        '\t\telif state == S.ATTACK and atk_id == "air_l1":\n'
        '\t\t\t_buffered = true\n'
        '\t\treturn\n'
        '\tif state == S.IDLE or state == S.BLOCK:\n', rel)
    src = swap_once(src,
        '\tif state == S.IDLE and atk_lock <= 0.0 and not in_block and _queued_skill == "":\n\t\t_queued_light_t = 0.0\n\t\t_start_attack(_combo_next if _combo_timer > 0.0 else "l1")\n',
        '\tif state == S.IDLE and atk_lock <= 0.0 and not in_block and _queued_skill == "":\n'
        '\t\t_queued_light_t = 0.0\n'
        '\t\tif kit == "assassin" and not on_ground:\n'
        '\t\t\tif nyx_air_strikes < 2: _start_attack("air_l%d" % (nyx_air_strikes + 1))\n'
        '\t\telse:\n'
        '\t\t\t_start_attack(_combo_next if _combo_timer > 0.0 else "l1")\n', rel)
    src = swap_once(src,
        '\tatk = attacks[aid].duplicate(true)\n',
        '\tatk = attacks[aid].duplicate(true)\n'
        '\t# FRG19Q — count at swing START, so every subsequent air cut is separate.\n'
        '\tif kit == "assassin" and aid in ["air_l1", "air_l2"]:\n'
        '\t\tnyx_air_strikes = 1 if aid == "air_l1" else 2\n', rel)
    src = swap_once(src,
        '\t_move(dt)\n\t_vertical(dt)\n\tif state != S.BLOCK:\n',
        '\t_move(dt)\n\t_vertical(dt)\n'
        '\t# FRG19Q — landing restores air charges; interrupted air combos cannot\n'
        '\t# restart a third airborne strike on the ground.\n'
        '\tif kit == "assassin" and on_ground and nyx_air_strikes != 0:\n'
        '\t\tnyx_air_strikes = 0\n'
        '\t\t_combo_next = "l1"\n'
        '\t\t_combo_timer = 0.0\n'
        '\t\tif atk_id in ["air_l1", "air_l2"]:\n'
        '\t\t\t_buffered = false\n'
        '\t\t\tatk["next"] = ""\n'
        '\tif state != S.BLOCK:\n', rel)
    src = swap_once(src,
        'func _start_attack(aid: String) -> void:\n\tatk_power = 1.0\n',
        'func _start_attack(aid: String) -> void:\n'
        '\t# FRG19Q — never allow queued air strikes when back on the ground.\n'
        '\tif kit == "assassin" and aid in ["air_l1", "air_l2"] and on_ground: return\n'
        '\tatk_power = 1.0\n', rel)
    src = swap_once(src,
        'var steer := 1.0 if state == S.IDLE else 0.5 if state == S.BLOCK else 0.4 if state == S.CHARGE else 0.35 if kit == "chainblade" and state == S.ATTACK and atk_id in ["z", "c"] else 0.0\n',
        'var steer := 1.0 if state == S.IDLE else 0.5 if state == S.BLOCK else 0.4 if state == S.CHARGE else 0.63 if kit == "assassin" and not on_ground and state == S.ATTACK and atk_id in ["air_l1", "air_l2"] else 0.35 if kit == "chainblade" and state == S.ATTACK and atk_id in ["z", "c"] else 0.0\n', rel)
    changes[rel] = src.encode("utf-8")

    rel = "scripts/match.gd"
    src = (root / rel).read_text(encoding="utf-8")
    src = swap_once(src,
        '\tvar result := d.receive_hit(attacker, incoming_attack, power)\n',
        '\t# FRG19Q — Phantom Rush stacks increase only projectile/area SKILL damage.\n'
        '\t# Basic light and charged attacks NEVER receive the bonus.\n'
        '\tvar delivered_power: float = power\n'
        '\tif attacker is Fighter and attacker.kit == "assassin" and String(a.get("id", "")) in ["z", "x", "c", "v"] and String(a.get("type", "")) in ["projectile", "strike", "lob"]:\n'
        '\t\tdelivered_power *= 1.0 + float(attacker.nyx_ambush_stacks) * 0.02\n'
        '\tvar result := d.receive_hit(attacker, incoming_attack, delivered_power)\n', rel)
    src = swap_once(src,
        '\tif result in ["hit", "crit", "ko"]:\n\t\td.notify_passive_event("received_hit", attacker if attacker is Fighter else null)\n',
        '\tif result in ["hit", "crit", "ko"]:\n'
        '\t\t# FRG19Q — ONLY an actual Phantom Rush contact earns +2% ranged power.\n'
        '\t\tif attacker is Fighter and attacker.kit == "assassin" and String(a.get("id", "")) == "c":\n'
        '\t\t\tattacker.nyx_ambush_stacks += 1\n'
        '\t\td.notify_passive_event("received_hit", attacker if attacker is Fighter else null)\n', rel)
    changes[rel] = src.encode("utf-8")
    changes["data/browser_nyx_19q.json"] = dump_json({
        "version": VERSION, "character": "nyx", "state": "FIRST PLAYABLE REFINEMENT",
        "source": "https://raw.githubusercontent.com/KimmelDevs/Fight-Royale/main/web/src/game/kits.ts",
        "completed": [
            "Existing Nyx dual-dagger four-light chain and Smoke Step, Shuriken Fan, Phantom Rush retained",
            "Two aerial dagger strikes per jump, individual swing/contact tracking and air steering",
            "Phantom Rush landed hit grants one permanent round-local Ambush stack",
            "Each Ambush stack grants +2% damage to ranged skills only; never basic/charged melee",
            "Venom Fan applies 4s poison on genuinely damaging hits",
            "Ambush value shown beside Nyx's status bar; resets each match",
            "Existing assassin animation library, model fallback and other fighters preserved",
        ],
        "pending": ["Unique airborne dagger poses", "VRM alignment, complete Godot engine playtest"],
    })
    changes["reports/nyx_19q.txt"] = (
        "19Q — Nyx / Shadow Blade\n"
        "Two separate aerial dagger slashes per jump; input buffering and air steering.\n"
        "Phantom Rush (C) real contact = one Ambush stack; +2% ranged skill power per stack.\n"
        "Venom Fan = 5 poisoned shurikens; 4s poison on landed hits.\n"
        "Other fighter kits and gameplay modes unchanged. Godot engine runtime unverified.\n"
    ).encode("utf-8")
    return changes


def digest(blob: bytes | None) -> str | None:
    return hashlib.sha256(blob).hexdigest() if blob is not None else None


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".frg19q-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def install(root: Path, dry_run: bool) -> None:
    if (root / "data/browser_nyx_19q.json").is_file():
        print("19Q already installed. No changes.")
        return
    changes = build(root)  # Preflight EVERYTHING, then write.
    altered = {rel: blob for rel, blob in changes.items()
               if not (root / rel).is_file() or (root / rel).read_bytes() != blob}
    for rel in altered:
        print("Update:", rel)
    if dry_run:
        print("19Q dry run successful. No files changed.")
        return
    backup = (root.parent / (root.name + "_backups") /
              ("nyx_19q_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]))
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "project": str(root), "files": {}}
    for rel, blob in altered.items():
        old = (root / rel).read_bytes() if (root / rel).is_file() else None
        manifest["files"][rel] = {"before": digest(old), "after": digest(blob)}
        if old is not None:
            oldfile = backup / rel
            oldfile.parent.mkdir(parents=True, exist_ok=True)
            oldfile.write_bytes(old)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    completed = []
    try:
        for rel, blob in altered.items():
            atomic_write(root / rel, blob)
            completed.append(rel)
    except BaseException:
        for rel in reversed(completed):
            saved = backup / rel
            if saved.is_file(): atomic_write(root / rel, saved.read_bytes())
            else: (root / rel).unlink(missing_ok=True)
        raise
    print("19Q installed. Backup:", backup)


def restore(root: Path, backup: Path) -> None:
    manifest = read_json(backup, "manifest.json")
    if manifest.get("project") != str(root):
        raise RuntimeError("Backup belongs to a different project")
    for rel, item in manifest["files"].items():
        current = (root / rel).read_bytes() if (root / rel).is_file() else None
        if digest(current) != item["after"]:
            raise RuntimeError("Restore refused; file changed since installation: " + rel)
    for rel, item in manifest["files"].items():
        saved = backup / rel
        if item["before"] is None: (root / rel).unlink(missing_ok=True)
        else: atomic_write(root / rel, saved.read_bytes())
    print("Restored:", backup)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--restore", type=Path)
    args = p.parse_args()
    root = Path.cwd().resolve()
    try:
        if args.restore: restore(root, args.restore.expanduser().resolve())
        else: install(root, args.dry_run)
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
