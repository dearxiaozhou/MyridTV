# -*- coding: utf-8 -*-
"""
镜头预演渲染器（Blender 端 · 多 Scene 版）
============================================
读取镜头表 JSON，自动搭建草模场景（地面/道具/胶囊人），
每镜头一个独立 Blender Scene（共享场景道具），摄像机按运镜类型生成关键帧动画。

两种模式:
  1. 构建 .blend（前端可看可改）:
       blender.exe --python previz_render.py -- \
           --input 镜头表.json --save-blend 预演.blend
     生成的 .blend 打开后左侧 Scene 列表 = 每个镜头，点选即看该镜头动画，
     可在界面里直接拖拽人物/摄像机修改，改完保存。

  2. 无头直接渲染镜头 MP4（后台）:
       blender.exe --background --python previz_render.py -- \
           --input 镜头表.json --output 输出目录 --video-dir 镜头视频目录
     每个镜头由 Blender 直接编码 MP4，并写 manifest.json 供拼接器使用。

参数:
  --input      镜头表 JSON 路径（必填）
  --output     清单输出目录（渲染模式）
  --video-dir  Blender 直接编码的镜头 MP4 输出目录
  --save-blend .blend 保存路径（构建模式）
  --fps        覆盖帧率（可选）
"""
import bpy
import json
import math
import os
import random
import sys

import mathutils

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
from camera_language import effective_moves, shot_languages, support_assets_for_languages

# ---------------- 默认参数 ----------------
SHOT_SIZE = {  # 景别 -> 默认焦距(mm) / 视距(m)
    "特写":   {"focal": 85, "dist": 1.5},
    "近景":   {"focal": 50, "dist": 2.5},
    "中近景": {"focal": 35, "dist": 3.2},
    "中景":   {"focal": 35, "dist": 4.5},
    "全景":   {"focal": 28, "dist": 8.0},
    "远景":   {"focal": 24, "dist": 15.0},
    "大远景": {"focal": 18, "dist": 30.0},
}
DOLLY_RATIO = 0.25      # 推/拉默认行程 = 视距 x 0.25
DEFAULT_PAN = 30        # 摇默认角度(度)
DEFAULT_ORBIT = 360     # 环绕默认一整圈(度)
DEFAULT_TRACK = 3.0     # 移默认距离(m)
DEFAULT_TILT = 25        # 俯仰默认角度(度)
DEFAULT_PEDESTAL = 2.0   # 升降默认高度(m)
DEFAULT_WHIP = 120       # 甩镜默认角度(度)
DEFAULT_ZOOM_TO = 70     # 变焦默认终点焦距(mm)
DEFAULT_HANDHELD = 0.15 # 手持默认晃动幅度(m)

GRAY = (0.45, 0.45, 0.48)
SKIN = (0.82, 0.70, 0.58)
BODY = (0.25, 0.38, 0.55)
ARROW = (1.0, 0.62, 0.12)


def parse_args():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    d = {}
    i = 0
    while i < len(args):
        if args[i].startswith("--"):
            key = args[i][2:]
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                d[key] = args[i + 1]
                i += 2
            else:
                d[key] = True
                i += 1
        else:
            i += 1
    return d


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for m in list(bpy.data.materials):
        bpy.data.materials.remove(m)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)
    for c in list(bpy.data.cameras):
        bpy.data.cameras.remove(c)


def set_active_scene(scene):
    try:
        bpy.context.window.scene = scene
    except Exception:
        pass
    try:
        for w in bpy.context.window_manager.windows:
            w.scene = scene
    except Exception:
        pass


def set_world(color):
    world = bpy.data.worlds.new("PrevizWorld")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (color[0], color[1], color[2], 1.0)
    return world


def make_material(name, color, use_checker=False, checker_color=(0.26, 0.26, 0.29)):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if use_checker:
        tc = mat.node_tree.nodes.new("ShaderNodeTexChecker")
        tc.inputs["Scale"].default_value = 6.0
        tc.inputs["Color1"].default_value = (color[0], color[1], color[2], 1.0)
        tc.inputs["Color2"].default_value = (checker_color[0], checker_color[1], checker_color[2], 1.0)
        mat.node_tree.links.new(tc.outputs[0], bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
    return mat


def _assign(obj, mat):
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


def move_to_collection(obj, target_col):
    """把对象从所有集合移除，再链接到目标集合。"""
    for col in list(obj.users_collection):
        col.objects.unlink(obj)
    target_col.objects.link(obj)


def add_ground(size, color=GRAY, y=0.0):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, y))
    obj = bpy.context.object
    obj.name = "地面"
    _assign(obj, make_material("地面_mat", color, use_checker=True))
    return obj


def add_box(name, size, loc, color=GRAY):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(loc[0], loc[1], loc[2]))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = (size[0], size[1], size[2])
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    _assign(obj, make_material(name + "_mat", color))
    return obj


def add_cylinder(name, radius, height, loc, color=GRAY):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=height, location=(loc[0], loc[1], loc[2]))
    obj = bpy.context.object
    obj.name = name
    _assign(obj, make_material(name + "_mat", color))
    return obj


def add_sphere(name, radius, loc, color=GRAY):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=(loc[0], loc[1], loc[2]))
    obj = bpy.context.object
    obj.name = name
    _assign(obj, make_material(name + "_mat", color))
    return obj


def _asset_root(name):
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    return root


def _asset_box(root, name, size, loc, color):
    obj = add_box(name, size, loc, color)
    obj.parent = root
    obj.color = (*color, 1.0)
    return obj


def _asset_cylinder(root, name, radius, height, loc, color):
    obj = add_cylinder(name, radius, height, loc, color)
    obj.parent = root
    obj.color = (*color, 1.0)
    return obj


def _semantic_room_asset(p):
    """Build legible blocking assemblies for common interior assets.

    The input asset remains the named root; children form an editable low-poly
    object rather than a single anonymous cuboid.
    """
    name = str(p.get("名称", "道具"))
    low = name.lower()
    x, y, z = (list(p.get("位置", [0, 0, 0])) + [0, 0, 0])[:3]
    w, d, h = (list(p.get("尺寸", [2, 2, 2])) + [2, 2, 2])[:3]
    color = tuple(p.get("颜色", GRAY))
    orientation = str(p.get("朝向") or ("北" if "北墙" in name else "南" if "南墙" in name else "东" if "东墙" in name else "西" if "西墙" in name else ""))
    root = _asset_root(name)
    parts = [root]

    if "床头柜" in name:
        parts += [_asset_box(root, name + "_柜体", (w, d, max(h - .06, .1)), (x, y, z + max(h - .06, .1) / 2), color),
                  _asset_box(root, name + "_台面", (w + .05, d + .05, .06), (x, y, z + h - .03), (0.28, .18, .10)),
                  _asset_box(root, name + "_抽屉", (w * .82, .025, h * .28), (x, y - d / 2 - .014, z + h * .55), (0.38, .26, .14))]
    elif "床" in name:
        frame_h = max(.16, h * .36)
        mattress_h = max(.16, h * .42)
        parts += [_asset_box(root, name + "_床架", (w, d, frame_h), (x, y, z + frame_h / 2), (0.20, .16, .13)),
                  _asset_box(root, name + "_床垫", (w * .96, d * .94, mattress_h), (x, y, z + frame_h + mattress_h / 2), (0.72, .72, .70)),
                  _asset_box(root, name + "_床头", (w, .12, max(.7, h * 1.5)), (x, y + d / 2 - .06, z + max(.7, h * 1.5) / 2), (0.18, .15, .12)),
                  _asset_box(root, name + "_枕头", (w * .62, d * .22, .12), (x, y + d * .22, z + frame_h + mattress_h + .06), (0.88, .86, .78))]
    elif "窗" in name:
        frame = min(.10, w * .08)
        # “北/南墙窗” is a wall opening: its broad face runs east-west (X),
        # with a shallow Y depth.  This keeps the window vertical instead of
        # treating its supplied [w,d,h] as a horizontal furniture block.
        wall_depth = max(.06, min(.14, d))
        # East/west walls rotate the opening 90 degrees.  North/south walls
        # retain the supplied X-wide, Y-thin convention.
        north_south = orientation not in ("东", "西")
        glass_size = (w, wall_depth, h) if north_south else (wall_depth, w, h)
        top_size = (w + frame * 2, wall_depth, frame) if north_south else (wall_depth, w + frame * 2, frame)
        side_size = (frame, wall_depth, h) if north_south else (wall_depth, frame, h)
        side_offset = (w / 2 - frame / 2)
        left_loc = (x - side_offset, y, z + h / 2) if north_south else (x, y - side_offset, z + h / 2)
        right_loc = (x + side_offset, y, z + h / 2) if north_south else (x, y + side_offset, z + h / 2)
        parts += [_asset_box(root, name + "_玻璃", glass_size, (x, y, z + h / 2), (0.42, .68, .78)),
                  _asset_box(root, name + "_上框", top_size, (x, y, z + h - frame / 2), (0.92, .92, .88)),
                  _asset_box(root, name + "_下框", top_size, (x, y, z + frame / 2), (0.92, .92, .88)),
                  _asset_box(root, name + "_左框", side_size, left_loc, (0.92, .92, .88)),
                  _asset_box(root, name + "_右框", side_size, right_loc, (0.92, .92, .88))]
    elif "衣柜" in name or "柜" in name:
        parts += [_asset_box(root, name + "_柜体", (w, d, h), (x, y, z + h / 2), color),
                  _asset_box(root, name + "_左门", (w * .47, .035, h * .9), (x - w * .245, y - d / 2 - .02, z + h * .5), (0.22, .22, .24)),
                  _asset_box(root, name + "_右门", (w * .47, .035, h * .9), (x + w * .245, y - d / 2 - .02, z + h * .5), (0.25, .25, .27))]
    elif "序端" in name or "屏幕" in name or "显示器" in name:
        sw, sd, sh = max(w, .32), max(d, .12), max(h, .20)
        parts += [_asset_box(root, name + "_机身", (sw, sd, sh), (x, y, z + sh / 2), (0.08, .09, .11)),
                  _asset_box(root, name + "_屏幕", (sw * .82, .018, sh * .60), (x, y - sd / 2 - .011, z + sh * .58), (0.10, .38, .50)),
                  _asset_box(root, name + "_底座", (sw * .55, sd * 1.15, .04), (x, y, z + .02), (0.12, .12, .13))]
    else:
        return None
    return parts


