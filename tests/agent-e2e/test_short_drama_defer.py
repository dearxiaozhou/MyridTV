#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
验证短剧制作板改为"先问后建"：
- 用户仅说"参数已确认" → 只返回 preview，不调用 canvas_batch_operations
- 用户说"执行制作板" → 才真正调用 batch 建节点
"""
import sys
sys.path.insert(0, "D:/APP/MyridTV")

import rh_official_proxy as beh

# 打桩：记录 batch 调用；并强制命中短剧分支
_called = {"count": 0}
_original_batch = beh._agent_tool_batch_operations
_original_is_short = beh._agent_is_short_drama_request


def fake_batch_operations(batch_args, preset=None):
    _called["count"] += 1
    _called["ops"] = len(batch_args.get("operations", []))
    return {"ok": True, "save_ok": True}


def always_short(text):
    return True


beh._agent_tool_batch_operations = fake_batch_operations
beh._agent_is_short_drama_request = always_short


def make_payload(latest_text):
    return {
        "messages": [
            {"role": "user", "content": "帮我做一个短剧"},
            {"role": "user", "content": latest_text},
        ],
        "agent_session_id": "test-session",
    }


def test_confirm_only_does_not_create():
    _called["count"] = 0
    payload = make_payload("""
idea=都市反转短剧：一次意外消息引发误会
故事一句话=都市反转短剧：一次意外消息引发误会
duration=30秒
clip_count=3
aspect_ratio=9:16
style=写实短剧
参数已确认
""")
    result = beh._agent_short_drama_board_result(payload)
    assert result is not None, "应命中短剧制作板分支"
    assert _called["count"] == 0, "仅确认参数不应调用 batch，实际调了 {} 次".format(_called["count"])
    text = result.get("text", "")
    assert "已准备好" in text, "应返回准备态文案"
    assert "执行制作板" in text, "文案应提示用户说执行制作板"
    print("PASS: 仅参数确认不建节点")


def test_execute_creates_nodes():
    _called["count"] = 0
    payload = make_payload("""
idea=都市反转短剧：一次意外消息引发误会
duration=30秒
clip_count=3
aspect_ratio=9:16
style=写实短剧
执行制作板
""")
    result = beh._agent_short_drama_board_result(payload)
    assert result is not None, "应命中短剧制作板分支"
    assert _called["count"] == 1, "执行制作板应调用 batch，实际调了 {} 次".format(_called["count"])
    assert _called.get("ops", 0) > 0, "应包含 operations"
    print("PASS: 明确执行后建节点 (ops={})".format(_called.get("ops")))


if __name__ == "__main__":
    try:
        test_confirm_only_does_not_create()
        test_execute_creates_nodes()
        print("RESULT: PASS")
    finally:
        beh._agent_tool_batch_operations = _original_batch
        beh._agent_is_short_drama_request = _original_is_short
