"""Pure parameter/catalog contract; no Blender, host or agent dependency."""
import copy,json,math
from pathlib import Path

ROOT=Path(__file__).resolve().parent
VERSION='2.1.0'
FRAMINGS=[('wide','大全景'),('full','全景'),('medium','中景'),('close','近景'),('detail','特写')]
ALIASES={
 '02':('推近','push','distance'), '03':('摇镜揭示','pan','angle'),
 '08':('跟随','follow','distance'), '09':('穿梭','generic','distance'),
 '10':('漂浮升移','generic','distance'), '11':('希区柯克变焦','dolly_zoom','distance'),
 '14':('拉远','pull','distance'), '16':('上摇','tilt_up','angle'),
 '17':('下摇','tilt_down','angle'), '18':('水平摇镜','pan','angle'),
 '19':('横移','lateral','distance'), '20':('渐进横移','lateral_fast','distance'),
 '21':('升高','crane_up','distance'), '22':('降低','crane_down','distance'),
 '25':('第一人称行进','first_person','distance'), '26':('遮挡揭示','reveal','distance'),
 '27':('穿飞','generic','distance'), '29':('窥视推进','push','distance'),
 '30':('环绕','orbit','angle')}
PRIMARY=['02','14','19','30','21','22','08']

def catalog():
 data=json.loads((ROOT/'assets/motion_catalog.json').read_text(encoding='utf8'))
 presets=[]
 for record in data['presets']:
  if not record['keep']:continue
  name,kind,unit=ALIASES[record['id'][:2]]
  presets.append({'id':record['id'],'name':name,'source_name':record['name'],'kind':kind,'amount_type':unit,
    'direction':kind in {'lateral','lateral_fast','orbit','pan'},'primary':record['id'][:2] in PRIMARY,
    'default_pace':'accelerate' if kind=='lateral_fast' else 'smooth','source_path':record['cameras'][0]['path']})
 presets.sort(key=lambda p:(PRIMARY.index(p['id'][:2]) if p['primary'] else 99,p['id']))
 return {'version':VERSION,'presets':presets,'removed':[r for r in data['presets'] if not r['keep']],
         'kept_count':len(presets),'removed_count':data['removed_count'],'source_sha256':data['source_sha256']}

def defaults():
 return {'schema_version':'motion/1.0','preset':'02_慢推进','duration':4,'framing':'full',
         'lens_mm':50,'amount':None,'subject':'x_bot','direction':'left','pace':'preset',
         'composition':'center','pose':'STAND','end_framing':'auto','fps':24,'resolution':[960,540],
         'actions':[], 'target_start':'auto','target_end':'same','target_motion':'follow','view':'front','focus_subject':'first','travel_reference':'subject'}

def validate(value):
 if not isinstance(value,dict):raise ValueError('缺少运镜设置')
 result={**defaults(),**copy.deepcopy(value)}
 if result['schema_version']!='motion/1.0':raise ValueError('运镜参数版本不支持')
 entries={p['id']:p for p in catalog()['presets']}
 if result['preset'] not in entries:raise ValueError('请选择有实际运动的相机预设')
 for key,lo,hi,label in [('duration',1,30,'时长'),('lens_mm',18,135,'焦距')]:
  v=result[key]
  if type(v) not in {int,float} or not math.isfinite(v) or not lo<=v<=hi:
   raise ValueError(f'{label}应在{lo}至{hi}之间')
 if result['amount'] is not None:
  if type(result['amount']) not in {int,float} or not math.isfinite(result['amount']) or result['amount']<=0:
   raise ValueError('运动幅度应为正数，留空则自动计算')
  maximum=(360 if entries[result['preset']]['kind']=='orbit' else 180) if entries[result['preset']]['amount_type']=='angle' else 20
  if result['amount']>maximum:raise ValueError('运动幅度过大')
 if result['framing'] not in dict(FRAMINGS) or result['end_framing'] not in ['auto']+list(dict(FRAMINGS)):
  raise ValueError('景别无效')
 if result['subject'] not in {'x_bot','y_bot','both'}:raise ValueError('请选择主体')
 if result['pose'] not in {'STAND','WALK','RUN','SIT'}:raise ValueError('姿态无效')

 if result['direction'] not in {'left','right'}:raise ValueError('方向无效')
 if result['pace'] not in {'preset','smooth','linear','accelerate','decelerate'}:raise ValueError('节奏无效')
 if result['composition'] not in {'center','left','right'}:raise ValueError('构图无效')
 if type(result['fps']) is not int or not 12<=result['fps']<=30:raise ValueError('帧率应在12至30之间')
 if not isinstance(result['resolution'],list) or len(result['resolution'])!=2 or any(type(v)is not int or not 64<=v<=1920 for v in result['resolution']):
  raise ValueError('预览尺寸无效')
 parts={'auto','head','chest','hips','feet'}
 if result['target_start'] not in parts or result['target_end'] not in parts|{'same'}:raise ValueError('请选择起镜和结束时拍摄的部位')
 if result['target_motion'] not in {'follow','fixed'} or result['view'] not in {'front','back','left','right'}:raise ValueError('拍摄方位无效')
 if result['travel_reference'] not in {'subject','scene'}:raise ValueError('机位移动参照无效')
 if result['focus_subject'] not in {'first','second'}:raise ValueError('拍摄主体无效')
 segments=result['actions']
 if not isinstance(segments,list) or len(segments)>12:raise ValueError('动作组合最多12段')
 elapsed=0;previous='stand';clean=[]
 for index,segment in enumerate(segments):
  if not isinstance(segment,dict):raise ValueError('动作设置无效')
  item={**{'action':'stand','duration':1,'distance':0,'direction':'forward'},**segment}
  if item['action'] not in {'stand','walk','run','stop','sit','stand_up'}:raise ValueError('未知主体动作')
  if item['direction'] not in {'forward','backward','left','right'}:raise ValueError('主体移动方向无效')
  for key,lo,hi in [('duration',.2,30),('distance',0,50)]:
   if type(item[key]) not in {int,float} or not math.isfinite(item[key]) or not lo<=item[key]<=hi:raise ValueError('每段动作时长至少0.2秒，移动距离应为0至50米')
  if item['action'] not in {'walk','run'} and item['distance']!=0:raise ValueError('只有走路和跑步可填写移动距离')
  if item['action']=='stand_up' and previous!='sit':raise ValueError('起身之前请先添加坐下动作')
  if previous=='sit' and item['action'] not in {'sit','stand_up','stop'}:raise ValueError('坐下后请先起身再走跑')
  if item['action']!='stop':previous=item['action']
  elapsed+=item['duration'];clean.append(item)
 if elapsed>result['duration']+.00001:raise ValueError('动作总时长超过镜头时长，请缩短动作或增加镜头时长')
 result['actions']=clean
 return result