def _camera_structure_asset(p):
    """只为镜头语言必要的特殊轮廓建最小结构，不把通行/遮挡对象压成实心块。"""
    name = str(p.get("名称", "道具"))
    kind = str(p.get("类型", "box"))
    x, y, z = (list(p.get("位置", [0, 0, 0])) + [0, 0, 0])[:3]
    w, d, h = (list(p.get("尺寸", [2, 2, 2])) + [2, 2, 2])[:3]
    color = tuple(p.get("颜色", GRAY))
    orientation = str(p.get("朝向") or "北")
    root = _asset_root(name)
    parts = [root]

    # 文字名称是旧数据兼容；新数据优先使用明确类型，避免对普通 box 过度建模。
    is_portal = kind == "门洞框" or ("门洞" in name and kind == "box")
    is_canopy = kind == "棚架" or ("棚架" in name and kind == "box")
    is_scooter = kind == "电驱车" or (("电驱" in name or "电动车" in name or "摩托" in name) and kind == "box")
    is_pole = kind == "立杆设备" or (("监测" in name or "监控" in name) and kind == "box")

    if is_portal:
        # 宽口沿朝向展开；深度只保留框体厚度，确保镜头可从中穿过。
        thick = max(.10, min(.24, d * .12))
        post = max(.12, min(.28, w * .09))
        ns = orientation not in ("东", "西")
        width, depth = (w, thick) if ns else (thick, w)
        side_size = (post, depth, h) if ns else (depth, post, h)
        top_size = (width + post * 2, depth, post)
        delta = width / 2 + post / 2
        left = (x - delta, y, z + h / 2) if ns else (x, y - delta, z + h / 2)
        right = (x + delta, y, z + h / 2) if ns else (x, y + delta, z + h / 2)
        parts += [_asset_box(root, name + "_左柱", side_size, left, color),
                  _asset_box(root, name + "_右柱", side_size, right, color),
                  _asset_box(root, name + "_横梁", top_size, (x, y, z + h - post / 2), color)]
    elif is_canopy:
        post = max(.08, min(.18, min(w, d) * .10))
        roof_h = max(.10, min(.18, h * .08))
        # 顶棚略向镜头/街道一侧前挑，两个前柱足以读成棚架。
        parts.append(_asset_box(root, name + "_顶棚", (w, d, roof_h), (x, y, z + h - roof_h / 2), color))
        for side in (-1, 1):
            parts.append(_asset_box(root, name + ("_左柱" if side < 0 else "_右柱"),
                                    (post, post, h - roof_h), (x + side * (w / 2 - post), y - d / 2 + post, z + (h - roof_h) / 2), color))
    elif is_scooter:
        # 车长沿 X，给侧拍/横移一个清晰轮廓；只保留两轮、低车身、座垫与把手。
        length, width = max(w, .8), max(d, .35)
        wheel_r = max(.16, min(.32, h * .24))
        wheel_w = max(.08, min(.16, width * .45))
        body_h = max(.22, h * .28)
        for side in (-1, 1):
            wheel = _asset_cylinder(root, name + ("_前轮" if side > 0 else "_后轮"), wheel_r, wheel_w,
                                    (x + side * length * .32, y, z + wheel_r), (0.06, .07, .08))
            wheel.rotation_euler[0] = math.radians(90)
        parts += [_asset_box(root, name + "_车身", (length * .66, width, body_h), (x, y, z + wheel_r + body_h / 2), color),
                  _asset_box(root, name + "_座垫", (length * .30, width * .72, .10), (x - length * .10, y, z + wheel_r + body_h + .05), (0.12, .12, .13)),
                  _asset_box(root, name + "_车把", (.08, width * .85, .08), (x + length * .28, y, z + wheel_r + body_h + .45), color)]
    elif is_pole:
        pole_h = max(h * .68, .6)
        parts += [_asset_cylinder(root, name + "_立杆", max(.035, min(w, d) * .10), pole_h,
                                      (x, y, z + pole_h / 2), color),
                  _asset_box(root, name + "_箱体", (w, d, max(h - pole_h, .25)),
                             (x, y, z + pole_h + max(h - pole_h, .25) / 2), color)]
    else:
        return None
    return parts


def add_prop(p):
    """Create an editable semantic assembly where the asset type is known.

    The asset-table row remains the named empty root, with its visible parts
    underneath it.  This restores the first detailed previs modelling style:
    beds read as a frame/mattress/headboard/pillow, windows read as glass and
    frames, cabinets have doors, and screen props have a visible screen.
    Unknown props intentionally retain the simple primitive fallback.
    `位置.z=0` still means the asset rests on the ground plane.
    """
    camera_structure = _camera_structure_asset(p)
    if camera_structure is not None:
        return camera_structure
    semantic = _semantic_room_asset(p)
    if semantic is not None:
        return semantic
    t = p.get("类型", "box")
    loc = p.get("位置", [0, 0, 0])
    color = tuple(p.get("颜色", GRAY))
    name = p.get("名称", "道具")
    if t == "box":
        size = p.get("尺寸", [2, 2, 2])
        o = add_box(name, size, (loc[0], loc[1], loc[2] + size[2] / 2), color)
    elif t == "cylinder":
        height = p.get("高度", 2.0)
        o = add_cylinder(name, p.get("半径", 0.5), height, (loc[0], loc[1], loc[2] + height / 2), color)
    elif t == "sphere":
        radius = p.get("半径", 0.5)
        o = add_sphere(name, radius, (loc[0], loc[1], loc[2] + radius), color)
    else:
        size = p.get("尺寸", [2, 2, 2])
        o = add_box(name, size, (loc[0], loc[1], loc[2] + size[2] / 2), color)
    # Workbench OBJECT 模式使用显式资产色，不能随机染色。
    o.color = (*color, 1.0)
    return [o]


def should_build_asset(p, shots):
    """Keep only props that can affect the authored shots.

    Asset tables often describe a whole room, while previs needs only what is
    named by the shots.  Structural shell geometry is background and is never
    required as a separate asset; the renderer already supplies ground/world.
    Windows and doors are retained only when the shot calls for one.
    """
    name = str(p.get("名称") or "").strip()
    if not name:
        return False
    brief = " ".join(
        " ".join(str(shot.get(k) or "") for k in ("备注", "原始提示词"))
        for shot in shots
    )
    # 明确的镜头用途是资产表的合同，优先于后续按名称猜测是否可见。
    purpose = str(p.get("镜头用途") or "").strip()
    if purpose:
        # 默认地面由渲染器统一提供，避免与显式地面 box 重叠闪烁。
        return name not in ("地面", "地板")
    # Openings are visual assets only when the shot explicitly needs them.
    if "窗" in name:
        return "窗" in brief
    if "门" in name:
        return "门" in brief
    # 未声明用途的建筑壳体默认不建，避免自动补出看不见的整间房。
    if any(word in name for word in ("墙", "地面", "天花", "楼板", "地板")):
        return False
    # Match the complete asset name first; then permit common furniture stems
    # such as “床头” for “床头柜”.
    stems = [name]
    for suffix in ("柜", "桌", "架", "台", "椅", "子"):
        if name.endswith(suffix) and len(name) > len(suffix):
            stems.append(name[:-len(suffix)])
    return any(token and token in brief for token in stems)


def _bed_surface_height():
    """Return the top of the nearest generated bed assembly, if one exists."""
    tops = []
    for obj in bpy.data.objects:
        if obj.type == "MESH" and "床垫" in obj.name:
            tops.append(max((obj.matrix_world @ v.co).z for v in obj.data.vertices))
    return max(tops) if tops else 0.0


def _bed_dimensions():
    """Return the footprint of the generated bed used as the character scale cue."""
    for obj in bpy.data.objects:
        if obj.type == "MESH" and "床垫" in obj.name:
            dims = obj.dimensions
            return float(dims.x), float(dims.y)
    return 1.5, 2.0


def _subject_pose(shot, subject):
    explicit = str((subject or {}).get("姿态") or "").lower()
    if explicit in ("lying", "sitting", "standing"):
        return explicit
    text = " ".join(str(shot.get(k) or "") for k in ("备注", "原始提示词"))
    if any(word in text for word in ("仰卧", "躺在床", "躺床", "平躺")):
        return "lying"
    if any(word in text for word in ("坐在床", "坐起", "坐着")):
        return "sitting"
    return "standing"


def add_person(name, loc, facing_deg=0, body_color=BODY, skin=SKIN, model_path=None, pose="standing"):
    """胶囊人草模。可选 model_path 导入 glb/fbx 底模替换草模。"""
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    floor_z = float(loc[2]) if len(loc) > 2 else 0.0
    if pose == "lying":
        floor_z = max(floor_z, _bed_surface_height())
    root.location = (loc[0], loc[1], floor_z)
    root.rotation_euler = (0, 0, math.radians(facing_deg))

    def parent_local(obj, parent, location, rotation=None):
        """建立严格局部层级。人物可再挂到车辆空物体而绝不产生偏移。"""
        obj.parent = parent
        obj.matrix_parent_inverse.identity()
        obj.location = location
        if rotation is not None:
            obj.rotation_euler = rotation
        return obj

    if model_path and os.path.exists(model_path):
        before = set(bpy.data.objects.keys())
        ext = os.path.splitext(model_path)[1].lower()
        if ext == ".glb" or ext == ".gltf":
            bpy.ops.import_scene.gltf(filepath=model_path)
        elif ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=model_path)
        elif ext == ".obj":
            bpy.ops.wm.obj_import(filepath=model_path)
        # 用 bpy.data.objects diff（OBJ 导入可能把对象建到其他 collection）
        imported = [o for o in bpy.data.objects if o.name not in before]
        # 确保链接到当前场景 collection（未被链接的补链）
        for o in imported:
            if o.name not in bpy.context.scene.collection.objects:
                bpy.context.scene.collection.objects.link(o)
        # 注意：Blender OBJ 导入已自动 Y-up→Z-up（对象 rotation.x ≈ pi/2 站直），勿再旋转
        for o in imported:
            o.parent = root
        return root

    # A blocking human is proportional to the bed rather than a fixed-size token.
    bed_w, bed_d = _bed_dimensions()
    human = max(0.75, min(1.15, bed_d / 2.0))
    body_radius, head_radius = .22 * human, .18 * human
    if pose == "lying":
        # Coordinate convention: +Y is north.  A default lying character's
        # head therefore points north (+Y), matching “头朝北窗”.
        bpy.ops.mesh.primitive_cylinder_add(radius=body_radius, depth=.78 * human,
                                            location=(0, 0, 0))
        body_loc = (0, -.10 * human, body_radius)
        head_loc = mathutils.Vector((0, .52 * human, head_radius))
        body_rotation = (math.pi / 2, 0, 0)
    elif pose == "sitting":
        bpy.ops.mesh.primitive_cylinder_add(radius=0.30, depth=0.78, location=(0, 0, 0))
        body_loc = (0, 0, 0.39)
        head_loc = mathutils.Vector((0, 0, .98))
        body_rotation = None
    else:
        bpy.ops.mesh.primitive_cylinder_add(radius=0.30, depth=1.15, location=(0, 0, 0))
        body_loc = (0, 0, .575)
        head_loc = mathutils.Vector((0, 0, 1.39))
        body_rotation = None
    body = bpy.context.object
    body.name = name + "_体"
    parent_local(body, root, body_loc, body_rotation)
    _assign(body, make_material(name + "_体_mat", body_color))
    body.color = (*body_color, 1.0)

    # 头部是人物 root 的局部子节点；眼睛、鼻向和箭头再作为它的局部子节点。
    # 因此人物被绑定到车辆空物体、车辆旋转时，整个面部层级始终跟随本体。
    head_pivot = bpy.data.objects.new(name + "_头部枢轴", None)
    bpy.context.scene.collection.objects.link(head_pivot)
    parent_local(head_pivot, root, head_loc)

    bpy.ops.mesh.primitive_uv_sphere_add(radius=head_radius, location=(0, 0, 0))
    head = bpy.context.object
    head.name = name + "_头"
    parent_local(head, head_pivot, (0, 0, 0))
    _assign(head, make_material(name + "_头_mat", skin))
    head.color = (*skin, 1.0)

    # 最小面部：两只深色眼睛 + 一个短鼻向。它不是角色建模，而是预演时
    # 一眼判断“人物到底朝哪边”的方向标记。默认正面为人物局部 -Y。
    front = mathutils.Vector((0, -1, 0))
    face_right = mathutils.Vector((1, 0, 0))
    eye_mat = make_material(name + "_眼_mat", (0.025, 0.025, 0.03))
    eye_center = front * (head_radius * .88) + mathutils.Vector((0, 0, head_radius * .10))
    for side, eye_label in ((-1, "左眼"), (1, "右眼")):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=max(.028, head_radius * .20), location=(0, 0, 0))
        eye = bpy.context.object
        eye.name = name + "_" + eye_label
        parent_local(eye, head_pivot, eye_center + face_right * side * head_radius * .38)
        _assign(eye, eye_mat)
        eye.color = (0.025, 0.025, 0.03, 1.0)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=max(.022, head_radius * .15),
                                          location=(0, 0, 0))
    nose = bpy.context.object
    nose.name = name + "_鼻向"
    parent_local(nose, head_pivot, front * (head_radius * 1.04))
    _assign(nose, make_material(name + "_鼻向_mat", (0.46, 0.25, 0.17)))
    nose.color = (0.46, 0.25, 0.17, 1.0)

    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=0.14, depth=0.20, location=(0, 0, 0))
    arrow = bpy.context.object
    arrow.name = name + "_朝向"
    parent_local(arrow, head_pivot, (0, 0, -head_loc.z + .10))
    _assign(arrow, make_material(name + "_朝向_mat", ARROW))
    arrow.color = (*ARROW, 1.0)
    if pose == "lying":
        # Simple limbs make the blocking read as a human rather than a token.
        for suffix, dx, y0, y1 in (("左臂", -.24 * human, .18 * human, -.24 * human),
                                   ("右臂", .24 * human, .18 * human, -.24 * human),
                                   ("左腿", -.13 * human, -.43 * human, -.86 * human),
                                   ("右腿", .13 * human, -.43 * human, -.86 * human)):
            a = mathutils.Vector((dx, y0, body_radius))
            b = mathutils.Vector((dx, y1, body_radius))
            mid = (a + b) * .5
            bpy.ops.mesh.primitive_cylinder_add(radius=body_radius * .42, depth=(b-a).length, location=(0, 0, 0))
            limb = bpy.context.object
            limb.name = name + "_" + suffix
            parent_local(limb, root, mid, (math.pi / 2, 0, 0))
            _assign(limb, make_material(limb.name + "_mat", body_color))
    return root


