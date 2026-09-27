# -*- coding: utf-8 -*-
"""Browser regression for generated-media and task-result normalization."""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright


import os

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")
CHROMIUM = r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"
VERSION = json.loads(urllib.request.urlopen(BASE + "/health", timeout=10).read())["version"]
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + name + (" | " + str(detail)[:300] if detail else ""))


with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/static/app_config.json*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))
    page.goto(f"{BASE}/smart-canvas.html?v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    result = page.evaluate("""() => {
      const normalized=CanvasGenerationResultModel.resultMediaUrls({
        outputs:[
          {url:'/assets/a.png',kind:'image',name:'A'},
          {path:'/assets/b.mp4',type:'video',filename:'B'},
          '/assets/a.png'
        ],
        result:{video_url:'/assets/c.mp4'}
      });
      return {
        module:typeof CanvasGenerationResultModel==='object',
        normalized,
        taskIds:CanvasGenerationResultModel.taskIdsFromResult({
          taskIds:[' job-1 ','job-2'],task_ids:['job-2','job-3'],task_id:'job-4',taskId:'job-5'
        }),
        kinds:{
          image:CanvasGenerationResultModel.mediaKindForUrls(['/assets/a.png']),
          video:CanvasGenerationResultModel.mediaKindForUrls(['/assets/a.mp4']),
          audio:CanvasGenerationResultModel.mediaKindForUrls(['/assets/a.wav']),
          text:CanvasGenerationResultModel.mediaKindForUrls(['/assets/a.json']),
          explicit:CanvasGenerationResultModel.mediaKindForUrls(['/assets/a.png'],'video')
        }
      };
    }""")

    normalized_urls = [item["url"] if isinstance(item, dict) else item for item in result["normalized"]]
    check("生成结果模型加载并递归读取输出对象", result["module"]
          and normalized_urls == ["/assets/a.png", "/assets/b.mp4", "/assets/c.mp4"], result["normalized"])
    check("重复 URL 只保留一次且对象元数据保留", len(result["normalized"]) == 3
          and result["normalized"][0]["kind"] == "image"
          and result["normalized"][0]["name"] == "A"
          and result["normalized"][1]["kind"] == "video", result["normalized"])
    check("任务 ID 跨字段去重并清理空白", result["taskIds"] == ["job-1", "job-2", "job-3", "job-4", "job-5"], result["taskIds"])
    check("常见媒体 URL 分类正确", result["kinds"] == {
        "image":"image", "video":"video", "audio":"audio", "text":"text", "explicit":"video"
    }, result["kinds"])
    check("媒体与任务结果归一化无页面脚本异常", not errors, errors[:3])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
