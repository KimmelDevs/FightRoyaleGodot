extends Node
## FIGHT_ROYALE_MODES_V02 — only Duel vs CPU and CPU vs CPU.
## All fighters are freely selectable. No store, economy UI, teams or survival.

const MODES := {
	"duel": "Duel vs CPU",
	"cpu_vs_cpu": "CPU vs CPU",
}

var _ui: Control
var _match: Match
var _hud: Hud
var _preview: FighterModel
var _mode := "duel"
var _difficulty := 1
var _char_a := 0
var _char_b := 1
var _pick_side := 0
var _loadout_a: Array = ["z", "x", "c"]
var _loadout_b: Array = ["z", "x", "c"]
var _rebinding: Array = []

func _ready() -> void:
	_char_a = maxi(Data.index_of(Profile.last_char), 0)
	_char_b = (_char_a + 1) % maxi(Data.roster.size(), 1)
	_loadout_a = _saved_loadout(_char_a)
	_loadout_b = _saved_loadout(_char_b)
	var args := OS.get_cmdline_user_args()
	if "--cpu-vs-cpu" in args:
		_mode = "cpu_vs_cpu"
		_start_match()
	elif "--duel" in args:
		_start_match()
	else:
		show_menu()

func _screen() -> VBoxContainer:
	if is_instance_valid(_ui):
		_ui.queue_free()
	_ui = Control.new()
	_ui.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(_ui)
	var bg := ColorRect.new()
	bg.color = Color("#111829")
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	_ui.add_child(bg)
	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	for edge in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + edge, 24)
	_ui.add_child(margin)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 12)
	margin.add_child(v)
	return v

func _title(parent: Node, value: String, font_size: int = 40) -> Label:
	var label := Label.new()
	label.text = value
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", Color("#ffe08a"))
	parent.add_child(label)
	return label

func _text(parent: Node, value: String, font_size: int = 18, color: Color = Color("#d6deef")) -> Label:
	var label := Label.new()
	label.text = value
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	parent.add_child(label)
	return label

func _btn(parent: Node, value: String, action: Callable, width: float = 240.0) -> Button:
	var button := Button.new()
	button.text = value
	button.custom_minimum_size = Vector2(width, 43)
	button.add_theme_font_size_override("font_size", 18)
	if action.is_valid():
		button.pressed.connect(action)
	parent.add_child(button)
	return button

func _saved_loadout(index: int) -> Array:
	if Data.roster.is_empty():
		return ["z", "x", "c"]
	var stored: Array = Profile.loadout(Data.character(index).id)
	if stored.size() != 3:
		return ["z", "x", "c"]
	var out: Array = stored.duplicate()
	for k in out:
		if not k in ["z", "x", "c", "v"]:
			return ["z", "x", "c"]
	if out[0] == out[1] or out[0] == out[2] or out[1] == out[2]:
		return ["z", "x", "c"]
	return out

func show_menu() -> void:
	_end_match()
	var v := _screen()
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	_title(v, "FIGHT ROYALE", 62)
	_text(v, "GODOT EDITION  •  1 VS 1 COMBAT", 20)
	_btn(v, "Duel vs CPU", func(): _mode = "duel"; _pick_side = 0; show_select(), 320)
	_btn(v, "CPU vs CPU", func(): _mode = "cpu_vs_cpu"; _pick_side = 0; show_select(), 320)
	_btn(v, "Settings / Keybinds", show_settings, 320)
	_btn(v, "Quit", func(): get_tree().quit(), 320)
	_text(v, "All fighters are selectable. No shop or currency system.", 14, Color("#a8b7d2"))

func _choose_side(side: int) -> void:
	_pick_side = side
	show_select()

func _choose_character(index: int) -> void:
	if _pick_side == 0:
		_char_a = index
		_loadout_a = _saved_loadout(index)
	else:
		_char_b = index
		_loadout_b = _saved_loadout(index)
	show_select()

