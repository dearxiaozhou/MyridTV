"""Blender panel adapter. engine.py remains independently callable offline."""
bl_info = {
    "name": "TYGG Offline Previs / 离线起落幅预演",
    "author": "TYGG",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar > 离线预演",
    "description": "用现成机器人与约束相机生成可编辑的起幅、落幅",
    "category": "Animation",
}

import json
from pathlib import Path
import bpy
from bpy.props import EnumProperty, IntProperty, FloatProperty, StringProperty, PointerProperty
from bpy_extras.io_utils import ImportHelper
from bpy.app.handlers import persistent
from . import engine


def default_spec(settings=None):
    spec = {
        "schema_version": "1.0", "id": "EndpointShot", "fps": 24,
        "frame_start": 1, "frame_end": 97 if settings is None else 1+settings.duration*24,
        "resolution": [1280, 720],
        "camera": {"preset": "08_中景跟拍" if settings is None else settings.preset,
                   "start": [5,-8,3.8], "end": [3,-5,2.8], "via": [],
                   "aim_start": [0,0,1], "aim_end": [0,1,1],
                   "lens_mm": 40 if settings is None else settings.lens, "timing": "LINEAR"},
        "actors": [
            {"id": "actor_x", "asset": "x_bot" if settings is None else settings.actor_a,
             "start": {"position": [-.85,-.8,0], "yaw_deg": 0, "pose": "WALK"},
             "end": {"position": [-.45,1,0], "yaw_deg": 20, "pose": "STAND"}},
            {"id": "actor_y", "asset": "y_bot" if settings is None else settings.actor_b,
             "start": {"position": [.85,1.4,0], "yaw_deg": 180, "pose": "STAND"},
             "end": {"position": [.75,1.4,0], "yaw_deg": 180, "pose": "WALK"}},
        ]}
    if spec['camera']['preset']=='01_慢镜头感':
        spec['camera']['end']=spec['camera']['start'][:]
    return spec


def update_lens(self, context):
    if context and context.scene.get("pv_owned") and context.scene.get("pv_refs"):
        engine.set_lens(context.scene, self.lens)


class PV_Settings(bpy.types.PropertyGroup):
    preset: EnumProperty(name="约束相机预设", items=[(p,p+('（固定机位）' if p=='01_慢镜头感' else ''),"") for p in engine.PRESETS], default="08_中景跟拍")
    duration: IntProperty(name="时长（秒）", default=4, min=1, max=600)
    lens: FloatProperty(name="焦距（毫米）", default=40, min=5, max=300, update=update_lens)
    actor_a: EnumProperty(name="人物 A", items=[("x_bot","X_Bot",""),("y_bot","Y_Bot","")], default="x_bot")
    actor_b: EnumProperty(name="人物 B", items=[("x_bot","X_Bot",""),("y_bot","Y_Bot","")], default="y_bot")
    output: StringProperty(name="导出目录", subtype="DIR_PATH", default="")


class PV_OT_Create(bpy.types.Operator):
    bl_idname = "tygg_previs.create"
    bl_label = "新建离线预演"
    bl_description = "使用两个人物资产与已集成的约束相机；保留当前场景"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        try:
            settings = context.scene.pv_settings
            scene = engine.build(default_spec(settings))
            scene.pv_settings.output = settings.output
            scene.pv_settings.duration = settings.duration
            self.report({"INFO"}, "已创建。拖动机位和目标控制器即可修改构图")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class PV_OT_FromJSON(bpy.types.Operator, ImportHelper):
    bl_idname = "tygg_previs.from_json"
    bl_label = "从镜头 JSON 生成"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})
    def execute(self, context):
        try:
            scene = engine.build(json.loads(Path(self.filepath).read_text(encoding="utf-8")))
            scene.pv_settings.output = str(Path(self.filepath).parent/"endpoints")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class PV_OT_Select(bpy.types.Operator):
    bl_idname = "tygg_previs.select_control"
    bl_label = "选择控制器"
    object_name: StringProperty()
    def execute(self, context):
        obj = bpy.data.objects.get(self.object_name)
        if not obj:
            return {"CANCELLED"}
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {"FINISHED"}


class PV_OT_Jump(bpy.types.Operator):
    bl_idname = "tygg_previs.jump"
    bl_label = "查看端点"
    which: EnumProperty(items=[("start","起幅",""),("end","落幅","")])
    def execute(self, context):
        scene = context.scene
        scene.frame_set(scene.frame_start if self.which=="start" else scene.frame_end)
        for area in context.screen.areas if context.screen else []:
            if area.type=="VIEW_3D":
                area.spaces.active.region_3d.view_perspective="CAMERA"
        return {"FINISHED"}


