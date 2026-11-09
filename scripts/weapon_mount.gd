# Fight Royale Godot - Update 05 | automatic procedural weapon mounts.
class_name WeaponMount
extends RefCounted

## All positions are meters in bone-grip local coordinates. Rotations are XYZ
## Euler degrees in that same local space; scale changes all built geometry
## including trail and projectile pivots, keeping the gameplay anchors aligned.
## Missing or invalid entries always use neutral/default transformations.
const SETTINGS := "res://data/weapon_profiles.json"

static func _vec3(raw: Variant, fallback: Vector3 = Vector3.ZERO) -> Vector3:
    if not (raw is Array) or raw.size() != 3:
        return fallback
    for value in raw:
        if not (value is int or value is float):
            return fallback
        if is_nan(float(value)) or is_inf(float(value)):
            return fallback
    return Vector3(float(raw[0]), float(raw[1]), float(raw[2]))

static func _apply(target: Node3D, correction: Dictionary) -> Node3D:
    if target == null:
        return target
    var pos: Vector3 = _vec3(correction.get("position", []))
    var degrees: Vector3 = _vec3(correction.get("rotation_deg", []))
    var amount: float = float(correction.get("scale", 1.0))
    if is_nan(amount) or is_inf(amount) or amount < 0.1 or amount > 5.0:
        amount = 1.0
    var local_offset := Transform3D(Basis.from_euler(Vector3(deg_to_rad(degrees.x), deg_to_rad(degrees.y), deg_to_rad(degrees.z))), pos)
    target.transform = target.transform * local_offset
    target.scale = target.scale * (Vector3.ONE * amount)
    return target

static func _merge_settings(dst: Dictionary, entry: Variant) -> void:
    if not (entry is Dictionary):
        return
    for key in ["right", "left", "shield"]:
        var item: Variant = entry.get(key, {})
        if not (item is Dictionary):
            continue
        var data: Dictionary = dst.get(key, {}).duplicate(true)
        for field in ["position", "rotation_deg", "scale"]:
            if item.has(field):
                data[field] = item[field]
        dst[key] = data

static func profile_for(look: Dictionary, resolved_model_id: String) -> Dictionary:
    var neutral := {"position": [0.0, 0.0, 0.0], "rotation_deg": [0.0, 0.0, 0.0], "scale": 1.0}
    var result := {"right": neutral.duplicate(true), "left": neutral.duplicate(true), "shield": neutral.duplicate(true)}
    if not FileAccess.file_exists(SETTINGS):
        return result
    var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(SETTINGS))
    if not (parsed is Dictionary):
        return result
    var kit_key: String = str(look.get("kit", "")).to_lower()
    var model_key: String = resolved_model_id.to_lower()
    var id_key: String = str(look.get("name", "")).to_lower()
    var kits: Variant = parsed.get("kits", {})
    var models: Variant = parsed.get("models", {})
    var fighters: Variant = parsed.get("fighters", {})
    if kits is Dictionary:
        _merge_settings(result, kits.get(kit_key, {}))
    if models is Dictionary:
        _merge_settings(result, models.get(model_key, {}))
    if fighters is Dictionary:
        _merge_settings(result, fighters.get(id_key, {}))
    return result

static func configure_grip(grip: Node3D, profile: Dictionary, side: String) -> Node3D:
    if grip == null:
        return grip
    var key: String = side.to_lower()
    var entry: Variant = profile.get(key, {})
    if entry is Dictionary:
        _apply(grip, entry)
    return grip

## Mount a shield on the left FOREARM, not on the hand's wrist rotation.
## Copy the hand-grip's REST position into forearm coordinates, preserving the
## shield's position when standing still. If there's no usable forearm, keep
## the original hand-grip mount instead of attaching to a missing bone.
static func forearm_shield_mount(sk: Skeleton3D, rig: Dictionary, left_grip: Node3D) -> Node3D:
    if sk == null or left_grip == null:
        return left_grip
    var forearm_name: String = FighterRig.name_for(sk, "LeftLowerArm", rig)
    var hand_name: String = FighterRig.name_for(sk, "LeftHand", rig)
    var forearm_index: int = sk.find_bone(forearm_name)
    var hand_index: int = sk.find_bone(hand_name)
    if forearm_index < 0 or hand_index < 0:
        push_warning("Fight Royale: no forearm mount; shield will follow hand")
        return left_grip
    var forearm_rest: Transform3D = sk.get_bone_global_rest(forearm_index)
    var hand_rest: Transform3D = sk.get_bone_global_rest(hand_index)
    if absf(forearm_rest.basis.determinant()) < 0.00001:
        return left_grip
    var attachment := BoneAttachment3D.new()
    attachment.name = "LeftShieldForearmAttachment05"
    attachment.bone_name = forearm_name
    sk.add_child(attachment)
    var local_mount := Node3D.new()
    local_mount.name = "ShieldMount05"
    attachment.add_child(local_mount)
    local_mount.transform = forearm_rest.affine_inverse() * hand_rest * left_grip.transform
    return local_mount

static func configure_shield(pivot: Node3D, profile: Dictionary) -> void:
    var entry: Variant = profile.get("shield", {})
    if pivot != null and entry is Dictionary:
        _apply(pivot, entry)
