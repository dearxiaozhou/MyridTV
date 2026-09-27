# -*- coding: utf-8 -*-
"""Browser regression for generation task polling and duplicate request sharing."""
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
      const calls={urls:[], waits:[], dedupe:0, timeout:0, activeSizes:[]};
      const response=(body,ok=true)=>({ok,text:async()=>String(body),json:async()=>body});
      const capture=async promise=>{try{return {value:await promise};}catch(error){return {message:error.message,name:error.name,isPending:error.isPending,options:error.options};}};
      const active=()=>new Map();
      const configure=options=>{
        const polls=active();
        CanvasGenerationTaskPoller.configure({
        activePolls:polls,proxyBase:()=>'',translate:key=>key,wait:async ms=>calls.waits.push(ms),
        fetcher:async url=>{calls.urls.push(url);return response({status:'succeeded',result:{images:['ok']}});},
        newJimengPendingSignal:options=>Object.assign(new Error('queue pending'),{isPending:true,options}),
        ...options
        });
        return polls;
      };

      configure({proxyBase:()=> 'https://proxy.test'});
      const success=await CanvasGenerationTaskPoller.poll('rhproxy_job/1');

      let release;
      let dedupeCalls=0;
      const dedupeActive=active();
      configure({activePolls:dedupeActive,wait:async()=>{},fetcher:async()=>{
        dedupeCalls++;
        await new Promise(resolve=>{release=resolve;});
        return response({status:'succeeded',result:{urls:['shared']}});
      }});
      const first=CanvasGenerationTaskPoller.poll('shared-task');
      const second=CanvasGenerationTaskPoller.poll('shared-task');
      await new Promise(resolve=>setTimeout(resolve,0));
      release();
      const deduped=await Promise.all([first,second]);
      calls.dedupe=dedupeCalls;
      calls.activeSizes.push(dedupeActive.size);

      const failedActive=configure({fetcher:async url=>{calls.urls.push(url);return response({status:'failed',error:'provider failed'});}});
      const failed=await capture(CanvasGenerationTaskPoller.poll('failed-task'));

      const pendingActive=configure({fetcher:async url=>{calls.urls.push(url);return response({
        status:'jimeng_pending',submit_id:'submit-1',kind:'video',queue_info:{position:2},message:'queued'
      });}});
      const pending=await capture(CanvasGenerationTaskPoller.poll('pending-task'));

      const timeoutActive=configure({maxAttempts:2,fetcher:async url=>{calls.timeout++;return response({status:'running'});}});
      const timeout=await capture(CanvasGenerationTaskPoller.poll('slow-task'));

      configure({fetcher:async url=>{calls.urls.push(url);return response('service unavailable',false);}});
      const httpError=await capture(CanvasGenerationTaskPoller.poll('http-task'));

      configure({fetcher:async()=>{throw new Error('must not fetch');}});
      const invalid=await capture(CanvasGenerationTaskPoller.poll(''));
      return {module:typeof CanvasGenerationTaskPoller==='object',success,calls,deduped,failed,pending,timeout,httpError,invalid,
        activeAfter:{failed:failedActive.size,pending:pendingActive.size,timeout:timeoutActive.size}};
    }""")

    check("任务轮询器加载并解析完成结果", result["module"] and result["success"] == {"images":["ok"]}, result["success"])
    check("代理任务走官方代理且任务 ID 安全编码", result["calls"]["urls"][0] == "https://proxy.test/api/canvas-image-tasks/rhproxy_job%2F1", result["calls"]["urls"][:2])
    check("同一任务并发轮询只发出一次请求", result["calls"]["dedupe"] == 1
          and result["deduped"] == [{"urls":["shared"]},{"urls":["shared"]}], result["deduped"])
    check("失败状态保留服务端错误且清理轮询锁", result["failed"]["message"] == "provider failed", result["failed"])
    check("排队状态转为携带提交信息的专用信号", result["pending"]["isPending"] is True
          and result["pending"]["options"] == {"submitId":"submit-1","kind":"video","queueInfo":{"position":2},"message":"queued"}, result["pending"])
    check("任务到达轮询上限后返回超时错误", result["timeout"]["message"] == "smart.errRunTimeout" and result["calls"]["timeout"] == 2, result["timeout"])
    check("失败、排队与超时后都释放共享轮询锁", result["activeAfter"] == {"failed":0,"pending":0,"timeout":0}, result["activeAfter"])
    check("HTTP 与无效任务错误可恢复且无页面脚本异常", result["httpError"]["message"] == "service unavailable"
          and result["invalid"]["message"] == "smart.errRunFailed" and not errors, {"http":result["httpError"],"invalid":result["invalid"],"pageErrors":errors[:3]})
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
