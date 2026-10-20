"""Standalone offline endpoint previs engine. Requires Blender, never an agent.

Public API: validate_spec, build, capture, retime, render_endpoints, export.
Importing this module does not modify Blender. Builds only a new owned scene.
"""
import copy
import json
import math
import re
import time
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
from bpy_extras.object_utils import world_to_camera_view

VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parent
CAMERA_LIBRARY = ROOT / "assets/camera_rigs.blend"
PRESETS = ["01_慢镜头感", "02_慢推进", "08_中景跟拍", "14_慢速拉出", "19_横移",
           "21_吊臂上升", "22_吊臂下降", "30_180度环绕"]
POSES = ["STAND", "WALK", "RUN", "SIT"]


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _vector(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 3 or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in value):
        raise ValueError(label + " requires three finite coordinates")


def validate_spec(value):
    spec = copy.deepcopy(value)
    if spec.get("schema_version") != "1.0":
        raise ValueError("schema_version must be 1.0")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", spec.get("id", "")):
        raise ValueError("id must be 1–32 ASCII letters/digits/underscores")
    for name in ("frame_start", "frame_end", "fps"):
        if type(spec.get(name)) is not int:
            raise ValueError(name + " must be an integer")
    if not 1 <= spec["fps"] <= 120 or spec["frame_end"] <= spec["frame_start"]:
        raise ValueError("Invalid fps or frame interval")
    resolution = spec.get("resolution", [1280, 720])
    if not isinstance(resolution, (list, tuple)) or len(resolution) != 2 or any(
            type(v) is not int or not 16 <= v <= 8192 for v in resolution):
        raise ValueError("Resolution requires two integer dimensions between 16 and 8192")
    actors = spec.get("actors", [])
    if not 1 <= len(actors) <= 8:
        raise ValueError("Provide 1–8 actors")
    registry = _json(ROOT / "assets/registry.json")["assets"]
    ids = []
    for actor in actors:
        aid = actor.get("id", "")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", aid) or aid in ids:
            raise ValueError("Actor IDs must be valid and unique")
        ids.append(aid)
        if actor.get("asset") not in registry:
            raise ValueError("Unknown actor asset")
        if not (ROOT / registry[actor["asset"]]["file"]).is_file():
            raise ValueError("Bundled character file is missing: " + actor["asset"])
        for which in ("start", "end"):
            state = actor[which]
            _vector(state["position"], aid + "." + which)
            if state.get("pose", "STAND") not in POSES:
                raise ValueError("Unknown endpoint pose")
            yaw = state.get("yaw_deg", 0)
            if not isinstance(yaw, (float, int)) or not math.isfinite(yaw):
                raise ValueError("yaw_deg must be finite")
    camera = spec["camera"]
    if camera.get("preset") not in PRESETS:
        raise ValueError("Choose a supported single-camera constraint preset")
    if not CAMERA_LIBRARY.is_file():
        raise ValueError("Bundled camera library is missing")
    for which in ("start", "end", "aim_start", "aim_end"):
        _vector(camera[which], "camera." + which)
    fixed = camera["preset"] == "01_慢镜头感" or bool(camera.get("hold_position"))
    if fixed and (Vector(camera["end"])-Vector(camera["start"])).length > .001:
        raise ValueError("Fixed camera requires identical start and end positions")
    if not fixed and not camera.get("via") and (Vector(camera["end"]) - Vector(camera["start"])).length < .001:
        raise ValueError("Use distinct camera endpoints; a tiny path can be held at progress 0")
    for camera_point, aim_point in (("start", "aim_start"), ("end", "aim_end")):
        if (Vector(camera[camera_point])-Vector(camera[aim_point])).length < .05:
            raise ValueError("Camera and look target must be separated")
    lens = camera.get("lens_mm", 40)
    if not isinstance(lens, (float, int)) or not math.isfinite(lens) or not 5 <= lens <= 300:
        raise ValueError("lens_mm must be between 5 and 300")
    for via in camera.get("via", []):
        _vector(via, "camera.via")
    if len(camera.get("via", [])) > 32:
        raise ValueError("At most 32 intermediate curve controls")
    if camera.get("timing", "LINEAR") not in {"LINEAR", "BEZIER"}:
        raise ValueError("Timing must be LINEAR or BEZIER")
    return spec


