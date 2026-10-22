"""Scene reuse or blockouts built only from the user's asset list."""
import bpy,json,math
from pathlib import Path
from mathutils import Vector,Matrix
from . import scene_layout

def _material(name,color):
 mat=bpy.data.materials.get(name) or bpy.data.materials.new(name);mat.diffuse_color=(*color,1);return mat

def _box(scene,name,location,dimensions,material):
 bpy.ops.mesh.primitive_cube_add(size=1,location=location);obj=bpy.context.object;obj.name=scene.name+'.SCENE.'+name;obj.dimensions=dimensions
 bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);obj.data.materials.append(material);obj['pv_scene_prop']=True
 return obj

def _import(scene,path,environment=False):
 path=Path(path);before=set(bpy.data.objects)
 if path.suffix.lower()=='.blend':
  with bpy.data.libraries.load(str(path),link=False) as (src,dst):dst.objects=list(src.objects)
  objects=[o for o in dst.objects if o]
  def owned(o):
   while o:
    if '.subject_' in o.name or '.CAMERA' in o.name or '.TARGET_' in o.name or o.get('pv_motion_target') or o.get('character_name'):return True
    o=o.parent
   return False
  kept=[o for o in objects if o.type not in {'CAMERA','LIGHT'} and not (environment and (owned(o) or o.name.endswith('.PROGRESS')))]
  for obj in kept:
   if obj.name not in scene.objects:scene.collection.objects.link(obj)
  for obj in objects:
   if obj not in kept:bpy.data.objects.remove(obj,do_unlink=True)
 elif path.suffix.lower()=='.fbx':bpy.ops.import_scene.fbx(filepath=str(path),use_image_search=False)
 elif path.suffix.lower()=='.obj':bpy.ops.wm.obj_import(filepath=str(path))
 else:bpy.ops.import_scene.gltf(filepath=str(path))
 objects=list(set(bpy.data.objects)-before)
 if not any(o.type=='MESH' for o in objects):raise ValueError('提供的工程或模型没有可用场景几何')
 for obj in objects:
  obj['pv_scene_prop']=True
  if 'pv_motion_seat' in obj:del obj['pv_motion_seat']
 return objects

def apply(scene,config,camera):
 signature=json.dumps({k:config[k] for k in ['scene_mode','scene_project','scene_assets']},sort_keys=True)
 if scene.get('pv_scene_signature')==signature:return
 if config['scene_mode']=='existing' and bpy.data.filepath and Path(config['scene_project']).resolve()==Path(bpy.data.filepath).resolve():
  scene['pv_scene_signature']=signature;scene['pv_scene_source']=config['scene_project'];return
 for obj in list(scene.objects):
  if obj.get('pv_scene_prop'):bpy.data.objects.remove(obj,do_unlink=True)
 if config['scene_mode']=='none':scene['pv_scene_signature']=signature;return
 for obj in list(scene.objects):
  if '.DEPTH_' in obj.name:bpy.data.objects.remove(obj,do_unlink=True)
 if config['scene_mode']=='existing':_import(scene,config['scene_project'],True)
 else:
  wood=_material('Previs furniture',(.37,.27,.19));neutral=_material('Previs scene',(.48,.51,.54));fabric=_material('Previs upholstery',(.26,.36,.39));green=_material('Previs foliage',(.24,.37,.23))
  for i,item in enumerate(config['scene_assets']):
   x,y=item['position'];w,d,h=item['size'];kind=item['kind'];name=item['name'];before=set(bpy.data.objects)
   if item.get('model'):
    objects=_import(scene,item['model']);points=[o.matrix_world@Vector(p) for o in objects if o.type=='MESH' for p in o.bound_box]
    lo=Vector(tuple(min(p[a] for p in points) for a in range(3)));hi=Vector(tuple(max(p[a] for p in points) for a in range(3)))
    scale=min(w/max(.001,hi.x-lo.x),d/max(.001,hi.y-lo.y),h/max(.001,hi.z-lo.z));origin=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,lo.z))
    parent=bpy.data.objects.new(scene.name+'.SCENE.'+name,None);scene.collection.objects.link(parent);parent['pv_scene_prop']=True
    for obj in objects:
     if obj.parent not in objects:matrix=obj.matrix_world.copy();obj.parent=parent;obj.matrix_world=matrix
    angle={'forward':0,'backward':math.pi,'left':math.pi/2,'right':-math.pi/2}[item.get('facing','forward')];parent.rotation_euler.z=angle;parent.location=Vector((x,y,0))-Matrix.Rotation(angle,3,'Z')@(origin*scale);parent.scale=(scale,)*3
   elif kind in {'sofa','chair','bed'}:
    _box(scene,name+'坐面' if kind!='bed' else name+'床面',(x,y,h-.08),(w,d,.16),fabric)
    _box(scene,name+'靠背',(x,y-d/2+.06,h+.32),(w,.12,.65),fabric)
    for a in [-1,1]:
     for b in [-1,1]:_box(scene,name+'支撑',(x+a*(w/2-.07),y+b*(d/2-.07),(h-.16)/2),(.09,.09,max(.1,h-.16)),wood)
   elif kind=='table':
    _box(scene,name+'桌面',(x,y,h-.04),(w,d,.08),wood)
    for a in [-1,1]:
     for b in [-1,1]:_box(scene,name+'桌腿',(x+a*(w/2-.07),y+b*(d/2-.07),(h-.08)/2),(.09,.09,max(.1,h-.08)),wood)
   elif kind=='tree':
    _box(scene,name+'树干',(x,y,h*.35),(.18,.18,h*.7),wood)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2,radius=1,location=(x,y,h*.75));obj=bpy.context.object;obj.name=name+'树冠';obj.scale=(w/2,d/2,h*.32);obj.data.materials.append(green);obj['pv_scene_prop']=True
   elif kind=='door':
    for sign in [-1,1]:_box(scene,name+'门框',(x+sign*w/2,y,h/2),(.1,d,h),wood)
    _box(scene,name+'门楣',(x,y,h),(w,d,.1),wood)
   else:_box(scene,name,(x,y,h/2),(w,d,h),neutral)
   # Rotate complete assemblies around their declared ground footprint.
   if not item.get('model'):
    angle={'forward':0,'backward':math.pi,'left':math.pi/2,'right':-math.pi/2}[item.get('facing','forward')]
    rotation=Matrix.Rotation(angle,4,'Z');pivot=Vector((x,y,0))
    for obj in set(bpy.data.objects)-before:
     obj.location=pivot+rotation.to_3x3()@(obj.location-pivot);obj.rotation_euler.z+=angle
 scene['pv_scene_signature']=signature;scene['pv_scene_source']=config['scene_project'] if config['scene_mode']=='existing' else 'User asset list'