def look_at(obj, target):
    direction = mathutils.Vector(target) - mathutils.Vector(obj.location)
    if direction.length < 1e-6:
        return
    quat = direction.to_track_quat('-Z', 'Y')
    obj.rotation_euler = quat.to_euler()


def build_camera(name, pos, target, focal):
    cam_data = bpy.data.cameras.new(name)
    cam_data.lens = focal
    cam = bpy.data.objects.new(name, cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = mathutils.Vector(pos)
    # 预演里的“看向哪里”必须是 Blender 中可见、可手调的对象，不能只
    # 藏在一次性的欧拉角计算里。移动这个空物体即可重新构图。
    target_obj = bpy.data.objects.new(name + "_镜头目标", None)
    bpy.context.scene.collection.objects.link(target_obj)
    target_obj.empty_display_type = 'SPHERE'
    target_obj.empty_display_size = 0.32
    target_obj.location = mathutils.Vector(target)
    target_obj.name = name + "_镜头目标"
    target_obj["用途"] = "相机注视点；移动此空物体即可改变相机构图。"

    track = cam.constraints.new(type='TRACK_TO')
    track.name = "跟踪_镜头目标"
    track.target = target_obj
    track.track_axis = 'TRACK_NEGATIVE_Z'
    track.up_axis = 'UP_Y'
    return cam, target_obj


def language_motion_params(shot):
    """Merge exact camera-language defaults with explicitly authored parameters."""
    params = dict(shot.get("运镜参数", {}) or {})
    languages = set(shot_languages(shot))
    if "慢推进" in languages or "推进 / 慢推" in languages or "慢速拉出" in languages:
        params.setdefault("距离", 0.9)
    if "180度环绕" in languages or "180° 环绕" in languages:
        params.setdefault("角度", 180)
    if "吊臂上升" in languages:
        params.setdefault("高度", 4.0)
    if "吊臂下降" in languages:
        params.setdefault("高度", -4.0)
    if "穿飞镜头" in languages:
        params.setdefault("距离", 7.0)
    if "缝隙窥视推进" in languages:
        params.setdefault("距离", 2.0)
    return params


def apply_composition_language(pos, target, focal, shot):
    """Apply non-trajectory language to the computed default camera setup."""
    languages = set(shot_languages(shot))
    pos, target = mathutils.Vector(pos), mathutils.Vector(target)
    distance = max((pos - target).length, 1.0)
    if "低机位" in languages:
        pos.z = max(0.45, target.z - 1.0)
    if "高机位" in languages:
        # “高机位”是从人物上方观察，不是把相机推到房间天花板。
        # 原先最低抬升 2m，会让床侧中景退化成只看见床面的顶视图。
        note = " ".join(str(shot.get(k) or "") for k in ("备注", "原始提示词"))
        lift = max(0.75, distance * 0.22) if "略俯拍" in note else max(1.15, distance * 0.35)
        pos.z = target.z + lift
    if "鱼眼镜头" in languages:
        focal = 8
    if "第一人称行走" in languages:
        pos.z = target.z
        focal = min(focal, 28)
    return pos, target, focal


def apply_optical_language(cam, shot, n_frames=0, offset=0):
    """Apply DoF, focus and lens presets after the camera object exists."""
    languages = set(shot_languages(shot))
    if not languages:
        return
    cam["镜头语言"] = " + ".join(shot_languages(shot))
    if "背景虚化" in languages:
        cam.data.dof.use_dof = True
        cam.data.dof.aperture_fstop = 2.2
    if "浅景深" in languages:
        cam.data.dof.use_dof = True
        cam.data.dof.aperture_fstop = 1.8
    if "转移焦点" in languages and n_frames:
        cam.data.dof.use_dof = True
        cam.data.dof.focus_distance = 2.2
        cam.data.dof.keyframe_insert(data_path="focus_distance", frame=offset + 1)
        cam.data.dof.focus_distance = 10.0
        cam.data.dof.keyframe_insert(data_path="focus_distance", frame=offset + n_frames)


def add_camera_support_assets(shot, cam_pos, cam_target):
    """Build editable blocking geometry required by transition/occlusion languages."""
    plan = shot.get("镜头辅助资产")
    if not isinstance(plan, list):
        plan = support_assets_for_languages(shot_languages(shot))
    if not plan:
        return []
    # 摄像机和注视点处在眼睛高度；辅助道具必须投影到地面后再摆放。
    start = mathutils.Vector((cam_pos[0], cam_pos[1], 0))
    target = mathutils.Vector((cam_target[0], cam_target[1], 0))
    forward = target - start
    if forward.length < 1e-6:
        forward = mathutils.Vector((0, 1, 0))
    forward.normalize()
    right = forward.cross(mathutils.Vector((0, 0, 1)))
    if right.length < 1e-6:
        right = mathutils.Vector((1, 0, 0))
    right.normalize()
    mid = start.lerp(target, 0.55)
    near = start.lerp(target, 0.30)
    objects = []

    def helper(name, size, location, kind):
        obj = add_box(name, size, location, (0.18, 0.5, 0.78))
        obj["镜头辅助资产"] = kind
        obj["生成规则"] = "由镜头语言自动生成；可直接替换为正式场景道具。"
        objects.append(obj)
        return obj

    for item in plan:
        kind = str(item.get("类型") or "镜头辅助")
        if kind == "遮挡柱":
            helper("辅助_遮挡柱", (1.1, 0.8, 5.0), mid + right * 0.8 + mathutils.Vector((0, 0, 2.5)), kind)
        elif kind == "转场遮挡":
            wipe = helper("辅助_前景转场遮挡", (2.2, 0.5, 4.5), near + right * 1.8 + mathutils.Vector((0, 0, 2.25)), kind)
            wipe.location = near + right * 4.5 + mathutils.Vector((0, 0, 2.25))
            wipe.keyframe_insert(data_path="location", frame=1)
            wipe.location = near - right * 4.5 + mathutils.Vector((0, 0, 2.25))
            wipe.keyframe_insert(data_path="location", frame=18)
        elif kind == "缝隙框":
            for side, sign in (("左", -1), ("右", 1)):
                helper("辅助_缝隙" + side, (0.75, 0.5, 4.2), near + right * sign * 1.2 + mathutils.Vector((0, 0, 2.1)), kind)
        elif kind == "门框":
            gate = start.lerp(target, 0.48)
            for side, sign in (("左柱", -1), ("右柱", 1)):
                helper("辅助_门框" + side, (0.45, 0.55, 4.8), gate + right * sign * 1.6 + mathutils.Vector((0, 0, 2.4)), kind)
            helper("辅助_门框横梁", (3.7, 0.55, 0.45), gate + mathutils.Vector((0, 0, 4.7)), kind)
        elif kind == "对话站位":
            for side, sign in (("A", -1), ("B", 1)):
                marker_pos = target + right * sign * 1.4
                marker = add_cylinder("辅助_对话站位_" + side, 0.45, 0.05,
                                      (marker_pos.x, marker_pos.y, 0.025), (0.95, 0.55, 0.16))
                marker["镜头辅助资产"] = kind
                objects.append(marker)
    return objects


def keyframe(obj, frame, loc=None, rot=None):
    if loc is not None:
        obj.location = loc
        obj.keyframe_insert(data_path="location", frame=frame)
    if rot is not None:
        obj.rotation_euler = rot
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)


def _asset_focus_from_note(shot):
    """Return the bounds centre of the named scene asset mentioned by a shot.

    A prop-only shot (screen, clock, product, etc.) has no character subject,
    but it must still receive a real camera target instead of looking at the
    room origin.
    """
    note = " ".join(str(shot.get(k) or "") for k in ("备注", "原始提示词"))
    # Normal preview assets are one mesh per row.  Keep support for an empty
    # parent only so old saved .blend files remain readable.
    direct_meshes = [o for o in bpy.data.objects if o.type == 'MESH' and o.name and o.name in note]
    if direct_meshes:
        chosen = max(direct_meshes, key=lambda o: len(o.name))
        meshes = [chosen]
    else:
        roots = [o for o in bpy.data.objects if o.type == 'EMPTY' and o.name and o.name in note]
        if not roots:
            return None
        root = max(roots, key=lambda o: len(o.name))
        meshes = [o for o in root.children_recursive if o.type == 'MESH']
    if not meshes:
        return None
    points = []
    for obj in meshes:
        points.extend(obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box)
    if not points:
        return None
    low = mathutils.Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    high = mathutils.Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return (low + high) * .5


def resolve_camera(shot, subjects):
    """优先用 JSON 给的摄像机参数，否则按景别给默认。"""
    cam = shot.get("摄像机")
    if cam and "位置" in cam and "目标" in cam:
        pos = mathutils.Vector(cam["位置"])
        target = mathutils.Vector(cam["目标"])
        focal = cam.get("焦距", 35)
        return apply_composition_language(pos, target, focal, shot)

    size_name = shot.get("景别", "中景")
    size = SHOT_SIZE.get(size_name, SHOT_SIZE["中景"])
    focal = size["focal"]
    dist = size["dist"]
    if subjects:
        dist *= .72  # subject-led shots should frame the person before the room.
        # 跟拍/移动镜头优先选择有走位的角色；静止配角不能因为排在主体列
        # 前面就抢走真正行动者的相机目标。
        subj = next((s for s in subjects if "终点" in s), subjects[0])
        base = mathutils.Vector(subj["位置"])
        pose = _subject_pose(shot, subj)
        base.z = max(float(base.z), _bed_surface_height() if pose == "lying" else 0.0)
        # 目标点：特写/近景 → 脸部/头部高度（资产站直后约 1.6m）
        if pose == "lying":
            # 床上人物的可读主体是上半身/头部；床面高度加 0.22m
            # 会把注视点落在躯干底部，使镜头看起来没有对准角色。
            target_h = 0.72
        elif size_name in ("特写", "近景", "中近景"):
            target_h = 1.55 if size_name == "特写" else 1.5
        else:
            target_h = 1.0
        center = base + mathutils.Vector((0, 0, target_h))
        note = " ".join(str(shot.get(k) or "") for k in ("备注", "原始提示词"))
        if pose == "lying":
            # 默认躺姿头朝 +Y（北）。所有人物镜头都略偏向上半身；特写再
            # 进一步偏到头部。这样中景仍能保留身体，且相机不会偏离人物。
            head_bias = 0.05 if size_name not in ("特写", "近景", "中近景") else 0.48
            center.y += head_bias * max(0.75, min(1.15, _bed_dimensions()[1] / 2.0))
        # 脸部朝向：默认脸朝 -Y（资产转直后的正面），主体可写 朝向=度
        front = mathutils.Vector((0, -1, 0))
        facing = float(subj.get("朝向") or 0)
        if facing:
            m = mathutils.Matrix.Rotation(math.radians(facing), 4, 'Z')
            front = m @ front
        if size_name in ("特写", "近景", "中近景"):
            # 特写/近景：从脸部正面拍（相机在脸的对面）
            pos = center + (-front) * dist
            pos.z = target_h
        else:
            # “床侧/侧拍” is an explicit side-camera constraint, not a
            # generic frontal room shot.
            if "床侧" in note or "侧拍" in note:
                # Bedside medium: compose the whole lying body around its
                # torso, with a slight front offset; never crop at the head.
                focal = 32
                pos = center + mathutils.Vector((3.80, -0.70, 0.25))
            else:
                pos = center + mathutils.Vector((0, dist, 0.2))
    else:
        asset_target = _asset_focus_from_note(shot)
        if asset_target is not None:
            # 资产特写默认从其可见正面（-Y）拍摄，注视点就是资产本身。
            center = asset_target
            pos = center + mathutils.Vector((0, -dist, 0.06))
        else:
            # 没有角色也没有命名资产时才使用房间默认构图。
            center = mathutils.Vector((0, -6, 1.4))
            pos = center + mathutils.Vector((0, dist, 0.2))
    return apply_composition_language(pos, center, focal, shot)


