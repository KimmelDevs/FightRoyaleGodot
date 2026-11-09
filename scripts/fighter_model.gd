class_name FighterModel
extends Node3D
## A fighter's body: the VRoid model (humanoid Skeleton3D), its pose animations (one library
## per kit, editable in res://animations/<kit>.tres), a MotionLayer for walk/hips/breathing,
## and the weapons mounted on the hand bones.

const FALLBACK := {"m": "rook", "f": "ember"}  ## stand-ins until a fighter has its own VRoid model

var look: Dictionary
var kit := ""
var skeleton: Skeleton3D
var rig_profile: Dictionary = {} # FRG04 - rig mapper integrated
var loaded_model_id := "" # FRG05 - automatic weapon profile mounts
# FRG08 - safe VRM loading and visible avatar fallback
var fallback_used := false
var fallback_reason := ""
var player: AnimationPlayer
var motion: MotionLayer
var vrm: Node3D

var blade_base: Node3D   ## trail start
var blade_tip: Node3D    ## trail end / projectile origin
var cast_point: Node3D
var shield_node: Node3D
var walk := 0.0
var run := 0.0  # FRG06 - locomotion and procedural footwork
var strafe := 0.0
var airborne := false
var burst := 0.0
var charge := 0.0
var recoil := 0.0

var _pose := ""
var _t := 0.0
var _phase := 0.0
var _flash_t := 0.0
var _meshes: Array[MeshInstance3D] = []
var _flash_mat: StandardMaterial3D

func setup(look_data: Dictionary) -> void:
	look = look_data
	kit = str(look.get("kit", "knight"))
	fallback_used = false
	fallback_reason = ""
	# Missing/unimported VRMs must never make the entire fighter invisible.
	var requested: String = str(look.get("vrm", ""))
	var candidate_ids: Array[String] = []
	if not requested.is_empty():
		candidate_ids.append(requested)
	var standin: String = str(FALLBACK.get(look.get("body", "f"), "ember"))
	if not candidate_ids.has(standin):
		candidate_ids.append(standin)
	for candidate in candidate_ids:
		var resource_path := "res://models/%s.vrm" % candidate
		if not ResourceLoader.exists(resource_path):
			continue
		var resource: Resource = ResourceLoader.load(resource_path)
		if not (resource is PackedScene):
			continue
		var instance: Node = (resource as PackedScene).instantiate()
		if not (instance is Node3D):
			instance.queue_free()
			continue
		vrm = instance as Node3D
		add_child(vrm)
		skeleton = FighterRig.find_skeleton(vrm)
		if skeleton != null and vrm.find_children("*", "MeshInstance3D", true, false).size() > 0:
			loaded_model_id = candidate
			break
		skeleton = null
		vrm.queue_free()
		vrm = null
	if skeleton == null:
		fallback_used = true
		fallback_reason = "No importable VRM with a Skeleton3D for " + str(look.get("name", "fighter"))
		push_warning("Fight Royale Update 08: " + fallback_reason + ". Using visible placeholder; check Godot's Import / Errors tabs.")
		_build_fallback_avatar()
		return
	rig_profile = FighterRig.profile_for(loaded_model_id)
	player = AnimationPlayer.new()
	player.name = "Poses"
	vrm.add_child(player)
	player.root_node = NodePath("..")
	var animation_resource: Resource = ResourceLoader.load("res://animations/%s.tres" % kit)
	if animation_resource is AnimationLibrary:
		player.add_animation_library("", animation_resource as AnimationLibrary)
	else:
		push_warning("Fight Royale: animation library for " + kit + " unavailable; model stays visible")
	motion = MotionLayer.new()
	motion.heavy = look.get("body", "f") == "m"
	motion.bone_map = FighterRig.runtime_bone_map(skeleton, rig_profile)
	skeleton.add_child(motion)
	for m in vrm.find_children("*", "MeshInstance3D", true, false):
		_meshes.append(m)
	_flash_mat = StandardMaterial3D.new()
	_flash_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_flash_mat.albedo_color = Color(1, 1, 1, 0.85)
	_flash_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_build_weapons()
	play_pose("idle", 10)

func _fallback_piece(parent: Node3D, dimensions: Vector3, center: Vector3, color: Color) -> MeshInstance3D:
	var mesh := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = dimensions
	mesh.mesh = box
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.8
	mesh.material_override = material
	mesh.position = center
	parent.add_child(mesh)
	_meshes.append(mesh)
	return mesh

