class_name Trail
extends MeshInstance3D
## Blade trail: a fading ribbon between the blade base and tip over the last few frames.

const SAMPLES := 14
var base: Node3D
var tip: Node3D
var emitting := false
var _pts: Array = []  # [base, tip, age]
var _im := ImmediateMesh.new()

func _init(b: Node3D, t: Node3D, color: Color) -> void:
	base = b; tip = t
	mesh = _im
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.vertex_color_use_as_albedo = true
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	m.albedo_color = color
	material_override = m
	top_level = true

func tick(dt: float) -> void:
	for p in _pts: p[2] += dt
	while not _pts.is_empty() and _pts[0][2] > 0.18: _pts.pop_front()
	if emitting and is_instance_valid(base) and is_instance_valid(tip):
		_pts.append([base.global_position, tip.global_position, 0.0])
		while _pts.size() > SAMPLES: _pts.pop_front()
	_im.clear_surfaces()
	if _pts.size() < 2: return
	_im.surface_begin(Mesh.PRIMITIVE_TRIANGLE_STRIP)
	for p in _pts:
		var a := clampf(1.0 - p[2] / 0.18, 0.0, 1.0)
		_im.surface_set_color(Color(1, 1, 1, a * 0.85)); _im.surface_add_vertex(p[0])
		_im.surface_set_color(Color(1, 1, 1, a)); _im.surface_add_vertex(p[1])
	_im.surface_end()