def apply_move(shot, cam_pos, cam_target, subjects, move=None, seg_n=None, n_frames=None):
    """按运镜类型返回结束帧的摄像机位置/目标。"""
    # 复合镜头须逐段执行当前物理动作，不能直接用原始中文镜头词。
    move = move or shot.get("运镜", "固定")
    params = language_motion_params(shot)
    v = mathutils.Vector(cam_target) - mathutils.Vector(cam_pos)
    d = v.length
    dirn = v.normalized() if d > 1e-6 else mathutils.Vector((0, -1, 0))
    end_pos = mathutils.Vector(cam_pos)
    end_target = mathutils.Vector(cam_target)

    if move == "推":
        end_pos = end_pos + dirn * params.get("距离", d * DOLLY_RATIO)
    elif move == "拉":
        end_pos = end_pos - dirn * params.get("距离", d * DOLLY_RATIO)
    elif move == "摇":
        angle = math.radians(params.get("角度", DEFAULT_PAN))
        m = mathutils.Matrix.Rotation(angle, 4, 'Z')
        end_target = end_pos + (m @ (end_target - end_pos))
    elif move == "移":
        step = params.get("距离", DEFAULT_TRACK)
        side = 1.0 if params.get("方向", "右") == "右" else -1.0
        # 复合运镜“跟+移”时，主体沿 x 轴奔跑，“移”若也沿 x 轴会与跟拍
        # 叠加造成相机超速（总位移 > 主体位移）。此时“移”改为沿 y 轴
        # 的横向平移（镜头横向掠过），不增加跟拍方向速度。
        if "跟" in str(shot.get("运镜", "")) and side:
            end_pos = end_pos + mathutils.Vector((0, side * step, 0))
            end_target = end_target + mathutils.Vector((0, side * step, 0))
        else:
            end_pos = end_pos + mathutils.Vector((side * step, 0, 0))
            end_target = end_target + mathutils.Vector((side * step, 0, 0))
    elif move == "跟":
        movers = [s for s in subjects if "终点" in s]
        if movers:
            delta = mathutils.Vector(movers[0]["终点"]) - mathutils.Vector(movers[0]["位置"])
            delta.z = 0
            # 复合运镜分段执行时，"跟"只在自己这段帧数内走主体同比例位移，
            # 否则相机在 n//n_moves 帧里跑完主体全程 -> 相机速度远快于主体。
            if seg_n is not None and n_frames:
                ratio = seg_n / max(float(n_frames), 1e-6)
                delta = delta * ratio
            end_pos = end_pos + delta
            end_target = end_target + delta
    elif move == "环绕":
        angle = math.radians(params.get("角度", DEFAULT_ORBIT))
        m = mathutils.Matrix.Rotation(angle, 4, 'Z')
        end_pos = end_target + (m @ (end_pos - end_target))
    elif move in ("俯仰", "俯拍", "仰拍"):
        angle = math.radians(params.get("角度", DEFAULT_TILT))
        up = 1.0 if ("仰" in move) else -1.0
        end_target = end_target + mathutils.Vector((0, 0, up * math.tan(angle) * max(d, 1.0)))
    elif move == "升降":
        height = params.get("高度", DEFAULT_PEDESTAL)
        end_pos = end_pos + mathutils.Vector((0, 0, height))
    elif move == "甩镜":
        angle = math.radians(params.get("角度", DEFAULT_WHIP))
        m = mathutils.Matrix.Rotation(angle, 4, 'Z')
        end_target = end_pos + (m @ (end_target - end_pos))
    return end_pos, end_target


def _ease(t):
    """smoothstep 缓动：缓入缓出，让运镜更自然"""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _beat_progress(seconds, beat):
    start, end = float(beat.get("开始秒", 0)), float(beat.get("结束秒", 0))
    if end <= start:
        return 0.0
    raw = max(0.0, min(1.0, (seconds - start) / (end - start)))
    name = str(beat.get("动作") or "")
    if "加速" in name:
        return raw * raw
    if "减速" in name:
        return 1.0 - (1.0 - raw) * (1.0 - raw)
    return _ease(raw)


def _composition_layout(text):
    """Return normalized subject position and camera distance for a film framing cue."""
    text = str(text or "")
    x = 0.0
    if "左侧留白" in text or "左侧负空间" in text:
        x = 1.0 / 6.0
    elif "右侧留白" in text or "右侧负空间" in text:
        x = -1.0 / 6.0
    elif "左三分" in text:
        x = -1.0 / 6.0
    elif "右三分" in text:
        x = 1.0 / 6.0
    y = -0.055 if "头顶留白" in text or "顶部留白" in text else (0.12 if "上三分" in text else 0.0)
    distance = 1.0
    if any(word in text for word in ("大全景", "远景", "环境建立", "全景建立")):
        distance = 1.38
    elif "全景" in text:
        distance = 1.22
    elif "特写" in text:
        distance = 0.62
    elif "中近景" in text:
        distance = 0.90
    elif "近景" in text:
        distance = 0.78
    return x, y, distance


def _apply_start_end_composition(p, tgt, focus, focal, composition, progress, cam):
    """Re-aim and scale the camera so the subject moves between designed frame layouts."""
    if not isinstance(composition, dict) or focus is None:
        return p, tgt
    start = _composition_layout(composition.get("起幅", ""))
    end = _composition_layout(composition.get("落幅", ""))
    blend = _ease(max(0.0, min(1.0, progress)))
    x = start[0] + (end[0] - start[0]) * blend
    y = start[1] + (end[1] - start[1]) * blend
    distance_scale = start[2] + (end[2] - start[2]) * blend
    focus = mathutils.Vector(focus)
    p = focus + (p - focus) * distance_scale
    view = tgt - p
    distance = max(view.length, 0.1)
    if view.length < 1e-6:
        view = mathutils.Vector((0, 1, 0))
    view.normalize()
    right = view.cross(mathutils.Vector((0, 0, 1)))
    if right.length < 1e-6:
        right = mathutils.Vector((1, 0, 0))
    right.normalize()
    up = right.cross(view).normalized()
    width = distance * float(cam.data.sensor_width) / max(float(focal), 1.0)
    height = width * float(bpy.context.scene.render.resolution_y) / max(float(bpy.context.scene.render.resolution_x), 1)
    tgt = focus - right * (x * width) - up * (y * height)
    return p, tgt


def subject_motion_progress(shot, seconds):
    """人物走位与跟拍节拍共用同一条时间曲线。"""
    note = str(shot.get("备注") or "")
    action = shot.get("载具动作") or {}
    # “冲出/全力奔跑 → 车辆急停”是事件链，不应把人物匀速拖到镜头末尾。
    # 若存在车辆事件，跑者在车辆动作开始前抵达落点，留出事件发生和反应
    # 的画面时间；普通走位仍按镜头节拍原样运行。
    if action and any(word in note for word in ("奔跑", "冲出", "全力", "疾跑", "飞奔")):
        try:
            arrival = max(.35, float(action.get("开始秒", 0)))
            return _ease(max(0.0, min(1.0, seconds / arrival)))
        except Exception:
            pass
    beats = shot.get("镜头节拍") or []
    follow = next((b for b in beats if "跟拍" in str(b.get("动作") or "") or str(b.get("动作") or "") == "跟"), None)
    if follow:
        return _beat_progress(seconds, follow)
    duration = max(float(shot.get("时长秒") or 0), 1e-3)
    return _ease(seconds / duration)


def vehicle_action_path(shot):
    """返回可读的高速车辆路径；短坐标会自动扩展为镜头外入场。"""
    action = shot.get("载具动作") or {}
    try:
        start = mathutils.Vector(action["起点"])
        end = mathutils.Vector(action["终点"])
        t0, t1 = float(action["开始秒"]), float(action["结束秒"])
    except Exception:
        return None
    note = str(shot.get("备注") or "")
    is_fast = any(word in (note + str(action.get("动作") or "")) for word in ("甩尾", "漂移", "急停", "冲入", "飞驰", "疾驰", "高速"))
    delta = end - start
    delta.z = 0.0
    distance = delta.length
    if is_fast:
        # 预演单位按米理解：高速车辆至少以 5m/s 横穿镜头纵深。
        # 原表中仅 0.9m 的“甩尾急停”会像挪车，甚至在镜头开始时仍露在
        # 画面边缘；因此沿原进场方向把起点延展到画外，再冲入终点。
        minimum = max(5.5, max(t1 - t0, .5) * 5.0)
        if distance < minimum:
            if distance > 1e-5:
                direction = delta.normalized()
            else:
                yaw = {"东": 0.0, "北": math.pi / 2, "西": math.pi, "南": -math.pi / 2}.get(str(action.get("起始朝向") or "东"), 0.0)
                direction = mathutils.Vector((math.cos(yaw), math.sin(yaw), 0))
            start = end - direction * minimum
    return start, end, t0, t1


def subject_motion_points(shot, subject):
    """返回人物安全走位终点；在车辆旁停步时给车体留出真实碰撞间隙。"""
    p0 = mathutils.Vector(subject.get("位置", [0, 0, 0]))
    p1 = mathutils.Vector(subject.get("终点", subject.get("位置", [0, 0, 0])))
    path = vehicle_action_path(shot)
    if "终点" not in subject or not path:
        return p0, p1
    _, vehicle_end, _, _ = path
    action = shot.get("载具动作") or {}
    yaw_map = {"东": 0.0, "北": math.pi / 2, "西": math.pi, "南": -math.pi / 2}
    yaw = yaw_map.get(str(action.get("结束朝向") or "东"), 0.0)
    side = mathutils.Vector((-math.sin(yaw), math.cos(yaw), 0))
    offset = p1 - vehicle_end
    lateral = offset.dot(side)
    # 车宽 0.7m + 人体半径约 0.3m + 0.15m 可读安全缝。
    safe_lateral = .82
    if abs(lateral) < safe_lateral:
        sign = -1.0 if lateral < 0 else 1.0
        p1 = vehicle_end + side * sign * safe_lateral
        p1.z = float(subject.get("终点", [0, 0, 0])[2] if len(subject.get("终点", [])) > 2 else 0.0)
    return p0, p1


def _movement_yaw(start, end, fallback=0.0):
    """把人物正面（默认 -Y）对齐到实际的 XY 位移方向。"""
    delta = mathutils.Vector(end) - mathutils.Vector(start)
    delta.z = 0.0
    if delta.length < 1e-5:
        return math.radians(float(fallback or 0.0))
    # 人物的正面向量为 (sin(yaw), -cos(yaw))，反解得到其 Z 轴 yaw。
    return math.atan2(delta.x, -delta.y)


