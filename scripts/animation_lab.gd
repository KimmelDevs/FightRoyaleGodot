extends Control
## Update 16A - visual humanoid joint inspector and locomotion profile editor.
## Uses the real FighterModel, imported VRMs, existing kit animations and MotionLayer.
## Click a colored skeleton marker or use the bone picker, then rotate via X/Y/Z sliders.

const Profiles = preload("res://scripts/animation_lab_profiles.gd")
const RIG = preload("res://scripts/rig_mapper.gd")
# FRG16B - combat choreography
const MODES := ["idle", "walk", "run", "attack", "charge", "block", "hit", "stagger", "dodge", "jump", "win"]

var _character: OptionButton
var _state: OptionButton
var _bone: OptionButton
var _axis: Array[HSlider] = []
var _axis_values: Array[Label] = []
var _gait: Dictionary = {}
var _info: Label
var _marker_info: Label
var _view: SubViewport
var _view_box: SubViewportContainer
var _world: Node3D
var _camera: Camera3D
var _model: FighterModel
var _marker_nodes: Dictionary = {}
var _joint_roles: Array[String] = []
var _selected_char := ""
var _selected_bone := ""
var _selected_state := "idle"
var _profile: Dictionary = {}
var _dirty := false
var _turning := false
var _yaw := 18.0
var _gait_running := true
# FRG16D - animation lab preview timeline
var _frg16d_elapsed := 0.0
var _frg16d_duration := 1.10
var _frg16d_playing := true
var _frg16d_loop := true
var _frg16d_speed := 1.0
var _frg16d_bar: HSlider
var _frg16d_label: Label
var _frg16d_play_button: Button
var _frg16d_loop_button: Button
var _frg16d_speed_select: OptionButton
# FRG16E - animation lab viewport inspector
var _frg16e_orbit_yaw := 0.0
var _frg16e_orbit_pitch := 8.0
var _frg16e_distance := 4.2
var _frg16e_target := Vector3(0.0, 1.12, 0.0)
var _frg16e_dragging := false
var _frg16e_markers_visible := true
var _frg16e_labels_visible := false
var _frg16e_markers_button: Button
var _frg16e_labels_button: Button
# FRG16C - animation lab pose tools
# FRG16C: temporary history in the editor; only Save Fighter writes to disk.
const FRG16C_HISTORY_LIMIT := 48
var _frg16c_undo_history: Array[Dictionary] = []
var _frg16c_redo_history: Array[Dictionary] = []
var _frg16c_clipboard: Dictionary = {}
var _frg16c_clipboard_valid := false
var _frg16c_clipboard_source := ""
var _frg16c_drag_active := false
var _frg16c_drag_recorded := false

func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	_build_ui()
	if Data.roster.is_empty():
		_info.text = "No fighters found in data/roster.json"
		return
	_character.select(0)
	_change_character(0)

func _style_text(parent: Node, label_text: String, font_size: int = 16, color: Color = Color("#dce6fa")) -> Label:
	var label := Label.new()
	label.text = label_text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	parent.add_child(label)
	return label

func _button(parent: Node, caption: String, callback: Callable) -> Button:
	var btn := Button.new()
	btn.text = caption
	btn.custom_minimum_size = Vector2(0, 34)
	parent.add_child(btn)
	btn.pressed.connect(callback)
	return btn

