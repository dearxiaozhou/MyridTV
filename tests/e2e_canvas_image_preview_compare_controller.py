# -*- coding: utf-8 -*-
"""Browser regression for image-preview comparison source and panel behavior."""
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright
from e2e_support import record_blocked_write


BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217").rstrip("/")
CHROMIUM = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
VERSION = json.loads(urllib.request.urlopen(BASE + "/health", timeout=10).read())["version"]
results = []
blocked_writes = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + name + (" | " + str(detail)[:300] if detail else ""))


with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/*", lambda route: (
        record_blocked_write(blocked_writes, route.request.method, route.request.url)
        or route.fulfill(status=204, body="")
    ) if route.request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"} else route.continue_())
    page.route("**/static/app_config.json*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))
    page.goto(f"{BASE}/smart-canvas.html?v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    outcome = page.evaluate("""() => {
      const controller=CanvasImagePreviewCompareController;
      const stage=document.getElementById('previewStage');
      const compareImage=document.getElementById('previewCompareImage');
      const compareLayer=document.getElementById('previewCompareLayer');
      const compareHandle=document.getElementById('previewCompareHandle');
      const thumbs=document.getElementById('compareThumbs');
      const toggle=document.getElementById('compareToggleBtn');
      const metas=[]; const toasts=[]; let syncCount=0;
      const editing={image:{kind:'image',url:'/current.png'},node:{id:'node-1',runPrompt:'Detailed test prompt',runInputRefs:[
        {url:'/reference-a.png',kind:'image'},{url:'/reference-a.png',kind:'image'},
        {url:'/reference-video.mp4',kind:'video'},{url:'/reference-b.png',kind:'image'}
      ]}};
      controller.configure({
        getEditing:()=>editing,getNodes:()=>[{id:'source-1',images:[{url:'/fallback.png',kind:'image'},{url:'/fallback.png',kind:'image'},{url:'/fallback-video.mp4',kind:'video'}]}],
        getInputImages:()=>[],mediaKindForItem:item=>item?.kind||'image',getStage:()=>stage,
        getCompareImage:()=>compareImage,getCompareLayer:()=>compareLayer,getCompareHandle:()=>compareHandle,
        getThumbs:()=>thumbs,getToggle:()=>toggle,syncFrameSize:()=>syncCount++,
        updateMetaHint:value=>metas.push(value),translate:key=>({
          'smart.runPromptPrefix':'Prompt: ','smart.panoramaHint':'Panorama',
          'smart.compareHover':'Compare','smart.compareEmpty':'No references',
          'smart.compareCancelTip':'Cancel reference','smart.compareUseTip':'Use reference',
          'smart.compareHintPick':'Choose a reference','smart.compareNoSource':'No reference images'
        }[key]||key),escapeHtml:value=>String(value),toast:value=>toasts.push(value)
      });
      const fromRefs=controller.sources().map(item=>item.url);
      editing.node.runInputRefs=[]; editing.node.sourceNodeId='source-1';
      const fromSourceNode=controller.sources().map(item=>item.url);
      editing.node.runInputRefs=[
        {url:'/reference-a.png',kind:'image'},{url:'/reference-a.png',kind:'image'},
        {url:'/reference-video.mp4',kind:'video'},{url:'/reference-b.png',kind:'image'}
      ];
      controller.refresh('image');
      const available={sources:controller.sources().map(item=>item.url),disabled:toggle.disabled};
      const toggled=controller.toggle();
      const opened={toggled,state:{...controller.getState()},thumbs:thumbs.querySelectorAll('[data-compare-idx]').length,
        image:compareImage.getAttribute('src'),layerVisible:compareLayer.style.display!=='none',handleVisible:compareHandle.style.display!=='none',activeClass:stage.classList.contains('compare-on')};
      thumbs.querySelectorAll('[data-compare-idx]')[1].click();
      const switched={index:controller.getState().index,image:compareImage.getAttribute('src')};
      thumbs.querySelectorAll('[data-compare-idx]')[1].click();
      const deselected={index:controller.getState().index,active:controller.getState().active,hidden:compareLayer.style.display==='none',hint:metas[metas.length-1]};
      controller.refresh('video');
      const video={state:{...controller.getState()},disabled:toggle.disabled,hidden:compareLayer.style.display==='none'};
      controller.refresh('panorama');
      const panorama={state:{...controller.getState()},hidden:compareLayer.style.display==='none',hint:metas[metas.length-1]};
      editing.node.runInputRefs=[]; editing.node.sourceNodeId='missing';
      const noSourceToggle=controller.toggle(); controller.refresh('image');
      const empty={noSourceToggle,disabled:toggle.disabled,state:{...controller.getState()},toast:toasts[0]};
      controller.reset();
      return {fromRefs,fromSourceNode,available,opened,switched,deselected,video,panorama,empty,syncCount};
    }""")

    check("对比来源优先使用已保存输入并按图片类型去重", outcome["fromRefs"] == ["/reference-a.png", "/reference-b.png"], outcome["fromRefs"])
    check("没有保存输入时回退读取来源节点图片", outcome["fromSourceNode"] == ["/fallback.png"], outcome["fromSourceNode"])
    check("有可用参考图时启用对比入口", outcome["available"] == {
        "sources": ["/reference-a.png", "/reference-b.png"], "disabled": False
    }, outcome["available"])
    check("开启对比后默认选中首张并显示滑杆和缩略图", outcome["opened"]["toggled"]
          and outcome["opened"]["state"] == {"active": True, "index": 0}
          and outcome["opened"]["thumbs"] == 2 and outcome["opened"]["image"] == "/reference-a.png"
          and outcome["opened"]["layerVisible"] and outcome["opened"]["handleVisible"]
          and outcome["opened"]["activeClass"], outcome["opened"])
    check("选择另一张缩略图会切换当前对比图", outcome["switched"] == {"index": 1, "image": "/reference-b.png"}, outcome["switched"])
    check("再次点击当前缩略图会保留选择模式并隐藏对比滑杆", outcome["deselected"]["index"] == -1
          and outcome["deselected"]["active"] and outcome["deselected"]["hidden"]
          and "Choose a reference" in outcome["deselected"]["hint"], outcome["deselected"])
    check("视频预览清空对比选择并禁用入口", outcome["video"] == {
        "state": {"active": False, "index": -1}, "disabled": True, "hidden": True
    }, outcome["video"])
    check("全景预览隐藏对比面板并更新提示", outcome["panorama"]["state"]["active"] is False
          and outcome["panorama"]["hidden"] and outcome["panorama"]["hint"] == "Panorama", outcome["panorama"])
    check("没有参考图时拒绝开启并清除过期选择", outcome["empty"]["noSourceToggle"] is False
          and outcome["empty"]["disabled"] and outcome["empty"]["state"] == {"active": False, "index": -1}
          and outcome["empty"]["toast"] == "No reference images", outcome["empty"])
    check("正式服务验收会话没有画布写请求", not blocked_writes, blocked_writes)
    check("画布页面无脚本异常", not errors, errors[:3])

    screenshot = os.environ.get("MYRIDTV_VERIFY_SCREENSHOT")
    if screenshot:
        page.screenshot(path=screenshot, full_page=False)
        print("SCREENSHOT: " + screenshot)
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