func show_select() -> void:
	var v := _screen()
	_title(v, "Choose Fighters  ·  " + MODES[_mode], 38)
	_text(v, "Select a slot, then click a fighter. Both fighters can use the same character.", 16)
	var row := HBoxContainer.new()
	row.size_flags_vertical = Control.SIZE_EXPAND_FILL
	row.add_theme_constant_override("separation", 18)
	v.add_child(row)
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(440, 320)
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	row.add_child(scroll)
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 7)
	grid.add_theme_constant_override("v_separation", 7)
	scroll.add_child(grid)
	for i in Data.roster.size():
		var fighter: Dictionary = Data.roster[i]
		var b := _btn(grid, fighter.look.name, _choose_character.bind(i), 200)
		if i == (_char_a if _pick_side == 0 else _char_b):
			b.modulate = Color("#ffe08a")
	var right := VBoxContainer.new()
	right.custom_minimum_size = Vector2(350, 0)
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(right)
	var name_a := "YOU" if _mode == "duel" else "CPU A"
	var name_b := "OPPONENT" if _mode == "duel" else "CPU B"
	var pick_a := _btn(right, "%s: %s %s" % [name_a, Data.character(_char_a).look.name, "◀" if _pick_side == 0 else ""], _choose_side.bind(0), 310)
	var pick_b := _btn(right, "%s: %s %s" % [name_b, Data.character(_char_b).look.name, "◀" if _pick_side == 1 else ""], _choose_side.bind(1), 310)
	if _pick_side == 0:
		pick_a.modulate = Color("#ffe08a")
	else:
		pick_b.modulate = Color("#ffe08a")
	var chosen: Dictionary = Data.character(_char_a if _pick_side == 0 else _char_b)
	_title(right, chosen.look.name, 30)
	_text(right, "%s  •  %s" % [chosen.title, chosen.role], 15)
	_text(right, chosen.desc, 15)
	var s: Dictionary = chosen.stats
	_text(right, "Power %s  Speed %s  Range %s  Defense %s" % [s.power, s.speed, s.range, s.defense], 14, Color("#9fd8ff"))
	var preview := _preview_box()
	preview.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right.add_child(preview)
	_preview_set(_char_a if _pick_side == 0 else _char_b)
	var nav := HBoxContainer.new()
	v.add_child(nav)
	_btn(nav, "Back", show_menu, 150)
	_btn(nav, "Continue", show_prepare, 190)

func _preview_box() -> SubViewportContainer:
	var box := SubViewportContainer.new()
	box.stretch = true
	box.custom_minimum_size = Vector2(320, 240)
	var viewport := SubViewport.new()
	viewport.size = Vector2i(400, 320)
	viewport.own_world_3d = true
	viewport.transparent_bg = true
	box.add_child(viewport)
	var camera := Camera3D.new()
	camera.position = Vector3(0, 1.0, 3.2)
	camera.fov = 42
	viewport.add_child(camera)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-35, 25, 0)
	viewport.add_child(light)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_CLEAR_COLOR
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color("#e6f0ff")
	env.environment.ambient_light_energy = 0.8
	viewport.add_child(env)
	var holder := Node3D.new()
	holder.name = "PreviewHolder"
	viewport.add_child(holder)
	return box

func _preview_set(index: int) -> void:
	var holder := _ui.find_child("PreviewHolder", true, false) as Node3D
	if holder == null:
		return
	for child in holder.get_children():
		child.queue_free()
	_preview = FighterModel.new()
	holder.add_child(_preview)
	_preview.setup(Data.character(index).look)
	_preview.rotation.y = 0.35

func _skill_changed(chosen: int, side: int, slot: int) -> void:
	var pool := ["z", "x", "c", "v"]
	var new_key: String = pool[chosen]
	var arr: Array = _loadout_a if side == 0 else _loadout_b
	var previous: String = arr[slot]
	var old_position := arr.find(new_key)
	if old_position != -1 and old_position != slot:
		arr[old_position] = previous
	arr[slot] = new_key
	if side == 0:
		_loadout_a = arr
	else:
		_loadout_b = arr
	show_prepare()

func _skill_picker(parent: Node, side: int) -> void:
	var index := _char_a if side == 0 else _char_b
	var fighter: Dictionary = Data.character(index)
	var arr: Array = _loadout_a if side == 0 else _loadout_b
	_title(parent, fighter.look.name + " Skills", 21)
	var attacks: Dictionary = Data.attacks_for(fighter.id)
	var row := HBoxContainer.new()
	parent.add_child(row)
	for slot in 3:
		var options := OptionButton.new()
		options.custom_minimum_size = Vector2(188, 40)
		for key in ["z", "x", "c", "v"]:
			options.add_item("%s: %s" % [key.to_upper(), attacks[key].name])
		options.select(["z", "x", "c", "v"].find(arr[slot]))
		options.item_selected.connect(_skill_changed.bind(side, slot))
		row.add_child(options)

