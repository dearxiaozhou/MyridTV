"""Offline endpoint previs plugin. Host injects storage, cancellation and logging."""
import copy
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import importlib.util
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote,unquote,urlsplit

ROOT = Path(__file__).resolve().parent
RENDER_LOCK = threading.Lock()
PRESETS = ['01_慢镜头感','02_慢推进','08_中景跟拍','14_慢速拉出','19_横移','21_吊臂上升','22_吊臂下降','30_180度环绕']

@lru_cache(maxsize=1)
def motion_model():
    spec=importlib.util.spec_from_file_location('offline_camera_motion_model',ROOT/'tygg_previs/motion_model.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def metadata():
    library=motion_model().catalog()
    return {'id':'offline-previs','version':'2.0.0','name':'运镜动画预设',
            'available':(ROOT/'offline_previs_cli.py').is_file(),
            'camera_presets':PRESETS,'character_assets':['x_bot','y_bot'],
            'default_spec':json.loads((ROOT/'default-shot.json').read_text(encoding='utf8')),
            'motion_presets':library['presets'],'default_motion':motion_model().defaults(),
            'motion_library':{'kept_count':library['kept_count'],'removed_count':library['removed_count']}}


def web_asset(name):
    if name not in {'plugin.js','plugin.css'}:
        raise ValueError('未知插件资源')
    source='motion.js' if name=='plugin.js' else name
    return (ROOT/'web'/source).read_bytes(), ('text/javascript; charset=utf-8' if name.endswith('.js') else 'text/css; charset=utf-8')


def resolve_blender(configured):
    override=os.environ.get('MYRIDTV_OFFLINE_PREVIS_BLENDER','').strip()
    if override and Path(override).is_file():
        return override
    candidates=[]
    if configured and Path(configured).is_file():
        candidates.append(Path(configured))
    roots=[Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Blender Foundation']
    roots += [Path(letter+':/blender') for letter in 'CDEFGHIJKLMNOPQRSTUVWXYZ']
    for root in roots:
        if root.is_dir():
            candidates.extend(root.glob('*/blender.exe'))
    def version(path):
        found=re.search(r'(\d+)\.(\d+)(?:\.(\d+))?',path.parent.name)
        return tuple(int(x or 0) for x in found.groups()) if found else (0,0,0)
    if candidates:
        return str(max(candidates,key=version))
    return shutil.which('blender') or configured or 'blender'


def run(payload, *, assets_dir, blender_bin, ratio_size, folder_name, cancelled, log):
    motion=payload.get('previz_output')=='motion'
    spec=motion_model().validate(payload.get('offline_motion_spec')) if motion else copy.deepcopy(payload.get('offline_previs_spec'))
    if not motion and (not isinstance(spec,dict) or spec.get('schema_version')!='1.0'):
        raise ValueError('请先打开“起落幅设置”保存镜头参数')
    if len(json.dumps(spec))>200000:
        raise ValueError('镜头参数过大')
    if not motion and spec.get('camera',{}).get('preset') not in PRESETS:
        raise ValueError('请选择插件支持的约束相机')
    if not motion and (not isinstance(spec.get('actors'),list) or not 1<=len(spec['actors'])<=2):
        raise ValueError('本插件支持1至2个人物')
    for actor in spec.get('actors',[]):
        if actor.get('asset') not in {'x_bot','y_bot'}:
            raise ValueError('未知机器人资产')
    spec['resolution']=list(ratio_size(payload.get('aspectRatio')))
    if not motion:spec['id']='CanvasEndpoints'
    name=folder_name(payload.get('canvas_title') or '离线预演',payload.get('canvas_id') or '')
    run_id=('motion_' if motion else 'offline_')+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]
    assets_dir=Path(assets_dir)
    output=assets_dir/'output'/name/'previs_data'/run_id
    output.mkdir(parents=True)
    input_file=output/'input.json'
    input_file.write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf8')
    command=[resolve_blender(blender_bin),'--background','--factory-startup','--python-exit-code','1',
             '--python',str(ROOT/('motion_previs_cli.py' if motion else 'offline_previs_cli.py')),'--','--spec',str(input_file),'--output',str(output)]
    if motion:
        previous=unquote(urlsplit(str(payload.get('offline_motion_previous') or '')).path)
        if previous.startswith('/assets/'):
            candidate=(assets_dir/previous[len('/assets/'):]).resolve()
            if candidate.is_relative_to((assets_dir/'output'/name).resolve()) and candidate.name=='previs.blend' and candidate.is_file():
                command+=['--previous-blend',str(candidate)]
        encoder=shutil.which('ffmpeg')
        if encoder:command+=['--ffmpeg',encoder]
    with RENDER_LOCK:
        if cancelled():
            raise RuntimeError('预演已停止')
        started=time.monotonic()
        with (output/'render.log').open('w',encoding='utf8') as stream:
            process=subprocess.Popen(command,cwd=str(ROOT),stdout=stream,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                while process.poll() is None:
                    if cancelled():
                        raise RuntimeError('预演已停止')
                    if time.monotonic()-started>300:
                        raise RuntimeError('离线预演超过5分钟，已停止')
                    time.sleep(.25)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=10)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
        if process.returncode:
            detail=(output/'render.log').read_text(encoding='utf8',errors='replace')[-1500:]
            log('offline-previs failed: '+detail)
            raise RuntimeError('离线预演失败，请检查镜头参数或本地Blender。'+detail[-350:])
    for file in (['preview.mp4','poster.png','previs.blend','shot.json','checks.json'] if motion else ['start.png','end.png','previs.blend','shot.json','checks.json']):
        if not (output/file).is_file():
            raise RuntimeError('预演结果不完整：'+file)
    checks=json.loads((output/'checks.json').read_text(encoding='utf8'))
    if checks.get('errors'):
        raise RuntimeError('起落幅约束检查未通过')
    def url(file):
        return '/assets/'+quote((output/file).relative_to(assets_dir).as_posix(),safe='/')
    log('offline-previs completed: '+run_id)
    if motion:
        return {'backend':'blender-motion-presets','plugin':'offline-previs','plugin_version':'2.0.0',
            'images':[{'url':url('preview.mp4'),'name':run_id+'.mp4','kind':'video','display_name':next(p['name'] for p in motion_model().catalog()['presets'] if p['id']==spec['preset'])}],
            'video_url':url('preview.mp4'),'previs_blend_url':url('previs.blend'),'previs_data_url':url('shot.json'),
            'validation_url':url('checks.json'),'poster_url':url('poster.png'),'motion_preset':spec['preset'],
            'validation':checks,'output_kind':'video','duration_seconds':round(round(spec['duration']*spec['fps'])/spec['fps'],3),'pushed_by_plugin':False}
    return {'backend':'blender-offline-endpoints','plugin':'offline-previs','plugin_version':'1.0.0',
        'images':[{'url':url(file),'name':run_id+'_'+file,'kind':'image',
                   'display_name':label} for file,label in [('start.png','起幅'),('end.png','落幅')]],
        'previs_blend_url':url('previs.blend'),'previs_data_url':url('shot.json'),
        'validation_url':url('checks.json'),'validation':checks,
        'output_kind':'image','pushed_by_plugin':False}
