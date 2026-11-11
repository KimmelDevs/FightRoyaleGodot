class_name Fx
extends Node3D
## Combat effects: sparks, flashes, ground rings, telegraph markers, rocks, light motes,
## smoke and floating damage numbers. Everything removes itself when finished.

var _items: Array = []  # [node, updater Callable(dt) -> bool alive]

# FRG17D - VFX quality and performance
# Purely cosmetic. Read presets at startup from res://data/vfx_quality.json.
# When the settings file is absent or invalid, use balanced defaults.
var _vfx17d_max_active: int = 120
var _vfx17d_max_particles: int = 36
var _vfx17d_particle_scale: float = 0.82

func _ready() -> void:
	var preset := "balanced"
	var cfg_path := "res://data/vfx_quality.json"
	if FileAccess.file_exists(cfg_path):
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(cfg_path))
		if parsed is Dictionary:
			preset = String(parsed.get("preset", "balanced"))
	match preset:
		"eco":
			_vfx17d_max_active = 65
			_vfx17d_max_particles = 20
			_vfx17d_particle_scale = 0.55
		"ultra":
			_vfx17d_max_active = 200
			_vfx17d_max_particles = 64
			_vfx17d_particle_scale = 1.0
		_:
			_vfx17d_max_active = 120
			_vfx17d_max_particles = 36
			_vfx17d_particle_scale = 0.82

func active_effect_count_17d() -> int:
	return _items.size()

func _process(dt: float) -> void:
	for i in range(_items.size() - 1, -1, -1):
		var it: Array = _items[i]
		if not it[1].call(dt):
			it[0].queue_free()
			_items.remove_at(i)

func _add(n: Node3D, upd: Callable) -> void:
	# FRG17D: retire the oldest visual if the budget is full. Never block a new hit.
	if _items.size() >= _vfx17d_max_active:
		var oldest: Array = _items.pop_front()
		if is_instance_valid(oldest[0]):
			oldest[0].queue_free()
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
	# FRG17D: reduce MultiMesh instance work while preserving effect shapes/timing.
	var actual_amount: int = clampi(roundi(float(amount) * _vfx17d_particle_scale), 0, _vfx17d_max_particles)
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = mesh
	mm.instance_count = actual_amount
	var mi := MultiMeshInstance3D.new()
	mi.multimesh = mm
	mi.material_override = mat
	var vel: Array[Vector3] = []
	var p: Array[Vector3] = []
	var sizes: Array[float] = []
	for i in actual_amount:
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
		for i in actual_amount:
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

# FRG17A - combat impact VFX
# Cosmetic only: no damage, collisions, hit-stop or combat timings are changed.
# Each ray burst is one MultiMesh, not a node for each spark.
func _vfx17a_rays(pos: Vector3, color: Color, direction: Vector3, amount: int, reach: float, duration: float) -> void:
	var rays := BoxMesh.new()
	rays.size = Vector3(0.025, 0.025, 1.0)
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = rays
	mm.instance_count = amount
	var node := MultiMeshInstance3D.new()
	node.multimesh = mm
	node.material_override = unlit(color, 0.94, true)
	var orientations: Array[Vector3] = []
	var distances: Array[float] = []
	var heading := direction.normalized() if direction.length_squared() > 0.0001 else Vector3.UP
	for i in range(amount):
		var jitter := Vector3(randf_range(-1.0, 1.0), randf_range(-1.0, 1.0), randf_range(-1.0, 1.0))
		var ray := (heading * 0.60 + jitter).normalized()
		if ray.length_squared() < 0.0001:
			ray = Vector3.UP
		orientations.append(ray)
		distances.append(reach * randf_range(0.65, 1.10))
	var elapsed := [0.0]
	_add(node, func(dt: float) -> bool:
		elapsed[0] += dt
		var progress: float = clampf(elapsed[0] / maxf(duration, 0.01), 0.0, 1.0)
		for i in range(amount):
			var ray: Vector3 = orientations[i]
			var up: Vector3 = Vector3.UP if absf(ray.dot(Vector3.UP)) < 0.92 else Vector3.FORWARD
			var basis := Basis.looking_at(ray, up)
			var visible_length: float = maxf(0.001, distances[i] * 0.28 * (1.0 - progress))
			var center: Vector3 = pos + ray * (0.1 + distances[i] * progress * 0.60)
			mm.set_instance_transform(i, Transform3D(basis.scaled(Vector3(1.0, 1.0, visible_length)), center))
		return elapsed[0] < duration)

