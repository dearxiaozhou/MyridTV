# -*- coding: utf-8 -*-
"""Node layout controller browser regression: align, size, spacing and groups."""
import json
import sys
from playwright.sync_api import sync_playwright

import os

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")
CHROMIUM = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} - {label} | {detail}")
    return 0 if ok else 1


def main():
    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM, headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1680, "height": 980})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route_config(route):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"proxy": {"base_url": BASE}}))

        page.route("**/static/app_config.json*", route_config)
        page.goto(f"{BASE}/smart-canvas.html", wait_until="networkidle")
        page.wait_for_timeout(1200)
        loaded = page.evaluate("""typeof CanvasNodeLayoutController === 'object'
            && typeof CanvasNodeLayoutController.handleToolAction === 'function'
            && typeof CanvasNodeLayoutController.ungroupNode === 'function'""")
        failures += check("节点分组布局控制器加载", loaded)

        page.evaluate("""() => {
            const item=(id,x,y,w,h)=>({id,type:'smart-image',title:id,x,y,w,h,scale:1,status:'ready',role:'media',created_at:Date.now(),
                images:[{url:'/assets/input/ref_test.png',name:id+'.png',kind:'image',generatedResult:true,natural_w:512,natural_h:512}]});
            nodes.push(item('layout_a',100,100,120,90),item('layout_b',360,300,180,120),item('layout_c',700,520,140,100));
            selectedIds=['layout_a','layout_b','layout_c'];selectedId='';render();
        }""")
        page.wait_for_timeout(300)

        page.evaluate("handleSmartNodeToolAction('align-left')")
        xs = page.evaluate("['layout_a','layout_b','layout_c'].map(id=>nodes.find(n=>n.id===id).x)")
        failures += check("左对齐统一节点 x 坐标", len(set(xs)) == 1, str(xs))

        page.evaluate("handleSmartNodeToolAction('align-top')")
        ys = page.evaluate("['layout_a','layout_b','layout_c'].map(id=>nodes.find(n=>n.id===id).y)")
        failures += check("顶对齐统一节点 y 坐标", len(set(ys)) == 1, str(ys))

        page.evaluate("""() => {
            const byId=id=>nodes.find(n=>n.id===id);
            byId('layout_a').x=100;byId('layout_a').y=100;
            byId('layout_b').x=360;byId('layout_b').y=100;
            byId('layout_c').x=700;byId('layout_c').y=100;render();
        }""")
        ref_size = page.evaluate("nodeRect(nodes.find(n=>n.id==='layout_a'))")
        page.evaluate("handleSmartNodeToolAction('same-size')")
        sizes = page.evaluate("['layout_a','layout_b','layout_c'].map(id=>nodeRect(nodes.find(n=>n.id===id))).map(r=>[r.width,r.height])")
        expected = [ref_size["width"], ref_size["height"]]
        failures += check("统一尺寸使用首节点尺寸", all(size == expected for size in sizes), str(sizes))

        page.evaluate("""() => {
            const a=nodes.find(n=>n.id==='layout_a'),b=nodes.find(n=>n.id==='layout_b'),c=nodes.find(n=>n.id==='layout_c');
            a.x=100;b.x=360;c.x=700;a.y=b.y=c.y=100;render();
        }""")
        page.evaluate("handleSmartNodeToolAction('distribute-horizontal')")
        horizontal = page.evaluate("['layout_a','layout_b','layout_c'].map(id=>{const n=nodes.find(x=>x.id===id),r=nodeRect(n);return{x:n.x,w:r.width}})")
        h_gaps = [horizontal[i+1]["x"]-(horizontal[i]["x"]+horizontal[i]["w"]) for i in range(2)]
        failures += check("水平等距保持相邻节点间距", h_gaps[0] == h_gaps[1], str(horizontal))

        page.evaluate("""() => {
            const a=nodes.find(n=>n.id==='layout_a'),b=nodes.find(n=>n.id==='layout_b'),c=nodes.find(n=>n.id==='layout_c');
            a.y=100;b.y=330;c.y=650;a.x=b.x=c.x=100;render();
        }""")
        page.evaluate("handleSmartNodeToolAction('distribute-vertical')")
        vertical = page.evaluate("['layout_a','layout_b','layout_c'].map(id=>{const n=nodes.find(x=>x.id===id),r=nodeRect(n);return{y:n.y,h:r.height}})")
        v_gaps = [vertical[i+1]["y"]-(vertical[i]["y"]+vertical[i]["h"]) for i in range(2)]
        failures += check("垂直等距保持相邻节点间距", v_gaps[0] == v_gaps[1], str(vertical))

        page.evaluate("""() => {selectedIds=['layout_a','layout_b'];selectedId='';render();handleSmartNodeToolAction('group');}""")
        group = page.evaluate("nodes.filter(n=>n.type==='smart-group').map(n=>({id:n.id,members:n.memberIds}))")
        failures += check("打组创建分组并记录成员", any({'layout_a','layout_b'} <= set(item['members']) for item in group), str(group))

        page.evaluate("""() => {
            nodes.push({id:'legacy_image_group',type:'smart-image',title:'Group',x:980,y:420,w:260,h:180,scale:.8,
                images:[{url:'/assets/input/a.png',name:'a.png',kind:'image',natural_w:512,natural_h:512},
                        {url:'/assets/input/b.png',name:'b.png',kind:'image',natural_w:512,natural_h:512}]});
            render();
        }""")
        before_count = page.evaluate("nodes.length")
        ungrouped = page.evaluate("CanvasNodeLayoutController.ungroupNode('legacy_image_group')")
        after = page.evaluate("({count:nodes.length,old:nodes.some(n=>n.id==='legacy_image_group'),selected:selectedIds.length,created:nodes.filter(n=>n.id!=='legacy_image_group'&&n.type==='smart-image').length})")
        failures += check("拆分图片组生成图片节点", ungrouped and not after["old"] and after["count"] == before_count + 1 and after["selected"] == 2, str(after))

        real_errors = [error for error in errors if "WebSocket" not in error and "stats" not in error]
        failures += check("无 JS 报错", not real_errors, str(real_errors[:3]))
        browser.close()

    total = 9
    print(f"\nRESULT: {total - failures}/{total}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
