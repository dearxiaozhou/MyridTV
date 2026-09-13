# -*- coding: utf-8 -*-
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import agent_task_runtime as rt


class AgentTaskRuntimeTest(unittest.TestCase):
    def test_01_asset_analysis_blocks_node_creation(self):
        task = rt.create_task("conv_a", "canvas_a", "分析这个剧本里有哪些重要资产。")
        self.assertEqual(task["current_step_id"], "extract_assets")
        policy = rt.authorize_tool(task, "canvas_create_generation_node", {"prompt": "完整提示词"})
        self.assertFalse(policy["allowed"])
        self.assertEqual(policy["reason"], "tool_not_allowed_in_current_step")

    def test_02_asset_prompt_completion_requires_real_prompts(self):
        task = rt.create_task("conv_b", "canvas_b", "为这些资产生成文生图 Prompt。")
        rt.upsert_asset(task, {"asset_id": "character_1", "type": "character", "prompt": "写实女性角色定妆照，服装清晰，电影光线"})
        rt.upsert_asset(task, {"asset_id": "scene_1", "type": "scene", "prompt": "城市夜景街道，雨后反光，霓虹灯"})
        result = rt.validate_step_completion(task, "已完成所有资产提示词。")
        self.assertTrue(result["complete"])

    def test_03_model_early_create_is_blocked_by_step_policy(self):
        task = rt.create_task("conv_c", "canvas_c", "为这些资产生成文生图 Prompt。")
        policy = rt.authorize_tool(task, "canvas_batch_operations", {"operations": []})
        self.assertFalse(policy["allowed"])

    def test_04_placeholder_prompt_blocks_materialize(self):
        task = rt.create_task("conv_d", "canvas_d", "根据这个剧本做一套 AI 短片")
        task["current_step_id"] = "materialize_asset_nodes"
        policy = rt.authorize_tool(task, "canvas_create_generation_node", {"prompt": "TODO"})
        self.assertFalse(policy["allowed"])
        self.assertEqual(policy["reason"], "invalid_or_placeholder_prompt")

    def test_05_partial_asset_approval_keeps_waiting(self):
        task = rt.create_task("conv_e", "canvas_e", "根据这个剧本做一套 AI 短片")
        task["current_step_id"] = "review_assets"
        for idx in range(3):
            rt.upsert_asset(task, {"asset_id": "asset_%d" % idx, "type": "character", "review_status": "pending"})
        rt.record_asset_review_decision(task, "asset_0", "approved")
        rt.record_asset_review_decision(task, "asset_1", "approved")
        result = rt.validate_step_completion(task, "已确认部分资产")
        self.assertFalse(result["complete"])

    def test_06_regenerate_one_asset_keeps_other_approvals(self):
        task = rt.create_task("conv_f", "canvas_f", "根据这个剧本做一套 AI 短片")
        task["current_step_id"] = "review_assets"
        for idx in range(3):
            rt.upsert_asset(task, {"asset_id": "asset_%d" % idx, "type": "character", "review_status": "approved", "status": "approved"})
        rt.record_asset_review_decision(task, "asset_1", "regenerate")
        assets = {a["asset_id"]: a for a in task["assets"]}
        self.assertEqual(assets["asset_0"]["review_status"], "approved")
        self.assertEqual(assets["asset_1"]["status"], "generating")
        self.assertEqual(assets["asset_2"]["review_status"], "approved")

    def test_07_rollback_invalidates_later_turn_work(self):
        task = rt.create_task("conv_g", "canvas_g", "根据这个剧本做一套 AI 短片")
        t1 = rt.begin_turn(task, "第一轮")
        t2 = rt.begin_turn(task, "第二轮")
        task["tool_runs"].append({"turn_id": t2["turn_id"], "status": "completed"})
        res = rt.rollback_to_turn(task, t1["turn_id"])
        self.assertTrue(res["ok"])
        self.assertEqual(len(task["turns"]), 1)
        self.assertEqual(task["tool_runs"][0]["status"], "invalidated")

    def test_08_save_load_keeps_current_step_and_interaction(self):
        task = rt.create_task("conv_h", "canvas_h", "根据这个剧本做一套 AI 短片")
        turn = rt.begin_turn(task, "开始")
        rt.record_interaction(task, turn, {"card_id": "card_1", "intent": "choose", "title": "选方向"})
        path = os.path.join(ROOT, "tests", "_tmp_agent_tasks.json")
        try:
            rt.save_tasks(path, {task["task_id"]: task})
            loaded = rt.load_tasks(path)
            restored = loaded[task["task_id"]]
            self.assertEqual(restored["current_step_id"], task["current_step_id"])
            self.assertEqual(restored["interactions"][0]["status"], "waiting")
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def test_09_two_tasks_same_canvas_do_not_mix(self):
        store = {}
        a = rt.ensure_task(store, "conv_i1", "canvas_i", "根据剧本做短片 A")
        b = rt.ensure_task(store, "conv_i2", "canvas_i", "根据剧本做短片 B")
        self.assertNotEqual(a["task_id"], b["task_id"])
        self.assertEqual(a["canvas_id"], b["canvas_id"])

    def test_10_llm_completion_claim_does_not_complete_unmet_step(self):
        task = rt.create_task("conv_j", "canvas_j", "根据这个剧本做一套 AI 短片")
        task["current_step_id"] = "review_assets"
        rt.upsert_asset(task, {"asset_id": "asset_j", "type": "character", "review_status": "pending"})
        validation = rt.advance_step_if_complete(task, "全部完成")
        self.assertFalse(validation["complete"])
        self.assertNotEqual(task["status"], "completed")

    def test_11_full_runtime_flow_skeleton(self):
        task = rt.create_task("conv_k", "canvas_k", "根据这个剧本开始做短片。")
        self.assertEqual(task["current_step_id"], "analyze_script")
        turn1 = rt.begin_turn(task, "根据这个剧本开始做短片。")
        rt.advance_step_if_complete(task, "剧本分析完成：主角在雨夜发现线索。")
        self.assertEqual(task["current_step_id"], "determine_visual_direction")

        task["current_step_id"] = "generate_asset_prompts"
        blocked = rt.authorize_tool(task, "canvas_create_generation_node", {"prompt": "角色A完整提示词"})
        self.assertFalse(blocked["allowed"])

        rt.upsert_asset(task, {"asset_id": "character_a", "type": "character", "prompt": "角色A，写实短剧主角，服装清晰，电影光线"})
        ready = rt.advance_step_if_complete(task, "资产 Prompt 已完成。")
        self.assertTrue(ready["complete"])
        self.assertEqual(task["current_step_id"], "materialize_asset_nodes")

        allowed = rt.authorize_tool(task, "canvas_create_generation_node", {"prompt": "角色A，写实短剧主角，服装清晰，电影光线"})
        self.assertTrue(allowed["allowed"])
        rt.record_tool_run(task, turn1, "canvas_create_generation_node", {"prompt": "角色A，写实短剧主角，服装清晰，电影光线"}, {"ok": True, "node_id": "node_a"}, allowed)
        task["assets"][0]["canvas_node_id"] = "node_a"
        rt.advance_step_if_complete(task, "已创建资产节点。", [{"result": {"node_id": "node_a", "ok": True}}])
        self.assertEqual(task["current_step_id"], "generate_assets")

        task["current_step_id"] = "review_assets"
        turn2 = rt.begin_turn(task, "确认资产")
        rt.record_interaction(task, turn2, {"card_id": "card_review", "intent": "confirm", "title": "确认资产"})
        self.assertEqual(task["status"], "waiting_user")
        rt.record_asset_review_decision(task, "character_a", "approved")
        self.assertEqual(task["status"], "running")
        rt.advance_step_if_complete(task, "资产已确认。")
        self.assertEqual(task["current_step_id"], "generate_storyboard")

        task["current_step_id"] = "qa"
        done = rt.advance_step_if_complete(task, "QA 通过，任务完成。")
        self.assertTrue(done["complete"])
        self.assertEqual(task["status"], "completed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
