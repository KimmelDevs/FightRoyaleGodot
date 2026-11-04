extends SceneTree
## Loads every script under res://scripts and reports parse failures (CI-style check).
func _init() -> void:
	var bad := 0
	for f in DirAccess.get_files_at("res://scripts"):
		if not f.ends_with(".gd"): continue
		var s: Script = load("res://scripts/" + f)
		if s == null or not s.can_instantiate():
			print("FAIL ", f); bad += 1
	print("checked, failures: ", bad)
	quit(bad)