func _build_ui() -> void:
	var background := ColorRect.new()
	background.color = Color("#101729")
	background.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(background)
	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 16)
	add_child(margin)
	var layout := HBoxContainer.new()
	layout.add_theme_constant_override("separation", 16)
	margin.add_child(layout)
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(370, 0)
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	layout.add_child(scroll)
	var panel := VBoxContainer.new()
	panel.custom_minimum_size = Vector2(342, 0)
	panel.add_theme_constant_override("separation", 10)
	scroll.add_child(panel)
	_style_text(panel, "ANIMATION LAB", 29, Color("#ffe6a6"))
	_style_text(panel, "Edit joints for locomotion AND combat. Actions use additive offsets over kit animations.", 13)
	_style_text(panel, "Fighter", 15)
	_character = OptionButton.new()
	panel.add_child(_character)
	for character in Data.roster:
		_character.add_item(String(character.look.get("name", character.id)))
	_character.item_selected.connect(_change_character)
	_style_text(panel, "Animation state", 15)
	_state = OptionButton.new()
	panel.add_child(_state)
	for mode in MODES:
		_state.add_item(mode.capitalize())
	_state.item_selected.connect(_change_state)
	_style_text(panel, "Joint (click a marker in the preview, or choose here)", 14)
	_bone = OptionButton.new()
	panel.add_child(_bone)
	_bone.item_selected.connect(_change_bone)
	for axis in 3:
		var head := HBoxContainer.new()
		panel.add_child(head)
		_style_text(head, ["Pitch / X", "Yaw / Y", "Roll / Z"][axis], 14)
		var val := _style_text(head, "0.0°", 14, Color("#a8d9ff"))
		val.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		val.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		_axis_values.append(val)
		var slider := HSlider.new()
		slider.min_value = -90.0
		slider.max_value = 90.0
		slider.step = 0.5
		slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		panel.add_child(slider)
		_axis.append(slider)
		slider.value_changed.connect(_on_axis.bind(axis))
		slider.drag_started.connect(_frg16c_drag_start)
		slider.drag_ended.connect(_frg16c_drag_end)
	_style_text(panel, "Walk cycle controls", 18, Color("#ffe6a6"))
	for field in ["stride", "knee", "arms", "bob"]:
		var head := HBoxContainer.new()
		panel.add_child(head)
		_style_text(head, {"stride": "Stride length", "knee": "Knee lift", "arms": "Arm swing", "bob": "Hip bounce"}[field], 14)
		var value := _style_text(head, "1.00x", 14, Color("#a8d9ff"))
		value.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		value.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		var slider := HSlider.new()
		slider.min_value = 0.0
		slider.max_value = 2.0
		slider.step = 0.05
		panel.add_child(slider)
		_gait[field] = [slider, value]
		slider.value_changed.connect(_on_gait.bind(field))
		slider.drag_started.connect(_frg16c_drag_start)
		slider.drag_ended.connect(_frg16c_drag_end)
	var actions := HBoxContainer.new()
	panel.add_child(actions)
	_button(actions, "Save Fighter", _save)
	_button(actions, "Reset State", _reset_state)
	_button(actions, "Reset All", _reset_all)
	# FRG16C: editing tools work with ALL 16B animation states, not just walk/run.
	_style_text(panel, "Pose tools (Ctrl+Z / Ctrl+Y)", 15, Color("#ffe6a6"))
	var history_tools := HBoxContainer.new()
	panel.add_child(history_tools)
	_button(history_tools, "Undo", _frg16c_undo)
	_button(history_tools, "Redo", _frg16c_redo)
	var clipboard_tools := HBoxContainer.new()
	panel.add_child(clipboard_tools)
	_button(clipboard_tools, "Copy Pose", _frg16c_copy_pose)
	_button(clipboard_tools, "Paste Pose", _frg16c_paste_pose)
	var mirror_tools := HBoxContainer.new()
	panel.add_child(mirror_tools)
	_button(mirror_tools, "Mirror L/R", _frg16c_mirror_pose)
	_button(mirror_tools, "Reset Joint", _frg16c_reset_joint)
	_info = _style_text(panel, "Changes are previews until Save Fighter is pressed.", 13, Color("#b8d6c8"))
	_button(panel, "Back to Main Menu", _back)
	var right := VBoxContainer.new()
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.size_flags_vertical = Control.SIZE_EXPAND_FILL
	layout.add_child(right)
	_marker_info = _style_text(right, "Blue dots = selectable joints · Gold = selected joint", 14, Color("#ffe6a6"))
	_view_box = SubViewportContainer.new()
	_view_box.stretch = true
	_view_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_view_box.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_view_box.custom_minimum_size = Vector2(500, 420)
	right.add_child(_view_box)
	_view_box.gui_input.connect(_viewport_input)
	_view = SubViewport.new()
	_view.size = Vector2i(900, 670)
	_view.own_world_3d = true
	_view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_view_box.add_child(_view)
	_world = Node3D.new()
	_view.add_child(_world)
	_camera = Camera3D.new()
	_camera.fov = 40.0
	_camera.position = Vector3(0.0, 1.25, 4.2)
	_world.add_child(_camera)
	_camera.make_current()
	_frg16e_update_camera()
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45, 28, 0)
	light.light_energy = 1.0
	_world.add_child(light)
	var fill := OmniLight3D.new()
	fill.position = Vector3(-2.0, 2.8, 2.2)
	fill.light_energy = 0.7
	_world.add_child(fill)
	var world_env := WorldEnvironment.new()
	world_env.environment = Environment.new()
	world_env.environment.background_mode = Environment.BG_COLOR
	world_env.environment.background_color = Color("#24344b")
	world_env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world_env.environment.ambient_light_color = Color("#d3e1f7")
	world_env.environment.ambient_light_energy = 0.7
	_world.add_child(world_env)
	var ground := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(20, 20)
	ground.mesh = plane
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color("#354958")
	ground.material_override = mat
	_world.add_child(ground)
	var tools := HBoxContainer.new()
	right.add_child(tools)
	_button(tools, "Front", func(): _yaw = 0.0)
	_button(tools, "Side", func(): _yaw = 90.0)
	_button(tools, "Back", func(): _yaw = 180.0)
	_button(tools, "Reset View", _frg16e_reset_view)
	var inspector_tools := HBoxContainer.new()
	right.add_child(inspector_tools)
	_frg16e_markers_button = _button(inspector_tools, "Joints: ON", _frg16e_toggle_markers)
	_frg16e_labels_button = _button(inspector_tools, "Names: OFF", _frg16e_toggle_names)
	_style_text(right, "Preview: right-drag to orbit, mouse wheel to zoom, left-click a joint to edit.", 13)
	# FRG16D: timeline controls are preview-only; no profile writes or undo history.
	var playback := HBoxContainer.new()
	right.add_child(playback)
	_frg16d_play_button = _button(playback, "Pause", _frg16d_toggle)
	_button(playback, "◀ Frame", func(): _frg16d_step(-1))
	_button(playback, "Frame ▶", func(): _frg16d_step(1))
	_frg16d_loop_button = _button(playback, "Loop: ON", _frg16d_toggle_loop)
	_frg16d_speed_select = OptionButton.new()
	playback.add_child(_frg16d_speed_select)
	for caption in ["0.25x", "0.5x", "1x", "1.5x", "2x"]:
		_frg16d_speed_select.add_item(caption)
	_frg16d_speed_select.select(2)
	_frg16d_speed_select.item_selected.connect(_frg16d_set_speed)
	_frg16d_label = _style_text(right, "0.00s / 1.10s (0%)", 13, Color("#a8d9ff"))
	_frg16d_bar = HSlider.new()
	_frg16d_bar.min_value = 0.0
	_frg16d_bar.max_value = 1.0
	_frg16d_bar.step = 0.005
	_frg16d_bar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.add_child(_frg16d_bar)
	_frg16d_bar.value_changed.connect(_frg16d_scrub_to)
	_style_text(right, "Preview walk/run or combat motion; drag the timeline to inspect joint positions. Editing remains on the left.", 13)