def _empty(collection, name, location, display="SPHERE"):
    obj = bpy.data.objects.new(name, None)
    collection.objects.link(obj)
    obj.location = location
    obj.empty_display_type = display
    obj.empty_display_size = .18
    obj.hide_render = True
    return obj


def _collection(scene, name):
    collection = bpy.data.collections.new(name)
    scene.collection.children.link(collection)
    return collection


def _var(driver, name, obj, path):
    var = driver.variables.new()
    var.name = name
    var.type = "SINGLE_PROP"
    var.targets[0].id = obj
    var.targets[0].data_path = path


def _linear_driver(owner, data_path, index, start, end, progress, constant=0):
    fc = owner.driver_add(data_path, index)
    driver = fc.driver
    driver.type = "SCRIPTED"
    _var(driver, "a", start, data_path + "[" + str(index) + "]")
    _var(driver, "b", end, data_path + "[" + str(index) + "]")
    _var(driver, "u", progress, '["progress"]')
    driver.expression = repr(constant) + "+a+(b-a)*u"


def action_curves(obj):
    ad = obj.animation_data
    if not ad or not ad.action:
        return []
    action = ad.action
    if getattr(action, "is_action_legacy", True):
        return list(action.fcurves)
    result = []
    for layer in action.layers:
        for strip in layer.strips:
            bag = strip.channelbag(ad.action_slot) if ad.action_slot else None
            if bag:
                result.extend(bag.fcurves)
    return result


def _progress_keys(controller, start, end, interpolation):
    controller.animation_data_clear()
    for frame, value in ((start, 0.), (end, 1.)):
        controller["progress"] = value
        controller.keyframe_insert(data_path='["progress"]', frame=frame)
    for fc in action_curves(controller):
        for key in fc.keyframe_points:
            key.interpolation = interpolation
            if interpolation == "BEZIER":
                key.handle_left_type = key.handle_right_type = "AUTO_CLAMPED"


def _set_poses(rig, p0, p1, start, end):
    rig.animation_data_clear()
    for bone in rig.pose.bones:
        name = bone.name.split(":")[-1]
        bone.rotation_mode = "QUATERNION"
        bone.scale = (1, 1, 1)
        for path in ("location", "rotation_quaternion"):
            v0, v1 = p0[name][path], p1[name][path]
            different = any(abs(a-b) > 1e-6 for a, b in zip(v0, v1))
            setattr(bone, path, v0)
            if different:
                bone.keyframe_insert(data_path=path, frame=start, group=name)
                setattr(bone, path, v1)
                bone.keyframe_insert(data_path=path, frame=end, group=name)
    for fc in action_curves(rig):
        for key in fc.keyframe_points:
            key.interpolation = "LINEAR"


def _actors(scene, spec, progress, prefix):
    registry = _json(ROOT / "assets/registry.json")["assets"]
    poses = _json(ROOT / "assets/poses.json")
    result = []
    collection = _collection(scene, prefix + ".ACTORS")
    for actor in spec["actors"]:
        asset = registry[actor["asset"]]
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=str(ROOT / asset["file"]))
        imported = list(set(bpy.data.objects)-before)
        rig = next(obj for obj in imported if obj.type == "ARMATURE")
        rig.animation_data_clear()
        name = prefix + "." + actor["id"]
        root = _empty(collection, name + ".ROOT", (0, 0, 0), "ARROWS")
        for obj in imported:
            for link in list(obj.users_collection):
                link.objects.unlink(obj)
            collection.objects.link(obj)
            if not obj.parent:
                matrix = obj.matrix_world.copy()
                obj.parent = root
                obj.matrix_parent_inverse = Matrix.Identity(4)
                obj.matrix_basis = matrix
        rig.name = name + ".RIG"
        controls = []
        for which in ("start", "end"):
            state = actor[which]
            ctrl = _empty(collection, name + "." + which.upper(), state["position"], "CUBE")
            ctrl.rotation_euler.z = math.radians(state.get("yaw_deg", 0))
            ctrl["pose"] = state.get("pose", "STAND")
            ctrl["help"] = "Move this endpoint in meters; rotate Z to change actor heading."
            controls.append(ctrl)
        for axis in range(3):
            _linear_driver(root, "location", axis, *controls, progress)
        _linear_driver(root, "rotation_euler", 2, *controls, progress,
                       constant=math.radians(asset["forward_correction_deg"]))
        p0, p1 = [poses[actor["asset"]][actor[which].get("pose", "STAND")]["bones"] for which in ("start", "end")]
        _set_poses(rig, p0, p1, spec["frame_start"], spec["frame_end"])
        material = bpy.data.materials.new(name + ".Neutral")
        material.diffuse_color = (.16, .40, .59, 1) if actor["asset"] == "x_bot" else (.72, .36, .18, 1)
        for obj in imported:
            if obj.type == "MESH":
                obj.data.materials.clear()
                obj.data.materials.append(material)
                for polygon in obj.data.polygons:
                    polygon.material_index = 0
        result.append({"id": actor["id"], "asset": actor["asset"], "root": root.name,
                       "rig": rig.name, "start": controls[0].name, "end": controls[1].name})
    return result


