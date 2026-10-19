"""Reusable, constraint-driven camera animations from a filtered asset library."""
import json,math,shutil,subprocess,time
from pathlib import Path
import bpy
from mathutils import Vector,Quaternion
from bpy_extras.object_utils import world_to_camera_view
from . import engine
from . import motion_model as model

ROOT=Path(__file__).resolve().parent
CROP={'wide':(1.45,.50),'full':(1.08,.50),'medium':(.62,.70),'close':(.34,.83),'detail':(.18,.91)}

def _entry(config):return next(p for p in model.catalog()['presets'] if p['id']==config['preset'])

def _pose_and_bounds(scene,config):
 ref=engine.refs(scene)
 for actor in ref['actors']:
  start=bpy.data.objects[actor['start']];end=bpy.data.objects[actor['end']]
  end.location=start.location
  start['pose']=end['pose']=config['pose']
 engine.apply_poses(scene)
 scene.frame_set(scene.frame_start);bpy.context.view_layer.update()
 dg=bpy.context.evaluated_depsgraph_get();points=[]
 rigs={bpy.data.objects[a['rig']] for a in ref['actors']}
 for obj in scene.objects:
  if obj.type=='MESH' and obj.find_armature() in rigs:
   evaluated=obj.evaluated_get(dg);points.extend(evaluated.matrix_world@Vector(p) for p in evaluated.bound_box)
 if not points:raise ValueError('人物模型没有可见几何')
 low=Vector(tuple(min(p[i] for p in points) for i in range(3)))
 high=Vector(tuple(max(p[i] for p in points) for i in range(3)))
 return low,high

def _fit(config,low,high,framing):
 height=high.z-low.z;scale,center=CROP[framing]
 focus=Vector(((low.x+high.x)/2,(low.y+high.y)/2,low.z+height*center))
 aspect=config['resolution'][0]/config['resolution'][1]
 tan_h=36/(2*config['lens_mm']);tan_v=tan_h/aspect
 distance=max(height*scale/(2*tan_v*.80),(high.x-low.x)*1.08/(2*tan_h*.84))
 return focus,distance