func _change_character(index: int) -> void:
	if index < 0 or index >= Data.roster.size():
		return
	var fighter: Dictionary = Data.character(index)
	_selected_char = String(fighter.id)
	_profile = Profiles.load_for(_selected_char)
	_frg16c_reset_history()
	if _profile.is_empty():
		_profile = Profiles.new_profile()
	_dirty = false
	for marker in _marker_nodes.values():
		if is_instance_valid(marker):
			(marker as Node).queue_free()
	_marker_nodes.clear()
	if is_instance_valid(_model):
		_model.queue_free()
	_model = FighterModel.new()
	_model.character_id = _selected_char
	_world.add_child(_model)
	_model.setup(fighter.look)
	_joint_roles.clear()
	_bone.clear()
	if _model.skeleton != null:
		for role in RIG.BONES:
			var resolved: String = RIG.name_for(_model.skeleton, String(role), _model.rig_profile)
			if resolved.is_empty():
				continue
			_joint_roles.append(String(role))
			_bone.add_item(String(role))
			_create_marker(String(role))
	else:
		_info.text = "This fighter is a placeholder. Import a rigged VRM to edit its joints."
	_change_state(_state.selected if _state.selected >= 0 else 0)
	if not _joint_roles.is_empty():
		_bone.select(0)
		_change_bone(0)
	else:
		_selected_bone = ""
		_refresh_sliders()
	_refresh_gait()
	_apply_live()
	if _model.fallback_used:
		_info.text = "Fallback model shown. Import VRM in Godot Editor to use joint controls."
	else:
		_info.text = "Editing " + String(fighter.look.get("name", _selected_char)) + " · Save Fighter to keep edits."