def _normalize_angle(angle):
    """把角度归一到 [-pi, pi]，供头部选择最短的回头路径。"""
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def apply_vehicle_action(shot, asset_roots, roots, n_frames, offset):
    """执行显式的车辆急停/甩尾预演，并让坐在车上的角色随车移动。

    车辆资产表的位置是最终停住的位置；动作数据给出车辆的起点、终点、
    朝向和秒数。预演只做可读的位移与偏航，不假装模拟真实轮胎物理。
    """
    action = shot.get("载具动作") or {}
    name = str(action.get("名称") or "").strip()
    root = (asset_roots or {}).get(name)
    if not root:
        return
    path = vehicle_action_path(shot)
    if not path:
        return
    start, end, t0, t1 = path
    if t1 <= t0:
        return
    # 车体默认长轴朝东（+X）；旋转只用 Z 轴偏航。
    facing = {"东": 0.0, "北": 90.0, "西": 180.0, "南": -90.0}
    yaw0 = math.radians(facing.get(str(action.get("起始朝向") or "东"), 0.0))
    yaw1 = math.radians(facing.get(str(action.get("结束朝向") or "东"), 0.0))
    duration = max(float(shot.get("时长秒") or 0), 1e-3)
    # 特殊资产的根节点默认在世界原点，不能直接旋转它，否则整辆车会
    # 围绕世界原点打转。先创建一个位于“最终停车点”的局部枢轴，保留
    # 现有世界变换后把车根节点挂上去；之后只动画枢轴。
    pivot_name = name + "_动作枢轴"
    pivot = bpy.data.objects.get(pivot_name)
    if pivot is None:
        pivot = bpy.data.objects.new(pivot_name, None)
        bpy.context.scene.collection.objects.link(pivot)
        pivot.location = end
        # 特殊资产的可见零件此前以“世界坐标”建在空 root 下。若只把
        # root 保持世界变换后挂到旋转枢轴，甩尾时零件会带着那段世界
        # 偏移绕 pivot 打转，而角色却在正确的座垫锚点，视觉上就成了
        # “人悬在车外”。先把零件改成相对车辆终点的局部坐标；从此
        # 车体、座垫、车轮和乘员全部共用同一个移动/旋转参考系。
        for child in list(root.children):
            child.location -= end
        root.parent = pivot
        root.matrix_parent_inverse.identity()
        root.location = (0.0, 0.0, 0.0)
        root.rotation_euler = (0.0, 0.0, 0.0)
    vehicle_size = tuple(root.get("预演_尺寸", (1.9, .7, 1.1)))
    vehicle_length = max(float(vehicle_size[0]), .8)
    vehicle_height = max(float(vehicle_size[2]), .6)
    wheel_radius = max(.16, min(.32, vehicle_height * .24))
    body_height = max(.22, vehicle_height * .28)
    # 电驱车构造中的座垫位于后半车身，人物 root 是坐姿臀部锚点：
    # 让它自动落在座垫上方，而不是落在车辆的地面中心。
    seat_anchor = mathutils.Vector((-vehicle_length * .10, 0.0, wheel_radius + body_height + .11))
    # 载具绑定是人物和车辆的父子关系，不是“刚好坐在同一坐标”。
    # 显式绑定优先；旧镜头表仅写“跨坐车上”时，保留距离兜底兼容。
    passengers = []
    for i, subject in enumerate(shot.get("主体", [])):
        if i >= len(roots) or "终点" in subject or _subject_pose(shot, subject) != "sitting":
            continue
        pos = mathutils.Vector(subject.get("位置", [999, 999, 999]))
        binding = str(subject.get("载具绑定") or "").strip()
        inferred_on_vehicle = any(word in str(shot.get("备注") or "") for word in ("跨坐车上", "坐在车上", "骑在车上"))
        if binding and binding != name:
            continue
        if binding == name or (not binding and inferred_on_vehicle and (pos - end).length <= 1.35):
            passenger = roots[i]
            if passenger and passenger.parent != pivot:
                passenger.parent = pivot
                passenger.matrix_parent_inverse.identity()
                passenger.location = seat_anchor
                # 车头默认沿车辆局部 +X；胶囊人默认正面为局部 -Y，
                # 因此角色本地转 90° 后才能真正“骑在车上面向车头”。
                passenger.rotation_euler = (0.0, 0.0, math.radians(90.0))
            passengers.append((passenger, subject))

    # “回头”不是整个人瞬间掉头：身体始终随车头，只有头部在动作后段
    # 转向最近的另一位角色。没有可旋转头部的外部人物模型则安全跳过。
    look_back = "回头" in str(shot.get("备注") or "")
    head_turn = {}
    if look_back:
        others = [(roots[i], s) for i, s in enumerate(shot.get("主体", []))
                  if i < len(roots) and roots[i] and _subject_pose(shot, s) != "sitting"]
        for passenger, _ in passengers:
            if not passenger or not others:
                continue
            head = bpy.data.objects.get(passenger.name + "_头部枢轴")
            if not head:
                continue
            target_root, target_subject = min(
                others,
                key=lambda item: (mathutils.Vector(item[1].get("终点", item[1].get("位置", [0, 0, 0]))) - end).length,
            )
            target_pos = mathutils.Vector(target_subject.get("终点", target_subject.get("位置", [0, 0, 0])))
            seat_end = end + mathutils.Matrix.Rotation(yaw1, 4, 'Z') @ seat_anchor
            desired_yaw = _movement_yaw(seat_end, target_pos)
            rider_world_yaw = yaw1 + math.radians(90.0)
            head_turn[head.name] = _normalize_angle(desired_yaw - rider_world_yaw)

    # “高速驶入/甩尾急停”不是让车辆早早停在画面边缘等演员跑过来。
    # 跟拍镜头的广角视野可能仍看见延展后的远处起点，因此在动作开始
    # 前临时隐藏车体及骑手；起始帧解除隐藏后，车辆按路径从画外冲入。
    fast_entry = any(word in (str(shot.get("备注") or "") + str(action.get("动作") or ""))
                     for word in ("甩尾", "漂移", "急停", "冲入", "飞驰", "疾驰", "高速"))
    render_objects = []
    if fast_entry:
        def _collect_render_objects(obj):
            if obj:
                render_objects.append(obj)
                for child in obj.children:
                    _collect_render_objects(child)
        _collect_render_objects(root)
        for passenger, _ in passengers:
            _collect_render_objects(passenger)

    for k in range(1, n_frames + 1):
        sec = (k - 1) * duration / max(n_frames - 1, 1)
        raw = max(0.0, min(1.0, (sec - t0) / (t1 - t0)))
        # 急停：前段位移更快、末段明显减速；甩尾转向集中在后半段。
        travel = 1.0 - (1.0 - raw) ** 3
        spin = _ease(max(0.0, min(1.0, (raw - .35) / .65)))
        current = start.lerp(end, travel)
        pivot.location = current
        pivot.rotation_euler = (0, 0, yaw0 + (yaw1 - yaw0) * spin)
        pivot.keyframe_insert(data_path="location", frame=offset + k)
        pivot.keyframe_insert(data_path="rotation_euler", frame=offset + k)
        if render_objects:
            visible = sec >= t0
            for obj in render_objects:
                obj.hide_render = not visible
                obj.keyframe_insert(data_path="hide_render", frame=offset + k)
        if head_turn:
            # 仅在甩尾的后 35% 回头；此前始终正对车头。
            turn_raw = max(0.0, min(1.0, (raw - .65) / .35))
            for head_name, angle in head_turn.items():
                head = bpy.data.objects.get(head_name)
                if head:
                    head.rotation_euler = (0.0, 0.0, angle * _ease(turn_raw))
                    head.keyframe_insert(data_path="rotation_euler", frame=offset + k)
        # 乘员已父级绑定到动作枢轴：位移与甩尾旋转自动完全同步。


def apply_foreground_composition(shot, cam, target_obj, asset_roots, asset_specs, n_frames, offset):
    """把“前景/前景掠过”从备注落实为相机相对的空间约束。

    资产表坐标仍是叙事世界坐标；只有明确标为前景的资产会在本镜被
    调整到相机—主体之间的近景带。它保持世界静止，横移镜头经过时
    自然产生掠过视差，绝不把建筑本身横着滑过街道。
    """
    note = str(shot.get("备注") or "")
    shot_id = str(shot.get("镜号") or "")
    # 前景要在“横移进行到中段”时掠过画面，而不是刚开始横移便贴在镜头前。
    # 因此以横移节拍中点预测相机位，静态棚架会在该时刻进入画面边缘，随后被相机掠过。
    side_beat = None
    for beat in shot.get("镜头节拍") or []:
        if "横移" in str(beat.get("动作") or ""):
            side_beat = beat
            break
    if side_beat:
        side_start = (float(side_beat.get("开始秒") or 0) + float(side_beat.get("结束秒") or 0)) / 2.0
    else:
        side_start = 0.0
    # 相机已经完成关键帧：在横移中点直接读取它和目标空物体的实际世界位置。
    # 不再手算叠加后的方向，避免“相机横移、目标锁主体”使前景落到镜头侧后。
    duration = max(float(shot.get("时长秒") or 0), 1e-3)
    event_frame = offset + 1 + int(round(side_start / duration * max(n_frames - 1, 0)))
    scene = bpy.context.scene
    previous_frame = scene.frame_current
    scene.frame_set(event_frame)
    bpy.context.view_layer.update()
    event_pos = cam.matrix_world.translation.copy()
    event_target = target_obj.matrix_world.translation.copy() if target_obj else event_pos + mathutils.Vector((0, 1, 0))
    scene.frame_set(previous_frame)
    view = event_target - event_pos
    view.z = 0
    if view.length < 1e-5:
        return
    view.normalize()
    right = view.cross(mathutils.Vector((0, 0, 1)))
    if right.length < 1e-5:
        return
    right.normalize()
    forward = view
    distance = (event_target - event_pos).length
    placed = []
    for asset in asset_specs or []:
        name = str(asset.get("名称") or "")
        purpose = str(asset.get("镜头用途") or "")
        # “前景”必须是该资产自身的用途合同。不能因为镜头备注提到某个
        # 资产、同时提到“前景”，就把门洞、车辆等全部误搬到相机前。
        declared_foreground = "前景" in purpose
        if not name or not declared_foreground or (shot_id and shot_id not in purpose):
            continue
        root = (asset_roots or {}).get(name)
        if not root:
            continue
        authored = mathutils.Vector(asset.get("位置") or [0, 0, 0])
        authored_side = (authored - event_target).dot(right)
        side = 1.0 if authored_side >= 0 else -1.0
        size = asset.get("尺寸") or [1.0, 1.0, 1.0]
        # 前景资产的“中心”不能被推得太偏，否则整个棚架都落到画外。
        # 大体积资产本身已有宽度，保留小幅侧偏即可在画面边缘形成掠过。
        # 棚架这类大体积前景不能贴在近裁面，也不能大幅偏到侧外；
        # 放在相机—主体视线的中段，再以小侧偏掠过，既可见又不会遮死主角。
        side_gap = max(.12, min(.28, float(size[0]) * .10))
        near = max(1.0, min(2.2, distance * .60))
        desired = event_pos + forward * near + right * side * side_gap
        desired.z = authored.z
        root.location = desired - authored
        root["构图角色"] = "前景掠过"
        root["构图镜号"] = shot_id
        root.keyframe_insert(data_path="location", frame=offset + 1)
        root.keyframe_insert(data_path="location", frame=offset + n_frames)
        placed.append(name)
        print("[previz] 前景构图定位 %s -> %s" % (name, tuple(round(v, 2) for v in desired)))
    # 这不是给用户看的提示词字段，而是验镜合同：凡是声称“前景掠过”的
    # 资产，都必须在首/中/尾至少一个采样帧有实际可见的屏幕投影。
    shot["_前景资产"] = placed
    return placed


