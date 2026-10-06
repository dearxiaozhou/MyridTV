"""Contact sheets for inspecting the independently generated replacements."""
import json
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
queue=json.loads((ROOT/'style-preview-unique-queue.json').read_text(encoding='utf-8'))
font=ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',18)
for offset in range(0,len(queue),20):
    sheet=Image.new('RGB',(1200,1400),'#eeeeee')
    draw=ImageDraw.Draw(sheet)
    for index,preset in enumerate(queue[offset:offset+20]):
        x=(index%4)*300
        y=(index//4)*280
        record=ROOT/'style-preview-records'/(preset['id']+'.json')
        if record.exists():
            data=json.loads(record.read_text(encoding='utf-8'))
            if data.get('accepted') is not False:
                with Image.open(data['path']) as original:
                    sheet.paste(ImageOps.contain(original.convert('RGB'),(260,240)),(x+20,y))
        draw.text((x+12,y+244),f"{offset+index+1}. {preset['name']}",font=font,fill='black')
    sheet.save(ROOT/f'verification-unique-style-review-{offset//20+1}.jpg',quality=94)
print('Saved 5 review sheets')
