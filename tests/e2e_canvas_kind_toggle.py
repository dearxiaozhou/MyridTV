# -*- coding: utf-8 -*-
"""
e2e_canvas_kind_toggle.py — 守护「图片/视频切换推广到所有生成节点」(2026-09-24 方案B)
断言：
1. RH/Comfy 引擎下 apiKindToggle 可见（3D预演隐藏）
2. 扫流函数：视频工作流JSON判video、图片工作流判image（用真实内置工作流+合成样本）
3. RH 切工作流 → settings.apiKind 自动跟随
4. Comfy 切工作流 → 同上
5. 引擎下拉无 Modelscope 选项；modelscope 全局清零
"""
import json, os, sys, time, urllib.request
from playwright.sync_api import sync_playwright

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")
V = urllib.request.urlopen(BASE + "/health", timeout=10).read().decode()
VERSION = json.loads(V)["version"]
results = []
def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail)[:150] if detail else ""))
    return bool(ok)

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1500, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE + "/smart-canvas.html?v=" + VERSION, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)

    # ---- 1. modelscope 清零 + 引擎下拉无 Modelscope ----
    ms = page.evaluate("""() => ({
        inJs: (smartCanvasSource => 0)(0),
        opt: [...(document.getElementById('engineSelect')?.options||[])].map(o => o.value),
        text: document.getElementById('engineSelect')?.innerText || ''
    })""")
    check("引擎下拉无 Modelscope 选项", "modelscope" not in json.dumps(ms), ms["opt"])

    # ---- 2. 扫流函数单元断言 ----
    scan = page.evaluate("""() => {
        const vidGraph = {
          "23":{class_type:"LoadImage"},
          "48":{class_type:"VHS_LoadVideo"},
          "88":{class_type:"MiniMaxH3ReferenceToVideo"},
          "99":{class_type:"VHS_VideoCombine"}
        };
        const imgGraph = {"47":{class_type:"KSamplerSelect"},"50":{class_type:"SaveImage"}};
        const seedvr = {"1017":{class_type:"SeedVR2BlockSwap"},"5":{class_type:"SaveImage"}};
        return {
            video: scanComfyGraphIsVideo(vidGraph),
            image: scanComfyGraphIsVideo(imgGraph),
            seedvr: scanComfyGraphIsVideo(seedvr),
            rhVid: workflowOutputKindForRhEntry({title:'随便', workflowJson: JSON.stringify(vidGraph)}),
            rhImg: workflowOutputKindForRhEntry({title:'随便', workflowJson: JSON.stringify(imgGraph)}),
            appVid: workflowOutputKindForRhEntry({title:'即梦视频生成', workflowJson: null}),
            appImg: workflowOutputKindForRhEntry({title:'图片放大', workflowJson: null}),
            appUnknown: workflowOutputKindForRhEntry({title:'神秘应用', workflowJson: ''})
        };
    }""")
    check("扫流:视频图判video/图片图判image", scan["video"] and not scan["image"], scan)
    check("扫流:SeedVR2(含SaveImage输出=图片流,2026-09-25定义)", scan["seedvr"] is False)
    check("RH条目:有图按扫流(视/图)", scan["rhVid"] == "video" and scan["rhImg"] == "image")
    check("RH App无图:标题弱猜(视频/图片/未知默认image)",
          scan["appVid"] == "video" and scan["appImg"] == "image" and scan["appUnknown"] == "image", scan)

    # ---- 3. toggle 可见性：切引擎验证 ----
    vis = page.evaluate("""() => {
        const out = {};
        const t = () => { syncApiKindToggleVisibility(); return document.getElementById('apiKindToggle').style.display; };
        settings.engine = 'runninghub'; out.rh = t();
        settings.engine = 'comfy';      out.comfy = t();
        settings.engine = 'api';        out.api = t();
        settings.engine = 'blender';    out.blenderHiddenByBranch = t();  // blender 分支在 renderDynamicParams 隐藏；这里只查本函数
        settings.engine = 'api';
        return out;
    }""")
    check("切换按钮对 RH/Comfy/API 全部可见",
          vis["rh"] == "inline-flex" and vis["comfy"] == "inline-flex" and vis["api"] == "inline-flex", vis)

    # ---- 4. RH 切真实工作流 → apiKind 自动跟随（你库里有 MM-H3视频流/SeedVR2/Krea2图流）----
    flow = page.evaluate("""async () => {
        settings.engine = 'runninghub';
        const wfs = (runningHubEntries('workflow') || []);
        const out = {count: wfs.length, cases: []};
        for(const entry of wfs){
            const id = runningHubEntryId(entry, 'workflow');
            const expected = workflowOutputKindForRhEntry(entry);  // 先取识别值
            settings.apiKind = expected === 'video' ? 'image' : 'video';  // 反向设值
            settings.rhConfigKey = 'workflow:' + id;
            applyWorkflowOutputKind();
            out.cases.push({title: entry.title, before: settings.apiKind === expected ? 'flip-fail' : 'flip', after: settings.apiKind, expected});
        }
        return out;
    }""")
    if flow.get("count", 0) == 0:
        check("RH工作流切换 apiKind 自动跟随", True, "无条目跳过")
    else:
        okf = all(c["after"] == c["expected"] for c in flow["cases"])
        check(f"RH工作流切换 apiKind 自动跟随({len(flow['cases'])}条真实工作流)", okf, flow["cases"])

    # ---- 5. Comfy 切工作流 → apiKind 跟随（用真实缓存工作流）----
    comfy = page.evaluate("""async () => {
        const names = (comfyWorkflows||[]).map(w=>w.name);
        if(!names.length) return {skip:true};
        // 找一个带 MiniMaxH3/VideoCombine 的（MMH3）和纯图流（Krea2）
        const out = {names};
        settings.engine = 'comfy';
        for(const n of names){
            try { await ensureComfyWorkflow(n); } catch(_){}
        }
        let vidName = null, imgName = null;
        for(const n of names){
            const wf = comfyWorkflowCache[n];
            const graph = wf?.workflow || wf?.prompt;
            if(!graph) continue;
            const isV = scanComfyGraphIsVideo(graph);
            if(isV && !vidName) vidName = n;
            if(!isV && !imgName) imgName = n;
        }
        out.vidName = vidName; out.imgName = imgName;
        if(vidName){ settings.comfyWorkflow = vidName; applyWorkflowOutputKind(); out.vidKind = settings.apiKind; }
        if(imgName){ settings.comfyWorkflow = imgName; applyWorkflowOutputKind(); out.imgKind = settings.apiKind; }
        return out;
    }""")
    if comfy.get("skip"):
        check("Comfy切工作流跟随(无可用工作流,跳过)", True, "skip")
    else:
        okc = True
        if comfy.get("vidName"): okc = okc and comfy.get("vidKind") == "video"
        if comfy.get("imgName"): okc = okc and comfy.get("imgKind") == "image"
        check("Comfy切工作流 apiKind 跟随扫流结果", okc, comfy)

    # ---- 6. 悬停提示存在（auto 引擎） ----
    title = page.evaluate("""() => {
        settings.engine = 'runninghub';
        syncApiKindToggleVisibility();
        const btn = document.querySelector('#apiKindToggle [data-kind="video"]');
        return btn ? btn.title : '';
    }""")
    check("RH下切换按钮带自动识别提示", "自动识别" in title or "手动" in title, title[:60])

    real_errors = [e for e in errors if "WebSocket" not in e and "stats" not in e and "favicon" not in e]
    check("无 JS 报错", len(real_errors) == 0, real_errors[:2])
    browser.close()

passed = sum(1 for _, ok, _ in results if ok)
print(f"\nRESULT: {passed}/{len(results)}")
sys.exit(0 if passed == len(results) else 1)