func _build_fallback_avatar() -> void:
	# Intentionally simple, but always drawn even if .vrm import is broken.
	vrm = Node3D.new()
	vrm.name = "VisibleFallback08"
	add_child(vrm)
	var armor := Color(str(look.get("tunic", "#5579bb")))
	var limbs := Color(str(look.get("metal", "#c5d3e7")))
	var skin := Color("#e8c4a1")
	_fallback_piece(vrm, Vector3(0.56, 0.78, 0.33), Vector3(0, 1.12, 0), armor)
	_fallback_piece(vrm, Vector3(0.34, 0.35, 0.33), Vector3(0, 1.73, 0), skin)
	_fallback_piece(vrm, Vector3(0.22, 0.71, 0.24), Vector3(-0.41, 1.14, 0), limbs)
	_fallback_piece(vrm, Vector3(0.22, 0.71, 0.24), Vector3(0.41, 1.14, 0), limbs)
	_fallback_piece(vrm, Vector3(0.23, 0.75, 0.26), Vector3(-0.16, 0.39, 0), armor.darkened(0.25))
	_fallback_piece(vrm, Vector3(0.23, 0.75, 0.26), Vector3(0.16, 0.39, 0), armor.darkened(0.25))
	# Keep blade/trail and projectile anchors safe even without humanoid bones.
	var sword := Node3D.new()
	sword.position = Vector3(0.52, 1.02, 0)
	vrm.add_child(sword)
	_fallback_piece(sword, Vector3(0.07, 0.66, 0.07), Vector3(0, 0.37, 0), Color("#e2ecff"))
	blade_base = Node3D.new()
	blade_base.position = Vector3(0, 0.06, 0)
	sword.add_child(blade_base)
	blade_tip = Node3D.new()
	blade_tip.position = Vector3(0, 0.7, 0)
	sword.add_child(blade_tip)
	cast_point = blade_tip
	shield_node = Node3D.new()
	shield_node.position = Vector3(-0.48, 1.2, 0)
	vrm.add_child(shield_node)
	var warning := Label3D.new()
	warning.text = "VRM IMPORT NEEDED"
	warning.position = Vector3(0, 2.16, 0)
	warning.modulate = Color("#ffe08a")
	warning.pixel_size = 0.004
	warning.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	vrm.add_child(warning)

## Blend to a pose; `speed` is the web game's blend rate (higher = snappier).
func play_pose(pose_name: String, speed: float) -> void:
	if player == null or pose_name == _pose or not player.has_animation(pose_name):
		return
	_pose = pose_name
	player.play(pose_name, clampf(2.2 / maxf(speed, 0.1), 0.03, 0.45))
	var anim := player.get_animation(pose_name)
	_hips_target = float(anim.get_meta("hips_y", 0.0))

var _hips_target := 0.0

func _process(dt: float) -> void:
	_t += dt
	_phase += dt * (10.0 + 6.0 * run) * walk
	if motion == null: return
	motion.t = _t
	motion.walk = walk
	motion.run = run
	motion.strafe = strafe
	motion.airborne = airborne
	motion.burst = burst
	motion.phase = _phase
	motion.hips_offset = lerpf(motion.hips_offset, _hips_target, 1.0 - exp(-12.0 * dt))
	if _flash_t > 0.0:
		_flash_t -= dt
		if _flash_t <= 0.0:
			for m in _meshes: m.material_overlay = null

## Brief solid flash over the body (hit feedback).
func flash(color := Color.WHITE, duration := 0.1) -> void:
	_flash_mat.albedo_color = Color(color, 0.85)
	for m in _meshes: m.material_overlay = _flash_mat
	_flash_t = duration

# --- weapons ------------------------------------------------------------------------

## A frame in the hand: +Y runs out of the fist on the thumb side (where a held blade
## points), +X along the fingers. Built from this model's own finger bones.
func _grip(side: String) -> Node3D:
	return FighterRig.make_grip(skeleton, side, rig_profile)

func _foot(side: String) -> Node3D:
	return FighterRig.make_foot(skeleton, side, rig_profile)

func _mat(c: String, metal := false) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(c)
	m.diffuse_mode = BaseMaterial3D.DIFFUSE_TOON
	m.specular_mode = BaseMaterial3D.SPECULAR_TOON
	m.roughness = 0.35 if metal else 0.8
	m.rim_enabled = true
	m.rim = 0.4 if metal else 0.15
	var o := StandardMaterial3D.new()  # inverted-hull outline
	o.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	o.albedo_color = Color(c).darkened(0.65)
	o.cull_mode = BaseMaterial3D.CULL_FRONT
	o.grow = true
	o.grow_amount = 0.006
	m.next_pass = o
	return m

