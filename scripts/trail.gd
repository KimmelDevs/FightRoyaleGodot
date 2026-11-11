class_name Trail
extends MeshInstance3D
## FRG17B - twin-layer weapon trails
## Bright core plus softly fading edge; samples interpolate through quick swings.
## Compatibility: Trail.new(base, tip, color), .emitting and .tick(dt).
## No hit detection is performed here. This node only draws a ribbon.

const SAMPLES := 26
const MAX_INTERPOLATION := 5

var base: Node3D
var tip: Node3D
var emitting := false
var _pts: Array = [] # [blade_base, blade_tip, age_seconds, intensity]
var _im := ImmediateMesh.new()
var _color: Color = Color.WHITE
var _life := 0.22
var _spread := 1.22
var _brightness := 1.0
var _previous_base := Vector3.ZERO
var _previous_tip := Vector3.ZERO
var _has_previous := false

func _init(b: Node3D, t: Node3D, color: Color) -> void:
    base = b
    tip = t
    _color = color
    mesh = _im
    var material := StandardMaterial3D.new()
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.vertex_color_use_as_albedo = true
    material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
    material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
    material.cull_mode = BaseMaterial3D.CULL_DISABLED
    material.albedo_color = Color.WHITE
    material_override = material
    top_level = true

## Changes VFX character, not weapon grip, attacks, or the humanoid rig.
func configure(kit: String, element: String) -> void:
    match kit:
        "greatsword":
            _life = 0.28
            _spread = 1.34
            _brightness = 1.12
        "katana", "assassin":
            _life = 0.18
            _spread = 1.13
            _brightness = 1.08
        "knuckles", "kicks":
            _life = 0.14
            _spread = 1.10
            _brightness = 0.80
        "mage", "bow":
            _life = 0.20
            _spread = 1.16
            _brightness = 0.72
        _:
            _life = 0.22
            _spread = 1.22
            _brightness = 1.0
    if element in ["light", "lightning", "electric", "ice"]:
        _brightness *= 1.12

func _sample(a: Vector3, b: Vector3, intensity: float) -> void:
    if a.distance_squared_to(b) < 0.0009:
        return
    _pts.append([a, b, 0.0, intensity])
    while _pts.size() > SAMPLES:
        _pts.pop_front()

func tick(dt: float) -> void:
    var step := maxf(0.0, dt)
    for sample in _pts:
        sample[2] = float(sample[2]) + step
    while not _pts.is_empty() and float(_pts[0][2]) >= _life:
        _pts.pop_front()
    # A paused game must not generate new frames of a swing.
    if emitting and step > 0.0 and is_instance_valid(base) and is_instance_valid(tip):
        var a := base.global_position
        var b := tip.global_position
        if _has_previous:
            var distance := maxf(a.distance_to(_previous_base), b.distance_to(_previous_tip))
            if distance > 3.5:
                # Teleports and forced repositioning should not draw across an arena.
                _pts.clear()
                _sample(a, b, 0.8)
            elif distance > 0.012:
                var subdivisions := clampi(ceili(distance / 0.18), 1, MAX_INTERPOLATION)
                var speed := distance / maxf(step, 0.008)
                var energy := clampf(0.65 + speed * 0.042, 0.70, 1.30)
                for j in range(1, subdivisions + 1):
                    var t := float(j) / float(subdivisions)
                    _sample(_previous_base.lerp(a, t), _previous_tip.lerp(b, t), energy)
        else:
            _sample(a, b, 0.9)
        _previous_base = a
        _previous_tip = b
        _has_previous = true
    elif not emitting:
        _has_previous = false
    _im.clear_surfaces()
    if _pts.size() < 2:
        return
    _draw_layer(true)
    _draw_layer(false)

func _draw_layer(outer: bool) -> void:
    _im.surface_begin(Mesh.PRIMITIVE_TRIANGLE_STRIP)
    var n := _pts.size()
    for i in range(n):
        var sample: Array = _pts[i]
        var a: Vector3 = sample[0]
        var b: Vector3 = sample[1]
        var age: float = float(sample[2])
        var energy: float = float(sample[3])
        var life_fraction := clampf(1.0 - age / maxf(_life, 0.01), 0.0, 1.0)
        var leading_edge := pow(float(i + 1) / float(n), 0.6)
        var opacity := life_fraction * life_fraction * leading_edge * energy * _brightness
        # The outer ribbon is wider and translucent. The inner one is narrow
        # and bright, giving clear contours without any postprocessing blur.
        var center := (a + b) * 0.5
        var width := _spread if outer else 0.66
        var left := center + (a - center) * width
        var right := center + (b - center) * width
        var tint := _color if outer else _color.lerp(Color.WHITE, 0.60)
        var alpha := clampf(opacity * (0.26 if outer else 0.87), 0.0, 0.95)
        var color := Color(tint.r, tint.g, tint.b, alpha)
        _im.surface_set_color(color)
        _im.surface_add_vertex(left)
        _im.surface_set_color(color)
        _im.surface_add_vertex(right)
    _im.surface_end()