def _camera(scene, spec, progress, prefix):
    config = spec["camera"]
    fixed = config["preset"] == "01_慢镜头感" or bool(config.get("hold_position"))
    with bpy.data.libraries.load(str(CAMERA_LIBRARY), link=False) as (source, target):
        if config["preset"] not in source.collections:
            raise ValueError("Preset missing from bundled library")
        target.collections = [config["preset"]]
    collection = target.collections[0]
    scene.collection.children.link(collection)
    collection.name = prefix + ".CAMERA_RIG"
    camera = next(obj for obj in collection.objects if obj.type == "CAMERA")
    track = next(con for con in camera.constraints if con.type == "DAMPED_TRACK")
    aim = track.target
    paths = [obj for obj in collection.objects if obj.type == "CURVE"]
    hint_name = camera.get("PATH_GUIDE", "")
    path = next((obj for obj in paths if obj.name == hint_name), paths[-1] if paths else None)
    original = [point.co.copy() for point in path.data.splines[0].bezier_points] if path else []
    keep = {camera, aim, path, camera.parent}
    for obj in list(collection.objects):
        obj.animation_data_clear()
        if obj.data and hasattr(obj.data, "animation_data_clear"):
            obj.data.animation_data_clear()
        obj.hide_render = obj.type != "CAMERA"
        if obj not in keep:
            bpy.data.objects.remove(obj, do_unlink=True)
    root = camera.parent
    if root:
        root.location = (0, 0, 0)
        root.rotation_euler = (0, 0, 0)
        root.scale = (1, 1, 1)
        root.name = prefix + ".CAMERA_ROOT"
    if path is None:
        data = bpy.data.curves.new(prefix + ".PATH_DATA", "CURVE")
        path = bpy.data.objects.new(prefix + ".PATH", data)
        collection.objects.link(path)
    path.name = prefix + ".PATH_EDITABLE"
    path.parent = None
    path.matrix_world = Matrix.Identity(4)
    path.hide_render = True
    start, end = Vector(config["start"]), Vector(config["end"])
    if fixed:
        points = [start, start+Vector((.001, 0, 0))]
    elif "via" in config:
        points = [start] + [Vector(v) for v in config["via"]] + [end]
    elif len(original) >= 2 and (original[-1]-original[0]).length > .001:
        old = original[-1]-original[0]
        new = end-start
        rotate = old.rotation_difference(new)
        points = [start+rotate@(point-original[0])*(new.length/old.length) for point in original]
    else:
        points = [start, end]
    path.data.splines.clear()
    path.data.dimensions = "3D"
    path.data.use_path = True
    path.data.resolution_u = 24
    spline = path.data.splines.new("BEZIER")
    spline.bezier_points.add(len(points)-1)
    for bp, point in zip(spline.bezier_points, points):
        bp.co = point
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    handles = []
    for label, location, index in (("CAM_START", start, 0), ("CAM_END", end, len(points)-1)):
        control = _empty(collection, prefix + "." + label, location)
        bpy.context.view_layer.update()
        hook = path.modifiers.new(label, "HOOK")
        hook.object = control
        hook.vertex_indices_set([3*index, 3*index+1, 3*index+2])
        hook.matrix_inverse = control.matrix_world.inverted() @ path.matrix_world
        handles.append(control)
    aims = [_empty(collection, prefix + ".AIM_" + which.upper(), config["aim_"+which]) for which in ("start", "end")]
    aim.parent = None
    aim.name = prefix + ".AIM_RESOLVED"
    for axis in range(3):
        _linear_driver(aim, "location", axis, *aims, progress)
    camera.name = prefix + ".CAMERA"
    camera.location = (0, 0, 0)
    camera.rotation_euler = (Vector(config["aim_start"])-start).to_track_quat('-Z','Y').to_euler() if fixed else (0, 0, 0)
    if fixed:
        follow = camera.constraints.new("COPY_LOCATION")
        follow.name = "01_FIXED_POSITION"
        follow.target = handles[0]
        path.hide_set(True)
        handles[1].hide_set(True)
    else:
        follow = camera.constraints.new("FOLLOW_PATH")
        follow.name = "01_PATH_progress"
        follow.target = path
        follow.use_fixed_location = True
        follow.use_curve_follow = True
        follow.forward_axis, follow.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
        fc = follow.driver_add("offset_factor")
        _var(fc.driver, "u", progress, '["progress"]')
        fc.driver.expression = "u"
    # Follow Path resolves translation first; the reused library aim resolves orientation.
    bpy.context.view_layer.objects.active = camera
    camera.constraints.move(len(camera.constraints)-1, 0)
    track.name = "02_AIM_reused_library_constraint"
    track.track_axis = "TRACK_NEGATIVE_Z"
    camera.data.type = "PERSP"
    camera.data.sensor_width = 36
    camera.data.clip_start = .03
    camera.data.clip_end = 1000
    camera.data.dof.use_dof = False
    fc = camera.data.driver_add("lens")
    _var(fc.driver, "focal", progress, '["lens_mm"]')
    fc.driver.expression = "focal"
    scene.camera = camera
    return {"camera": camera.name, "path": path.name, "fixed": fixed, "start": handles[0].name,
            "end": handles[1].name, "aim_start": aims[0].name, "aim_end": aims[1].name}