func _glow(c: String) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = Color(c)
	return m

func _part(parent: Node3D, mesh: Mesh, mat: Material, pos := Vector3.ZERO, rot := Vector3.ZERO, scl := Vector3.ONE) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = mat
	mi.position = pos
	mi.rotation = rot
	mi.scale = scl
	parent.add_child(mi)
	return mi

func _box(x: float, y: float, z: float) -> BoxMesh:
	var b := BoxMesh.new(); b.size = Vector3(x, y, z); return b

func _cyl(top: float, bottom: float, h: float, seg := 12) -> CylinderMesh:
	var c := CylinderMesh.new(); c.top_radius = top; c.bottom_radius = bottom; c.height = h; c.radial_segments = seg; return c

func _sph(r: float) -> SphereMesh:
	var s := SphereMesh.new(); s.radius = r; s.height = r * 2; return s

func _pivot(parent: Node3D, pos := Vector3.ZERO) -> Node3D:
	var n := Node3D.new(); n.position = pos; parent.add_child(n); return n

func _build_weapons() -> void:
	var L := look
	var steel := _mat("#eef3ff", true)
	var trim := _mat(L.trim)
	var glow := _glow(L.glow)
	var mount_profile: Dictionary = WeaponMount.profile_for(look, loaded_model_id)
	var r: Node3D = WeaponMount.configure_grip(_grip("Right"), mount_profile, "right")
	var l: Node3D = WeaponMount.configure_grip(_grip("Left"), mount_profile, "left")
	match kit:
		"knight":
			_part(r, _cyl(0.016, 0.018, 0.17), _mat("#5a3a2a"))
			_part(r, _sph(0.026), trim, Vector3(0, -0.1, 0))
			_part(r, _box(0.21, 0.03, 0.04), trim, Vector3(0, 0.1, 0))
			_part(r, _box(0.056, 0.84, 0.012), steel, Vector3(0, 0.535, 0))
			_part(r, _box(0.014, 0.72, 0.016), glow, Vector3(0, 0.5, 0))
			blade_base = _pivot(r, Vector3(0, 0.4, 0)); blade_tip = _pivot(r, Vector3(0, 1.05, 0))
			# Heater shield on the left forearm, facing out from the back of the hand.
			var forearm_mount: Node3D = WeaponMount.forearm_shield_mount(skeleton, rig_profile, l)
			shield_node = _pivot(forearm_mount, Vector3(0, 0, -0.06))
			WeaponMount.configure_shield(shield_node, mount_profile)
			var sh := _pivot(shield_node)
			sh.rotation = Vector3(PI / 2, 0, 0)
			_part(sh, _heater(0.44, 0.68, 0.04), trim)
			_part(sh, _heater(0.4, 0.64, 0.05), _mat(L.shield), Vector3(0, -0.006, 0))
			_part(sh, _box(0.12, 0.06, 0.12), _mat(L.emblem), Vector3(0, -0.03, 0.04), Vector3(0, PI / 4, 0))
		"greatsword":
			_part(r, _cyl(0.02, 0.022, 0.34), _mat("#5a3a2a"), Vector3(0, 0.02, 0))
			_part(r, _box(0.34, 0.05, 0.06), trim, Vector3(0, 0.2, 0))
			_part(r, _box(0.13, 1.25, 0.024), steel, Vector3(0, 0.85, 0))
			_part(r, _box(0.026, 1.1, 0.028), glow, Vector3(0, 0.82, 0))
			blade_base = _pivot(r, Vector3(0, 0.5, 0)); blade_tip = _pivot(r, Vector3(0, 1.62, 0))
			shield_node = _pivot(r, Vector3(0, 0.6, 0))
		"katana":
			_part(r, _cyl(0.016, 0.016, 0.26), _mat(L.band), Vector3(0, -0.02, 0))
			_part(r, _cyl(0.048, 0.048, 0.014, 16), trim, Vector3(0, 0.12, 0))
			for i in 3:
				_part(r, _box(0.032, 0.34, 0.008), steel, Vector3(0.004 * i * i, 0.3 + i * 0.32, 0), Vector3(0, 0, -0.025 * i))
			blade_base = _pivot(r, Vector3(0, 0.35, 0)); blade_tip = _pivot(r, Vector3(0.02, 1.12, 0))
			shield_node = _pivot(r, Vector3(0, 0.5, 0))
		"mage":
			var s := _pivot(r, Vector3(0, -0.25, 0))
			_part(s, _cyl(0.016, 0.016, 1.5), _mat(L.tunic), Vector3(0, 0.45, 0))
			_part(s, _cyl(0.034, 0.016, 0.08), trim, Vector3(0, 1.22, 0))
			var orb := _pivot(s, Vector3(0, 1.32, 0))
			_part(orb, _sph(0.07), _glow(L.glow))
			_part(orb, TorusMesh.new(), trim, Vector3.ZERO, Vector3(PI / 2, 0, 0), Vector3.ONE * 0.11)
			blade_base = _pivot(s, Vector3(0, 0.9, 0)); blade_tip = orb; cast_point = orb
			shield_node = _pivot(l)
		"bow":
			_part(l, _cyl(0.022, 0.022, 0.12), _mat("#5a3a2a"))
			for sgn in [1.0, -1.0]:
				_part(l, _cyl(0.01, 0.019, 0.55), _mat(L.band), Vector3(0, sgn * 0.3, -0.05), Vector3(sgn * -0.2, 0, 0))
			_part(l, _cyl(0.003, 0.003, 1.08), _glow("#f4f0e0"), Vector3(0, 0, -0.1))
			blade_base = l; blade_tip = _pivot(l, Vector3(0, 0, 0.12)); cast_point = blade_tip; shield_node = l
		"assassin":
			for g in [r, l]:
				_part(g, _cyl(0.014, 0.015, 0.12), _mat(L.pants))
				_part(g, _box(0.09, 0.022, 0.03), trim, Vector3(0, 0.07, 0))
				_part(g, _box(0.04, 0.3, 0.01), steel, Vector3(0, 0.23, 0))
			blade_base = _pivot(r, Vector3(0, 0.12, 0)); blade_tip = _pivot(r, Vector3(0, 0.42, 0)); shield_node = l
		"knuckles":
			for g in [r, l]:
				_part(g, _box(0.1, 0.09, 0.1), _mat(L.metal, true), Vector3(0.03, 0, 0.0))
				_part(g, _box(0.11, 0.015, 0.11), glow, Vector3(0.03, 0.05, 0))
			blade_base = r; blade_tip = _pivot(r, Vector3(0.08, 0, 0)); shield_node = l
		"kicks":
			for side in ["Left", "Right"]:
				var f := _foot(side)
				var ring := TorusMesh.new(); ring.inner_radius = 0.045; ring.outer_radius = 0.06
				_part(f, ring, glow, Vector3(0, 0.05, 0))
			var fr := _foot("Right")
			blade_base = _pivot(fr, Vector3(0, 0.1, 0)); blade_tip = _pivot(fr, Vector3(0, 0, 0.12)); shield_node = l
	if cast_point == null: cast_point = blade_tip
	if shield_node == null: shield_node = l

