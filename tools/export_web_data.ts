// Exports the web game's data (roster, kit stats, attacks/skills, poses, economy, emblems)
// to JSON for the Godot game. Run from the web repo so its node_modules resolve:
//   cd ../fight-royale/web && npx tsx ../../fight-royale-godot/tools/export_web_data.ts
import { writeFileSync, mkdirSync } from "node:fs";
import { CHARACTERS } from "../../fight-royale/web/src/game/roster";
import * as Kits from "../../fight-royale/web/src/game/kits";
import * as Eco from "../../fight-royale/web/src/game/economy";

const out = new URL("../data/", import.meta.url);
mkdirSync(out, { recursive: true });
const save = (name: string, data: unknown) => writeFileSync(new URL(name, out), JSON.stringify(data, null, 1));

save("roster.json", CHARACTERS);
save("stats.json", Kits.STATS);

const kits = [...new Set(CHARACTERS.map((c) => c.look.kit))];
const attacks: Record<string, Record<string, unknown>> = {};
for (const c of CHARACTERS) attacks[c.id] = Kits.attacks(c.look.kit, c.look.element);
save("attacks.json", attacks);

const poses: Record<string, unknown> = {};
for (const k of kits) poses[k] = Kits.poses(k);
save("poses.json", poses);

save("economy.json", {
  start_characters: Eco.START_CHARACTERS, character_price: Eco.CHARACTER_PRICE, skill_price: Eco.SKILL_PRICE,
  win_gold: Eco.WIN_GOLD, max_bet: Eco.MAX_BET, mob_gold: Eco.MOB_GOLD, emblem_max: Eco.EMBLEM_MAX,
  default_loadout: Eco.DEFAULT_LOADOUT,
  emblems: Eco.EMBLEMS.map((e) => ({ id: e.id, name: e.name, per_level: e.bonus(1), desc1: e.desc(1) })),
});
console.log("exported", CHARACTERS.length, "fighters,", kits.length, "kits");
