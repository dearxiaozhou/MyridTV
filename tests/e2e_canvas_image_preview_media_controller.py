# -*- coding: utf-8 -*-
"""Browser regression for preview metadata and video frame navigation."""
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright


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
        blocked_writes.append({"method": route.request.method, "url": route.request.url})
        or route.fulfill(status=204, body="")
    ) if route.request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"} else route.continue_())
    page.route("**/static/app_config.json*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))
    page.goto(f"{BASE}/smart-canvas.html?v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    outcome = page.evaluate("""async () => {
      const controller=CanvasImagePreviewMediaController;
      const hint=document.getElementById('previewMetaHint');
      const image={};
      const editing={image,node:{}};
      let modalOpen=false, saves=0, kind='video';
      const listeners=new Map();
      const video={
        readyState:2,duration:10,currentTime:1,videoWidth:1920,videoHeight:1080,pauseCount:0,
        pause(){this.pauseCount++;},
        addEventListener(name,fn){const list=listeners.get(name)||[];list.push(fn);listeners.set(name,list);},
        removeEventListener(name,fn){listeners.set(name,(listeners.get(name)||[]).filter(item=>item!==fn));},
        dispatch(name){for(const fn of [...(listeners.get(name)||[])]) fn();}
      };
      let currentImage={naturalWidth:1280,naturalHeight:720};
      let cropImage={naturalWidth:640,naturalHeight:480};
      controller.configure({
        getEditing:()=>editing,isModalOpen:()=>modalOpen,getCurrentImage:()=>currentImage,
        getCurrentVideo:()=>video,getCropImage:()=>cropImage,getMetaHint:()=>hint,
        mediaKindForItem:()=>kind,translate:key=>key==='smart.resolution'?'Resolution':key,
        scheduleSave:()=>saves++
      });
      const currentOutside=controller.currentVideo();
      modalOpen=true;
      const currentInside=controller.currentVideo()===video;
      editing.image={kind:'video',fps:24};
      const step24=controller.frameStep();
      const moved=controller.seekFrames(1);
      const afterForward={currentTime:video.currentTime,pauseCount:video.pauseCount};
      video.currentTime=9.99;
      const clamped=controller.seekFrames(1);
      const afterClamp=video.currentTime;
      video.readyState=0; const notReady=controller.seekFrames(-1);
      video.readyState=2; video.currentTime=0; controller.seekFrames(-1); const atStart=video.currentTime;
      editing.image={kind:'video',fps:240}; const stepMax=controller.frameStep();
      editing.image={kind:'video',fps:0}; const stepDefault=controller.frameStep();

      editing.image={kind:'video'};
      const videoResolution=controller.resolutionText();
      controller.updateMetaHint('Video preview');
      const videoHint=hint.textContent;
      currentImage={naturalWidth:0,naturalHeight:0}; video.videoWidth=0; video.videoHeight=0;
      const cropResolution=controller.resolutionText();
      controller.updateMetaHint();
      const retainedHint=hint.textContent;
      controller.updateMetaHint(''); const clearedHint=hint.textContent;

      editing.image={kind:'video'}; video.videoWidth=1920; video.videoHeight=1080;
      const remembered=controller.rememberResolution();
      const rememberedImage={...editing.image,saves};
      const noDuplicateSave=controller.rememberResolution();

      const eventWait=controller.waitForEvent(video,'seeked',80);
      video.dispatch('seeked'); await eventWait;
      const listenerRemoved=(listeners.get('seeked')||[]).length===0;
      const noSeek=await controller.seekForFrame(video,video.currentTime+0.001);
      const seekPromise=controller.seekForFrame(video,5);
      const targetTime=video.currentTime;
      video.dispatch('seeked');
      const didSeek=await seekPromise;
      return {currentOutside,currentInside,step24,moved,afterForward,clamped,afterClamp,notReady,atStart,stepMax,stepDefault,
        videoResolution,videoHint,cropResolution,retainedHint,clearedHint,remembered,rememberedImage,noDuplicateSave,
        listenerRemoved,noSeek,didSeek,targetTime,finalSaves:saves};
    }""")

    check("视频节点只在编辑器打开时返回预览视频", not outcome["currentOutside"] and outcome["currentInside"], outcome)
    check("视频帧率计算支持元数据并将极端帧率限制到 120", abs(outcome["step24"]-1/24)<1e-9 and abs(outcome["stepMax"]-1/120)<1e-9,
          {"24fps":outcome["step24"],"max":outcome["stepMax"]})
    check("缺省或无效帧率按 30fps 处理", abs(outcome["stepDefault"]-1/30)<1e-9, outcome["stepDefault"])
    check("逐帧前进会暂停视频并更新当前时间", outcome["moved"] and abs(outcome["afterForward"]["currentTime"]-(1+1/24))<1e-9
          and outcome["afterForward"]["pauseCount"] == 1, outcome["afterForward"])
    check("逐帧导航不会超过视频末尾且未就绪时不操作", outcome["clamped"]
          and abs(outcome["afterClamp"]-(10-1/48))<1e-9 and not outcome["notReady"] and outcome["atStart"] == 0,
          {"end":outcome["afterClamp"],"notReady":outcome["notReady"],"start":outcome["atStart"]})
    check("分辨率提示优先使用视频尺寸并保留附加提示", outcome["videoResolution"] == "Resolution: 1920 x 1080"
          and outcome["videoHint"] == "Resolution: 1920 x 1080 · Video preview", outcome["videoHint"])
    check("视频尺寸缺失时回退到裁剪图尺寸", outcome["cropResolution"] == "Resolution: 640 x 480", outcome["cropResolution"])
    check("不传附加提示时保留上次内容，传空值时清空", outcome["retainedHint"] == "Resolution: 640 x 480 · Video preview"
          and outcome["clearedHint"] == "Resolution: 640 x 480", {"retained":outcome["retainedHint"],"cleared":outcome["clearedHint"]})
    check("读取媒体尺寸后仅在需要时写回并触发保存", outcome["remembered"]
          and outcome["rememberedImage"] == {"kind":"video","natural_w":1920,"natural_h":1080,"saves":1}
          and not outcome["noDuplicateSave"] and outcome["finalSaves"] == 1, outcome["rememberedImage"])
    check("等待视频事件后移除监听并按目标时间寻帧", outcome["listenerRemoved"] and not outcome["noSeek"]
          and outcome["didSeek"] and outcome["targetTime"] == 5, outcome)

    refresh = page.evaluate("""() => {
      const controller=CanvasImagePreviewMediaController;
      const attrs={};
      const image={style:{},dataset:{},complete:false,naturalWidth:0,naturalHeight:0,
        onload:null,onerror:null,
        getAttribute(name){return attrs[name] ?? null;},
        removeAttribute(name){delete attrs[name];},
        set src(value){attrs.src=String(value);},get src(){return attrs.src || '';}};
      const videoAttrs={};
      const video={style:{},readyState:2,videoWidth:320,videoHeight:180,duration:4,
        onloadedmetadata:null,onloadeddata:null,pauseCount:0,loadCount:0,
        pause(){this.pauseCount++;},load(){this.loadCount++;},
        getAttribute(name){return videoAttrs[name] ?? null;},
        removeAttribute(name){delete videoAttrs[name];},
        set src(value){videoAttrs.src=String(value);},get src(){return videoAttrs.src || '';}};
      const classes=new Map();
      const toggle={style:{},classList:{toggle(name,value){classes.set(name,Boolean(value));}}};
      const editing={image:{kind:'image',url:'https://media.test/a.png'},node:{}};
      const compareModes=[],frames=[];
      const hint={textContent:''};
      let token=1,panorama=false,saves=0,syncs=0,fallbacks=0;
      controller.configure({
        getEditing:()=>editing,getCurrentImage:()=>image,getCurrentVideo:()=>video,getCropImage:()=>null,
        getMetaHint:()=>hint,getPanoramaToggle:()=>toggle,isPanoramaEnabled:()=>panorama,getLoadToken:()=>token,
        getCompareController:()=>({refresh:mode=>compareModes.push(mode)}),
        displayMediaUrl:item=>'display:'+item.url,proxiedMediaUrl:item=>{fallbacks++;return 'proxy:'+item.url;},
        syncFrameSize:()=>syncs++,requestAnimationFrame:callback=>frames.push(callback),
        mediaKindForItem:item=>item?.kind || 'image',translate:key=>key==='smart.resolution'?'Resolution':key,
        scheduleSave:()=>saves++
      });
      controller.refreshCurrentMedia();
      const staleLoad=image.onload;
      image.onerror(); image.onerror();
      const fallbackSrc=image.src;
      token++;
      staleLoad();
      const staleIgnored=syncs===0 && saves===0;
      editing.image={kind:'video',url:'https://media.test/a.mp4'};
      controller.refreshCurrentMedia();
      frames.shift()?.();
      const videoActivated=image.style.display==='none' && video.style.display==='block'
        && video.src==='display:https://media.test/a.mp4' && compareModes.at(-1)==='video';
      const videoRemembered=editing.image.natural_w===320 && editing.image.natural_h===180 && saves===1;
      editing.image={kind:'image',url:'https://media.test/a.png'};
      panorama=true;
      controller.refreshCurrentMedia();
      return {fallbackSrc,fallbacks,staleIgnored,videoActivated,videoRemembered,panoramaHidden:image.style.display==='none'
        && compareModes.at(-1)==='panorama',pauseCount:video.pauseCount,loadCount:video.loadCount,
        compareModes,syncs,hint:hint.textContent,toggleDisplay:toggle.style.display,classes:Object.fromEntries(classes)};
    }""")
    check("图片加载失败只回退一次，过期加载不会更新预览", refresh["fallbackSrc"] == "proxy:https://media.test/a.png"
          and refresh["fallbacks"] == 1 and refresh["staleIgnored"], refresh)
    check("切换到视频会隐藏图片、载入视频源并记住尺寸", refresh["videoActivated"] and refresh["videoRemembered"]
          and refresh["pauseCount"] >= 1 and refresh["loadCount"] >= 2, refresh)
    check("全景预览接管时隐藏普通图片并通知比较面板", refresh["panoramaHidden"]
          and refresh["compareModes"] == ["image", "video", "panorama"], refresh)
    check("正式服务验收会话没有画布写请求", not blocked_writes, blocked_writes)
    check("画布页面无脚本异常", not errors, errors[:3])

    screenshot = os.environ.get("MYRIDTV_VERIFY_SCREENSHOT")
    if screenshot:
        page.screenshot(path=screenshot, full_page=False)
        print("SCREENSHOT: " + screenshot)
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