def relationship_focus_for_event(shot, seconds, lead_focus):
    """把“行动者 → 终点人物关系”的叙事意图落到镜头目标空物体。

    普通跟拍只需锁住行动者；但“车辆甩尾 + 骑手回头/对视/回应”是一个
    关系事件。若仍全程盯行动者，车和反应角色只会被挤到画外。本函数在
    事件开始后平滑把焦点过渡到两人的关系中心，并返回相机应让出的少量
    横向位移。它只读取已有镜头表，不要求提示词增加额外坐标字段。
    """
    action = shot.get("载具动作") or {}
    note = str(shot.get("备注") or "")
    if not action or not any(word in note for word in ("回头", "对视", "回应", "看向")):
        return None
    path = vehicle_action_path(shot)
    if not path:
        return None
    start, end, t0, t1 = path
    seated = [s for s in shot.get("主体", []) if _subject_pose(shot, s) == "sitting" and "终点" not in s]
    if not seated or t1 <= t0:
        return None
    # 与车辆动画同一条“急停”曲线，车在前段快速接近终点、后段收束。
    raw = max(0.0, min(1.0, (seconds - t0) / (t1 - t0)))
    travel = 1.0 - (1.0 - raw) ** 3
    vehicle = start.lerp(end, travel)
    rider_focus = vehicle + mathutils.Vector((0.0, 0.0, 1.35))
    # 镜头从动作发生时开始转关系；首半段仍优先林野，末段稳定在两人之间。
    blend = _ease(raw)
    relation = lead_focus.lerp((lead_focus * .48 + rider_focus * .52), blend)
    # 只让相机向关系中心让出一部分，不硬切机位，维持一镜到底的动势。
    shift = (relation - lead_focus) * .38
    shift.z = 0.0
    return relation, shift


def apply_camera_beats(cam, cam_pos, cam_target, n_frames, offset, shot, target_obj):
    """按显式秒数执行复合运镜，避免把 12 秒长镜头生硬均分成几段。"""
    beats = shot.get("镜头节拍") or []
    if not beats or not target_obj:
        return False
    duration = max(float(shot.get("时长秒") or 0), 1e-3)
    movers = [s for s in shot.get("主体", []) if "终点" in s]
    p0, target0 = mathutils.Vector(cam_pos), mathutils.Vector(cam_target)
    follow_delta = mathutils.Vector((0, 0, 0))
    if movers:
        mover_start, mover_end = subject_motion_points(shot, movers[0])
        follow_delta = mover_end - mover_start
        follow_delta.z = 0
    follow_beat = next((b for b in beats if "跟拍" in str(b.get("动作") or "") or str(b.get("动作") or "") == "跟"), None)
    has_follow = follow_beat is not None
    focal0 = float(cam.data.lens)
    focal_end = float(language_motion_params(shot).get("焦距", DEFAULT_ZOOM_TO))
    for k in range(1, n_frames + 1):
        sec = (k - 1) * duration / max(n_frames - 1, 1)
        p, tgt = p0.copy(), target0.copy()
        if has_follow:
            # 与人物 root 的位置动画使用同一函数，确保开始、结束和缓动一致。
            tt = subject_motion_progress(shot, sec)
            p += follow_delta * tt
            tgt += follow_delta * tt
        # 车辆到场的反应镜头不是“继续盯着跑者”。在动作后段将目标空物体
        # 交给二人关系中心，让车、骑手回头和林野停步同时构成画面信息。
        relation = relationship_focus_for_event(shot, sec, tgt)
        if relation:
            tgt, relation_shift = relation
            p += relation_shift
        view = tgt - p
        view.z = 0
        if view.length < 1e-6:
            view = mathutils.Vector((0, 1, 0))
        view.normalize()
        right = view.cross(mathutils.Vector((0, 0, 1)))
        if right.length < 1e-6:
            right = mathutils.Vector((1, 0, 0))
        right.normalize()
        lens = focal0
        for beat in beats:
            name = str(beat.get("动作") or "")
            t = _beat_progress(sec, beat)
            if "横移" in name:
                shift = float(language_motion_params(shot).get("距离", DEFAULT_TRACK)) * t
                p += right * shift
                # 跟拍时目标必须继续锁在行动者；横移只改变相机相对主体的
                # 观察位置以产生视差，不能把目标空物体一并推离人物。
                if not has_follow:
                    tgt += right * shift
            elif "下压" in name or "下降" in name:
                p.z = max(.35, p.z - max(.45, (p0 - target0).length * .18) * t)
                tgt.z -= .15 * t
            elif "上升" in name:
                p.z += max(.45, (p0 - target0).length * .18) * t
            elif "慢推" in name or name == "推进":
                p += (tgt - p).normalized() * max(.5, (tgt - p).length * DOLLY_RATIO) * t
            elif "环绕" in name:
                # 按节拍做围绕目标的真实圆弧运动，令预设环绕不需要手动插相机帧。
                orbit_angle = math.radians(float(language_motion_params(shot).get("角度", DEFAULT_ORBIT))) * t
                orbit_offset = p - tgt
                p = tgt + (mathutils.Matrix.Rotation(orbit_angle, 4, 'Z') @ orbit_offset)
            elif "冲击变焦" in name:
                # 冲击在节拍后段发生，前半保持构图，后半快速进入焦距变化。
                impact = max(0.0, min(1.0, (t - .62) / .38))
                lens = focal0 + (focal_end - focal0) * _ease(impact)
            elif "变焦" in name:
                lens = focal0 + (focal_end - focal0) * t
        composition = shot.get("构图起落幅")
        if composition and shot.get("主体"):
            subject = shot["主体"][0]
            subject_start, subject_end = subject_motion_points(shot, subject)
            subject_progress = subject_motion_progress(shot, sec) if "终点" in subject else 0.0
            focus = subject_start.lerp(subject_end, subject_progress)
            focus.z += target0.z - float(subject_start.z)
            p, tgt = _apply_start_end_composition(
                p, tgt, focus, lens, composition, sec / duration, cam
            )
        cam.location = p
        target_obj.location = tgt
        cam.keyframe_insert(data_path="location", frame=offset + k)
        target_obj.keyframe_insert(data_path="location", frame=offset + k)
        cam.data.lens = lens
        cam.data.keyframe_insert(data_path="lens", frame=offset + k)
    return True


def apply_camera_animation(cam, cam_pos, cam_target, n_frames, offset, shot, target_obj=None):
    """专业运镜主函数：推/拉/摇/俯仰/移/升降/环绕/跟/手持/变焦/甩镜。
    支持复合运镜（如 "环绕+拉"）分段执行，线性类运镜带缓动曲线。"""
    if apply_camera_beats(cam, cam_pos, cam_target, n_frames, offset, shot, target_obj):
        return
    params = language_motion_params(shot)
    moves = effective_moves(shot)
    # 跟拍是“全程跟随主体”的行为：跟拍段必须覆盖全程帧数，否则相机在
    # 自己那一段里跑完主体全程位移 -> 相机速度远快于主体。
    # 其他运镜（横移/推拉等）作为附加运动叠加在跟拍之上，不瓜分帧数。
    follow_whole = "跟" in moves and len(moves) > 1
    if follow_whole:
        moves = [m for m in moves if m != "跟"]
        n = len(moves) + 1  # 跟段 + 附加段
    else:
        n = len(moves)
    base_seg = n_frames // n
    rem = n_frames % n
    cur_pos = mathutils.Vector(cam_pos)
    cur_target = mathutils.Vector(cam_target)
    follow_base_pos = cur_pos
    follow_base_target = cur_target
    follow_delta = mathutils.Vector((0, 0, 0))
    if target_obj:
        target_obj.location = cur_target
        target_obj.keyframe_insert(data_path="location", frame=offset + 1)
    f = 1
    if follow_whole:
        # 跟段：全程 0..n_frames，delta = 主体全程位移（不缩放）
        movers = [s for s in shot.get("主体", []) if "终点" in s]
        if movers:
            delta = mathutils.Vector(movers[0]["终点"]) - mathutils.Vector(movers[0]["位置"])
            delta.z = 0
            for k in range(1, n_frames + 1):
                tt = _ease((k - 1) / max(n_frames - 1, 1))
                p = cur_pos + delta * tt
                tgt = cur_target + delta * tt
                cam.location = p
                cam.keyframe_insert(data_path="location", frame=offset + f)
                if target_obj:
                    target_obj.location = tgt
                    target_obj.keyframe_insert(data_path="location", frame=offset + f)
                else:
                    look_at(cam, tgt)
                    cam.keyframe_insert(data_path="rotation_euler", frame=offset + f)
                f += 1
            # 附加段叠加基准 = 跟段起点（不是跟段终点），
            # 且附加段全程叠加，保证不破坏跟段的跟随位移
            follow_base_pos = cur_pos
            follow_base_target = cur_target
            follow_delta = delta
            cur_pos = cur_pos + delta
            cur_target = cur_target + delta
    for seg_i, m in enumerate(moves):
        seg_n = base_seg + (1 if seg_i < rem else 0)
        if seg_n <= 0:
            continue
        # follow_whole 时，跟段已插完全程帧；附加段全程叠加在跟段之上，
        # 且以跟段起点（follow_base）为基准，保证不破坏跟段的跟随位移。
        seg_start = 1 if follow_whole else f
        if follow_whole:
            seg_n = n_frames  # 附加段覆盖全程
            # 临时用跟段起点作为附加段的插值基准
            base_pos = cur_pos
            base_target = cur_target
            cur_pos = follow_base_pos
            cur_target = follow_base_target
        if m == "手持":
            amp = params.get("晃动", DEFAULT_HANDHELD)
            random.seed(hash(shot.get("镜号", "S")) & 0xffffffff)
            base = cur_pos
            for k in range(1, seg_n + 1):
                p = base + mathutils.Vector((
                    random.uniform(-1, 1) * amp,
                    random.uniform(-1, 1) * amp * 0.6,
                    random.uniform(-1, 1) * amp * 0.3))
                cam.location = p
                cam.keyframe_insert(data_path="location", frame=offset + seg_start + k - 1)
                if target_obj:
                    target_obj.location = cur_target
                    target_obj.keyframe_insert(data_path="location", frame=offset + seg_start + k - 1)
                else:
                    look_at(cam, cur_target)
                    cam.keyframe_insert(data_path="rotation_euler", frame=offset + seg_start + k - 1)
                f = max(f, seg_start + k)
            continue
        if m == "环绕":
            angle_total = math.radians(float(params.get("角度", DEFAULT_ORBIT)))
            center = cur_target
            start_offset = cur_pos - center
            if start_offset.length < 1e-6:
                start_offset = mathutils.Vector((0, 1, 0))
            for k in range(1, seg_n + 1):
                tt = (k - 1) / max(seg_n - 1, 1)
                rot = mathutils.Matrix.Rotation(angle_total * tt, 4, 'Z')
                p = center + (rot @ start_offset)
                cam.location = p
                cam.keyframe_insert(data_path="location", frame=offset + seg_start + k - 1)
                if target_obj:
                    target_obj.location = center
                    target_obj.keyframe_insert(data_path="location", frame=offset + seg_start + k - 1)
                else:
                    look_at(cam, center)
                    cam.keyframe_insert(data_path="rotation_euler", frame=offset + seg_start + k - 1)
                f = max(f, seg_start + k)
            continue
        # 线性类运镜：段终点 + 逐帧缓动插值
        end_pos, end_target = apply_move(
            shot, list(cur_pos), list(cur_target), shot.get("主体", []), move=m,
            seg_n=seg_n, n_frames=n_frames)
        for k in range(1, seg_n + 1):
            tt = _ease((k - 1) / max(seg_n - 1, 1))
            if follow_whole and m == "移" and "移" in shot.get("运镜", ""):
                # follow_whole + 跟+移：跟段已插全程 x 跟随（同速）。
                # "移"是垂直跟拍方向的 y 横移，x 必须保留跟段插值
                # （否则 y 横移每帧覆盖 cam.location，跟段 x 被逐渐抹成终点值）。
                # x 按跟段公式重算：follow_base.x + follow_delta.x * _ease(全程比例)
                tt_global = (k - 1) / max(n_frames - 1, 1)
                fx = follow_base_pos.x + follow_delta.x * _ease(tt_global)
                fy = cur_pos.y + (end_pos.y - cur_pos.y) * tt
                p = mathutils.Vector((fx, fy, cam.location.z))
                cam.location = p
                cam.keyframe_insert(data_path="location", frame=offset + seg_start + k - 1)
                if target_obj:
                    tx = follow_base_target.x + follow_delta.x * _ease(tt_global)
                    ty = cur_target.y + (end_target.y - cur_target.y) * tt
                    target_obj.location = mathutils.Vector((tx, ty, target_obj.location.z))
                    target_obj.keyframe_insert(data_path="location", frame=offset + seg_start + k - 1)
                f = max(f, seg_start + k)
                continue
            p = cur_pos.lerp(end_pos, tt)
            tgt = cur_target.lerp(end_target, tt)
            cam.location = p
            cam.keyframe_insert(data_path="location", frame=offset + seg_start + k - 1)
            if target_obj:
                target_obj.location = tgt
                target_obj.keyframe_insert(data_path="location", frame=offset + seg_start + k - 1)
            else:
                look_at(cam, tgt)
                cam.keyframe_insert(data_path="rotation_euler", frame=offset + seg_start + k - 1)
            f = max(f, seg_start + k)
        cur_pos, cur_target = end_pos, end_target
    # 变焦：焦距关键帧（35 → 默认70mm，可写 焦距=数字）
    if "变焦" in moves:
        try:
            start_focal = float(shot.get("摄像机", {}).get("焦距", 35))
        except Exception:
            start_focal = 35.0
        end_focal = float(params.get("焦距", DEFAULT_ZOOM_TO))
        impact = "冲击变焦" in shot_languages(shot)
        for k in range(1, n_frames + 1):
            raw_t = (k - 1) / max(n_frames - 1, 1)
            tt = _ease(raw_t)
            if impact:
                tt = 0.0 if raw_t < 0.68 else _ease(min(1.0, (raw_t - 0.68) / 0.16))
            cam.data.lens = start_focal + (end_focal - start_focal) * tt
            cam.data.keyframe_insert(data_path="lens", frame=offset + k)


