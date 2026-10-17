#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 OBJ 资产朝向：从 4 个方向渲染模型，确认脸部在哪一面。"""
import bpy
import math
import os
import sys

MODEL = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else ""
OUT = sys.argv[sys.argv.index("--") + 2] if "--" in sys.argv else "."

# 清空场景
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_WORKBENCH'
scene.render.resolution_x = 512
scene.render.resolution_y = 512
scene.render.image_settings.file_format = 'PNG'
scene.render.film_transparent = True

# 导入模型
bpy.ops.wm.obj_import(filepath=MODEL)
obj = None
for o in bpy.context.selected_objects:
    obj = o
    break
if obj is None and bpy.context.scene.collection.objects:
    obj = bpy.context.scene.collection.objects[0]
print("[check] object:", obj.name if obj else "none")
if obj is None:
    sys.exit(1)

# 居中
bpy.ops.object.select_all(action='DESELECT')
obj.select_set(True)
bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
dims = obj.dimensions
print("[check] dims:", [round(v, 3) for v in dims])
obj.location = (0, 0, 0)

# 添加灯光
light_data = bpy.data.lights.new("L", 'POINT')
light_data.energy = 1000
light = bpy.data.objects.new("L", light_data)
scene.collection.objects.link(light)
light.location = (5, 5, 8)

# 相机（视角方向：相机看向模型中心）
def render_view(name, cam_pos, look_at=(0, 0, dims.z * 0.5)):
    cam_data = bpy.data.cameras.new(name)
    cam = bpy.data.objects.new(name, cam_data)
    scene.collection.objects.link(cam)
    cam.location = cam_pos
    direction = (bpy.mathutils.Vector(look_at) - cam.location).normalized() if hasattr(bpy, 'mathutils') else None
    import mathutils
    direction = mathutils.Vector(look_at) - cam.location
    quat = direction.to_track_quat('-Z', 'Y')
    cam.rotation_euler = quat.to_euler()
    scene.camera = cam
    path = os.path.join(OUT, f"{name}.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("[check] saved", path)

d = max(dims.x, dims.y, 1.0) * 1.8
# +Y（模型默认前方？）、-Y、+X、-X 四视角
render_view("view_plusY", (0, d, dims.z * 0.5))
render_view("view_minusY", (0, -d, dims.z * 0.5))
render_view("view_plusX", (d, 0, dims.z * 0.5))
render_view("view_minusX", (-d, 0, dims.z * 0.5))
# 俯视（头顶朝下）看朝向
render_view("view_top", (0, 0, d * 1.5), look_at=(0, 0, 0))
print("[check] done")