def build(value):
    """Validate before scene creation. Never clears the caller's existing scene."""
    spec = validate_spec(value)
    if bpy.context.mode != "OBJECT":
        raise ValueError("请先回到物体模式，再新建预演")
    started = time.perf_counter()
    scene = bpy.data.scenes.new("PV_" + spec["id"])
    bpy.context.window.scene = scene
    scene["pv_owned"] = True
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    scene.render.fps = spec["fps"]
    scene.frame_start, scene.frame_end = spec["frame_start"], spec["frame_end"]
    prefix = scene.name
    control_collection = _collection(scene, prefix + ".CONTROLS")
    progress = _empty(control_collection, prefix + ".PROGRESS", (0, 0, 0), "ARROWS")
    progress["progress"] = 0.
    progress["lens_mm"] = spec["camera"].get("lens_mm", 40)
    progress.id_properties_ui("progress").update(min=0, max=1)
    progress.id_properties_ui("lens_mm").update(min=5, max=300)
    _progress_keys(progress, scene.frame_start, scene.frame_end, spec["camera"].get("timing", "LINEAR"))
    actors = _actors(scene, spec, progress, prefix)
    camera = _camera(scene, spec, progress, prefix)
    # FBX imports can adopt their source FPS. The shot contract owns timing.
    scene.render.fps, scene.render.fps_base = spec["fps"], 1.0
    scene.frame_start, scene.frame_end = spec["frame_start"], spec["frame_end"]
    ground_collection = _collection(scene, prefix + ".GROUND")
    mesh = bpy.data.meshes.new(prefix + ".GROUND_MESH")
    mesh.from_pydata([(-10,-10,0),(10,-10,0),(10,10,0),(-10,10,0)], [], [(0,1,2,3)])
    floor = bpy.data.objects.new(prefix + ".GROUND", mesh)
    ground_collection.objects.link(floor)
    material = bpy.data.materials.new(prefix + ".GroundMaterial")
    material.diffuse_color = (.20, .23, .27, 1)
    mesh.materials.append(material)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x, scene.render.resolution_y = spec.get("resolution", [1280, 720])
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = "WORLD"
    scene.world = bpy.data.worlds.new(prefix + ".World")
    scene.world.color = (.055, .065, .08)
    scene["pv_spec"] = json.dumps(spec, ensure_ascii=False)
    scene["pv_refs"] = json.dumps({"progress": progress.name, "actors": actors, "camera": camera}, ensure_ascii=False)
    if hasattr(scene, "pv_settings"):
        scene.pv_settings.lens = spec["camera"].get("lens_mm", 40)
        scene.pv_settings.duration = max(1, round((scene.frame_end-scene.frame_start)/scene.render.fps))
    scene["pv_build_seconds"] = time.perf_counter()-started
    scene.frame_set(scene.frame_start)
    bpy.context.view_layer.update()
    return scene


