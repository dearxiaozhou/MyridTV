# -*- coding: utf-8 -*-
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import rh_official_proxy as beh


class AgentTaskBackendRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.old_request = beh.request_chat_json_with_retry
        self.old_get_canvas = beh._agent_get_canvas
        self.old_http = beh._agent_http
        self.old_resolve = beh.resolve_chat_target
        self.old_prefers = beh.payload_prefers_codex_local
        self.old_tasks = dict(beh.TASKS)
        beh.TASKS.clear()
        self.store = {"c_backend": {"id": "c_backend", "title": "测试画布", "nodes": [], "connections": [], "artifacts": [], "deleted": [], "settings": {}}}

        def fake_get_canvas(cid):
            cid = cid or "c_backend"
            return cid, self.store[cid]

        def fake_http(method, path, payload=None, timeout=30):
            return {"ok": True, "canvas": payload or {}}

        beh._agent_get_canvas = fake_get_canvas
        beh._agent_http = fake_http
        # 第22刀后生成工具住在 myridtv_agent_generation（属性链调 state），
        # 打桩须同打属主模块（X2/test_backend_wiring 同款处方）
        import myridtv_agent_state as _st
        self.old_st_get_canvas = _st._agent_get_canvas
        self.old_st_http = _st._agent_http
        _st._agent_get_canvas = fake_get_canvas
        _st._agent_http = fake_http
        beh.resolve_chat_target = lambda payload: ("fake", "fake-model", "http://fake.local/v1", "key")
        beh.payload_prefers_codex_local = lambda payload: False

    def tearDown(self):
        import myridtv_agent_state as _st
        _st._agent_get_canvas = self.old_st_get_canvas
        _st._agent_http = self.old_st_http
        beh.request_chat_json_with_retry = self.old_request
        beh._agent_get_canvas = self.old_get_canvas
        beh._agent_http = self.old_http
        beh.resolve_chat_target = self.old_resolve
        beh.payload_prefers_codex_local = self.old_prefers
        beh.TASKS.clear()
        beh.TASKS.update(self.old_tasks)

    def test_submit_chat_blocks_tool_by_step_policy_and_returns_task_state(self):
        calls = {"count": 0}

        def fake_request(url, body, headers, attempts=3, timeout=300):
            calls["count"] += 1
            if calls["count"] == 1:
                return {"choices": [{"message": {"content": "我要提前建节点", "tool_calls": [{
                    "id": "tc_block",
                    "function": {"name": "canvas_create_generation_node", "arguments": "{\"title\":\"角色A\",\"prompt\":\"角色A完整提示词\"}"},
                }]}}]}
            return {"choices": [{"message": {"content": "已输出资产清单：角色A、场景B、道具C。"}}]}

        beh.request_chat_json_with_retry = fake_request
        task = beh._agent_task_for_payload({
            "message": "为这些资产生成文生图 Prompt。",
            "canvas_id": "c_backend",
            "agent_session_id": "conv_backend_block",
        })
        task["current_step_id"] = "generate_asset_prompts"
        result = beh.submit_chat({
            "message": "继续处理资产提示词。",
            "messages": [{"role": "user", "content": "继续处理资产提示词。"}],
            "canvas_id": "c_backend",
            "agent_session_id": "conv_backend_block",
        })
        self.assertEqual(result["task"]["workflow_type"], "video_creation")
        self.assertEqual(result["agent_result"]["task"]["task_id"], result["task"]["task_id"])
        self.assertEqual(len(self.store["c_backend"]["nodes"]), 0)
        self.assertTrue(result["tool_log"][0]["result"]["blocked"])

    def test_submit_chat_allows_materialize_and_writes_provenance(self):
        calls = {"count": 0}

        def fake_request(url, body, headers, attempts=3, timeout=300):
            calls["count"] += 1
            if calls["count"] > 1:
                return {"choices": [{"message": {"content": "节点已创建，等待执行生成。"}}]}
            return {"choices": [{"message": {"content": "开始创建节点", "tool_calls": [{
                "id": "tc_create",
                "function": {"name": "canvas_create_generation_node", "arguments": "{\"title\":\"角色A\",\"prompt\":\"角色A，电影感定妆照，服装清晰，完整可执行提示词\"}"},
            }]}}]}

        beh.request_chat_json_with_retry = fake_request
        task = beh._agent_task_for_payload({
            "message": "根据这个剧本做一套 AI 短片",
            "canvas_id": "c_backend",
            "agent_session_id": "conv_backend_create",
        })
        task["current_step_id"] = "materialize_asset_nodes"
        result = beh.submit_chat({
            "message": "把这些已批准资产 Prompt 创建到画布。",
            "messages": [{"role": "user", "content": "把这些已批准资产 Prompt 创建到画布。"}],
            "canvas_id": "c_backend",
            "agent_session_id": "conv_backend_create",
        })
        node = self.store["c_backend"]["nodes"][0]
        self.assertTrue(result["agent_result"]["created_nodes"])
        self.assertEqual(node["task_id"], task["task_id"])
        self.assertEqual(node["step_id"], "materialize_asset_nodes")
        self.assertEqual(node["tool_call_id"], "tc_create")


if __name__ == "__main__":
    unittest.main(verbosity=2)