def _resolve(config,low,high):
 entry=_entry(config);kind=entry['kind'];height=high.z-low.z
 focus,distance=_fit(config,low,high,config['framing'])
 minimum=max(.40,(high.x-low.x)*.56)
 if config['amount'] is None:
  if kind=='orbit':amount=90.
  elif entry['amount_type']=='angle':amount=10.
  elif kind in {'crane_up','crane_down'}:amount=height*.6
  elif kind=='follow':amount=3.
  elif kind in {'push','dolly_zoom'}:amount=min(distance*.30,max(.02,distance-minimum-.08))
  else:amount=distance*.35
 else:amount=float(config['amount'])
 if config['end_framing']!='auto' and kind in {'push','pull','dolly_zoom'}:
  _,target_distance=_fit(config,low,high,config['end_framing'])
  amount=distance-target_distance if kind in {'push','dolly_zoom'} else target_distance-distance
  if amount<=.01:raise ValueError('结束景别与运镜方向矛盾：推近需更近，拉远需更远')
 if kind in {'push','dolly_zoom'} and amount>=distance-minimum:
  raise ValueError(f'距离过大：当前景别最多推进约{max(0,distance-minimum):.2f}米，请减小距离或选择更远景别')
 if kind in {'tilt_up','tilt_down'} and amount>60:raise ValueError('上摇／下摇角度请不超过60度')
 elevation=height*.08
 if kind=='first_person':elevation=height*.40
 if kind=='crane_down':elevation=min(distance*.65,amount+height*.12)
 radial=math.sqrt(max(.01,distance*distance-elevation*elevation))
 start=focus+Vector((0,radial,elevation));end=start.copy();aim0=focus.copy();aim1=focus.copy()
 direction=-1 if config['direction']=='left' else 1
 points=[start.copy()];actor_delta=Vector((0,0,0));fixed=False
 if kind in {'push','pull','dolly_zoom'}:
  end=start+(focus-start).normalized()*amount*(1 if kind!='pull' else -1)
 elif kind in {'lateral','lateral_fast','reveal'}:end.x+=direction*amount
 elif kind=='orbit':
  points=[focus+Vector((radial*math.sin(direction*math.radians(amount)*i/8),radial*math.cos(direction*math.radians(amount)*i/8),elevation)) for i in range(9)]
  end=points[-1]
 elif kind in {'crane_up','crane_down'}:
  end.z+=amount*(1 if kind=='crane_up' else -1)
  if end.z<.15:raise ValueError('下降距离过大，会使相机进入地面')
 elif kind in {'pan','tilt_up','tilt_down'}:
  fixed=True
  angle=math.radians(amount)*(direction if kind=='pan' else -1 if kind=='tilt_up' else 1)
  axis=Vector((0,0,1)) if kind=='pan' else Vector((1,0,0))
  aim1=start+Quaternion(axis,angle)@(focus-start)
 elif kind=='follow':
  actor_delta=Vector((0,amount,0));end+=actor_delta;aim1+=actor_delta
  # A three-quarter front follow preserves face visibility and readable ground travel.
  offset=Vector((distance*.65,distance*.75,elevation));offset.normalize();offset*=distance
  start=focus+offset;end=start+actor_delta
 else:
  source=[Vector(p) for p in entry['source_path']]
  travel=sum((b-a).length for a,b in zip(source,source[1:]))
  if travel<.001:raise ValueError('该预设缺少有效移动路线')
  points=[start+Vector((-(p-source[0]).x,-(p-source[0]).y,(p-source[0]).z))*amount/travel for p in source]
  end=points[-1]
 if len(points)==1:points=[start.copy(),end.copy()]
 if fixed:points=[start.copy(),start+Vector((.001,0,0))]
 for point in points:
  if point.z<.12:raise ValueError('移动幅度会使相机进入地面，请减小幅度')
 pace=entry['default_pace'] if config['pace']=='preset' else config['pace']
 return {'entry':entry,'focus':focus,'start':start,'end':end,'aim_start':aim0,'aim_end':aim1,'points':points,'fixed':fixed,
  'amount':amount,'start_distance':distance,'end_distance':(end-aim1).length,'actor_delta':actor_delta,'pace':pace}

def _timing(scene,pace):
 controller=bpy.data.objects[engine.refs(scene)['progress']]
 engine._progress_keys(controller,scene.frame_start,scene.frame_end,'LINEAR' if pace=='linear' else 'BEZIER')
 if pace=='linear':return
 fc=engine.action_curves(controller)[0];first,last=fc.keyframe_points;span=(last.co.x-first.co.x)/3
 first.handle_left_type=first.handle_right_type=last.handle_left_type=last.handle_right_type='FREE'
 y1,y2={'smooth':(0,1),'accelerate':(0,1/3),'decelerate':(2/3,1)}[pace]
 first.handle_right=(first.co.x+span,y1);last.handle_left=(last.co.x-span,y2)
 fc.update()

def _path(scene,resolved):
 refs=engine.refs(scene);record=refs['camera'];path=bpy.data.objects[record['path']]
 first,last=bpy.data.objects[record['start']],bpy.data.objects[record['end']]
 first.location=resolved['start'];last.location=resolved['end']
 for key in ['aim_start','aim_end']:bpy.data.objects[record[key]].location=resolved[key]
 path.modifiers.clear();path.data.splines.clear();spline=path.data.splines.new('BEZIER');spline.bezier_points.add(len(resolved['points'])-1)
 for point,co in zip(spline.bezier_points,resolved['points']):point.co=co;point.handle_left_type=point.handle_right_type='AUTO'
 bpy.context.view_layer.update()
 for control,index in [(first,0),(last,len(resolved['points'])-1)]:
  modifier=path.modifiers.new('Endpoint','HOOK');modifier.object=control
  modifier.vertex_indices_set([3*index,3*index+1,3*index+2]);modifier.matrix_inverse=control.matrix_world.inverted()@path.matrix_world
 return refs

