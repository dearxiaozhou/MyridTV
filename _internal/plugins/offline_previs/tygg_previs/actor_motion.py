"""Reusable Mixamo clips, independent of camera presets and camera easing."""
import json,math
from pathlib import Path
import bpy
from mathutils import Vector
from . import engine
ROOT=Path(__file__).resolve().parent
DIRECTIONS={'forward':Vector((0,1,0)),'backward':Vector((0,-1,0)),'left':Vector((-1,0,0)),'right':Vector((1,0,0))}

def segments(config):
 items=config['actions']
 if not items and config['preset'].startswith('08_'):
  items=[{'action':'walk','duration':config['duration'],'distance':config['amount'] if config['amount'] is not None else min(15,config['duration']*1.35),'direction':'forward'}]
 return items

def _load(kind,asset):
 info=json.loads((ROOT/f'assets/{kind}_actions.json').read_text(encoding='utf8'));name=info['actions'][asset]
 action=bpy.data.actions.get(name)
 if action is None:
  with bpy.data.libraries.load(str(ROOT/f'assets/{kind}_actions.blend'),link=False) as (source,target):target.actions=[name]
  action=target.actions[0]
 return action,info

def _stand(rig,asset):
 name='PV_STAND_'+asset;action=bpy.data.actions.get(name)
 if action:return action,{'frame_start':1,'frame_end':2}
 poses=json.loads((ROOT/'assets/poses.json').read_text(encoding='utf8'))[asset]['STAND']['bones']
 rig.animation_data_clear()
 for pb in rig.pose.bones:
  state=poses[pb.name.split(':')[-1]];pb.rotation_mode='QUATERNION'
  for path in ['location','rotation_quaternion']:
   setattr(pb,path,state[path]);pb.keyframe_insert(data_path=path,frame=1)
 action=rig.animation_data.action;action.name=name;action.use_fake_user=True;rig.animation_data.action=None
 return action,{'frame_start':1,'frame_end':2}

def apply(scene,config):
 items=segments(config);ref=engine.refs(scene);fps=config['fps'];total=Vector((0,0,0));elapsed=0;timeline=[]
 for item in items:
  delta=DIRECTIONS[item['direction']]*item['distance'];timeline.append({**item,'start':elapsed,'from':list(total),'to':list(total+delta)})
  total+=delta;elapsed+=item['duration']
 for actor in ref['actors']:
  rig=bpy.data.objects[actor['rig']];root=bpy.data.objects[actor['root']]
  stand,stand_info=_stand(rig,actor['asset']);rig.animation_data_clear();rig.animation_data_create()
  root.animation_data_clear();start=bpy.data.objects[actor['start']];origin=start.location.copy();yaw=0.
  base_correction=math.radians(180);end=bpy.data.objects[actor['end']];end.location=origin+total
  if not timeline:
   root.location=origin;root.rotation_euler.z=base_correction
  else:
   for item in timeline:
    t0=1+item['start']*fps;t1=min(scene.frame_end,1+(item['start']+item['duration'])*fps)
    delta=Vector(item['to'])-Vector(item['from']);new_yaw=math.atan2(-delta.x,delta.y) if delta.length else yaw
    while new_yaw-yaw>math.pi:new_yaw-=math.tau
    while new_yaw-yaw<-math.pi:new_yaw+=math.tau
    root.location=origin+Vector(item['from']);root.keyframe_insert(data_path='location',frame=t0)
    root.rotation_euler.z=yaw+base_correction;root.keyframe_insert(data_path='rotation_euler',index=2,frame=t0)
    root.rotation_euler.z=new_yaw+base_correction;root.keyframe_insert(data_path='rotation_euler',index=2,frame=min(t1,t0+fps*.15))
    root.location=origin+Vector(item['to']);root.keyframe_insert(data_path='location',frame=t1)
    root.keyframe_insert(data_path='rotation_euler',index=2,frame=t1);yaw=new_yaw
   for fc in engine.action_curves(root):
    for key in fc.keyframe_points:key.interpolation='LINEAR'
  body=[{'action':'stand','start':0,'duration':max(config['duration'],.2),'distance':0}]+timeline
  previous='stand'
  for index,item in enumerate(body):
   kind=item['action'];t0=1+item['start']*fps;t1=min(scene.frame_end,1+(item['start']+item['duration'])*fps)
   if kind=='stop':kind='sit' if previous=='sit' else 'stand'
   if kind=='stand':action,info=stand,stand_info
   else:action,info=_load(kind,actor['asset'])
   track=rig.animation_data.nla_tracks.new();track.name=f'{index:02d} {kind}'
   strip=track.strips.new(kind,int(t0),action)
   if hasattr(strip,'action_slot') and action.slots:strip.action_slot=action.slots[0]
   strip.frame_start=t0;strip.frame_end=max(t0+1,t1);strip.extrapolation='HOLD_FORWARD';strip.blend_type='REPLACE'
   strip.blend_in=0 if index==0 else min(fps*.18,(t1-t0)*.2)
   strip.use_animated_time=True
   period=info['frame_end']-info['frame_start'];first=info['frame_start']
   if kind in {'walk','run'}:
    cycles=item['distance']/info['stride_m'] if item['distance']>0 else item['duration']*info['source_fps']/period
    strip.use_animated_time_cyclic=True;values=(first,first+cycles*period)
   elif item['action']=='stop' and kind=='sit':values=(info['frame_end'],info['frame_end'])
   else:values=(first,info['frame_end'])
   for frame,value in [(t0,values[0]),(max(t0+1,t1),values[1])]:
    strip.strip_time=value;strip.keyframe_insert(data_path='strip_time',frame=frame)
   for fc in strip.fcurves:
    for key in fc.keyframe_points:key.interpolation='LINEAR'
   previous=kind
  root['movement_directions']='Scene axes: forward +Y, backward -Y, left -X, right +X'
 scene['pv_actor_timeline']=json.dumps(timeline,ensure_ascii=False)
 scene.frame_set(1);bpy.context.view_layer.update()
 return total
