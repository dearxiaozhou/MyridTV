# -*- coding: utf-8 -*-
"""Browser regression for bounded cascade round scheduling and failure cleanup."""
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

    result = page.evaluate("""async () => {
      CanvasCascadeRoundScheduler.configure({
        shouldStop:state=>Boolean(state?.stopRequested),
        isStoppedError:error=>Boolean(error?.smartCascadeStopped)
      });
      const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
      const concurrent={active:0,max:0,finished:[]};
      await CanvasCascadeRoundScheduler.runWithLimit([0,1,2,3,4,5],3,async round=>{
        concurrent.active++;
        concurrent.max=Math.max(concurrent.max,concurrent.active);
        await sleep(round%2?4:2);
        concurrent.finished.push(round);
        concurrent.active--;
      });

      const serial=[];
      await CanvasCascadeRoundScheduler.runWithLimit([1,2,3],1,async round=>serial.push(round));

      const stopState={stopRequested:false};
      const stopped=[];
      await CanvasCascadeRoundScheduler.runWithLimit([1,2,3,4],1,async round=>{
        stopped.push(round);
        if(round===2) stopState.stopRequested=true;
      },stopState);

      const cancellation=[];
      await CanvasCascadeRoundScheduler.runWithLimit([0,1,2],1,async round=>{
        cancellation.push(round);
        throw Object.assign(new Error('user stop'),{smartCascadeStopped:true});
      });

      let releaseOther;
      const assigned=[];
      let otherFinished=false;
      let schedulerSettled=false;
      let schedulerError='';
      const failedRun=CanvasCascadeRoundScheduler.runWithLimit([0,1,2,3],2,async round=>{
        assigned.push(round);
        if(round===0){await Promise.resolve();throw new Error('generation failed');}
        await new Promise(resolve=>{releaseOther=resolve;});
        otherFinished=true;
      }).then(()=>{schedulerSettled=true;},error=>{schedulerSettled=true;schedulerError=error.message;});
      await sleep(10);
      const waitedForActive= !schedulerSettled;
      const assignedBeforeRelease=[...assigned];
      releaseOther();
      await failedRun;

      let emptyCalls=0;
      await CanvasCascadeRoundScheduler.runWithLimit([],4,async()=>emptyCalls++);
      return {
        module:typeof CanvasCascadeRoundScheduler==='object',concurrent,serial,stopped,cancellation,
        failure:{assignedBeforeRelease,waitedForActive,otherFinished,schedulerError},emptyCalls
      };
    }""")

    check("调度器加载且并行数不超过上限", result["module"] and result["concurrent"]["max"] == 3
          and result["concurrent"]["active"] == 0, result["concurrent"])
    check("并行轮次全部且仅运行一次", sorted(result["concurrent"]["finished"]) == [0,1,2,3,4,5]
          and len(set(result["concurrent"]["finished"])) == 6, result["concurrent"]["finished"])
    check("串行上限保持原始轮次顺序", result["serial"] == [1,2,3], result["serial"])
    check("收到停止标记后不再分派新轮次", result["stopped"] == [1,2], result["stopped"])
    check("专用停止信号结束调度而不当作失败", result["cancellation"] == [0], result["cancellation"])
    check("失败阻止后续轮次但等待在途轮次完成", result["failure"] == {
        "assignedBeforeRelease":[0,1],"waitedForActive":True,"otherFinished":True,"schedulerError":"generation failed"
    }, result["failure"])
    check("空轮次不调用任务执行器", result["emptyCalls"] == 0, result["emptyCalls"])
    check("级联调度流程无页面脚本异常", not errors, errors[:3])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