def _walk(scene,actor,delta):
 rig=bpy.data.objects[actor['rig']];rig.animation_data_clear();rig.animation_data_create()
 info=json.loads((ROOT/'assets/walk_actions.json').read_text(encoding='utf8'));name=info['actions'][actor['asset']]
 action=bpy.data.actions.get(name)
 if not action:
  with bpy.data.libraries.load(str(ROOT/'assets/walk_actions.blend'),link=False) as (source,target):target.actions=[name]
  action=target.actions[0]
 track=rig.animation_data.nla_tracks.new();track.name='Library walk cycle'
 strip=track.strips.new('Reusable Walk',scene.frame_start,action)
 if hasattr(strip,'action_slot') and action.slots:strip.action_slot=action.slots[0]
 period=info['frame_end']-info['frame_start'];cycles=delta.length/info['stride_m']
 strip.scale=(scene.frame_end-scene.frame_start+1)/period
 strip.use_animated_time=True
 driver=strip.driver_add('strip_time').driver
 progress=bpy.data.objects[engine.refs(scene)['progress']]
 engine._var(driver,'u',progress,'["progress"]')
 driver.expression=f'{info["frame_start"]}+((u*{cycles!r}*{period})%{period})'

def _stage(scene):
 if scene.get('pv_motion_stage'):return
 verts=[];faces=[]
 for axis in range(2):
  for i in range(-8,9):
   strip=[(-8,i-.008,.001),(8,i-.008,.001),(8,i+.008,.001),(-8,i+.008,.001)]
   if axis:strip=[(y,x,z) for x,y,z in strip]
   n=len(verts);verts+=strip;faces.append(tuple(range(n,n+4)))
 mesh=bpy.data.meshes.new(scene.name+'.GRID');mesh.from_pydata(verts,[],faces)
 obj=bpy.data.objects.new(scene.name+'.GRID',mesh);scene.collection.objects.link(obj)
 mat=bpy.data.materials.new('Stage grid');mat.diffuse_color=(.38,.43,.46,1);mesh.materials.append(mat)
 for i,(x,y,z) in enumerate([(-2.5,1.7,.5),(2.5,2.2,.9),(-1.6,-2.3,.28)]):
  bpy.ops.mesh.primitive_cube_add(size=1,location=(x,y,z/2));box=bpy.context.object;box.name=scene.name+'.DEPTH_'+str(i)
  box.dimensions=(.45,.45,z);bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
  material=bpy.data.materials.new('Depth marker');material.diffuse_color=(.32+.035*i,.34+.025*i,.36+.015*i,1);box.data.materials.append(material)
 scene['pv_motion_stage']=True