def apply_orbit_frames(cam, cam_pos, cam_target, n_frames, offset=0, params=None):
    """环绕运镜：镜头绕目标逐帧做圆弧运动（真正的转圈，不是直线插值）。"""
    params = params or {}
    angle_total = math.radians(float(params.get("角度", DEFAULT_ORBIT)))
    start_offset = mathutils.Vector(cam_pos) - mathutils.Vector(cam_target)
    if start_offset.length < 1e-6:
        start_offset = mathutils.Vector((0, 1, 0))
    center = mathutils.Vector(cam_target)
    for f in range(1, n_frames + 1):
        t = (f - 1) / max(n_frames - 1, 1)
        m = mathutils.Matrix.Rotation(angle_total * t, 4, 'Z')
        p = center + (m @ start_offset)
        cam.location = p
        cam.keyframe_insert(data_path="location", frame=offset + f)
        look_at(cam, center)
        cam.keyframe_insert(data_path="rotation_euler", frame=offset + f)


def setup_render(scene, w, h, fps):
    scene.render.fps = fps
    scene.render.resolution_x = w
    scene.render.resolution_y = h
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.film_transparent = False
    try:
        scene.render.engine = 'BLENDER_WORKBENCH'
    except Exception:
        try:
            scene.render.engine = 'BLENDER_EEVEE_NEXT'
        except Exception:
            scene.render.engine = 'BLENDER_EEVEE'
    try:
        shading = scene.display.shading
        shading.color_type = 'OBJECT'      # 用 object.color：道具随机色、主体设定色
        shading.background_type = 'WORLD'  # 用世界背景色
    except Exception:
        pass


def setup_direct_video_render(scene):
    """Blender 5 Workbench 直接编码预演 MP4，不切换到 Eevee。"""
    try:
        scene.render.engine = 'BLENDER_WORKBENCH'
    except Exception:
        # 仅为旧版 Blender 保留可用退路；正式预演默认使用 Blender 5。
        try:
            scene.render.engine = 'BLENDER_EEVEE_NEXT'
        except Exception:
            scene.render.engine = 'BLENDER_EEVEE'
    try:
        # Blender 5 将输出媒介与文件格式分开：必须先切 VIDEO，FFMPEG
        # 枚举才可用。此前直接设置 FFMPEG 会迫使流程落入 Eevee。
        try:
            scene.render.image_settings.media_type = 'VIDEO'
        except Exception:
            pass  # Blender 4.x 没有该字段，仍兼容旧式 FFMPEG 配置。
        scene.render.image_settings.file_format = 'FFMPEG'
        scene.render.ffmpeg.format = 'MPEG4'
        scene.render.ffmpeg.codec = 'H264'
        scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'
    except Exception as exc:
        raise RuntimeError("当前 Blender 无法配置直接 MP4 编码: %s" % exc)
    try:
        shading = scene.display.shading
        # 用 object.color：人物沿用提示词指定的红/蓝，普通资产沿用各自
        # 资产色；这等价于 Workbench 的“一物一色”，且不会随机掉角色色。
        shading.light = 'STUDIO'
        shading.color_type = 'OBJECT'
        shading.background_type = 'WORLD'
        shading.show_shadows = True
        shading.show_cavity = True
    except Exception:
        pass


def build_shot_scene(shot, shot_id, n_frames, shared, world, w, h, fps):
    """为一个镜头建独立 Scene，返回 (scene, cam, roots)。"""
    scene = bpy.data.scenes.new(shot_id)
    scene.world = world
    setup_render(scene, w, h, fps)
    scene.collection.children.link(shared)
    set_active_scene(scene)

    move = shot.get("运镜", "固定")
    roots = []
    for s in shot.get("主体", []):
        roots.append(add_person(
            s["名称"],
            s.get("位置", [0, 0, 0]),
            s.get("朝向", 0),
            body_color=tuple(s.get("颜色", BODY)),
            model_path=s.get("模型"),
            pose=_subject_pose(shot, s),
        ))

    cam_pos, cam_target, focal = resolve_camera(shot, shot.get("主体", []))
    cam, target_obj = build_camera(shot_id + "_摄像机", cam_pos, cam_target, focal)
    scene.camera = cam
    add_camera_support_assets(shot, cam_pos, cam_target)

    # 主体位置动画（与相机运镜一致：smoothstep 逐帧缓动）
    for i, s in enumerate(shot.get("主体", [])):
        if "终点" in s and i < len(roots):
            root = roots[i]
            if root:
                p0, p1 = subject_motion_points(shot, s)
                p0.z = 0.0
                p1.z = 0.0
                run_yaw = _movement_yaw(p0, p1, s.get("朝向", 0))
                duration = max(float(shot.get("时长秒") or 0), 1e-3)
                for k in range(1, n_frames + 1):
                    sec = (k - 1) * duration / max(n_frames - 1, 1)
                    tt = subject_motion_progress(shot, sec)
                    root.location = p0.lerp(p1, tt)
                    root.keyframe_insert(data_path="location", frame=k)
                    root.rotation_euler = (0.0, 0.0, run_yaw)
                    root.keyframe_insert(data_path="rotation_euler", frame=k)

    # 运镜关键帧（专业运镜 + 缓动 + 复合）
    apply_camera_animation(cam, cam_pos, cam_target, n_frames, 0, shot, target_obj)
    apply_optical_language(cam, shot, n_frames, 0)

    scene.frame_start = 1
    scene.frame_end = n_frames
    return scene, cam, roots


def build_shot_single(shot, shot_id, n_frames, offset, fps, character_roots=None, asset_roots=None, asset_specs=None):
    """单场景模式：所有镜头对象放进同一场景，关键帧按 offset 时间偏移。

    character_roots: 跨镜头复用的主体 root 字典（名称 -> root）。同一角色
    在多镜头出现时只建一个模型（否则 .blend 里有 林野__S01/S02/S03 多个副本，
    用作参考会被误认为多个角色）。复用对象时只追加本镜时间段的关键帧。
    """
    character_roots = {} if character_roots is None else character_roots
    move = shot.get("运镜", "固定")
    roots = []
    for s in shot.get("主体", []):
        name = s["名称"]
        root = character_roots.get(name)
        if root is None:
            # 首镜创建。单场景下同名角色跨镜头复用（不带 __镜号 后缀），
            # 避免 objects.get("林野") 命中第一个、其余副本静止的问题，
            # 也避免 .blend 里出现多个同名模型副本。
            root = add_person(
                name,
                s.get("位置", [0, 0, 0]),
                s.get("朝向", 0),
                body_color=tuple(s.get("颜色", BODY)),
                model_path=s.get("模型"),
                pose=_subject_pose(shot, s),
            )
            character_roots[name] = root
        else:
            # 复用：重置到本镜起始位置（朝向/颜色/模型沿用首镜设定）。
            loc = s.get("位置", [0, 0, 0])
            root.location = (loc[0], loc[1], loc[2] if len(loc) > 2 else 0)
        roots.append(root)

    # 保存本镜静态角色的最终站位；车辆动作会在此基础上施加相同偏移。
    for root in roots:
        if root:
            root["预演_车辆终点位置"] = tuple(root.location)

    cam_pos, cam_target, focal = resolve_camera(shot, shot.get("主体", []))
    cam, target_obj = build_camera(shot_id + "_摄像机", cam_pos, cam_target, focal)
    bpy.context.scene.camera = cam  # 单场景：每镜头渲染前切到本镜头摄像机
    add_camera_support_assets(shot, cam_pos, cam_target)

    # 主体位置动画（时间偏移）——用本镜 roots[i]，不按名字查。
    # 与相机运镜一致：用 smoothstep 缓动逐帧插关键帧，保证跟拍时
    # 相机与主体速度曲线相同（否则相机缓入缓出、主体线性，中段相机更快）。
    for i, s in enumerate(shot.get("主体", [])):
        if "终点" in s and i < len(roots):
            root = roots[i]
            if root:
                p0, p1 = subject_motion_points(shot, s)
                p0.z = 0.0
                p1.z = 0.0
                run_yaw = _movement_yaw(p0, p1, s.get("朝向", 0))
                duration = max(float(shot.get("时长秒") or 0), 1e-3)
                for k in range(1, n_frames + 1):
                    sec = (k - 1) * duration / max(n_frames - 1, 1)
                    tt = subject_motion_progress(shot, sec)
                    root.location = p0.lerp(p1, tt)
                    root.keyframe_insert(data_path="location", frame=offset + k)
                    root.rotation_euler = (0.0, 0.0, run_yaw)
                    root.keyframe_insert(data_path="rotation_euler", frame=offset + k)

    apply_vehicle_action(shot, asset_roots, roots, n_frames, offset)

    # 运镜关键帧（时间偏移，专业运镜 + 缓动 + 复合）
    apply_camera_animation(cam, cam_pos, cam_target, n_frames, offset, shot, target_obj)
    apply_optical_language(cam, shot, n_frames, offset)
    # 必须等相机路径和目标空物体关键帧完成，再用横移中点的真实视线摆前景。
    apply_foreground_composition(shot, cam, target_obj, asset_roots, asset_specs, n_frames, offset)
    return cam, roots


def _validation_subject_point(root):
    """取头部优先、根节点兜底的可见主体点；不为检查额外创建几何。"""
    if not root:
        return None
    heads = [obj for obj in root.children_recursive if "头部" in obj.name]
    if heads:
        return heads[0].matrix_world.translation.copy()
    return root.matrix_world.translation + mathutils.Vector((0, 0, 1.55))


def _validation_asset_point(root):
    """为前景资产选取一个稳定的可投影点，不额外创建代理物体。"""
    if not root:
        return None
    meshes = [obj for obj in [root, *root.children_recursive] if obj.type == "MESH"]
    if not meshes:
        return root.matrix_world.translation.copy()
    # 组合体（棚架、门洞等）取各可见部件中心的平均值；比 empty 原点可靠。
    points = [obj.matrix_world.translation.copy() for obj in meshes]
    return sum(points, mathutils.Vector((0, 0, 0))) / len(points)