class PV_OT_Retime(bpy.types.Operator):
    bl_idname = "tygg_previs.retime"
    bl_label = "应用时长"
    def execute(self, context):
        try:
            scene = context.scene
            engine.retime(scene, scene.frame_start, scene.frame_start+scene.pv_settings.duration*scene.render.fps)
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class PV_OT_ApplyPoses(bpy.types.Operator):
    bl_idname = "tygg_previs.apply_poses"
    bl_label = "应用起止姿态"
    def execute(self, context):
        try:
            engine.apply_poses(context.scene)
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class PV_OT_SetPose(bpy.types.Operator):
    bl_idname = "tygg_previs.set_pose"
    bl_label = "设置端点姿态"
    bl_options = {"REGISTER", "UNDO"}
    object_name: StringProperty()
    pose: EnumProperty(items=[("STAND","站立",""),("WALK","行走",""),("RUN","跑步",""),("SIT","坐姿","")])
    def execute(self, context):
        obj=bpy.data.objects.get(self.object_name)
        if not obj:
            return {"CANCELLED"}
        previous=obj.get('pose','STAND')
        try:
            obj['pose']=self.pose
            engine.apply_poses(context.scene)
            return {"FINISHED"}
        except Exception as exc:
            obj['pose']=previous
            self.report({"ERROR"},str(exc))
            return {"CANCELLED"}


class PV_MT_Pose(bpy.types.Menu):
    bl_label = "选择端点姿态"
    bl_idname = "PV_MT_endpoint_pose"
    def draw(self, context):
        obj=context.pv_pose_control
        for value,label in [('STAND','站立'),('WALK','行走'),('RUN','跑步'),('SIT','坐姿')]:
            op=self.layout.operator('tygg_previs.set_pose',text=label)
            op.object_name=obj.name
            op.pose=value


class PV_OT_Export(bpy.types.Operator):
    bl_idname = "tygg_previs.export_endpoints"
    bl_label = "导出起幅、落幅和配置"
    def execute(self, context):
        try:
            chosen = context.scene.pv_settings.output
            path = engine.render_endpoints(context.scene, bpy.path.abspath(chosen) if chosen else Path(__file__).parent.parent/"exports"/context.scene.name)
            self.report({"INFO"}, "已导出："+str(path))
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class PV_PT_Panel(bpy.types.Panel):
    bl_label = "离线起落幅预演"
    bl_idname = "PV_PT_offline_previs"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "离线预演"
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.pv_settings
        if not scene.get("pv_owned"):
            layout.prop(settings,"preset")
            layout.prop(settings,"lens")
            layout.prop(settings,"duration")
            layout.prop(settings,"actor_a")
            layout.prop(settings,"actor_b")
            layout.operator("tygg_previs.create")
            layout.operator("tygg_previs.from_json")
            return
        reference = engine.refs(scene)
        row = layout.row(align=True)
        row.operator("tygg_previs.jump",text="看起幅").which="start"
        row.operator("tygg_previs.jump",text="看落幅").which="end"
        camera = reference["camera"]
        box = layout.box()
        box.label(text="拖动控制器即可改镜头")
        for label,key in (("起机位","start"),("落机位","end"),("起目标","aim_start"),("落目标","aim_end"),("编辑路径","path")):
            if camera.get('fixed') and key in {'end','path'}:
                continue
            row = box.row(align=True)
            row.operator("tygg_previs.select_control",text=label).object_name=camera[key]
        progress=bpy.data.objects[reference["progress"]]
        box.prop(settings,'lens',text="焦距")
        box.prop(settings,"duration")
        box.operator("tygg_previs.retime")
        for index,record in enumerate(reference["actors"],1):
            box = layout.box()
            box.label(text="人物 "+str(index)+" · "+{"x_bot":"X_Bot","y_bot":"Y_Bot"}.get(record["asset"],record["asset"]))
            for label,key in (("起点","start"),("终点","end")):
                obj=bpy.data.objects[record[key]]
                row=box.row(align=True)
                row.operator("tygg_previs.select_control",text=label).object_name=obj.name
                row.context_pointer_set('pv_pose_control',obj)
                row.menu('PV_MT_endpoint_pose',text={'STAND':'站立','WALK':'行走','RUN':'跑步','SIT':'坐姿'}.get(obj['pose'],'姿态'))
        layout.prop(settings,"output")
        layout.operator("tygg_previs.export_endpoints")
        layout.operator("tygg_previs.create",text="另建一个镜头")


CLASSES=(PV_Settings,PV_OT_Create,PV_OT_FromJSON,PV_OT_Select,PV_OT_Jump,PV_OT_Retime,PV_OT_ApplyPoses,PV_OT_SetPose,PV_MT_Pose,PV_OT_Export,PV_PT_Panel)


@persistent
def sync_loaded_scene(_=None):
    scene=bpy.context.scene
    if not scene or not scene.get('pv_owned') or not hasattr(scene,'pv_settings'):
        return
    try:
        spec=engine.capture(scene)
        scene.pv_settings.lens=spec['camera']['lens_mm']
        scene.pv_settings.preset=spec['camera']['preset']
        scene.pv_settings.duration=max(1,round((scene.frame_end-scene.frame_start)/scene.render.fps))
        if spec['actors']:
            scene.pv_settings.actor_a=spec['actors'][0]['asset']
        if len(spec['actors'])>1:
            scene.pv_settings.actor_b=spec['actors'][1]['asset']
    except (KeyError,ValueError) as exc:
        print('Offline Previs: scene controls need attention:',exc)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pv_settings=PointerProperty(type=PV_Settings)
    if sync_loaded_scene not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(sync_loaded_scene)
    sync_loaded_scene()


def unregister():
    if sync_loaded_scene in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(sync_loaded_scene)
    if hasattr(bpy.types.Scene,"pv_settings"):
        del bpy.types.Scene.pv_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