def _configure(scene,config):
 low,high=_pose_and_bounds(scene,config);resolved=_resolve(config,low,high)
 old_refs=engine.refs(scene);old_preset=json.loads(scene['pv_spec'])['camera']['preset']
 core=json.loads(scene['pv_spec']);core['frame_end']=max(2,round(config['duration']*config['fps']));core['fps']=config['fps']
 camera={'preset':config['preset'],'start':list(resolved['start']),'end':list(resolved['end']),
  'aim_start':list(resolved['aim_start']),'aim_end':list(resolved['aim_end']),
  'via':[list(v) for v in resolved['points'][1:-1]],'lens_mm':config['lens_mm'],'timing':'LINEAR','hold_position':resolved['fixed']}
 previous_fixed=bool(old_refs['camera'].get('fixed'))
 core['camera']=camera
 if old_preset!=config['preset'] or previous_fixed!=resolved['fixed']:
  # Changing preset replaces just its own camera collection; actor identities remain.
  camera_object=bpy.data.objects[old_refs['camera']['camera']]
  collection=next(c for c in camera_object.users_collection if c.name.endswith('.CAMERA_RIG'))
  for obj in list(collection.objects):bpy.data.objects.remove(obj,do_unlink=True)
  bpy.data.collections.remove(collection)
  record=engine._camera(scene,core,bpy.data.objects[old_refs['progress']],scene.name)
  old_refs['camera']=record;scene['pv_refs']=json.dumps(old_refs,ensure_ascii=False)
 scene['pv_spec']=json.dumps(core,ensure_ascii=False)
 scene.render.fps=config['fps'];scene.render.fps_base=1
 scene.frame_start=1;scene.frame_end=core['frame_end']
 scene.render.resolution_x,scene.render.resolution_y=config['resolution']
 refs=_path(scene,resolved);camera_obj=bpy.data.objects[refs['camera']['camera']];scene.camera=camera_obj
 camera_obj.data.sensor_fit='HORIZONTAL';camera_obj.data.shift_x={'center':0,'left':1/6,'right':-1/6}[config['composition']]
 # Stabilize the up axis for vertical routes and 180-degree orbits. The original
 # library aim constraint stays in place; this only removes unintended roll.
 up=next((c for c in camera_obj.constraints if c.name=='03_WORLD_UP'),None)
 if up is None:up=camera_obj.constraints.new('TRACK_TO');up.name='03_WORLD_UP'
 up.target=next(c.target for c in camera_obj.constraints if c.type=='DAMPED_TRACK')
 up.track_axis='TRACK_NEGATIVE_Z';up.up_axis='UP_Y'
 controller=bpy.data.objects[refs['progress']];controller['lens_mm']=config['lens_mm']
 fc=camera_obj.data.driver_add('lens')
 for variable in list(fc.driver.variables):fc.driver.variables.remove(variable)
 engine._var(fc.driver,'focal',controller,'["lens_mm"]')
 if resolved['entry']['kind']=='dolly_zoom':
  engine._var(fc.driver,'u',controller,'["progress"]');ratio=resolved['end_distance']/resolved['start_distance']
  fc.driver.expression=f'focal*(1+({ratio!r}-1)*u)'
 else:fc.driver.expression='focal'
 _timing(scene,resolved['pace'])
 for actor in refs['actors']:
  start=bpy.data.objects[actor['start']];end=bpy.data.objects[actor['end']];end.location=start.location+resolved['actor_delta']
  if resolved['entry']['kind']=='follow':_walk(scene,actor,resolved['actor_delta'])
 _stage(scene)
 scene['pv_motion_owned']=True;scene['pv_motion_spec']=json.dumps(config,ensure_ascii=False)
 scene['pv_motion_resolved']=json.dumps({'preset':config['preset'],'source_name':resolved['entry']['source_name'],
  'amount':resolved['amount'],'amount_type':resolved['entry']['amount_type'],'start_distance_m':resolved['start_distance'],
  'end_distance_m':resolved['end_distance'],'focus_start':list(resolved['focus']),'focus_end':list(resolved['focus']+resolved['actor_delta']),
  'pace':resolved['pace'],'framing':config['framing'],'actor_motion_m':resolved['actor_delta'].length},ensure_ascii=False)
 scene.frame_set(1);controller.update_tag();bpy.context.view_layer.update()
 return scene

def build(value,existing=None):
 config=model.validate(value)
 entries=model.catalog()['presets'];engine.PRESETS=list(dict.fromkeys(engine.PRESETS+[p['id'] for p in entries]));engine.CAMERA_LIBRARY=ROOT/'assets/motion_cameras.blend'
 if existing and existing.get('pv_motion_owned'):
  old=json.loads(existing['pv_motion_spec'])
  if old['subject']==config['subject']:
   bpy.context.window.scene=existing
   return _configure(existing,config)
 assets=['x_bot','y_bot'] if config['subject']=='both' else [config['subject']]
 actors=[]
 for index,asset in enumerate(assets):
  state={'position':[(-.75 if index==0 else .75) if len(assets)>1 else 0,0,0],'yaw_deg':0,'pose':config['pose']}
  actors.append({'id':'subject_'+str(index+1),'asset':asset,'start':dict(state),'end':dict(state)})
 base={'schema_version':'1.0','id':'MotionPreview','fps':config['fps'],'frame_start':1,'frame_end':round(config['duration']*config['fps']),
  'resolution':config['resolution'],'actors':actors,
  'camera':{'preset':'08_中景跟拍','start':[0,8,2],'end':[0,7,2],'aim_start':[0,0,1],'aim_end':[0,0,1],'via':[],'lens_mm':config['lens_mm'],'timing':'LINEAR'}}
 scene=engine.build(base)
 return _configure(scene,config)

