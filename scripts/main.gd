extends Node
## Game shell: main menu -> character select -> prepare (skills, emblem, difficulty) -> match.
## Also hosts the shop and settings (key bindings). Everything is built in code so the
## scene file stays tiny.

const MODES := {
	"duel": "Duel vs CPU",
	"team": "Team vs CPU",
	"survival": "Survival",
}

var _ui: Control
var _match: Match
var _hud: Hud
var _mode := "duel"
var _team_size := 2
var _difficulty := 1
var _char := 0
var _loadout: Array = ["z", "x", "c"]
var _emblem := {"id": "fighter", "level": 1}
var _preview: FighterModel
var _rebinding := []  # [action, slot, button]

func _ready() -> void:
	_char = maxi(Data.index_of(Profile.last_char), 0)
	var args := OS.get_cmdline_user_args()
	if "--duel" in args:
		_start_match()
	else:
		show_menu()

# --- helpers -------------------------------------------------------------------------------

func _screen() -> VBoxContainer:
	if _ui: _ui.queue_free()
	_ui = Control.new()
	_ui.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(_ui)
	var bg := ColorRect.new()
	bg.color = Color("#141a2b")
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	_ui.add_child(bg)
	var m := MarginContainer.new()
	m.set_anchors_preset(Control.PRESET_FULL_RECT)
	for s in ["left", "right", "top", "bottom"]: m.add_theme_constant_override("margin_" + s, 32)
	_ui.add_child(m)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 14)
	m.add_child(v)
	return v

func _title(parent: Node, text: String, size := 40) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", Color("#ffe08a"))
	parent.add_child(l)
	return l

func _text(parent: Node, text: String, size := 18, color := Color("#d6deef")) -> Label:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	parent.add_child(l)
	return l

func _btn(parent: Node, text: String, fn: Callable, w := 260.0) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(w, 46)
	b.add_theme_font_size_override("font_size", 20)
	b.pressed.connect(fn)
	parent.add_child(b)
	return b

func _wallet(parent: Node) -> void:
	_text(parent, "Gold %d    Diamonds %d" % [Profile.gold, Profile.diamonds], 18, Color("#ffd47a"))

# --- menu ----------------------------------------------------------------------------------

func show_menu() -> void:
	_end_match()
	var v := _screen()
	_title(v, "FIGHT ROYALE", 64)
	_wallet(v)
	for m in MODES:
		_btn(v, MODES[m], func(): _mode = m; show_select())
	_btn(v, "Shop", show_shop)
	_btn(v, "Settings", show_settings)
	_btn(v, "Quit", func(): get_tree().quit())
	_text(v, "3D characters made with VRoid Studio. Aster, Vesper, Garrick, Kaede, Rook, Raven and Ember models by Fruit.", 13, Color("#8e9ab5"))

# --- character select ----------------------------------------------------------------------

func show_select() -> void:
	var v := _screen()
	_title(v, "Choose your fighter - " + MODES[_mode])
	var row := HBoxContainer.new()
	row.size_flags_vertical = Control.SIZE_EXPAND_FILL
	row.add_theme_constant_override("separation", 24)
	v.add_child(row)
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 10)
	grid.add_theme_constant_override("v_separation", 10)
	row.add_child(grid)
	var order := range(Data.roster.size())
	order.sort_custom(func(a, b): return int(Profile.owns(Data.roster[a].id)) > int(Profile.owns(Data.roster[b].id)))
	var info := VBoxContainer.new()
	info.custom_minimum_size = Vector2(340, 0)
	var preview := _preview_box()
	row.add_child(preview)
	row.add_child(info)
	for i in order:
		var c: Dictionary = Data.roster[i]
		var own: bool = Profile.owns(c.id)
		var b := _btn(grid, c.look.name + ("" if own else "  (locked)"), func(): _char = i; _show_char(info); _preview_set(i), 200)
		if not own: b.modulate = Color(0.7, 0.7, 0.75)
	_show_char(info)
	_preview_set(_char)
	var nav := HBoxContainer.new()
	v.add_child(nav)
	_btn(nav, "Back", show_menu, 160)
	_btn(nav, "Next", func():
		if Profile.owns(Data.roster[_char].id): show_prepare(), 160)

