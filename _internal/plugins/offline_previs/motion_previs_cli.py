"""Blender background CLI for named camera-animation presets."""
import sys,argparse,json
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
from tygg_previs import motion_engine

parser=argparse.ArgumentParser()
parser.add_argument('--spec',required=True);parser.add_argument('--output',required=True)
parser.add_argument('--previous-blend');parser.add_argument('--ffmpeg')
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
existing=None
if args.previous_blend:
 bpy.ops.wm.open_mainfile(filepath=args.previous_blend,load_ui=False,use_scripts=False)
 if bpy.context.scene.get('pv_motion_owned'):existing=bpy.context.scene
value=json.loads(Path(args.spec).read_text(encoding='utf8'))
scene=motion_engine.build(value,existing=existing)
checks=motion_engine.export(scene,args.output,args.ffmpeg)
print(json.dumps({'status':'exported','mode':'motion','output':str(Path(args.output).resolve()),'camera_keys':checks['camera_action_keys']},ensure_ascii=False))
