# -*- coding: utf-8 -*-
"""
e2e_canvas_agent_batch_run.py
=============================
守护「Agent 面板执行按钮 = 本条消息创建的节点全部并行生成」语义（2026-09-23 修复）：

旧 bug 两个：
1. [data-agent-run]「执行」按钮调用 canvasAgentExecuteRecentNodes() 漏传 messageId
   → targets 恒空 → 永远 toast「未找到待执行的生成节点」。
2. 批量执行借道 composer 的 runGeneration() 逐个跑：改写 composer 草稿/选中态，
   且会把已有图的节点判成「覆盖重跑」→ 已生成的图被压进历史、新图叠同一节点
   （用户报告：3 个节点不同时跑，用一个节点跑还把图片压历史）。

新实现 canvasAgentBatchRunNodes：各节点用自己的 runPrompt/runPromptRefs 直接
runApiGeneration 并行提交，轮询/回填走 resumeSmartPendingNode（与单节点运行同一路径）。

测试不烧真实配额：window.fetch 打桩（submit 立即返回 task_id、poll 首轮 succeeded），
smartGeneratedOutputItems 打桩为本地假图，moveOutputImagesToHistoryForRun 打桩计数。

断言：
A. 3 个待生成节点 → 恰好 3 个 submit POST，node_id/prompt 各自对应（不是都拿同一个）。
B. 提交前 selectedId 不变；moveOutputImagesToHistoryForRun 调用数 = 0。
C. 带 runPromptRefs 的节点 payload.reference_images 有参考图。
D. 跑完 3 节点都有 generatedResult 图、pendingTasks 清干净。
E. canvasAgentExecuteRecentNodes('msg-id') 按消息 nodeIds 挑目标（msgId 漏传 bug 回归守护）。
F. 已有生成结果图的节点不会被重复执行。

依赖：隔离测试实例 3217
"""
import json, sys
from playwright.sync_api import sync_playwright

import os

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")


def check(label, ok, detail=""):
    sym = "PASS" if ok else "FAIL"
    print(f"{sym} - {label} | {detail}")
    return 1 if ok else 0


SETUP_JS = """
() => {
  // 打桩 fetch：canvas-image-tasks 提交/轮询 + 无关请求放走
  window.__submits = [];
  window.__archiveCalls = 0;
  const realFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = String(typeof input === 'string' ? input : (input && input.url) || '');
    if (url.includes('/api/canvas-image-tasks/')) {
      const taskId = decodeURIComponent(url.split('/api/canvas-image-tasks/')[1]);
      return new Response(JSON.stringify({task_id: taskId, status: 'succeeded', result: {images: ['stub://img_' + taskId + '.png']}}), {status: 200, headers: {'Content-Type':'application/json'}});
    }
    if (url.endsWith('/api/canvas-image-tasks')) {
      let body = {};
      try { body = JSON.parse((init && init.body) || '{}'); } catch(e) {}
      window.__submits.push(body);
      const tid = 'stubtask_' + window.__submits.length;
      return new Response(JSON.stringify({task_id: tid}), {status: 200, headers: {'Content-Type':'application/json'}});
    }
    return realFetch(input, init);
  };
  // 假图回填（避开真实下载/localize）
  window.smartGeneratedOutputItems = async (items, kind, options) => (items || []).map((it, i) => ({
    url: 'http://127.0.0.1:3217/assets/stub_out_' + Date.now() + '_' + i + '.png',
    name: 'stub_' + i + '.png', kind: 'image', generatedResult: true
  }));
  // 归档函数计数（必须 0 次调用）
  const realArchive = window.moveOutputImagesToHistoryForRun;
  window.moveOutputImagesToHistoryForRun = async (images) => { window.__archiveCalls += 1; return new Map(); };
}
"""

MAKE_NODES_JS = """
() => {
  const mk = (id, prompt, withRef) => {
    const node = {
      id: id, type: 'smart-image', title: '测试·' + id, x: 300 + Math.random()*400, y: 300,
      runPrompt: prompt,
      runPromptRefs: withRef ? [{url: '/assets/input/ref_a.png', name: '参考图A', kind: 'image', nodeId: 'src_a', imageIndex: 0}] : [],
      images: withRef ? [{url: '/assets/input/ref_a.png', name: '参考图A', kind: 'image'}] : [],
      runSettings: { engine: 'api', apiKind: 'image', provider_id: 'openai', model: 'gpt-image-test', count: 1, ratio: 'landscape43', resolution: '2k', quality: 'medium' },
      status: 'pending', role: 'generation', __origin: 'agent_tool_generation'
    };
    nodes.push(node);
    return node.id;
  };
  const ids = [
    mk('agent_test_n1', '提示词一号·红色狐耳少女', false),
    mk('agent_test_n2', '提示词二号·蓝色渡鸦少年', true),
    mk('agent_test_n3', '提示词三号·雨夜霓虹街景', false)
  ];
  render();
  return ids;
}
"""