# A shield-facing translucent disk; oriented toward the incoming strike.
func _vfx17a_shield_disk(pos: Vector3, color: Color, incoming: Vector3, radius: float, duration: float) -> void:
	var disk := MeshInstance3D.new()
	var sphere := SphereMesh.new()
	sphere.radius = 1.0
	sphere.height = 2.0
	sphere.radial_segments = 20
	sphere.rings = 8
	disk.mesh = sphere
	var mat := unlit(color, 0.38, true)
	disk.material_override = mat
	disk.position = pos
	var normal := incoming.normalized() if incoming.length_squared() > 0.0001 else Vector3.FORWARD
	var up := Vector3.UP if absf(normal.dot(Vector3.UP)) < 0.92 else Vector3.FORWARD
	disk.basis = Basis.looking_at(normal, up)
	var elapsed := [0.0]
	_add(disk, func(dt: float) -> bool:
		elapsed[0] += dt
		var progress: float = clampf(elapsed[0] / maxf(duration, 0.01), 0.0, 1.0)
		var grow: float = radius * (0.65 + progress * 0.55)
		disk.scale = Vector3(grow, grow, 0.035)
		mat.albedo_color.a = 0.38 * (1.0 - progress)
		return elapsed[0] < duration)

func combat_hit(pos: Vector3, color: Color, normal: Vector3, heavy: bool = false) -> void:
	var intensity: float = 1.0 if heavy else 0.65
	flash(pos, Color.WHITE.lerp(color, 0.35), 0.25 + 0.24 * intensity, 0.13, 0.85)
	sparks(pos, color, 24 if heavy else 13, 7.5 if heavy else 5.0, normal)
	_vfx17a_rays(pos, color, normal, 14 if heavy else 8, 1.25 if heavy else 0.72, 0.22 if heavy else 0.16)
	if heavy:
		ring(pos, color, 1.35, 0.22, 0.65)

func combat_guard(pos: Vector3, incoming: Vector3, perfect: bool = false) -> void:
	var tint := Color("#a8ecff") if perfect else Color("#ffc971")
	_vfx17a_shield_disk(pos, tint, incoming, 0.95 if perfect else 0.65, 0.27 if perfect else 0.17)
	sparks(pos, tint, 31 if perfect else 13, 8.0 if perfect else 4.5, -incoming)
	_vfx17a_rays(pos, tint, -incoming, 13 if perfect else 6, 0.95 if perfect else 0.48, 0.21 if perfect else 0.14)
	if perfect:
		flash(pos, Color("#e4fbff"), 0.40, 0.12, 0.8)
		ring(pos, tint, 1.5, 0.30, 0.85)

func combat_guard_break(pos: Vector3) -> void:
	var tint := Color("#ffad49")
	flash(pos, Color("#fff4c2"), 0.78, 0.17, 0.95)
	sparks(pos, tint, 36, 8.5)
	_vfx17a_rays(pos, tint, Vector3.UP, 20, 1.65, 0.27)
	ring(pos, tint, 1.75, 0.32, 0.84)

func combat_clash(pos: Vector3) -> void:
	var tint := Color("#ffe5a2")
	flash(pos, Color.WHITE, 0.75, 0.16, 0.92)
	sparks(pos, tint, 38, 9.0)
	_vfx17a_rays(pos, tint, Vector3.UP, 22, 1.55, 0.23)
	ring(pos, tint, 2.45, 0.35, 0.87)