func show_prepare() -> void:
	if Data.roster.is_empty():
		show_menu()
		return
	var v := _screen()
	_title(v, "Match Setup  ·  " + MODES[_mode], 38)
	var a := "You" if _mode == "duel" else "CPU A"
	_text(v, "%s: %s    VS    CPU B: %s" % [a, Data.character(_char_a).look.name, Data.character(_char_b).look.name], 23, Color.WHITE)
	_text(v, "Pick three skills per fighter. The fourth skill is freely available to equip.", 15)
	_skill_picker(v, 0)
	_skill_picker(v, 1)
	_title(v, "AI Difficulty", 23)
	var row := HBoxContainer.new()
	v.add_child(row)
	for i in 3:
		var b := _btn(row, ["Easy", "Normal", "Hard"][i], _choose_difficulty.bind(i), 145)
		if i == _difficulty:
			b.modulate = Color("#ffe08a")
	var nav := HBoxContainer.new()
	v.add_child(nav)
	_btn(nav, "Back to Fighters", show_select, 210)
	_btn(nav, "START FIGHT", _start_match, 230)
	if _mode == "cpu_vs_cpu":
		_text(v, "Spectator mode: both fighters are CPU-controlled. Esc pauses; R rematches.", 15)

func _choose_difficulty(index: int) -> void:
	_difficulty = index
	show_prepare()

func _start_match() -> void:
	if Data.roster.is_empty():
		push_error("Cannot start a match without data/roster.json entries")
		return
	_end_match()
	if is_instance_valid(_ui):
		_ui.queue_free()
		_ui = null
	Profile.last_char = Data.character(_char_a).id
	Profile.loadouts[Data.character(_char_a).id] = _loadout_a.duplicate()
	Profile.loadouts[Data.character(_char_b).id] = _loadout_b.duplicate()
	Profile.save()
	var spectator := _mode == "cpu_vs_cpu"
	var players: Array = [
		{"peer": "cpu_a" if spectator else "local", "name": "CPU A" if spectator else "You", "char": _char_a, "loadout": _loadout_a, "team": 0},
		{"peer": "cpu_b", "name": "CPU B" if spectator else "CPU", "char": _char_b, "loadout": _loadout_b, "team": 1},
	]
	_match = Match.new()
	_match.cfg = {"mode": "duel", "players": players, "local_peer": "spectator" if spectator else "local", "difficulty": _difficulty, "spectator": spectator}
	add_child(_match)
	_hud = Hud.new(_match)
	_hud.rematch.connect(func(): _match.start_round())
	_hud.quit_to_menu.connect(show_menu)
	add_child(_hud)

func _end_match() -> void:
	if is_instance_valid(_hud):
		_hud.queue_free()
	_hud = null
	if is_instance_valid(_match):
		_match.queue_free()
	_match = null

func show_settings() -> void:
	var v := _screen()
	_title(v, "Settings — Controls")
	_text(v, "Click a slot, then press a key or mouse button. Esc and R are reserved.", 16)
	var scroller := ScrollContainer.new()
	scroller.size_flags_vertical = Control.SIZE_EXPAND_FILL
	v.add_child(scroller)
	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 12)
	scroller.add_child(grid)
	for action in Keys.ACTIONS:
		_text(grid, action[1], 17, Color.WHITE)
		for slot in 2:
			var b := _btn(grid, Keys.label_of(Keys.bindings[action[0]][slot]), Callable(), 200)
			b.pressed.connect(_begin_rebind.bind(action[0], slot, b))
	var nav := HBoxContainer.new()
	v.add_child(nav)
	_btn(nav, "Back", show_menu, 160)
	_btn(nav, "Reset Defaults", func(): Keys.reset(); show_settings(), 200)

func _begin_rebind(action: String, slot: int, button: Button) -> void:
	_rebinding = [action, slot]
	button.text = "press a key..."

func _input(event: InputEvent) -> void:
	if _rebinding.is_empty() or not event.is_pressed():
		return
	if event is InputEventKey and (event.keycode in Keys.RESERVED or event.physical_keycode in Keys.RESERVED):
		if event.keycode == KEY_ESCAPE:
			_rebinding.clear()
			show_settings.call_deferred()
		return
	var code := Keys.code_of(event)
	if code.is_empty():
		return
	Keys.bind(_rebinding[0], _rebinding[1], code)
	_rebinding.clear()
	get_viewport().set_input_as_handled()
	show_settings.call_deferred()

func _process(dt: float) -> void:
	if is_instance_valid(_preview):
		_preview.rotation.y += dt * 0.4
