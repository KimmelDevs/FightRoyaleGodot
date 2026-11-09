extends Node
## Key bindings (autoload "Keys"). Each action has up to two inputs: a physical key or a mouse
## button. Saved in user://keys.cfg; editable from Settings -> Controls.

const ACTIONS := [
	["up", "Move up / forward"], ["down", "Move down / back"], ["left", "Move left"], ["right", "Move right"],
	["jump", "Jump"], ["attack", "Attack (tap) / charged attack (hold)"], ["block", "Block / shield"],
	["sprint", "Sprint (hold)"], ["dodge", "Dodge (tap)"],  # FRG06 - locomotion and procedural footwork
	["skill1", "Skill 1"], ["skill2", "Skill 2"], ["skill3", "Skill 3"],
]
## Codes: "k:<physical keycode>" or "m:<mouse button index>" ("" = empty slot).
const DEFAULTS := {
	"up": ["k:%d" % KEY_W, "k:%d" % KEY_UP], "down": ["k:%d" % KEY_S, "k:%d" % KEY_DOWN],
	"left": ["k:%d" % KEY_A, "k:%d" % KEY_LEFT], "right": ["k:%d" % KEY_D, "k:%d" % KEY_RIGHT],
	"jump": ["k:%d" % KEY_SPACE, ""], "attack": ["m:%d" % MOUSE_BUTTON_LEFT, ""], "block": ["m:%d" % MOUSE_BUTTON_RIGHT, ""],
	"sprint": ["k:%d" % KEY_SHIFT, ""], "dodge": ["k:%d" % KEY_Q, ""],
	"skill1": ["k:%d" % KEY_Z, ""], "skill2": ["k:%d" % KEY_X, ""], "skill3": ["k:%d" % KEY_C, ""],
}
const RESERVED := [KEY_ESCAPE, KEY_R]
const PATH := "user://keys.cfg"

var bindings: Dictionary = {}

func _ready() -> void:
	bindings = DEFAULTS.duplicate(true)
	var cfg := ConfigFile.new()
	if cfg.load(PATH) == OK:
		for a in DEFAULTS:
			var v = cfg.get_value("keys", a, null)
			if v is Array and v.size() == 2: bindings[a] = v

func save() -> void:
	var cfg := ConfigFile.new()
	for a in bindings: cfg.set_value("keys", a, bindings[a])
	cfg.save(PATH)

func reset() -> void:
	bindings = DEFAULTS.duplicate(true)
	save()

## Bind `code` to a slot, removing it from any other action.
func bind(action: String, slot: int, code: String) -> void:
	if code != "":
		for a in bindings:
			for i in 2:
				if bindings[a][i] == code: bindings[a][i] = ""
	bindings[action][slot] = code
	save()

static func code_of(e: InputEvent) -> String:
	if e is InputEventKey: return "k:%d" % e.physical_keycode
	if e is InputEventMouseButton: return "m:%d" % e.button_index
	return ""

func matches(action: String, e: InputEvent) -> bool:
	var c := code_of(e)
	return c != "" and c in bindings[action]

func held(action: String) -> bool:
	for c in bindings[action]:
		if c == "": continue
		var n := int(c.substr(2))
		if c.begins_with("k:") and Input.is_physical_key_pressed(n): return true
		if c.begins_with("m:") and Input.is_mouse_button_pressed(n): return true
	return false

static func label_of(code: String) -> String:
	if code == "": return "-"
	var n := int(code.substr(2))
	if code.begins_with("m:"):
		return {1: "Left click", 2: "Right click", 3: "Middle click"}.get(n, "Mouse %d" % n)
	return OS.get_keycode_string(n)

func label(action: String) -> String:
	var b: Array = bindings[action]
	return label_of(b[0] if b[0] != "" else b[1])
