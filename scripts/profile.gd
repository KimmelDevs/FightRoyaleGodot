extends Node
## Guest profile (autoload "Profile"): gold, diamonds, owned characters and skills, emblem
## levels and loadouts. Saved to user://profile.json. Online accounts can sync this later.

signal changed

const PATH := "user://profile.json"

var gold := 0
var diamonds := 0
var owned: Array = []          ## character ids
var skills: Dictionary = {}    ## char id -> Array of owned extra skill keys
var loadouts: Dictionary = {}  ## char id -> ["z","x","c"]
var emblems: Dictionary = {}   ## emblem id -> level
var last_char := "aster"

func _ready() -> void:
	owned = Data.economy.start_characters.duplicate()
	var f := FileAccess.open(PATH, FileAccess.READ)
	if f:
		var d = JSON.parse_string(f.get_as_text())
		if d is Dictionary:
			gold = int(d.get("gold", 0)); diamonds = int(d.get("diamonds", 0))
			for c in d.get("owned", []): if not c in owned: owned.append(c)
			skills = d.get("skills", {}); loadouts = d.get("loadouts", {}); emblems = d.get("emblems", {})
			last_char = d.get("last_char", last_char)

func save() -> void:
	var f := FileAccess.open(PATH, FileAccess.WRITE)
	f.store_string(JSON.stringify({"gold": gold, "diamonds": diamonds, "owned": owned, "skills": skills,
		"loadouts": loadouts, "emblems": emblems, "last_char": last_char}))
	changed.emit()

func add_gold(n: int) -> void:
	gold += n
	save()

func owns(char_id: String) -> bool:
	return char_id in owned

func buy_character(char_id: String) -> bool:
	var price: int = int(Data.economy.character_price.gold)
	if owns(char_id) or gold < price: return false
	gold -= price
	owned.append(char_id)
	save()
	return true

func loadout(char_id: String) -> Array:
	return loadouts.get(char_id, Data.economy.default_loadout.duplicate())
