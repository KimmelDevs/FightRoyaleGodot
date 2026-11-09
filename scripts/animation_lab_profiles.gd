extends RefCounted
## Update 16A. Versioned, character-specific locomotion overrides.
## In editor/development builds settings are copied to res://data/animation_lab_profiles.json.
## user:// overrides allow changes even in a read-only exported game.

const PROJECT_PATH := "res://data/animation_lab_profiles.json"
const USER_PATH := "user://animation_lab_profiles.json"
const STATES := ["idle", "walk", "run"]

static func _load_document(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var decoded: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if decoded is Dictionary and decoded.get("fighters", {}) is Dictionary:
		return decoded
	return {}

static func load_for(character_id: String) -> Dictionary:
	var document: Dictionary = _load_document(USER_PATH)
	if document.is_empty():
		document = _load_document(PROJECT_PATH)
	var fighters: Dictionary = document.get("fighters", {})
	var value: Variant = fighters.get(character_id, {})
	if value is Dictionary:
		return (value as Dictionary).duplicate(true)
	return {}

static func new_profile() -> Dictionary:
	return {"poses": {"idle": {}, "walk": {}, "run": {}}, "gait": {"stride": 1.0, "knee": 1.0, "arms": 1.0, "bob": 1.0}}

static func get_angles(profile: Dictionary, state: String, bone: String) -> Vector3:
	var poses: Dictionary = profile.get("poses", {})
	var offsets: Dictionary = poses.get(state, {})
	var a: Variant = offsets.get(bone, [0.0, 0.0, 0.0])
	if not (a is Array) or a.size() != 3:
		return Vector3.ZERO
	return Vector3(float(a[0]), float(a[1]), float(a[2]))

static func put_angles(profile: Dictionary, state: String, bone: String, angles: Vector3) -> void:
	if not profile.has("poses") or not (profile["poses"] is Dictionary):
		profile["poses"] = {}
	var poses: Dictionary = profile["poses"]
	if not poses.has(state) or not (poses[state] is Dictionary):
		poses[state] = {}
	var state_bones: Dictionary = poses[state]
	if angles.length_squared() < 0.00001:
		state_bones.erase(bone)
	else:
		state_bones[bone] = [snappedf(angles.x, 0.1), snappedf(angles.y, 0.1), snappedf(angles.z, 0.1)]

static func _write_document(path: String, document: Dictionary) -> bool:
	var handle := FileAccess.open(path, FileAccess.WRITE)
	if handle == null:
		return false
	handle.store_string(JSON.stringify(document, "\t") + "\n")
	handle.close()
	return true

static func save_for(character_id: String, profile: Dictionary) -> String:
	if character_id.is_empty():
		return "No character selected."
	var document := _load_document(USER_PATH)
	if document.is_empty():
		document = _load_document(PROJECT_PATH)
	if document.is_empty():
		document = {"version": 1, "fighters": {}}
	var fighters: Dictionary = document.get("fighters", {})
	fighters[character_id] = profile.duplicate(true)
	document["fighters"] = fighters
	document["version"] = 1
	if not _write_document(USER_PATH, document):
		return "ERROR: Could not save to user://animation_lab_profiles.json"
	# Best effort: update the shared project JSON when running from a writable checkout.
	# Exported games generally cannot write res://, but user:// is always authoritative.
	if _write_document(PROJECT_PATH, document):
		return "Saved for " + character_id + " (user + project JSON)"
	return "Saved for " + character_id + " (user data only; project folder read-only)"