func _show_char(info: VBoxContainer) -> void:
	for c in info.get_children(): c.queue_free()
	var c: Dictionary = Data.roster[_char]
	_title(info, c.look.name, 34)
	_text(info, c.title + " - " + c.role, 18, Color.WHITE)
	_text(info, c.desc)
	var s: Dictionary = c.stats
	_text(info, "Power %d   Speed %d   Range %d   Defense %d" % [s.power, s.speed, s.range, s.defense], 16, Color("#9fd8ff"))
	if not Profile.owns(c.id):
		var price := int(Data.economy.character_price.gold)
		_btn(info, "Unlock for %d gold" % price, func():
			if Profile.buy_character(c.id): show_select())
		_wallet(info)

func _preview_box() -> SubViewportContainer:
	var box := SubViewportContainer.new()
	box.stretch = true
	box.custom_minimum_size = Vector2(360, 480)
	var vp := SubViewport.new()
	vp.own_world_3d = true
	vp.transparent_bg = true
	box.add_child(vp)
	var cam := Camera3D.new()
	cam.position = Vector3(0, 1.0, 3.1)
	cam.fov = 40
	vp.add_child(cam)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-35, 25, 0)
	vp.add_child(light)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_CLEAR_COLOR
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color("#e6f0ff")
	env.environment.ambient_light_energy = 0.8
	vp.add_child(env)
	var holder := Node3D.new()
	holder.name = "Holder"
	vp.add_child(holder)
	return box

func _preview_set(i: int) -> void:
	var holder := _ui.find_child("Holder", true, false) as Node3D
	if holder == null: return
	for c in holder.get_children(): c.queue_free()
	_preview = FighterModel.new()
	holder.add_child(_preview)
	_preview.setup(Data.roster[i].look)
	_preview.rotation.y = 0.35

# --- prepare -------------------------------------------------------------------------------

func show_prepare() -> void:
	var c: Dictionary = Data.roster[_char]
	Profile.last_char = c.id
	Profile.save()
	_loadout = Profile.loadout(c.id)
	var v := _screen()
	_title(v, "Prepare - " + c.look.name)
	var atks := Data.attacks_for(c.id)
	_text(v, "Skills (pick 3 of 4; the 4th is swapped in for the slot you click):", 18, Color.WHITE)
	var sk := HBoxContainer.new(); v.add_child(sk)
	for k in ["z", "x", "c", "v"]:
		var on: bool = k in _loadout
		var b := _btn(sk, "%s%s" % [atks[k].name, "  *" if on else ""], func():
			if k in _loadout: return
			var unused := ["z", "x", "c", "v"].filter(func(x): return not x in _loadout)
			_loadout[["z", "x", "c"].find(unused[0]) if unused[0] != "v" else 2] = k
			Profile.loadouts[c.id] = _loadout.duplicate(); Profile.save(); show_prepare(), 230)
		b.tooltip_text = "%s - dmg %d, cooldown %ss" % [atks[k].name, int(atks[k].dmg), str(atks[k].cd)]
		if on: b.modulate = Color("#ffe08a")
	_text(v, "Emblem:", 18, Color.WHITE)
	var em := HBoxContainer.new(); v.add_child(em)
	for e in Data.economy.emblems:
		var b := _btn(em, e.name if e.has("name") else e.id, func(): _emblem = {"id": e.id, "level": int(Profile.emblems.get(e.id, 1))}; show_prepare(), 150)
		if _emblem.id == e.id: b.modulate = Color("#ffe08a")
	_text(v, "Difficulty:", 18, Color.WHITE)
	var df := HBoxContainer.new(); v.add_child(df)
	for i in 3:
		var b := _btn(df, ["Easy", "Normal", "Hard"][i], func(): _difficulty = i; show_prepare(), 130)
		if _difficulty == i: b.modulate = Color("#ffe08a")
	if _mode == "team":
		_text(v, "Team size:", 18, Color.WHITE)
		var ts := HBoxContainer.new(); v.add_child(ts)
		for n in [2, 3, 4]:
			var b := _btn(ts, "%dv%d" % [n, n], func(): _team_size = n; show_prepare(), 100)
			if _team_size == n: b.modulate = Color("#ffe08a")
	var nav := HBoxContainer.new(); v.add_child(nav)
	_btn(nav, "Back", show_select, 160)
	_btn(nav, "FIGHT!", _start_match, 200)