func _create_marker(role: String) -> void:
	var point := MeshInstance3D.new()
	point.name = role + "Marker"
	var sphere := SphereMesh.new()
	sphere.radius = 0.037
	sphere.height = 0.074
	point.mesh = sphere
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = Color("#60d2ff")
	point.material_override = material
	var name_label := Label3D.new()
	name_label.text = role
	name_label.font_size = 18
	name_label.pixel_size = 0.0025
	name_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	name_label.no_depth_test = true
	name_label.position = Vector3(0.08, 0.035, 0.0)
	name_label.visible = _frg16e_labels_visible
	point.add_child(name_label)
	_world.add_child(point)
	_marker_nodes[role] = point

func _change_state(index: int) -> void:
	_selected_state = MODES[clampi(index, 0, MODES.size() - 1)]
	_frg16d_elapsed = 0.0
	_frg16d_sync_ui()
	_refresh_sliders()
	_apply_live()

func _change_bone(index: int) -> void:
	if index < 0 or index >= _joint_roles.size():
		return
	_selected_bone = _joint_roles[index]
	_marker_info.text = "Selected: " + _selected_bone + "   ·   Click another blue joint to switch"
	_refresh_sliders()

func _refresh_sliders() -> void:
	var angles := Profiles.get_angles(_profile, _selected_state, _selected_bone) if not _selected_bone.is_empty() else Vector3.ZERO
	for i in 3:
		_axis[i].set_value_no_signal(angles[i])
		_axis_values[i].text = "%.1f°" % angles[i]
		_axis[i].editable = not _selected_bone.is_empty()

func _refresh_gait() -> void:
	var settings: Dictionary = _profile.get("gait", {})
	for field in _gait:
		var value: float = float(settings.get(field, 1.0))
		var slider: HSlider = _gait[field][0]
		var label: Label = _gait[field][1]
		slider.set_value_no_signal(value)
		label.text = "%.2fx" % value

func _on_axis(value: float, axis: int) -> void:
	if _selected_bone.is_empty():
		return
	var angles := Profiles.get_angles(_profile, _selected_state, _selected_bone)
	_frg16c_record_change()
	angles[axis] = value
	Profiles.put_angles(_profile, _selected_state, _selected_bone, angles)
	_axis_values[axis].text = "%.1f°" % value
	_mark_dirty()

func _on_gait(value: float, field: String) -> void:
	if _selected_char.is_empty():
		return
	_frg16c_record_change()
	var settings: Dictionary = _profile.get("gait", {})
	settings[field] = value
	_profile["gait"] = settings
	var label: Label = _gait[field][1]
	label.text = "%.2fx" % value
	_mark_dirty()

func _mark_dirty() -> void:
	_dirty = true
	_info.text = "Unsaved edits · press Save Fighter to use these changes in battles."
	_apply_live()

func _apply_live() -> void:
	if is_instance_valid(_model) and _model.motion != null:
		_model.motion.lab_profile = _profile.duplicate(true)

func _save() -> void:
	var message := Profiles.save_for(_selected_char, _profile)
	_dirty = message.begins_with("ERROR")
	_info.text = message

func _reset_state() -> void:
	_frg16c_record_change()
	var poses: Dictionary = _profile.get("poses", {})
	poses[_selected_state] = {}
	_profile["poses"] = poses
	_refresh_sliders()
	_mark_dirty()

func _reset_all() -> void:
	_frg16c_record_change()
	_profile = Profiles.new_profile()
	_refresh_sliders()
	_refresh_gait()
	_mark_dirty()

# FRG16C: animation editing helpers; no skeleton rest pose or joint hierarchy changes.
func _frg16c_reset_history() -> void:
	_frg16c_undo_history.clear()
	_frg16c_redo_history.clear()
	_frg16c_drag_active = false
	_frg16c_drag_recorded = false

func _frg16c_snapshot() -> Dictionary:
	return {"profile": _profile.duplicate(true), "dirty": _dirty}

func _frg16c_drag_start() -> void:
	_frg16c_drag_active = true
	_frg16c_drag_recorded = false

func _frg16c_drag_end(_value_changed: bool) -> void:
	_frg16c_drag_active = false
	_frg16c_drag_recorded = false