def refs(scene):
    if not scene.get("pv_owned"):
        raise ValueError("Select a scene generated by Offline Previs")
    return json.loads(scene["pv_refs"])


def capture(scene):
    reference = refs(scene)
    spec = json.loads(scene["pv_spec"])
    spec["frame_start"], spec["frame_end"], spec["fps"] = scene.frame_start, scene.frame_end, scene.render.fps
    for actor, record in zip(spec["actors"], reference["actors"]):
        for which in ("start", "end"):
            obj = bpy.data.objects[record[which]]
            actor[which]["position"] = list(obj.location)
            actor[which]["yaw_deg"] = math.degrees(obj.rotation_euler.z)
            actor[which]["pose"] = obj["pose"]
    for which in ("start", "end", "aim_start", "aim_end"):
        spec["camera"][which] = list(bpy.data.objects[reference["camera"][which]].location)
    path = bpy.data.objects[reference["camera"]["path"]]
    spec["camera"]["via"] = [list(path.matrix_world@bp.co) for bp in list(path.data.splines[0].bezier_points)[1:-1]]
    if reference["camera"].get("fixed"):
        spec["camera"]["end"] = spec["camera"]["start"][:]
        spec["camera"]["via"] = []
    spec["camera"]["lens_mm"] = bpy.data.objects[reference["progress"]]["lens_mm"]
    return spec


def set_lens(scene, value):
    if not isinstance(value, (int, float)) or not math.isfinite(value) or not 5 <= value <= 300:
        raise ValueError("lens_mm must be between 5 and 300")
    progress = bpy.data.objects[refs(scene)["progress"]]
    progress["lens_mm"] = value
    progress.update_tag()
    scene.frame_set(scene.frame_current, subframe=scene.frame_subframe)


def apply_poses(scene):
    """Refresh endpoint poses without reimporting actors or changing camera controls."""
    spec = validate_spec(capture(scene))
    reference = refs(scene)
    poses = _json(ROOT / "assets/poses.json")
    old_frame, old_sub = scene.frame_current, scene.frame_subframe
    for actor, record in zip(spec["actors"], reference["actors"]):
        p0, p1 = [poses[actor["asset"]][actor[which]["pose"]]["bones"] for which in ("start", "end")]
        _set_poses(bpy.data.objects[record["rig"]], p0, p1, scene.frame_start, scene.frame_end)
    scene["pv_spec"] = json.dumps(spec, ensure_ascii=False)
    scene.frame_set(old_frame, subframe=old_sub)


def retime(scene, start, end):
    """Retimes just the two endpoints; never bakes the camera or actor roots."""
    if type(start) is not int or type(end) is not int or end <= start:
        raise ValueError("Frame end must follow start")
    reference = refs(scene)
    old_start, old_end = scene.frame_start, scene.frame_end
    alpha = max(0., min(1., (scene.frame_current+scene.frame_subframe-old_start)/(old_end-old_start)))
    for actor in reference["actors"]:
        for fc in action_curves(bpy.data.objects[actor["rig"]]):
            for kp in fc.keyframe_points:
                t = (kp.co.x-old_start)/(old_end-old_start)
                kp.co.x = start+t*(end-start)
            fc.update()
    progress = bpy.data.objects[reference["progress"]]
    config = json.loads(scene["pv_spec"])
    _progress_keys(progress, start, end, config["camera"].get("timing", "LINEAR"))
    scene.frame_start, scene.frame_end = start, end
    current = start+alpha*(end-start)
    scene.frame_set(int(current), subframe=current-int(current))