# --- match ---------------------------------------------------------------------------------

func _start_match() -> void:
	if _ui: _ui.queue_free(); _ui = null
	_end_match()
	var me := {"peer": "local", "name": "You", "char": _char, "loadout": _loadout, "emblem": _emblem, "team": 0}
	var players: Array = [me]
	var pool := range(Data.roster.size()).filter(func(i): return i != _char)
	pool.shuffle()
	if _mode == "team":
		for i in _team_size * 2 - 1:
			var team := 0 if i < _team_size - 1 else 1
			players.append({"peer": "cpu%d" % i, "name": "CPU", "char": pool[i % pool.size()], "team": team})
	else:
		players.append({"peer": "cpu", "name": "CPU", "char": pool[0], "team": 1})
	_match = Match.new()
	_match.cfg = {"mode": "team" if _mode == "team" else "duel", "players": players, "local_peer": "local", "difficulty": _difficulty}
	add_child(_match)
	_hud = Hud.new(_match)
	_hud.rematch.connect(func(): _match.start_round())
	_hud.quit_to_menu.connect(show_menu)
	add_child(_hud)

func _end_match() -> void:
	if _hud: _hud.queue_free(); _hud = null
	if _match: _match.queue_free(); _match = null

# --- shop ----------------------------------------------------------------------------------

func show_shop() -> void:
	var v := _screen()
	_title(v, "Shop")
	_wallet(v)
	_text(v, "Fighters", 22, Color.WHITE)
	var g := GridContainer.new(); g.columns = 4; v.add_child(g)
	for c in Data.roster:
		var own: bool = Profile.owns(c.id)
		var b := _btn(g, c.look.name + ("  owned" if own else "  %d g" % int(Data.economy.character_price.gold)), func():
			if Profile.buy_character(c.id): show_shop(), 220)
		b.disabled = own
	_text(v, "Emblems (upgrade: 1000 gold x level)", 22, Color.WHITE)
	var eg := GridContainer.new(); eg.columns = 3; v.add_child(eg)
	for e in Data.economy.emblems:
		var lvl: int = int(Profile.emblems.get(e.id, 1))
		var cost: int = 1000 * lvl
		var b := _btn(eg, "%s  Lv %d  (%d g)" % [e.get("name", e.id), lvl, cost], func():
			if Profile.gold >= cost and lvl < int(Data.economy.emblem_max):
				Profile.gold -= cost; Profile.emblems[e.id] = lvl + 1; Profile.save(); show_shop(), 280)
		b.disabled = lvl >= int(Data.economy.emblem_max)
	_btn(v, "Back", show_menu, 160)

# --- settings ------------------------------------------------------------------------------

func show_settings() -> void:
	var v := _screen()
	_title(v, "Settings - Controls")
	_text(v, "Click a slot, then press a key or mouse button. Esc and R are reserved.", 16)
	var g := GridContainer.new(); g.columns = 3
	g.add_theme_constant_override("h_separation", 12)
	v.add_child(g)
	for a in Keys.ACTIONS:
		_text(g, a[1], 17, Color.WHITE)
		for slot in 2:
			var b := _btn(g, Keys.label_of(Keys.bindings[a[0]][slot]), Callable(), 200)
			b.pressed.connect(func(): _rebinding = [a[0], slot, b]; b.text = "press...")
	var nav := HBoxContainer.new(); v.add_child(nav)
	_btn(nav, "Back", show_menu, 160)
	_btn(nav, "Reset defaults", func(): Keys.reset(); show_settings(), 200)

func _input(e: InputEvent) -> void:
	if _rebinding.is_empty() or not e.is_pressed(): return
	if e is InputEventKey and (e.keycode in Keys.RESERVED or e.physical_keycode in Keys.RESERVED):
		if e.keycode == KEY_ESCAPE: _rebinding = []; show_settings()
		return
	var code := Keys.code_of(e)
	if code == "": return
	Keys.bind(_rebinding[0], _rebinding[1], code)
	_rebinding = []
	get_viewport().set_input_as_handled()
	show_settings.call_deferred()

func _process(dt: float) -> void:
	if is_instance_valid(_preview): _preview.rotation.y += dt * 0.4