func _frg16c_record_change() -> void:
	# A continuous slider drag counts as ONE undo step, not hundreds.
	if _frg16c_drag_active and _frg16c_drag_recorded:
		return
	_frg16c_undo_history.append(_frg16c_snapshot())
	if _frg16c_undo_history.size() > FRG16C_HISTORY_LIMIT:
		_frg16c_undo_history.pop_front()
	_frg16c_redo_history.clear()
	if _frg16c_drag_active:
		_frg16c_drag_recorded = true

func _frg16c_restore_snapshot(snapshot: Dictionary, message: String) -> void:
	var restored: Variant = snapshot.get("profile", {})
	if not (restored is Dictionary):
		return
	_profile = (restored as Dictionary).duplicate(true)
	_dirty = bool(snapshot.get("dirty", true))
	_frg16c_drag_active = false
	_frg16c_drag_recorded = false
	_refresh_sliders()
	_refresh_gait()
	_apply_live()
	_info.text = message + " · Press Save Fighter to keep these edits."

func _frg16c_undo() -> void:
	if _frg16c_undo_history.is_empty():
		_info.text = "Nothing to undo."
		return
	var previous: Dictionary = _frg16c_undo_history.pop_back()
	_frg16c_redo_history.append(_frg16c_snapshot())
	_frg16c_restore_snapshot(previous, "Undid change")

func _frg16c_redo() -> void:
	if _frg16c_redo_history.is_empty():
		_info.text = "Nothing to redo."
		return
	var next_pose: Dictionary = _frg16c_redo_history.pop_back()
	_frg16c_undo_history.append(_frg16c_snapshot())
	_frg16c_restore_snapshot(next_pose, "Redid change")

func _frg16c_copy_pose() -> void:
	var poses: Dictionary = _profile.get("poses", {})
	var current: Variant = poses.get(_selected_state, {})
	if not (current is Dictionary):
		_info.text = "Selected pose has invalid data."
		return
	_frg16c_clipboard = (current as Dictionary).duplicate(true)
	_frg16c_clipboard_valid = true
	_frg16c_clipboard_source = _selected_char + "/" + _selected_state
	_info.text = "Copied " + _frg16c_clipboard_source + " · Change state or fighter and Paste Pose."

func _frg16c_paste_pose() -> void:
	if not _frg16c_clipboard_valid:
		_info.text = "Copy a pose first."
		return
	var poses: Dictionary = _profile.get("poses", {})
	var current: Dictionary = poses.get(_selected_state, {})
	if current == _frg16c_clipboard:
		_info.text = "Destination pose already matches the copied pose."
		return
	_frg16c_record_change()
	poses[_selected_state] = _frg16c_clipboard.duplicate(true)
	_profile["poses"] = poses
	_refresh_sliders()
	_mark_dirty()
	_info.text = "Pasted " + _frg16c_clipboard_source + " into " + _selected_char + "/" + _selected_state + ". Save Fighter to keep it."

func _frg16c_mirror_pose() -> void:
	var poses: Dictionary = _profile.get("poses", {})
	var current: Dictionary = poses.get(_selected_state, {})
	if current.is_empty():
		_info.text = "This pose has no joint offsets to mirror."
		return
	var mirrored: Dictionary = {}
	for key in current.keys():
		var bone: String = String(key)
		var dest: String = bone
		if bone.begins_with("Left"):
			dest = "Right" + bone.substr(4)
		elif bone.begins_with("Right"):
			dest = "Left" + bone.substr(5)
		var raw: Variant = current[key]
		if not (raw is Array) or raw.size() != 3:
			continue
		# Mirror in local bone Euler coordinates: pitch stays, yaw/roll invert.
		mirrored[dest] = [float(raw[0]), -float(raw[1]), -float(raw[2])]
	if mirrored == current:
		_info.text = "Pose is already symmetrical."
		return
	_frg16c_record_change()
	poses[_selected_state] = mirrored
	_profile["poses"] = poses
	_refresh_sliders()
	_mark_dirty()
	_info.text = "Mirrored Left/Right joint offsets for " + _selected_state + ". Save Fighter to keep it."

func _frg16c_reset_joint() -> void:
	if _selected_bone.is_empty():
		_info.text = "Select a joint first."
		return
	if Profiles.get_angles(_profile, _selected_state, _selected_bone).length_squared() < 0.00001:
		_info.text = "This joint is already reset."
		return
	_frg16c_record_change()
	Profiles.put_angles(_profile, _selected_state, _selected_bone, Vector3.ZERO)
	_refresh_sliders()
	_mark_dirty()