def inspect(scene):
 refs=engine.refs(scene);camera=bpy.data.objects[refs['camera']['camera']]
 old_frame,old_sub=scene.frame_current,scene.frame_subframe
 rows=[]
 try:
  for fraction in [0,.1,.25,.5,.75,.9,1]:
   frame=scene.frame_start+(scene.frame_end-scene.frame_start)*fraction
   scene.frame_set(int(frame),subframe=frame-int(frame));dg=bpy.context.evaluated_depsgraph_get();cam=camera.evaluated_get(dg)
   rows.append({'progress_fraction':fraction,'camera_position':list(cam.matrix_world.translation),
    'camera_rotation':list(cam.matrix_world.to_quaternion()),'lens_mm':cam.data.lens,
    'up_z':(cam.matrix_world.to_quaternion()@Vector((0,1,0))).z,
    'actors':[list(bpy.data.objects[a['root']].evaluated_get(dg).matrix_world.translation) for a in refs['actors']]})
 finally:scene.frame_set(old_frame,subframe=old_sub)
 first=Vector(rows[0]['camera_position']);distance=max((Vector(r['camera_position'])-first).length for r in rows)
 q0=Quaternion(rows[0]['camera_rotation']);angle=max(min(q0.rotation_difference(Quaternion(r['camera_rotation'])).angle,math.tau-q0.rotation_difference(Quaternion(r['camera_rotation'])).angle) for r in rows)
 keys=sum(len(fc.keyframe_points) for fc in engine.action_curves(camera))
 if distance<.005 and angle<math.radians(.2):raise ValueError('该预览未产生有效镜头运动')
 if keys:raise ValueError('相机出现了逐帧动画通道')
 return {'status':'sampled_motion_checks_passed','camera_action_keys':keys,'progress_keys':sum(len(fc.keyframe_points) for fc in engine.action_curves(bpy.data.objects[refs['progress']])),
  'translation_range_m':distance,'rotation_range_deg':math.degrees(angle),'samples':rows,
  'resolved':json.loads(scene['pv_motion_resolved']),'unverified':['continuous_collision','aesthetic_quality']}

def export(scene,output,ffmpeg=None):
 output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
 checks=inspect(scene);config=json.loads(scene['pv_motion_spec'])
 (output/'checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf8')
 (output/'shot.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf8')
 frames=output/'frames';frames.mkdir(exist_ok=True)
 scene.render.image_settings.file_format='PNG';scene.render.filepath=str(frames/'frame_')
 bpy.ops.render.render(animation=True)
 command=ffmpeg or shutil.which('ffmpeg')
 if not command:raise ValueError('未找到本地视频编码器ffmpeg')
 subprocess.run([str(command),'-hide_banner','-loglevel','error','-y','-framerate',str(scene.render.fps),'-start_number','1',
  '-i',str(frames/'frame_%04d.png'),'-frames:v',str(scene.frame_end),'-c:v','libx264','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(output/'preview.mp4')],check=True)
 shutil.copy2(frames/'frame_0001.png',output/'poster.png')
 scene.frame_set(1);bpy.data.libraries.write(str(output/'previs.blend'),{scene},path_remap='RELATIVE',fake_user=True)
 # Temporary frames are safe to remove only after successful encoding and save.
 if frames.resolve().parent==output:shutil.rmtree(frames)
 return checks