def inspect_endpoints(scene):
    """Read exactly two states. Returns evidence, never reframes or bakes a shot.

    Projection warnings are informational: a close-up may intentionally omit feet.
    This does not assess gait, acting, occlusion or continuous collisions.
    """
    reference = refs(scene)
    camera = bpy.data.objects[reference["camera"]["camera"]]
    old_scene = bpy.context.window.scene
    old_frame, old_sub = scene.frame_current, scene.frame_subframe
    rows, warnings, errors = [], [], []
    try:
        bpy.context.window.scene = scene
        for label, frame in (("start", scene.frame_start), ("end", scene.frame_end)):
            scene.frame_set(frame)
            dg = bpy.context.evaluated_depsgraph_get()
            cam = camera.evaluated_get(dg)
            aim = bpy.data.objects[reference["camera"]["aim_"+label]].matrix_world.translation
            delta = aim-cam.matrix_world.translation
            aligned = delta.length>.001 and (cam.matrix_world.to_quaternion()@Vector((0,0,-1))).dot(delta.normalized())>.999
            if not aligned:
                errors.append({"code":"AIM_MISMATCH", "frame":frame})
            row = {"state":label, "frame":frame, "camera_position":list(cam.matrix_world.translation),
                   "lens_mm":cam.data.lens, "aim_aligned":bool(aligned), "actors":[]}
            for actor in reference["actors"]:
                rig = bpy.data.objects[actor["rig"]].evaluated_get(dg)
                points = []
                for bone_name in ("Head", "LeftToeBase", "RightToeBase"):
                    bone = next(b for b in rig.pose.bones if b.name.split(":")[-1]==bone_name)
                    point = rig.matrix_world@bone.head
                    p = world_to_camera_view(scene, cam, point)
                    inside = cam.data.clip_start<=p.z<=cam.data.clip_end and 0<=p.x<=1 and 0<=p.y<=1
                    points.append({"bone":bone_name,"ndc":list(p),"inside":inside})
                    if not inside:
                        warnings.append({"code":"POINT_OUTSIDE_FRAME","actor":actor["id"],"bone":bone_name,"frame":frame})
                root = bpy.data.objects[actor["root"]].evaluated_get(dg)
                row["actors"].append({"id":actor["id"],"asset":actor["asset"],"position":list(root.matrix_world.translation),"points":points})
            rows.append(row)
    finally:
        scene.frame_set(old_frame,subframe=old_sub)
        bpy.context.window.scene = old_scene
    camera_keys = sum(len(fc.keyframe_points) for fc in action_curves(camera))
    if camera_keys:
        warnings.append({"code":"CAMERA_ACTION_KEYS_PRESENT","count":camera_keys})
    return {"status":"error" if errors else "sampled_endpoint_checks_passed", "version":VERSION,
            "camera_action_keys":camera_keys,"endpoints":rows,"errors":errors,"warnings":warnings,
            "unverified":["intermediate_gait_and_acting","continuous_collisions","occlusion","aesthetic_quality"]}


def render_endpoints(scene, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    reference = refs(scene)
    old_scene = bpy.context.window.scene
    old_frame, old_subframe, old_path, old_camera = scene.frame_current, scene.frame_subframe, scene.render.filepath, scene.camera
    try:
        bpy.context.window.scene = scene
        scene.camera = bpy.data.objects[reference["camera"]["camera"]]
        for name, frame in (("start", scene.frame_start), ("end", scene.frame_end)):
            scene.frame_set(frame)
            scene.render.filepath = str(output / (name + ".png"))
            bpy.ops.render.render(write_still=True)
        (output / "shot.json").write_text(json.dumps(capture(scene), ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "checks.json").write_text(json.dumps(inspect_endpoints(scene), ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        scene.frame_set(old_frame, subframe=old_subframe)
        scene.render.filepath, scene.camera = old_path, old_camera
        bpy.context.window.scene = old_scene
    return output


def export(scene, output):
    output = render_endpoints(scene, output)
    # Write just the owned scene and dependencies. Do not change the caller's
    # current project path or include unrelated scenes from a host application.
    bpy.data.libraries.write(str(output / "previs.blend"), {scene}, path_remap="RELATIVE", fake_user=True)
    return output
