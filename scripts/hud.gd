class_name Hud
extends CanvasLayer
## In-match HUD: HP/guard bars, team lists, skill slots with cooldowns, ATK rest and DASH,
## READY/FIGHT banners, the result screen and the Esc pause menu.

signal rematch
signal quit_to_menu

var match_node: Match
var _me_bar: Control
var _other_bar: Control
var _side_list: VBoxContainer
var _slots: HBoxContainer
var _banner: Label
var _banner_sub: Label
var _banner_t := 0.0
var _over: PanelContainer
var _over_title: Label
var _over_sub: Label
var _pause: PanelContainer

func _init(m: Match) -> void:
	match_node = m

func _ready() -> void:
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)
	_me_bar = _bar_block(root, false)
	_other_bar = _bar_block(root, true)
	_side_list = VBoxContainer.new()
	_side_list.position = Vector2(16, 96)
	root.add_child(_side_list)
	_slots = HBoxContainer.new()
	_slots.add_theme_constant_override("separation", 8)
	_slots.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_slots.position = Vector2(-220, -86)
	_slots.size = Vector2(440, 70)
	_slots.alignment = BoxContainer.ALIGNMENT_CENTER
	root.add_child(_slots)
	_banner = _label(root, 72, Color.WHITE)
	_banner.set_anchors_preset(Control.PRESET_CENTER)
	_banner.position = Vector2(-400, -120); _banner.size = Vector2(800, 90)
	_banner_sub = _label(root, 26, Color("#e8ecf6"))
	_banner_sub.set_anchors_preset(Control.PRESET_CENTER)
	_banner_sub.position = Vector2(-400, -30); _banner_sub.size = Vector2(800, 40)
	_over = _panel(root)
	var ov := VBoxContainer.new(); ov.add_theme_constant_override("separation", 12)
	_over.add_child(ov)
	_over_title = _label(ov, 56, Color.WHITE)
	_over_sub = _label(ov, 20, Color("#e8ecf6"))
	ov.add_child(_button("Rematch (R)", func(): rematch.emit()))
	ov.add_child(_button("Main menu", func(): quit_to_menu.emit()))
	_over.hide()
	_pause = _panel(root)
	var pv := VBoxContainer.new(); pv.add_theme_constant_override("separation", 12)
	_pause.add_child(pv)
	_label(pv, 44, Color.WHITE).text = "PAUSED"
	pv.add_child(_button("Resume (Esc)", func(): set_paused(false)))
	pv.add_child(_button("Restart", func(): set_paused(false); rematch.emit()))
	pv.add_child(_button("Quit to menu", func(): set_paused(false); quit_to_menu.emit()))
	_pause.hide()
	match_node.ui_event.connect(_on_event)

func _label(parent: Node, size: int, color: Color) -> Label:
	var l := Label.new()
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	l.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.85))
	l.add_theme_constant_override("outline_size", 8)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(l)
	return l

func _panel(parent: Control) -> PanelContainer:
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.06, 0.08, 0.14, 0.86)
	sb.set_corner_radius_all(14)
	sb.set_content_margin_all(28)
	p.add_theme_stylebox_override("panel", sb)
	p.set_anchors_preset(Control.PRESET_CENTER)
	p.grow_horizontal = Control.GROW_DIRECTION_BOTH
	p.grow_vertical = Control.GROW_DIRECTION_BOTH
	p.custom_minimum_size = Vector2(380, 0)
	parent.add_child(p)
	return p

