extends SceneTree
## Optional Godot-side verification, launched by the Python installer with --check-godot.
func _init() -> void:
    var results: Array[String] = []
    var cfg: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/rig_profiles.json"))
    if not (cfg is Dictionary):
        printerr("RIG04 ERROR: no readable rig profiles")
        quit(2)
        return
    var models: Dictionary = cfg.get("models", {})
    var failed: int = 0
    for id in models.keys():
        var path: String = "res://models/%s.vrm" % id
        var packed: Resource = load(path)
        if not (packed is PackedScene):
            results.append(str(id) + ": VRM import failed")
            failed += 1
            continue
        var scene: Node = (packed as PackedScene).instantiate()
        var sk: Skeleton3D = FighterRig.find_skeleton(scene)
        if sk == null:
            results.append(str(id) + ": Skeleton3D not found")
            failed += 1
        else:
            var profile: Dictionary = models[id]
            var mapped: Dictionary = FighterRig.runtime_bone_map(sk, profile)
            var required: Array = ["Hips", "Head", "LeftHand", "RightHand", "LeftFoot", "RightFoot"]
            var missing: Array[String] = []
            for key in required:
                if not mapped.has(key):
                    missing.append(key)
            results.append(str(id) + ": " + str(sk.get_bone_count()) + " bones, " + str(mapped.size()) + " roles, missing=" + str(missing))
            if not missing.is_empty():
                failed += 1
        scene.free()
    for line in results:
        print("RIG04 ", line)
    print("RIG04 completed: models=", models.size(), " errors=", failed)
    quit(0 if failed == 0 else 2)
