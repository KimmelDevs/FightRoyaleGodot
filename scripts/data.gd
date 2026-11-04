extends Node
## Game data (autoload "Data"): roster, kit stats, attacks/skills, economy.
## Loaded from res://data/*.json (exported from the web game; edit the JSON to balance).

var roster: Array = []
var stats: Dictionary = {}
var attacks: Dictionary = {}
var economy: Dictionary = {}
var by_id: Dictionary = {}

func _ready() -> void:
	roster = _load("roster")
	stats = _load("stats")
	attacks = _load("attacks")
	economy = _load("economy")
	for c in roster:
		by_id[c.id] = c

func _load(name: String) -> Variant:
	var txt := FileAccess.get_file_as_string("res://data/%s.json" % name)
	var v: Variant = JSON.parse_string(txt)
	assert(v != null, "bad json: " + name)
	return v

func character(i: int) -> Dictionary:
	return roster[clampi(i, 0, roster.size() - 1)]

func index_of(id: String) -> int:
	for i in roster.size():
		if roster[i].id == id:
			return i
	return -1

## Attack table for a fighter (l1.., heavy, z, x, c, v), duplicated so callers can modify it.
func attacks_for(char_id: String) -> Dictionary:
	return attacks[char_id].duplicate(true)
