"""blender --background --factory-startup --python THIS -- --spec shot.json --output result/"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from tygg_previs import engine


def main():
    args=argparse.ArgumentParser(description="Standalone offline endpoint previs")
    args.add_argument("--spec",required=True)
    args.add_argument("--output",required=True)
    parsed=args.parse_args(sys.argv[sys.argv.index("--")+1:])
    spec=json.loads(Path(parsed.spec).read_text(encoding="utf-8"))
    scene=engine.build(spec)
    output=engine.export(scene,parsed.output)
    print(json.dumps({"status":"exported","output":str(output),"version":engine.VERSION,
                      "build_seconds":scene["pv_build_seconds"]},ensure_ascii=False))


if __name__=="__main__":
    main()
