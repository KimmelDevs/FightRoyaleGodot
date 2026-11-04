class_name Fx
extends Node3D
## Combat effects: sparks, flashes, ground rings, telegraph markers, rocks, light motes,
## smoke and floating damage numbers. Everything removes itself when finished.

var _items: Array = []  # [node, updater Callable(dt) -> bool alive]

func _process(dt: float) -> void:
	for i in range(_items.size() - 1, -1, -1):
		var it: Array = _items[i]
		if not it[1].call(dt):
			it[0].queue_free()
			_items.remove_at(i)

func _add(n: Node3D, upd: Callable) -> void:
	add_child(n)
	_items.append([n, upd])

static func unlit(c: Color, alpha := 1.0, additive := false) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = Color(c, alpha)
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	if additive: m.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	return m

## Burst of small pieces flying out under gravity.
func burst(pos: Vector3, mesh: Mesh, mat: Material, amount: int, speed: float, dir := Vector3.ZERO, spread := 1.0, gravity := 9.0, life := 0.4, size := 1.0) -> void:
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = mesh
	mm.instance_count = amount
	var mi := MultiMeshInstance3D.new()
	mi.multimesh = mm
	mi.material_override = mat
	var vel: Array[Vector3] = []
	var p: Array[Vector3] = []
	var sizes: Array[float] = []
	for i in amount:
		var d := Vector3(randf() - 0.5, randf() - 0.5, randf() - 0.5).normalized()
		if dir != Vector3.ZERO: d = (dir.normalized() + d * spread).normalized()
		elif spread < 1.0: d = Vector3(d.x * spread, 1, d.z * spread).normalized()
		vel.append(d * speed * (0.5 + randf() * 0.5))
		p.append(pos)
		sizes.append(size * (0.5 + randf() * 0.7))
	var t := [0.0]
	_add(mi, func(dt: float) -> bool:
		t[0] += dt
		var f := maxf(1.0 - t[0] / life, 0.0)
		for i in amount:
			vel[i].y -= gravity * dt
			vel[i] *= maxf(1.0 - 3.0 * dt, 0.0)
			p[i] += vel[i] * dt
			mm.set_instance_transform(i, Transform3D(Basis.from_scale(Vector3.ONE * f * sizes[i]), p[i]))
		return t[0] < life)

func sparks(pos: Vector3, color: Color, amount := 20, speed := 7.0, dir := Vector3.ZERO) -> void:
	var b := BoxMesh.new(); b.size = Vector3(0.016, 0.016, 0.016) * 2.5
	burst(pos, b, unlit(color, 1.0, true), amount, speed, dir, 0.7 if dir != Vector3.ZERO else 1.0, 9.0, 0.35, 1.0)

func flash(pos: Vector3, color: Color, size := 0.5, dur := 0.14, opacity := 0.8) -> void:
	var m := MeshInstance3D.new()
	var s := SphereMesh.new(); s.radius = 1; s.height = 2; s.radial_segments = 16; s.rings = 8
	m.mesh = s
	var mat := unlit(color, opacity, true)
	m.material_override = mat
	m.position = pos
	var t := [0.0]
	_add(m, func(dt: float) -> bool:
		t[0] += dt
		var f := minf(t[0] / dur, 1.0)
		m.scale = Vector3.ONE * size * (0.3 + 0.7 * (1.0 - (1.0 - f) * (1.0 - f)))
		mat.albedo_color.a = opacity * (1.0 - f)
		return t[0] < dur)

func ring(pos: Vector3, color: Color, radius := 2.0, dur := 0.35, opacity := 0.9) -> void:
	var m := MeshInstance3D.new()
	var tor := TorusMesh.new(); tor.inner_radius = 0.9; tor.outer_radius = 1.0
	m.mesh = tor
	var mat := unlit(color, opacity, true)
	m.material_override = mat
	m.position = Vector3(pos.x, maxf(pos.y, 0.05), pos.z)
	var t := [0.0]
	_add(m, func(dt: float) -> bool:
		t[0] += dt
		var f := minf(t[0] / dur, 1.0)
		var r := radius * (0.2 + 0.8 * f)
		m.scale = Vector3(r, 0.3, r)
		mat.albedo_color.a = opacity * (1.0 - f)
		return t[0] < dur)

## Ground marker shown before an area strike lands.
func telegraph(pos: Vector3, color: Color, radius: float, dur: float) -> void:
	var m := MeshInstance3D.new()
	var c := CylinderMesh.new(); c.top_radius = 1; c.bottom_radius = 1; c.height = 0.01
	m.mesh = c
	var mat := unlit(color, 0.25)
	m.material_override = mat
	m.position = Vector3(pos.x, 0.03, pos.z)
	var t := [0.0]
	_add(m, func(dt: float) -> bool:
		t[0] += dt
		var f := minf(t[0] / dur, 1.0)
		m.scale = Vector3(radius * f, 1, radius * f)
		mat.albedo_color.a = 0.2 + 0.3 * f
		return t[0] < dur)

func explosion(pos: Vector3, color: Color, radius: float) -> void:
	flash(pos + Vector3(0, 0.4, 0), color, radius * 0.8, 0.3, 0.9)
	ring(pos, color, radius * 1.4, 0.4)
	sparks(pos + Vector3(0, 0.3, 0), color, 40, 9.0)

func smoke(pos: Vector3, color: Color) -> void:
	var c := pos + Vector3(0, 0.9, 0)
	flash(c, color, 0.7, 0.25, 0.6)
	sparks(c, color, 26, 4.0)

## Earth: chunky rocks, a dust cloud and a ground crack ring.
func rocks(pos: Vector3, amount := 16, power := 1.0) -> void:
	var g := Vector3(pos.x, maxf(pos.y, 0.05), pos.z)
	var rock := SphereMesh.new(); rock.radius = 0.07; rock.height = 0.12; rock.radial_segments = 5; rock.rings = 3
	var rm := StandardMaterial3D.new(); rm.albedo_color = Color("#8a6a48")
	burst(g, rock, rm, amount, 6.5 * power, Vector3.UP, 0.75, 20.0, 0.95, 1.5 * power)
	var dust := SphereMesh.new(); dust.radius = 1; dust.height = 2
	burst(g, dust, unlit(Color("#b89a74"), 0.45), 9, 2.2 * power, Vector3.UP, 1.4, -0.6, 1.0, 0.32 * power)
	ring(g, Color("#6a4a2a"), 1.5 * power, 0.45, 0.85)

## Light: small glowing motes drifting up.
func motes(pos: Vector3, color: Color, amount := 3) -> void:
	var o := SphereMesh.new(); o.radius = 0.03; o.height = 0.06; o.radial_segments = 4; o.rings = 2
	burst(pos, o, unlit(color, 0.95, true), amount, 1.1, Vector3.UP, 1.2, -1.2, 0.7, 2.2)

## Floating number / label (billboard text).
func number(pos: Vector3, text: String, color: Color, size := 1.0) -> void:
	var l := Label3D.new()
	l.text = text
	l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l.modulate = color
	l.outline_modulate = Color(0, 0, 0, 0.8)
	l.outline_size = 10
	l.font_size = int(64 * size)
	l.pixel_size = 0.004
	l.no_depth_test = true
	l.position = pos
	var t := [0.0]
	_add(l, func(dt: float) -> bool:
		t[0] += dt
		l.position.y += dt * 0.8
		l.modulate.a = clampf(1.6 - t[0] * 1.6, 0.0, 1.0)
		return t[0] < 1.0)

func clear() -> void:
	for it in _items: it[0].queue_free()
	_items.clear()
