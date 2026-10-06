# -*- coding: utf-8 -*-
"""Browser regression for Agent message rendering and interaction bindings."""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright
from e2e_support import record_blocked_write


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
    blocked_writes = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/static/app_config.json*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))
    def guard(route):
        if route.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            record_blocked_write(blocked_writes, route.request.method, route.request.url, as_url=True)
            route.abort()
        else:
            route.continue_()
    page.route("**/*", guard)
    page.goto(f"{BASE}/smart-canvas.html?v={VERSION}", wait_until="domcontentloaded")
    page.wait_for_timeout(900)

    result = page.evaluate("""async () => {
      const host=document.createElement('div');
      host.id='agent-view-test-host';
      host.style.cssText='height:120px;overflow:auto';
      document.body.appendChild(host);
      const input=document.createElement('textarea');
      const calls={preview:[],run:[],brainstorm:[],copy:[],edit:[],cancel:0,resend:[],quote:[],locate:[],locateSpecific:[],receipts:[],send:0,resize:0,posts:[],refresh:0,created:[],saved:[],toasts:[],titles:0,icons:0};
      const brainstorm={id:'brainstorm-msg',role:'assistant',text:'候选',brainstormCard:{candidates:[{title:'一'},{title:'二'}]}};
      const plan={id:'plan-msg',role:'assistant',text:'计划',actionPlan:{steps:[{type:'create'}]}};
      const plain={id:'plain-msg',role:'assistant',text:'普通回复'};
      const undo={id:'undo-msg',role:'assistant',toolTrace:{items:[{ok:true,batchId:'batch-7'}]}};
      const user={id:'user-choice',role:'user',chosenId:'option-2'};
      let messages=[brainstorm,user,plan,plain,undo];
      let chosenMap={};
      const markup=message=>{
        const card=`<div class="canvas-agent-ic" data-ic-intent="choose"><button class="canvas-agent-ic-opt" data-ic-card="card-1" data-ic-select="option-3"><span class="canvas-agent-ic-opt-label">选项三</span></button></div>`+
          `<div class="canvas-agent-ic" data-ic-intent="collect"><input data-ic-field="name" value="Myrid"/><button data-ic-card="card-2" data-ic-submit>提交</button></div>`+
          `<div class="canvas-agent-ic" data-ic-intent="confirm"><button data-ic-card="card-3" data-ic-submit data-ic-action="继续"><span class="canvas-agent-ic-opt-label">确认继续</span></button></div>`;
        let actions='';
        if(message.id==='brainstorm-msg') actions='<button data-bs-pick="pick-1" data-bs-title="候选一"></button><button data-bs-refresh></button><button data-bs-run="brainstorm-msg"></button><button data-agent-quick="create" data-agent-message="brainstorm-msg"></button>';
        if(message.id==='plan-msg') actions='<button data-agent-preview-plan="plan-msg"></button><button data-agent-run="plan-msg"></button><button data-agent-edit="plan-msg"></button><button data-agent-quote="plan-msg"></button><div class="canvas-agent-edit-box"><textarea data-agent-editing-textarea="plan-msg" value="编辑后"></textarea><button data-agent-edit-send="plan-msg"></button><button data-agent-edit-cancel></button></div>';
        if(message.id==='plain-msg') actions='<button data-agent-run="plain-msg"></button><button data-agent-copy="复制文本"></button><button data-agent-locate="plain-msg"></button><button data-agent-suggest="材质" data-agent-message="plain-msg"></button><button data-agent-suggest="节点" data-agent-action="locate_node" data-agent-node="node-3" data-agent-message="plain-msg"></button>';
        if(message.id==='undo-msg') actions='<button data-agent-quick="undo" data-agent-message="undo-msg"></button><button data-agent-quick="quote" data-agent-message="undo-msg"></button><button data-agent-quick="locate" data-agent-message="undo-msg"></button><button data-agent-quick="run" data-agent-message="undo-msg"></button>';
        return `<section class="canvas-agent-message" data-agent-message-id="${message.id}" style="height:160px">${actions}${message.id==='plan-msg'?card:''}</section>`;
      };
      CanvasAgentMessageViewController.configure({
        getContainer:()=>host,getWelcomeTemplate:()=>'<div class="canvas-agent-welcome">欢迎</div>',
        getMessages:()=>messages,setChosenMap:value=>{chosenMap=value;},renderMessage:markup,
        refreshHeadTitle:()=>calls.titles++,
        previewActionPlan:(value,id)=>calls.preview.push({id,steps:value?.steps?.length||0}),
        executeRecentNodes:id=>calls.run.push(id),
        sendBrainstormChoice:(...args)=>calls.brainstorm.push(args),runBrainstormNodes:id=>calls.brainstorm.push(['run',id]),
        copyMessageText:value=>calls.copy.push(value),editMessage:id=>calls.edit.push(id),cancelEditMessage:()=>calls.cancel++,
        resendEditedMessage:(...args)=>calls.resend.push(args),quoteMessageText:value=>calls.quote.push(value),
        locateMessageNode:value=>calls.locate.push(value),locateSpecificNode:(...args)=>calls.locateSpecific.push(args),
        submitInteractionReceipt:value=>calls.receipts.push(JSON.parse(JSON.stringify(value))),
        getInput:()=>input,resizeInput:()=>calls.resize++,sendMessage:()=>calls.send++,toast:message=>calls.toasts.push(message),
        fetcher:async(url,options)=>{calls.posts.push({url,options:JSON.parse(options.body)});return {ok:true,json:async()=>({ok:true,undone_ops:2})};},
        renderAgain:()=>CanvasAgentMessageViewController.render(),refreshAfterUndo:async()=>calls.refresh++,
        createBrainstormNodes:(...args)=>{calls.created.push(args);return [1,2];},saveReplyAsTextNode:value=>calls.saved.push(value),
        refreshIcons:()=>calls.icons++
      });
      renderCanvasAgentMessages();
      const initial={chosenMap:{...chosenMap},welcome:host.querySelector('.canvas-agent-welcome')!==null,
        scrollTop:host.scrollTop,titleCalls:calls.titles,iconCalls:calls.icons,messageCount:host.querySelectorAll('.canvas-agent-message').length};
      const click=selector=>host.querySelector(selector)?.click();
      click('[data-agent-preview-plan]'); click('[data-agent-run="plan-msg"]'); click('[data-agent-run="plain-msg"]');
      click('[data-bs-pick]'); click('[data-bs-refresh]'); click('[data-bs-run]');
      click('[data-agent-copy]'); click('[data-agent-edit]'); click('[data-agent-quote]'); click('[data-agent-locate]');
      click('[data-agent-suggest="材质"]'); click('[data-agent-suggest="节点"]');
      click('[data-ic-select]'); click('[data-ic-submit][data-ic-card="card-2"]'); click('[data-ic-submit][data-ic-card="card-3"]');
      const editBox=host.querySelector('textarea[data-agent-editing-textarea]');
      editBox.value='更新后的文字'; editBox.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',ctrlKey:true,bubbles:true}));
      editBox.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
      click('[data-agent-edit-send]'); click('[data-agent-edit-cancel]');
      click('[data-agent-quick="create"]'); click('[data-agent-quick="undo"]');
      click('[data-agent-quick="quote"]'); click('[data-agent-quick="locate"]'); click('[data-agent-quick="run"]');
      await new Promise(resolve=>setTimeout(resolve,10));
      const afterUndo={undone:undo.undone===true,posts:calls.posts,refresh:calls.refresh,toasts:[...calls.toasts]};
      messages=[]; renderCanvasAgentMessages();
      const emptyWelcome=host.querySelector('.canvas-agent-welcome')?.textContent||'';
      return {module:typeof CanvasAgentMessageViewController==='object',initial,calls,afterUndo,emptyWelcome};
    }""")

    calls = result["calls"]
    check("消息视图控制器加载并渲染空欢迎态", result["module"] and result["emptyWelcome"] == "欢迎", result["emptyWelcome"])
    check("重绘保留选择映射、滚到底部并刷新标题图标", result["initial"]["chosenMap"] == {"brainstorm-msg":"option-2"}
          and result["initial"]["scrollTop"] > 0 and result["initial"]["titleCalls"] == 1
          and result["initial"]["iconCalls"] == 1 and result["initial"]["messageCount"] == 5, result["initial"])
    check("计划预览与运行入口按消息类型分流", calls["preview"] == [{"id":"plan-msg","steps":1},{"id":"plan-msg","steps":1}]
          and "plain-msg" in calls["run"] and "undo-msg" in calls["run"], {"preview":calls["preview"],"run":calls["run"]})
    check("头脑风暴选择、刷新与运行动作有对应回调", calls["brainstorm"] == [["pick","pick-1","候选一"],["refresh"],["run","brainstorm-msg"]], calls["brainstorm"])
    check("交互卡片提交选择、表单字段和确认状态", len(calls["receipts"]) == 3
          and calls["receipts"][0]["selection"] == "option-3"
          and calls["receipts"][1]["fields"] == {"name":"Myrid"}
          and calls["receipts"][2]["confirmed"] is True, calls["receipts"])
    check("建议、编辑、引用、定位和复制动作正确转发", calls["send"] == 1 and calls["resize"] == 1
          and calls["locateSpecific"] == [["node-3","plain-msg"]]
          and calls["resend"] == [["plan-msg","更新后的文字"],["plan-msg","更新后的文字"]]
          and calls["cancel"] == 2 and calls["copy"] == ["复制文本"]
          and calls["quote"] == ["plan-msg","undo-msg"] and calls["locate"] == ["plain-msg","undo-msg"], calls)
    check("快捷操作撤销批次、刷新状态并提供反馈", result["afterUndo"]["undone"]
          and result["afterUndo"]["posts"] == [{"url":"/api/canvas-agent-undo-batch","options":{"batch_id":"batch-7"}}]
          and result["afterUndo"]["refresh"] == 1 and "已撤销 2 项操作" in result["afterUndo"]["toasts"], result["afterUndo"])
    check("头脑风暴快捷保存创建独立候选节点", calls["created"] == [[[{"title":"一"},{"title":"二"}],""]], calls["created"])
    check("Agent 消息交互没有脚本异常或真实写请求", not errors and not blocked_writes, {"errors":errors[:3],"blockedWrites":blocked_writes})
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