func _unhandled_key_input(event: InputEvent) -> void:
	if not (event is InputEventKey):
		return
	var key_event := event as InputEventKey
	if not key_event.pressed or key_event.echo or not key_event.ctrl_pressed:
		return
	if key_event.keycode == KEY_Z:
		_frg16c_undo()
		get_viewport().set_input_as_handled()
	elif key_event.keycode == KEY_Y:
		_frg16c_redo()
		get_viewport().set_input_as_handled()

# FRG16D: preview controls do not affect saved fighter poses or in-match animations.
func _frg16d_toggle() -> void:
	_frg16d_playing = not _frg16d_playing
	if _frg16d_playing and _frg16d_elapsed >= _frg16d_duration:
		_frg16d_elapsed = 0.0
	_frg16d_sync_ui()

func _frg16d_toggle_loop() -> void:
	_frg16d_loop = not _frg16d_loop
	_frg16d_sync_ui()

func _frg16d_step(direction: int) -> void:
	_frg16d_playing = false
	_frg16d_elapsed = clampf(_frg16d_elapsed + float(direction) / 30.0, 0.0, _frg16d_duration)
	_frg16d_sync_ui()

func _frg16d_scrub_to(value: float) -> void:
	_frg16d_playing = false
	_frg16d_elapsed = clampf(value, 0.0, 1.0) * _frg16d_duration
	_frg16d_sync_ui()

func _frg16d_set_speed(index: int) -> void:
	var speeds := [0.25, 0.5, 1.0, 1.5, 2.0]
	if index < 0 or index >= speeds.size():
		return
	_frg16d_speed = float(speeds[index])

func _frg16d_sync_ui() -> void:
	if is_instance_valid(_frg16d_bar):
		var alpha: float = clampf(_frg16d_elapsed / _frg16d_duration, 0.0, 1.0)
		_frg16d_bar.set_value_no_signal(alpha)
	if is_instance_valid(_frg16d_label):
		_frg16d_label.text = "%.2fs / %.2fs (%d%%)" % [_frg16d_elapsed, _frg16d_duration, int(round(100.0 * _frg16d_elapsed / _frg16d_duration))]
	if is_instance_valid(_frg16d_play_button):
		_frg16d_play_button.text = "Pause" if _frg16d_playing else "Play"
	if is_instance_valid(_frg16d_loop_button):
		_frg16d_loop_button.text = "Loop: ON" if _frg16d_loop else "Loop: OFF"

# FRG16E: viewport controls never alter FighterModel bones, profiles, or combat timing.
func _frg16e_update_camera() -> void:
	if not is_instance_valid(_camera):
		return
	var yaw := deg_to_rad(_frg16e_orbit_yaw)
	var pitch := deg_to_rad(_frg16e_orbit_pitch)
	var forward := Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch))
	_camera.position = _frg16e_target + forward * _frg16e_distance
	_camera.look_at(_frg16e_target, Vector3.UP)

func _frg16e_reset_view() -> void:
	_frg16e_dragging = false
	_frg16e_orbit_yaw = 0.0
	_frg16e_orbit_pitch = 8.0
	_frg16e_distance = 4.2
	_frg16e_update_camera()
	_yaw = 18.0

func _frg16e_toggle_markers() -> void:
	_frg16e_markers_visible = not _frg16e_markers_visible
	if is_instance_valid(_frg16e_markers_button):
		_frg16e_markers_button.text = "Joints: ON" if _frg16e_markers_visible else "Joints: OFF"

func _frg16e_toggle_names() -> void:
	_frg16e_labels_visible = not _frg16e_labels_visible
	if is_instance_valid(_frg16e_labels_button):
		_frg16e_labels_button.text = "Names: ON" if _frg16e_labels_visible else "Names: OFF"

func _back() -> void:
	get_tree().change_scene_to_file("res://scenes/main.tscn")

