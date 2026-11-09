extends SceneTree
## Optional runtime sanity check with --check-godot. Does not require user input.
func _init() -> void:
    call_deferred("_verify")

func _verify() -> void:
    var roster: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/roster.json"))
    if not (roster is Array):
        printerr("MOUNT05 ERROR: missing roster")
        quit(2)
        return
    var failures: int = 0
    var checked: int = 0
    for fighter in roster:
        if not (fighter is Dictionary):
            continue
        var look: Dictionary = fighter.get("look", {})
        var id: String = str(fighter.get("id", "unknown"))
        var requested: String = str(look.get("vrm", ""))
        var model_id: String = requested
        if not ResourceLoader.exists("res://models/%s.vrm" % model_id):
            model_id = "rook" if str(look.get("body", "f")) == "m" else "ember"
        if not ResourceLoader.exists("res://models/%s.vrm" % model_id):
            print("MOUNT05 SKIP ", id, ": missing model and fallback")
            continue
        var body := FighterModel.new()
        root.add_child(body)
        body.setup(look)
        var valid: bool = body.skeleton != null and body.blade_base != null and body.blade_tip != null and body.shield_node != null
        if valid:
            valid = body.blade_base.global_transform.origin.is_finite() and body.blade_tip.global_transform.origin.is_finite()
        if valid:
            checked += 1
            print("MOUNT05 OK ", id, " kit=", str(look.get("kit", "")), " rig=", body.loaded_model_id)
        else:
            failures += 1
            printerr("MOUNT05 FAIL ", id, " missing weapon or skeleton anchor")
        body.free()
    print("MOUNT05 result: checked=", checked, " failed=", failures)
    quit(0 if failures == 0 and checked > 0 else 2)
