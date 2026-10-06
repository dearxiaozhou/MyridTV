"""Install accepted generated originals and build the local preview URL map."""
import json
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
records=json.loads((ROOT/'style-preview-generation-v0820.json').read_text(encoding='utf-8'))
records.extend(json.loads(p.read_text(encoding='utf-8')) for p in sorted((ROOT/'style-preview-records').glob('*.json')))
target=ROOT/'_internal/static/images/styles/generated'
target.mkdir(parents=True,exist_ok=True)
assets={}
for record in records:
    if not record.get('path') or record.get('accepted') is False:
        continue
    path=Path(record['path'])
    if not path.is_file():
        raise FileNotFoundError(path)
    destination=target/(record['id']+'.png')
    shutil.copyfile(path,destination)
    assets[record['id']]='/static/images/styles/generated/'+destination.name
assignments=json.loads((ROOT/'style-preview-assignments.json').read_text(encoding='utf-8'))
assignments={style:style for style in assignments}
missing=sorted(set(assignments.values())-assets.keys())
if missing:
    raise ValueError('Missing accepted previews: '+', '.join(missing))
(ROOT/'style-preview-assignments.json').write_text(json.dumps(assignments,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
previews={style:assets[cover] for style,cover in assignments.items()}
(ROOT/'_internal/static/js/canvas-style-preview-assets.js').write_text('/* Independently generated style previews. */\nwindow.CanvasStylePreviewAssets=Object.freeze('+json.dumps(previews,ensure_ascii=False,indent=2)+');\n',encoding='utf-8')
print(f'Installed {len(assets)} generated assets for {len(previews)} styles')