def main():
    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
            headless=True,
            args=["--no-sandbox"],
        )
        ctx = browser.new_context(viewport={"width": 1680, "height": 980})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        def rc(route):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"proxy": {"base_url": BASE}}))

        page.route("**/static/app_config.json*", rc)
        page.goto(f"{BASE}/smart-canvas.html", wait_until="networkidle")
        page.wait_for_timeout(1500)

        page.evaluate(SETUP_JS)
        ids = page.evaluate(MAKE_NODES_JS)

        # === 核心批量执行：直接调 canvasAgentBatchRunNodes（消息路由在 E 步单独守护） ===
        page.evaluate("""(ids) => {
            window.__batchPromise = canvasAgentBatchRunNodes(ids.map(id => nodes.find(n => n.id === id)));
        }""", ids)
        page.wait_for_timeout(6000)
        result = page.evaluate("() => window.__batchPromise.then ? window.__batchPromise : null")
        # Promise 已在等待期内 resolve，evaluate 取回不了同一对象；改为读状态断言
        state = page.evaluate("""(ids) => {
            const ns = ids.map(id => nodes.find(n => n.id === id));
            return {
              submits: window.__submits.map(s => ({nid: s.node_id, prompt: (s.prompt||'').slice(0,20), refs: (s.reference_images||[]).length})),
              submitCount: window.__submits.length,
              archiveCalls: window.__archiveCalls,
              nodes: ns.map(n => ({id: n.id, gen: (n.images||[]).some(i => i.generatedResult), pendingTasks: (n.pendingTasks||[]).length, apiRunning: !!n.apiRunning})),
              selectedId: (typeof selectedId !== 'undefined') ? selectedId : null
            };
        }""", ids)

        subs = state["submits"]
        by_node = {s["nid"]: s for s in subs}
        failures += not check("3 个节点各自并行提交（submit 数=3）", state["submitCount"] == 3, json.dumps(subs, ensure_ascii=False))
        cn = ["一", "二", "三"]
        failures += not check("每个节点 node_id 与 prompt 一一对应（不是都拿同一提示词）",
                      all(f"agent_test_n{i}" in by_node and by_node[f"agent_test_n{i}"]["prompt"].startswith(f"提示词{cn[i-1]}") for i in (1,2,3)),
                      json.dumps(by_node, ensure_ascii=False))
        failures += not check("带参考图的节点提交带 reference_images", by_node.get("agent_test_n2", {}).get("refs", 0) >= 1, str(by_node.get("agent_test_n2")))
        failures += not check("批量执行不触发历史归档（moveOutputImagesToHistoryForRun=0）", state["archiveCalls"] == 0, str(state["archiveCalls"]))
        ok_nodes = [n for n in state["nodes"] if n["gen"] and n["pendingTasks"] == 0 and not n["apiRunning"]]
        failures += not check("3 节点回填成功且清 pending 状态", len(ok_nodes) == 3, json.dumps(state["nodes"], ensure_ascii=False))
        failures += not check("批量执行不改写选中态(selectedId 未被逐个占用)", state["selectedId"] in ("", None), str(state["selectedId"]))

        # === E. 消息路由回归：canvasAgentExecuteRecentNodes 必须按 messageId 找到本条消息的 nodeIds ===
        route = page.evaluate("""() => {
            const spyTargets = [];
            const realBatch = canvasAgentBatchRunNodes;
            window.canvasAgentBatchRunNodes = async (targets) => { spyTargets.push(targets.map(t => t.id)); return {ok:0, failed:0}; };
            canvasAgentMessagesState.push({id:'agent_msg_test_route', role:'assistant', text:'测试', nodeIds:['agent_test_n1','agent_test_n2','agent_test_n3']});
            return canvasAgentExecuteRecentNodes('agent_msg_test_route').then(() => {
                window.canvasAgentBatchRunNodes = realBatch;
                return spyTargets;
            });
        }""")
        # 现在 3 个节点都已有生成结果图 → F 步先断言“已出图不可再执行”，再重置一个跑路由断言
        # （路由本身仍会把 3 个 id 传进来吗？targets 经 canvasAgentPendingGenNode 过滤后应为空）
        failures += not check("已有生成结果图的节点不会被「执行」重复触发（targets 过滤为空即早退）",
                      route == [] or route == [[]], json.dumps(route))

        # 重置 n3 为待生成，验证路由把 n3 挑出来
        reset = page.evaluate("""() => {
            const n3 = nodes.find(n => n.id === 'agent_test_n3');
            n3.images = [];
            const spyTargets = [];
            const realBatch = canvasAgentBatchRunNodes;
            window.canvasAgentBatchRunNodes = async (targets) => { spyTargets.push(targets.map(t => t.id)); return {ok:0, failed:0}; };
            return canvasAgentExecuteRecentNodes('agent_msg_test_route').then(() => {
                window.canvasAgentBatchRunNodes = realBatch;
                canvasAgentMessagesState.pop();
                return {spy: spyTargets, total: spyTargets.reduce((a,b)=>a+b.length,0)};
            });
        }""")
        failures += not check("传 messageId 后按本条消息 nodeIds 路由目标节点",
                      reset.get("spy") == [["agent_test_n3"]], json.dumps(reset, ensure_ascii=False))

        real_errors = [e for e in errors if "WebSocket" not in e and "stats" not in e]
        failures += not check("无 JS 报错", len(real_errors) == 0, str(real_errors[:3]))

        browser.close()

    total = 9
    passed = total - failures
    print(f"\nRESULT: {passed}/{total}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