func _viewport_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		if not _frg16e_dragging:
			return
		var motion := event as InputEventMouseMotion
		_frg16e_orbit_yaw -= motion.relative.x * 0.38
		_frg16e_orbit_pitch = clampf(_frg16e_orbit_pitch - motion.relative.y * 0.28, -45.0, 65.0)
		_frg16e_update_camera()
		accept_event()
		return
	if not (event is InputEventMouseButton):
		return
	var click := event as InputEventMouseButton
	if click.button_index == MOUSE_BUTTON_RIGHT:
		_frg16e_dragging = click.pressed
		accept_event()
		return
	if not click.pressed:
		return
	if click.button_index == MOUSE_BUTTON_WHEEL_UP:
		_frg16e_distance = clampf(_frg16e_distance * 0.90, 1.3, 12.0)
		_frg16e_update_camera()
		accept_event()
		return
	if click.button_index == MOUSE_BUTTON_WHEEL_DOWN:
		_frg16e_distance = clampf(_frg16e_distance * 1.10, 1.3, 12.0)
		_frg16e_update_camera()
		accept_event()
		return
	if click.button_index != MOUSE_BUTTON_LEFT or not _frg16e_markers_visible:
		return
	if _model == null or _model.skeleton == null:
		return
	var ratio := _view_box.size / Vector2(_view.size)
	var nearest := 28.0
	var chosen := ""
	for role in _marker_nodes:
		var node: MeshInstance3D = _marker_nodes[role]
		if not node.visible or _camera.is_position_behind(node.global_position):
			continue
		var pixel: Vector2 = _camera.unproject_position(node.global_position) * ratio
		var dist: float = pixel.distance_to(click.position)
		if dist < nearest:
			nearest = dist
			chosen = role
	if chosen != "":
		var index := _joint_roles.find(chosen)
		if index >= 0:
			_bone.select(index)
			_change_bone(index)
		accept_event()

# FRG16B: preview the actual kit pose underneath editable joint offsets.
func _frg16b_preview_pose() -> String:
	match _selected_state:
		"attack":
			var attacks: Dictionary = Data.attacks_for(_selected_char)
			var basic: Dictionary = attacks.get("l1", {})
			return String(basic.get("pose_s", "idle"))
		"charge":
			var attacks: Dictionary = Data.attacks_for(_selected_char)
			var charged: Dictionary = attacks.get("heavy", {})
			return String(charged.get("pose_w", "idle"))
		"block": return "block"
		"hit": return "hit"
		"stagger": return "stagger"
		"jump": return "jump"
		"win": return "win"
		"dodge": return "idle"
		_: return "idle"

func _process(dt: float) -> void:
	if not is_instance_valid(_model):
		return
	_model.rotation_degrees.y = _yaw
	if _frg16d_playing:
		_frg16d_elapsed += maxf(dt, 0.0) * _frg16d_speed
		if _frg16d_elapsed >= _frg16d_duration:
			if _frg16d_loop:
				_frg16d_elapsed = fmod(_frg16d_elapsed, _frg16d_duration)
			else:
				_frg16d_elapsed = _frg16d_duration
				_frg16d_playing = false
	var phase: float = clampf(_frg16d_elapsed / _frg16d_duration, 0.0, 1.0)
	# Only the Animation Lab enables these preview overrides.
	_model.lab_preview_override = true
	_model.lab_preview_phase = phase * TAU
	_model.lab_preview_time = _frg16d_elapsed
	_model.lab_paused = true
	_model.walk = 1.0 if _selected_state in ["walk", "run"] else 0.0
	_model.run = 1.0 if _selected_state == "run" else 0.0
	_model.choreo_state = _selected_state if _selected_state not in ["idle", "walk", "run"] else "idle"
	_model.choreo_weight = 0.0 if _selected_state in ["idle", "walk", "run"] else 1.0
	_model.choreo_progress = phase
	_model.play_pose(_frg16b_preview_pose(), 18.0)
	_frg16d_sync_ui()
	if _model.skeleton == null:
		return
	for role in _marker_nodes:
		var marker: MeshInstance3D = _marker_nodes[role]
		var name: String = RIG.name_for(_model.skeleton, String(role), _model.rig_profile)
		var bone_id := _model.skeleton.find_bone(name)
		marker.visible = bone_id >= 0 and _frg16e_markers_visible
		if bone_id < 0:
			continue
		marker.global_position = _model.skeleton.global_transform * _model.skeleton.get_bone_global_pose(bone_id).origin
		var name_label := marker.get_child(0) as Label3D
		if is_instance_valid(name_label):
			name_label.visible = _frg16e_labels_visible
		var material: StandardMaterial3D = marker.material_override
		material.albedo_color = Color("#ffda72") if role == _selected_bone else Color("#60d2ff")

# FRG16D - animation lab preview timeline
