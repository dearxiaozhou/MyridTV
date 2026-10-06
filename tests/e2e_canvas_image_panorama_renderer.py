# -*- coding: utf-8 -*-
"""Browser regression for the panorama WebGL renderer lifecycle."""
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

    outcome = page.evaluate("""async () => {
      const module = CanvasImagePanoramaRenderer;
      const created = {renderers:0, scenes:0, cameras:0, geometries:0, materials:0, textures:0, renders:0, loads:0, ready:0, disposedTextures:0, raf:0, canceled:[]};
      const images = [];
      class FakeImage {
        constructor(){ this.complete=false; this.naturalWidth=0; this.naturalHeight=0; images.push(this); }
        set src(value){ this._src=value; }
        get src(){ return this._src; }
      }
      class FakeTexture {
        constructor(image){ this.image=image; created.textures++; }
        dispose(){ created.disposedTextures++; }
      }
      class FakeVector3 { constructor(x,y,z){ this.x=x; this.y=y; this.z=z; } }
      class FakeCamera {
        constructor(fov,aspect){ created.cameras++; this.fov=fov; this.aspect=aspect; this.position={set:(x,y,z)=>{this.positionValue=[x,y,z];}}; }
        updateProjectionMatrix(){ this.projectionUpdated=true; }
        lookAt(target){ this.target=[target.x,target.y,target.z]; }
      }
      class FakeRenderer {
        constructor(options){ created.renderers++; this.options=options; }
        setPixelRatio(value){ this.pixelRatio=value; }
        setSize(w,h,update){ this.size=[w,h,update]; }
        render(){ created.renders++; }
      }
      class FakeScene { constructor(){ created.scenes++; this.children=[]; } add(item){ this.children.push(item); } }
      class FakeGeometry { constructor(){ created.geometries++; } scale(x,y,z){ this.scaleValue=[x,y,z]; } }
      class FakeMaterial { constructor(value){ created.materials++; Object.assign(this,value); } }
      class FakeMesh { constructor(geometry,material){ this.geometry=geometry; this.material=material; } }
      const fakeThree={
        WebGLRenderer:FakeRenderer, Scene:FakeScene, PerspectiveCamera:FakeCamera,
        SphereGeometry:FakeGeometry, MeshBasicMaterial:FakeMaterial, Mesh:FakeMesh, Texture:FakeTexture,
        Vector3:FakeVector3, MathUtils:{degToRad:value=>value*Math.PI/180}, SRGBColorSpace:'srgb'
      };
      const originalImage=window.Image;
      const originalRaf=window.requestAnimationFrame;
      const originalCancel=window.cancelAnimationFrame;
      const rafCallbacks=new Map();
      let nextRaf=1;
      window.Image=FakeImage;
      window.requestAnimationFrame=callback=>{ const id=nextRaf++; rafCallbacks.set(id,callback); created.raf++; return id; };
      window.cancelAnimationFrame=id=>{ created.canceled.push(id); rafCallbacks.delete(id); };
      const stage=document.getElementById('panoramaStage');
      const canvas=document.getElementById('panoramaCanvas');
      canvas.width=640; canvas.height=320;
      const view={enabled:true,fov:82,yaw:35,pitch:14};
      module.configure({
        getCanvas:()=>canvas, getStage:()=>stage, getViewState:()=>view,
        getFallbackSource:()=>'/fallback.png', loadThree:async()=>{created.loads++; return fakeThree;},
        onReady:()=>{created.ready++;}, toast:()=>{}, translate:key=>key
      });
      try {
        const firstEnsure=await module.ensure();
        const secondEnsure=await module.ensure();
        const initialized=module.getState();
        const initial={firstEnsure,secondEnsure,rendererCount:created.renderers,sceneCount:created.scenes,cameraCount:created.cameras,loadCount:created.loads};

        const pending=module.load('/primary.png',true);
        await new Promise(resolve=>setTimeout(resolve,0));
        const primary=images[0];
        primary.onerror();
        await new Promise(resolve=>setTimeout(resolve,0));
        const fallback=images[1];
        fallback.naturalWidth=2048; fallback.naturalHeight=1024; fallback.complete=true;
        fallback.onload();
        await pending;
        const loaded={imageSource:fallback.src,loadedSrc:initialized.loadedSrc,texture:Boolean(initialized.texture),imageMatches:initialized.image===fallback,ready:created.ready,stageReady:stage.classList.contains('ready')};

        const drawResult=module.drawFrame();
        const frame={drawResult,renders:created.renders,cameraFov:initialized.camera.fov,cameraAspect:initialized.camera.aspect,projectionUpdated:initialized.camera.projectionUpdated,target:initialized.camera.target};
        module.start();
        const firstRaf=initialized.animationId;
        const callback=rafCallbacks.get(firstRaf);
        rafCallbacks.delete(firstRaf);
        callback();
        const loop={started:firstRaf>0,nextFrame:initialized.animationId>firstRaf,renderCount:created.renders};
        module.stop();
        const stopped={animationId:initialized.animationId,canceled:created.canceled.slice()};

        const stalePending=module.load('/stale.png',false);
        await new Promise(resolve=>setTimeout(resolve,0));
        const stale=images[2];
        const tokenBeforeDispose=initialized.loadToken;
        module.dispose();
        stale.naturalWidth=100; stale.naturalHeight=50; stale.onload();
        await stalePending;
        const invalidated={tokenAdvanced:initialized.loadToken>tokenBeforeDispose,loadedSrc:initialized.loadedSrc,image:initialized.image,texture:initialized.texture,disposeCount:created.disposedTextures};
        return {initial,loaded,frame,loop,stopped,invalidated,created};
      } finally {
        window.Image=originalImage;
        window.requestAnimationFrame=originalRaf;
        window.cancelAnimationFrame=originalCancel;
        module.dispose();
      }
    }""")

    check("渲染器可重复确保初始化且只创建一套场景", outcome["initial"] == {
        "firstEnsure": True, "secondEnsure": True, "rendererCount": 1,
        "sceneCount": 1, "cameraCount": 1, "loadCount": 1
    }, outcome["initial"])
    check("主图加载失败后会尝试备用图并进入就绪状态", outcome["loaded"] == {
        "imageSource": "/fallback.png", "loadedSrc": "/fallback.png", "texture": True,
        "imageMatches": True, "ready": 1, "stageReady": True
    }, outcome["loaded"])
    check("画面绘制使用当前视角和画布宽高比", outcome["frame"]["drawResult"]
          and outcome["frame"]["renders"] == 1 and outcome["frame"]["cameraFov"] == 82
          and outcome["frame"]["cameraAspect"] == 2 and outcome["frame"]["projectionUpdated"]
          and len(outcome["frame"]["target"]) == 3, outcome["frame"])
    check("动画循环能持续请求下一帧并在停止时取消", outcome["loop"]["started"]
          and outcome["loop"]["nextFrame"] and outcome["loop"]["renderCount"] == 2
          and outcome["stopped"]["animationId"] == 0
          and outcome["stopped"]["canceled"] == [2], {"loop": outcome["loop"], "stopped": outcome["stopped"]})
    check("释放时使尚未完成的旧图片失效并释放纹理", outcome["invalidated"]["tokenAdvanced"]
          and outcome["invalidated"]["loadedSrc"] == ""
          and outcome["invalidated"]["image"] is None
          and outcome["invalidated"]["texture"] is None
          and outcome["invalidated"]["disposeCount"] == 1, outcome["invalidated"])
    check("页面没有脚本异常", not errors, errors[:3])
    check("验收会话没有画布写请求", not blocked_writes, blocked_writes)

    screenshot = os.environ.get("MYRIDTV_VERIFY_SCREENSHOT")
    if screenshot:
        page.screenshot(path=screenshot, full_page=False)
        print("SCREENSHOT: " + screenshot)
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