def _is_descendant(obj, root):
    return bool(obj and root and (obj == root or obj in root.children_recursive))


def validate_shot_framing(shots_info, single):
    """快速验镜：确认目标约束、关键主体入画及意外几何遮挡。"""
    from bpy_extras.object_utils import world_to_camera_view
    report = {"状态": "通过", "镜头": []}
    for info in shots_info:
        scene = bpy.context.scene if single else info["scene"]
        cam = info["cam"]
        start = int(info["start_frame"])
        end = start + int(info["n_frames"]) - 1
        sample_frames = sorted({start, (start + end) // 2, end})
        entry = {"镜号": info["shot_id"], "采样帧": sample_frames, "状态": "通过", "问题": []}
        tracks = [c for c in cam.constraints if c.type == 'TRACK_TO' and c.target]
        if not tracks:
            entry["问题"].append("错误：摄像机没有连接镜头目标空物体。")
        else:
            target = tracks[0].target
            for frame in sample_frames:
                scene.frame_set(frame)
                bpy.context.view_layer.update()
                target_pos = target.matrix_world.translation.copy()
                projected = world_to_camera_view(scene, cam, target_pos)
                if projected.z <= 0 or not (0.05 <= projected.x <= 0.95 and 0.05 <= projected.y <= 0.95):
                    entry["问题"].append(f"错误：帧{frame}镜头目标不在安全画面内。")
                    break
                origin = cam.matrix_world.translation.copy()
                ray = target_pos - origin
                distance = ray.length
                if distance > 0.05:
                    hit, _, _, _, hit_obj, _ = scene.ray_cast(
                        bpy.context.evaluated_depsgraph_get(), origin, ray.normalized(), distance=distance - 0.03)
                    allowed = any(_is_descendant(hit_obj, root) for root in info.get("roots", []))
                    note = str(info["shot"].get("备注") or "")
                    hit_name = hit_obj.name.rsplit(".", 1)[0] if hit_obj else ""
                    hit_asset_name = hit_name.split("_", 1)[0] if hit_name else ""
                    if hit and hit_obj and hit_name not in note and hit_asset_name not in note and not allowed:
                        entry["问题"].append(f"警告：帧{frame}相机到目标先被“{hit_obj.name}”遮挡。")
                        break
        for root in info.get("roots", []):
            visible = False
            for frame in sample_frames:
                scene.frame_set(frame)
                bpy.context.view_layer.update()
                point = _validation_subject_point(root)
                if point is None:
                    continue
                projected = world_to_camera_view(scene, cam, point)
                if projected.z > 0 and 0.05 <= projected.x <= 0.95 and 0.05 <= projected.y <= 0.95:
                    visible = True
                    break
            if not visible:
                entry["问题"].append(f"错误：主体“{root.name}”在首/中/尾采样帧均未进入安全画面。")
        for name in info["shot"].get("_前景资产", []):
            root = info.get("asset_roots", {}).get(name)
            visible = False
            for frame in sample_frames:
                scene.frame_set(frame)
                bpy.context.view_layer.update()
                point = _validation_asset_point(root)
                if point is None:
                    continue
                projected = world_to_camera_view(scene, cam, point)
                # 前景可在边缘掠过，放宽安全框；但不能完全在镜头背面或画外。
                if projected.z > 0 and -0.15 <= projected.x <= 1.15 and -0.15 <= projected.y <= 1.15:
                    visible = True
                    break
            if not visible:
                entry["问题"].append(f"错误：前景资产“{name}”未在首/中/尾采样帧进入画面，不能宣称前景掠过。")
        if entry["问题"]:
            entry["状态"] = "需修正" if any(p.startswith("错误") for p in entry["问题"]) else "需查看"
            if entry["状态"] == "需修正":
                report["状态"] = "需修正"
            elif report["状态"] == "通过":
                report["状态"] = "需查看"
        report["镜头"].append(entry)
    return report


def main():
    args = parse_args()
    input_path = args.get("input")
    if not input_path:
        print("用法: --input 镜头表.json [--output 输出目录 | --save-blend 预演.blend] [--single-scene] [--fps N]")
        sys.exit(1)
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if args.get("fps"):
        data["fps"] = int(args["fps"])

    fps = int(data.get("fps", 24))
    w, h = data.get("分辨率", [1280, 720])
    single = bool(args.get("single-scene") or args.get("single_scene"))
    black_frames = int(round(0.4 * fps))  # 镜头间黑场（拼接时插入）

    # 主场景准备
    set_active_scene(bpy.context.scene)
    clear_scene()
    if single:
        bpy.context.scene.name = data.get("项目", "预演")
    else:
        bpy.context.scene.name = "总览"  # 主场景只是共享舞台容器
    world = set_world(data.get("背景颜色", (0.05, 0.05, 0.08)))
    bpy.context.scene.world = world
    setup_render(bpy.context.scene, w, h, fps)
    add_ground(data.get("地面大小", 60), tuple(data.get("地面颜色", GRAY)))

    # 共享场景集合（地面 + 道具），多Scene模式下每个镜头 scene 都链接它
    shared = bpy.data.collections.new("共享场景")
    bpy.context.scene.collection.children.link(shared)
    move_to_collection(bpy.context.object, shared)  # 地面
    shots = data.get("镜头", [])
    asset_roots = {}
    for p in data.get("场景", {}).get("道具", []):
        if not should_build_asset(p, shots):
            print("[previz] 跳过非镜头资产:", p.get("名称", "道具"))
            continue
        created = add_prop(p)
        if created:
            asset_roots[str(p.get("名称") or "")] = created[0]
            created[0]["预演_尺寸"] = tuple(p.get("尺寸") or [1.9, .7, 1.1])
        for obj in created:
            move_to_collection(obj, shared)
    manifest = {"fps": fps, "分辨率": [w, h], "镜头": []}
    shots_info = []

    if single:
        # ===== 单场景模式：所有摄像机/主体同场景，时间线偏移 =====
        # 同名角色跨镜头复用同一模型（character_roots），.blend 里每个角色只出现一次。
        character_roots = {}
        offset = 0
        for idx, shot in enumerate(shots):
            shot_id = shot.get("镜号", "S%02d" % (idx + 1))
            dur = float(shot.get("时长秒", 4))
            n_frames = max(1, int(round(dur * fps)))
            cam, roots = build_shot_single(shot, shot_id, n_frames, offset, fps, character_roots, asset_roots, data.get("场景", {}).get("道具", []))
            shots_info.append({
                "cam": cam, "roots": roots, "shot_id": shot_id,
                "shot": shot, "n_frames": n_frames, "start_frame": offset + 1,
                "asset_roots": asset_roots,
            })
            print("[previz] 构建 %s (%d帧 @帧%d, %s, %s)" % (shot_id, n_frames, offset + 1, shot.get("运镜", ""), shot.get("景别", "")))
            offset += n_frames + black_frames
        total_frames = offset
        bpy.context.scene.frame_end = max(total_frames, 1)
        # 时间线 Markers 绑定摄像机：播放时自动切换到对应镜头机位
        for info in shots_info:
            marker = bpy.context.scene.timeline_markers.new(info["shot_id"], frame=info["start_frame"])
            marker.camera = info["cam"]
    else:
        # ===== 多Scene模式：每镜头一个 Scene =====
        for idx, shot in enumerate(shots):
            shot_id = shot.get("镜号", "S%02d" % (idx + 1))
            dur = float(shot.get("时长秒", 4))
            n_frames = max(1, int(round(dur * fps)))
            scene, cam, roots = build_shot_scene(shot, shot_id, n_frames, shared, world, w, h, fps)
            shots_info.append({
                "scene": scene, "cam": cam, "roots": roots, "shot_id": shot_id,
                "shot": shot, "n_frames": n_frames, "start_frame": 1,
                "asset_roots": asset_roots,
            })
            print("[previz] 构建 %s (%d帧, %s, %s)" % (shot_id, n_frames, shot.get("运镜", ""), shot.get("景别", "")))

    # 每次生成均执行轻量验镜；结果随 manifest 和画布资产归档，而不是仅写日志。
    validation = validate_shot_framing(shots_info, single)
    print("[previz] 验镜状态:", validation.get("状态"))

    # 构建模式：保存 .blend 供前端查看/修改
    save_path = args.get("save-blend") or args.get("save_blend")
    if save_path:
        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        # 画布预演的交付物本身就是视频；在保存前就写入 Blender 5 的
        # Workbench + VIDEO 设置，用户打开 .blend 时看到的也与实际渲染一致。
        if args.get("video-dir") or args.get("video_dir"):
            setup_direct_video_render(bpy.context.scene)
        # 默认停在第一个镜头，视口进入相机视角：打开即看到预演画面
        try:
            if shots_info and single:
                bpy.context.scene.camera = shots_info[0]["cam"]
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            space.region_3d.view_perspective = 'CAMERA'
        except Exception:
            pass
        bpy.ops.wm.save_as_mainfile(filepath=save_path)
        print("[previz] .blend 已保存 -> %s （打开后左侧 Scene 列表逐镜头查看/修改）" % save_path)
        if not args.get("output"):
            return

    # 渲染模式：逐镜头直接编码 MP4。只有兼容旧命令时才输出 PNG 帧序列。
    outdir = args.get("output")
    if not outdir:
        return
    os.makedirs(outdir, exist_ok=True)
    video_dir = args.get("video-dir") or args.get("video_dir")
    if video_dir:
        os.makedirs(video_dir, exist_ok=True)
    scene = bpy.context.scene
    for info in shots_info:
        shot_id = info["shot_id"]
        shot = info["shot"]
        n_frames = info["n_frames"]
        start = info["start_frame"]
        clip_path = ""
        # 单场景模式下，所有镜头的主体共处同一场景；渲染本镜前
        # 隐藏其他镜头的主体，避免画面出现多个并排人（多副本污染）。
        if single:
            current_roots = {info["roots"][i] for i in range(len(shot.get("主体", []))) if i < len(info["roots"])}
            # 跨镜头复用的角色 root 全集（纯名称，无 __ 后缀）
            all_roots = set(character_roots.values())
            for obj in scene.objects:
                if obj in current_roots:
                    continue  # 本镜主体保留
                if obj in all_roots:
                    for o in [obj] + list(obj.children_recursive):
                        o.hide_render = True
                        o.hide_viewport = True
            for r in info["roots"]:
                if r:
                    for o in [r] + list(r.children_recursive):
                        o.hide_render = False
                        o.hide_viewport = False
        if video_dir:
            clip_path = os.path.join(video_dir, "%s.mp4" % shot_id)
            setup_direct_video_render(scene)
            scene.render.filepath = clip_path
        else:
            out_sub = os.path.join(outdir, shot_id)
            os.makedirs(out_sub, exist_ok=True)
            scene.render.image_settings.file_format = 'PNG'
            scene.render.filepath = os.path.join(out_sub, "f")
        scene.frame_start = start
        scene.frame_end = start + n_frames - 1
        if single:
            bpy.ops.render.render(animation=True)
        else:
            try:
                bpy.ops.render.render(scene=info["scene"].name, animation=True)
            except TypeError:
                set_active_scene(info["scene"])
                bpy.ops.render.render(animation=True)
        print("[previz] 渲染 %s 完成 (帧%d-%d)" % (shot_id, start, start + n_frames - 1))
        entry = {
            "镜号": shot_id,
            "时长秒": shot.get("时长秒", 4),
            "帧数": n_frames,
            "start_frame": start,
            "景别": shot.get("景别", ""),
            "运镜": shot.get("运镜", ""),
            "备注": shot.get("备注", ""),
        }
        if clip_path:
            entry["视频"] = clip_path
        manifest["镜头"].append(entry)

    manifest["验镜"] = validation
    with open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("[previz] manifest 已写入 %s" % os.path.join(outdir, "manifest.json"))
    print("[previz] 全部完成 -> %s" % outdir)


if __name__ == "__main__":
    main()