# FRG17C - elemental hit and skill VFX
# Cosmetic only: all damage, status, guard, projectile and AI calculations are unchanged.
# Lightweight MultiMesh bursts, with fewer particles on non-heavy strikes.
func elemental_hit_17c(at: Vector3, element: String, tint: Color, heavy: bool) -> void:
	var n := 11 if heavy else 5
	var color_key := element.to_lower()
	match color_key:
		"fire", "flame":
			var ember := BoxMesh.new()
			ember.size = Vector3(0.055, 0.10, 0.035)
			burst(at, ember, unlit(Color("#ff8b3d"), 0.95, true), n, 3.9, Vector3.UP, 1.0, -1.8, 0.42, 1.0)
			if heavy: flash(at, Color("#ffba54"), 0.35, 0.16, 0.5)
		"electric", "lightning":
			var spark := BoxMesh.new()
			spark.size = Vector3(0.025, 0.025, 0.19)
			burst(at, spark, unlit(Color("#d3f0ff"), 0.95, true), n + 3, 6.0, Vector3.ZERO, 1.0, 4.0, 0.20, 1.0)
			if heavy: ring(at, Color("#83d4ff"), 0.85, 0.17, 0.65)
		"water":
			var droplet := SphereMesh.new()
			droplet.radius = 0.045
			droplet.height = 0.09
			droplet.radial_segments = 6
			droplet.rings = 3
			burst(at, droplet, unlit(Color("#7bd7ff"), 0.75, true), n, 3.3, Vector3.UP, 1.2, 7.0, 0.36, 1.0)
			if heavy: ring(at, Color("#4caaff"), 0.8, 0.2, 0.45)
		"shadow", "moon", "blood":
			var dark_tint := Color("#b17bef") if color_key != "blood" else Color("#e44869")
			sparks(at, dark_tint, n + 2, 3.3)
			if heavy: flash(at, dark_tint, 0.45, 0.2, 0.42)
		"light", "blossom", "nature":
			motes(at, tint, n)
			if heavy: ring(at, tint, 0.7, 0.17, 0.46)
		"chi", "force":
			if heavy: ring(at, tint, 1.05, 0.22, 0.62)
		# Earth already emits rocks in Match; no duplicate burst here.
		_:
			pass

func elemental_skill_17c(at: Vector3, element: String, style: String, tint: Color, radius: float) -> void:
	var r := clampf(radius, 0.35, 5.0)
	match style:
		"lightning":
			var ray := BoxMesh.new()
			ray.size = Vector3(0.035, 0.25, 0.035)
			burst(at + Vector3.UP * 0.5, ray, unlit(Color("#d7f4ff"), 0.9, true), 15, 7.5, Vector3.UP, 0.85, 0.0, 0.27, 1.1)
		"meteor", "explosion":
			var coal := BoxMesh.new()
			coal.size = Vector3(0.08, 0.08, 0.08)
			burst(at + Vector3.UP * 0.25, coal, unlit(Color("#ff9d5b"), 0.85, true), 15, 4.2, Vector3.UP, 1.0, 12.0, 0.50, 1.0)
		"spin":
			motes(at + Vector3.UP * 0.65, tint, 10)
		"slam", "cleave":
			# 17A provides the ground crack and directional burst; add a small dust bloom.
			motes(at + Vector3.UP * 0.25, Color("#dac2a2"), 6)
		_:
			match element.to_lower():
				"water":
					ring(at, Color("#83d7ff"), r * 0.7, 0.21, 0.47)
				"moon", "shadow", "blood":
					flash(at + Vector3.UP * 0.4, tint, r * 0.28, 0.19, 0.3)
				"nature", "blossom", "light":
					motes(at + Vector3.UP * 0.4, tint, 7)
				_:
					pass
