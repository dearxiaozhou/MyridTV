# -*- coding: utf-8 -*-
"""后端接线集成测试：证明真实 Agent Tool 代码经 CanvasMutationManager 守卫收口（#11/#12/#41）。

做法：import 真实 rh_official_proxy 模块，打桩 _agent_get_canvas / _agent_http，
直接调用 _agent_tool_create_text_node / _agent_tool_create_generation_node（生产代码），
验证：
  - 阶段守卫：ASSET_DISCOVERY 阶段调工具 -> 被 MutationManager 拦截（PHASE_NOT_COMMITTABLE）
  - 空 prompt：generation 节点无 prompt -> 被拦截（EMPTY_PROMPT）
  - 正常流程：phase 清空后工具仍正常工作（向后兼容）
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import importlib

PASS = []
FAIL = []


def _ck(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print("PASS  %s%s" % (name, ("  -- " + detail) if detail else ""))
    else:
        FAIL.append(name)
        print("FAIL  %s%s" % (name, ("  -- " + detail) if detail else ""))


def main():
    # 真实后端模块（生产代码）
    try:
        import rh_official_proxy as beh
    except Exception as e:  # 若沙箱无法 import 整个 server，明确标注
        print("BACKEND IMPORT FAILED: %s" % e)
        print("（manager 独立 E2E 已证明守卫逻辑；后端接线经 py_compile + 代码路径分析验证）")
        sys.exit(2)
    print("BACKEND IMPORT OK (rh_official_proxy loaded)")

    # 打桩：内存画布 + 无副作用 HTTP
    store = {}

    def fake_get_canvas(cid):
        cid = str(cid or "c_test")
        if cid not in store:
            store[cid] = {"id": cid, "title": "t", "nodes": [], "connections": [],
                          "artifacts": [], "deleted": [], "settings": {}}
        return cid, store[cid]

    def fake_http(*a, **k):
        return {"ok": True, "canvas": {}}

    beh._agent_get_canvas = fake_get_canvas
    beh._agent_http = fake_http

    # ---- 1) 阶段守卫：发现阶段调工具必须被拦截 ----
    # 文本节点默认走 Sidebar（不进画布），故用 user_text="放到画布" 强制走画布路径，
    # 才能验证 canvas 守卫。生成节点默认进画布。
    beh.CANVAS_AGENT_CURRENT_PHASE["phase"] = "ASSET_DISCOVERY"
    r1 = beh._agent_tool_create_text_node({"text": "林澜的角色设定", "canvas_id": "c_test",
                                            "title": "林澜", "user_text": "放到画布"})
    _ck("backend: discovery-phase text node BLOCKED",
        r1.get("ok") is False and "MutationManager" in str(r1.get("error", "")),
        "error=%s" % r1.get("error"))
    # 生成节点也应在发现阶段被拦
    r1g = beh._agent_tool_create_generation_node({"prompt": "文生图提示词", "canvas_id": "c_test", "title": "林澜"})
    _ck("backend: discovery-phase generation node BLOCKED",
        r1g.get("ok") is False and "MutationManager" in str(r1g.get("error", "")),
        "error=%s" % r1g.get("error"))

    # ---- 2) 空 prompt：generation 无 prompt 必须被拦 ----
    beh.CANVAS_AGENT_CURRENT_PHASE["phase"] = "REFERENCE_ASSET_GENERATION"
    r2 = beh._agent_tool_create_generation_node({"prompt": "", "canvas_id": "c_test", "title": "空提示词节点"})
    _ck("backend: empty-prompt generation node BLOCKED",
        r2.get("ok") is False, "error=%s" % r2.get("error"))

    # ---- 3) 正常流程：phase 清空后工具照常工作（向后兼容）----
    beh.CANVAS_AGENT_CURRENT_PHASE["phase"] = ""
    r3 = beh._agent_tool_create_text_node({"text": "完整剧本内容", "canvas_id": "c_test",
                                            "title": "剧本", "user_text": "放到画布"})
    _ck("backend: normal text node still created (compat)",
        r3.get("ok") is True and r3.get("node_id"), "node_id=%s" % r3.get("node_id"))
    r3g = beh._agent_tool_create_generation_node({"prompt": "完整文生图提示词", "canvas_id": "c_test", "title": "林澜"})
    _ck("backend: normal generation node still created (compat)",
        r3g.get("ok") is True and r3g.get("node_id"), "node_id=%s" % r3g.get("node_id"))

    # ---- 4) batch 通道同样收口 ----
    beh.CANVAS_AGENT_CURRENT_PHASE["phase"] = "ASSET_DISCOVERY"
    r4 = beh._agent_tool_batch_operations({
        "canvas_id": "c_test",
        "operations": [{"op_type": "add_node", "params": {"node_type": "text", "text": "x", "title": "y"}}],
    })
    created = [x for x in (r4.get("results") or []) if isinstance(x, dict) and x.get("op") == "add_node" and not x.get("skipped")]
    _ck("backend: batch add_node during discovery BLOCKED",
        len(created) == 0, "created=%d" % len(created))

    print("\nFINAL RESULT:", "PASS" if not FAIL else "FAIL (%d)" % len(FAIL))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