func _button(text: String, fn: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(0, 44)
	b.add_theme_font_size_override("font_size", 20)
	b.pressed.connect(fn)
	return b

## Name + HP bar + guard bar, anchored top-left or top-right.
func _bar_block(root: Control, right: bool) -> Control:
	var box := VBoxContainer.new()
	box.size = Vector2(380, 70)
	if right:
		box.set_anchors_preset(Control.PRESET_TOP_RIGHT)
		box.position = Vector2(-396, 16)
	else:
		box.position = Vector2(16, 16)
	var name := _label(box, 20, Color.WHITE)
	name.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT if right else HORIZONTAL_ALIGNMENT_LEFT
	name.name = "Name"
	var hp := _progress(Color("#e85d5d"), 18); hp.name = "Hp"; box.add_child(hp)
	var gd := _progress(Color("#7fc4ff"), 8); gd.name = "Guard"; box.add_child(gd)
	if right:
		hp.fill_mode = ProgressBar.FILL_END_TO_BEGIN
		gd.fill_mode = ProgressBar.FILL_END_TO_BEGIN
	root.add_child(box)
	return box

func _progress(color: Color, h: float) -> ProgressBar:
	var p := ProgressBar.new()
	p.show_percentage = false
	p.custom_minimum_size = Vector2(0, h)
	var bg := StyleBoxFlat.new(); bg.bg_color = Color(0, 0, 0, 0.55); bg.set_corner_radius_all(4)
	var fg := StyleBoxFlat.new(); fg.bg_color = color; fg.set_corner_radius_all(4)
	p.add_theme_stylebox_override("background", bg)
	p.add_theme_stylebox_override("fill", fg)
	return p

func _fill(box: Control, info: Dictionary) -> void:
	box.visible = not info.is_empty()
	if info.is_empty(): return
	(box.get_node("Name") as Label).text = "%s  %d / %d" % [info.name, int(ceil(info.hp)), int(info.max_hp)]
	var hp: ProgressBar = box.get_node("Hp"); hp.max_value = info.max_hp; hp.value = info.hp
	var gd: ProgressBar = box.get_node("Guard"); gd.max_value = info.max_guard; gd.value = info.guard

func set_paused(p: bool) -> void:
	match_node.paused = p
	_pause.visible = p

func _unhandled_input(e: InputEvent) -> void:
	if e is InputEventKey and e.pressed and not e.echo:
		if e.keycode == KEY_ESCAPE and not _over.visible:
			set_paused(not match_node.paused)
			get_viewport().set_input_as_handled()
		elif e.keycode == KEY_R and match_node.can_restart:
			rematch.emit()

func _on_event(e: Dictionary) -> void:
	match e.type:
		"banner":
			_banner.text = e.text
			_banner.add_theme_color_override("font_color", e.color)
			_banner_sub.text = e.get("sub", "")
			_banner_t = 1.1
			_over.hide()
		"over":
			_over_title.text = e.text
			_over_title.add_theme_color_override("font_color", e.color)
			_over_sub.text = e.sub
			_over.show()
		"reward":
			if e.peer == match_node.cfg.local_peer and has_node("/root/Profile"):
				get_node("/root/Profile").add_gold(int(e.gold))

func _process(dt: float) -> void:
	_banner_t -= dt
	var a := clampf(_banner_t / 0.3, 0.0, 1.0)
	_banner.modulate.a = a; _banner_sub.modulate.a = a
	var h := match_node.hud()
	_fill(_me_bar, h.me)
	_fill(_other_bar, h.other)
	_list(h)
	_skills(h)

func _list(h: Dictionary) -> void:
	var rows: Array = []
	for t in h.team: rows.append([t, Color("#8fd0ff")])
	for t in h.foes: rows.append([t, Color("#ff9a9a")])
	while _side_list.get_child_count() < rows.size(): _label(_side_list, 16, Color.WHITE).horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	for i in _side_list.get_child_count():
		var l: Label = _side_list.get_child(i)
		l.visible = i < rows.size()
		if not l.visible: continue
		var info: Dictionary = rows[i][0]
		l.text = "%s  %s" % [info.name, "DOWN" if info.down else "%d" % int(ceil(info.hp))]
		l.add_theme_color_override("font_color", Color(0.6, 0.6, 0.6) if info.down else rows[i][1])

func _skills(h: Dictionary) -> void:
	var slots: Array = []
	for s in h.skills:
		slots.append([Keys.label("skill%d" % (["z", "x", "c"].find(s.key) + 1)), s.name, s.cd, s.max])
	if not h.atk_lock.is_empty(): slots.append(["ATK", "Rest", h.atk_lock.t, h.atk_lock.max])
	if not h.dash.is_empty(): slots.append(["2x dir", "Dash", h.dash.t, h.dash.max])
	while _slots.get_child_count() < slots.size(): _slots.add_child(_slot())
	for i in _slots.get_child_count():
		var c: Control = _slots.get_child(i)
		c.visible = i < slots.size()
		if not c.visible: continue
		var s: Array = slots[i]
		(c.get_node("V/Key") as Label).text = s[0]
		(c.get_node("V/Name") as Label).text = s[1]
		var cd: float = s[2]
		(c.get_node("V/Cd") as Label).text = "%.1f" % cd if cd > 0.05 else ""
		c.modulate = Color(0.55, 0.55, 0.6) if cd > 0.05 else Color.WHITE

func _slot() -> PanelContainer:
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new(); sb.bg_color = Color(0.05, 0.07, 0.12, 0.8); sb.set_corner_radius_all(8); sb.set_content_margin_all(6)
	p.add_theme_stylebox_override("panel", sb)
	p.custom_minimum_size = Vector2(92, 64)
	var v := VBoxContainer.new(); v.name = "V"; v.add_theme_constant_override("separation", 0)
	p.add_child(v)
	_label(v, 13, Color("#ffd47a")).name = "Key"
	_label(v, 14, Color.WHITE).name = "Name"
	_label(v, 18, Color("#9fd8ff")).name = "Cd"
	return p