## Heater shield outline (flat top, pointed bottom) extruded along Y.
func _heater(w: float, h: float, depth: float) -> Mesh:
	var pts := PackedVector2Array()
	pts.append(Vector2(-w / 2, h * 0.42)); pts.append(Vector2(w / 2, h * 0.42)); pts.append(Vector2(w / 2, h * 0.02))
	for i in range(1, 9):
		var a := float(i) / 8.0
		pts.append(Vector2(w / 2 * (1.0 - a), lerpf(h * 0.02, -h * 0.58, a * a * 0.5 + a * 0.5)))
	for i in range(1, 8):
		var a := float(i) / 8.0
		pts.append(Vector2(-w / 2 * a, lerpf(-h * 0.58, h * 0.02, a * a * 0.5 + a * 0.5)))
	# Mesh from the outline, lying in the XZ plane, facing +-Y.
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var tri := Geometry2D.triangulate_polygon(pts)
	for side in [1.0, -1.0]:
		for k in range(0, tri.size(), 3):
			var ids := [tri[k], tri[k + 1], tri[k + 2]] if side > 0 else [tri[k + 2], tri[k + 1], tri[k]]
			for id in ids:
				st.set_normal(Vector3(0, side, 0))
				st.add_vertex(Vector3(pts[id].x, side * depth / 2, -pts[id].y))
	for k in pts.size():
		var a := pts[k]; var b := pts[(k + 1) % pts.size()]
		var n := Vector3(b.y - a.y, 0, b.x - a.x).normalized()
		for v in [Vector3(a.x, depth / 2, -a.y), Vector3(b.x, depth / 2, -b.y), Vector3(b.x, -depth / 2, -b.y), Vector3(a.x, depth / 2, -a.y), Vector3(b.x, -depth / 2, -b.y), Vector3(a.x, -depth / 2, -a.y)]:
			st.set_normal(n); st.add_vertex(v)
	return st.commit()
