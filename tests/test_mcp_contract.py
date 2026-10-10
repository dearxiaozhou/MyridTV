"""Behavioral regression checks for external Agent reads and reversible mutations."""
import concurrent.futures
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import myridtv_mcp as mcp
import myridtv_mcp_contract as contract
import myridtv_canvas_store as store
import myridtv_agent_artifact as artifacts
import myridtv_agent_generation as generation


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        store.configure(root, root, lambda: None, lambda c: None, lambda p: None, lambda c: None)
        self.old_dir = artifacts.AGENT_BATCH_DIR
        artifacts.AGENT_BATCH_DIR = root / "batches"
        self.addCleanup(setattr, artifacts, "AGENT_BATCH_DIR", self.old_dir)
        self.registry = copy.deepcopy(mcp.MCP_TOOLS)
        def legacy(name, args):
            canvas = store.read_canvas_record(args["canvas_id"], False)
            canvas["nodes"][0]["text"] = args["text"]
            saved = store.save_canvas_record(canvas["id"], canvas)
            return {"ok": True, "save_ok": True, "updated_at": saved["updated_at"]}
        self.handle = contract.install(self.registry, legacy, None)
        self.canvas = store.create_canvas_record({"nodes": [
            {"id": "a", "type": "smart-prompt", "title": "原始标题", "text": "搜索提示词", "x": 1, "y": 2},
            {"id": "b", "type": "smart-image", "images": [{"url": "/assets/result.png"}], "runSettings": {"model": "configured"}}
        ], "connections": [{"from": "a", "to": "b", "kind": "input"}]})
        self.cid = self.canvas["id"]

    def call(self, name, **args):
        return self.handle(name, {"canvas_id": self.cid, **args})

    def current(self):
        return store.read_canvas_record(self.cid, False)

    def test_explicit_target_and_schema_validation(self):
        self.assertEqual(self.handle("canvas_update_node", {"node_id": "a", "text": "x"})["error_code"], "invalid_arguments")
        self.assertIn("未知参数", self.call("canvas_get_state", typo=True)["error"])
        self.assertIn("范围", self.call("canvas_get_state", limit=0)["error"])

    def test_details_pagination_and_real_text_search(self):
        result = self.call("canvas_get_state", limit=1)
        self.assertTrue(result["has_more"])
        self.assertEqual(result["nodes"][0]["text_preview"], "搜索提示词")
        node = self.call("canvas_get_node", node_id="b")["node"]
        self.assertEqual(node["images"][0]["url"], "/assets/result.png")
        self.assertEqual(self.call("canvas_search", query="提示词")["matches"], 1)
        self.assertEqual(self.call("canvas_get_node", node_id="missing")["error_code"], "node_not_found")
        self.assertFalse(self.call("canvas_get_selection")["available"])

    def test_parallel_reads_never_share_target(self):
        other = store.create_canvas_record({"title": "另一个画布"})
        def read(i):
            cid = self.cid if i % 2 else other["id"]
            return self.handle("canvas_get_state", {"canvas_id": cid})["canvas_id"] == cid
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertTrue(all(pool.map(read, range(50))))

    def test_batch_delete_undo_restores_tombstones_and_input_connections(self):
        result = self.call("canvas_batch_operations", operations=[{"op_type": "delete_node", "target_id": "a"}])
        self.assertTrue(result["save_ok"])
        self.assertEqual([n["id"] for n in self.current()["nodes"]], ["b"])
        self.assertEqual(self.current()["nodes"][0]["inputNodeIds"], [])
        undone = self.call("canvas_undo_batch", batch_id=result["batch_id"])
        self.assertTrue(undone["save_ok"])
        self.assertEqual([n["id"] for n in self.current()["nodes"]], ["a", "b"])
        self.assertNotIn("a", [t["id"] for t in self.current()["deleted"]])
        self.assertEqual(len(self.current()["connections"]), 1)
        self.assertTrue(self.call("canvas_undo_batch", batch_id=result["batch_id"])["already_undone"])

    def test_batch_failure_is_atomic_and_does_not_silently_drop_ops(self):
        before = self.current()
        result = self.call("canvas_batch_operations", operations=[
            {"op_type": "update_node", "target_id": "a", "params": {"text": "changed"}},
            {"op_type": "layer_operate", "target_id": "a", "params": {"action": "invalid"}}])
        self.assertFalse(result["ok"])
        self.assertEqual(self.current(), before)
        self.assertFalse(self.call("canvas_batch_operations", operations=[None])["ok"])
        self.assertFalse(self.call("canvas_batch_operations", operations=[{"op_type": "delete_node"}]*51)["ok"])

    def test_concurrent_same_revision_has_one_winner_and_same_key_runs_once(self):
        args = {"operations": [{"op_type": "update_node", "target_id": "a", "params": {"text": "并发"}}],
                "expected_updated_at": self.canvas["updated_at"]}
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.call("canvas_batch_operations", **args), range(8)))
        self.assertEqual(sum(r.get("ok") is True for r in results), 1)
        args.pop("expected_updated_at")
        args["idempotency_key"] = "parallel-retry"
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.call("canvas_batch_operations", **args), range(8)))
        self.assertTrue(all(r == results[0] for r in results))
        self.assertEqual(len(list(contract._directory("batches").glob("*.json"))), 2)

    def test_undo_refuses_later_edits_and_wrong_canvas(self):
        result = self.call("canvas_batch_operations", operations=[{"op_type": "update_node", "target_id": "a", "params": {"text": "batch"}}])
        canvas = self.current()
        canvas["nodes"][0]["text"] = "用户的新修改"
        store.save_canvas_record(self.cid, canvas)
        self.assertEqual(self.call("canvas_undo_batch", batch_id=result["batch_id"])["error_code"], "conflict")
        self.assertEqual(self.current()["nodes"][0]["text"], "用户的新修改")
        other = store.create_canvas_record({})
        self.assertFalse(self.call("canvas_undo_batch", canvas_id=other["id"], batch_id=result["batch_id"])["ok"])

    def test_snapshot_is_persistent_and_restore_checks_revision(self):
        snapshot = self.call("canvas_snapshot", label="验证快照")
        self.assertEqual(self.call("canvas_list_snapshots")["snapshots"][0]["snapshot_id"], snapshot["snapshot_id"])
        self.assertEqual(self.call("canvas_get_snapshot", snapshot_id=snapshot["snapshot_id"])["snapshot"]["nodes"][0]["text"], "搜索提示词")
        self.call("canvas_batch_operations", operations=[{"op_type": "delete_node", "target_id": "a"}])
        self.assertEqual(self.call("canvas_restore_snapshot", snapshot_id=snapshot["snapshot_id"], expected_updated_at=self.canvas["updated_at"])["error_code"], "conflict")
        restored = self.call("canvas_restore_snapshot", snapshot_id=snapshot["snapshot_id"], expected_updated_at=self.current()["updated_at"])
        self.assertTrue(restored["ok"])
        self.assertEqual(len(self.current()["nodes"]), 2)

    def test_idempotency_survives_handler_reload_and_rejects_key_reuse(self):
        args = {"operations": [{"op_type": "update_node", "target_id": "a", "params": {"text": "once"}}], "idempotency_key": "same-request"}
        first = self.call("canvas_batch_operations", **args)
        updated = self.current()["updated_at"]
        self.handle = contract.install(self.registry, lambda *a: None, None)
        self.assertEqual(self.call("canvas_batch_operations", **args), first)
        self.assertEqual(self.current()["updated_at"], updated)
        self.assertEqual(self.call("canvas_snapshot", idempotency_key="same-request")["error_code"], "idempotency_conflict")

    def test_missing_failed_succeeded_and_cross_canvas_tasks(self):
        with patch.object(contract.tasks, "get_task_state", return_value={}):
            self.assertEqual(self.call("canvas_check_generation", task_id="unknown")["error_code"], "task_not_found")
        with patch.object(contract.tasks, "get_task_state", return_value={"canvas_id": "other"}):
            self.assertEqual(self.call("canvas_check_generation", task_id="t")["error_code"], "task_canvas_mismatch")
        for status in ("running", "failed", "succeeded"):
            with patch.object(contract.tasks, "get_task_state", return_value={"canvas_id": self.cid}), patch.object(contract.state, "_agent_http", return_value={"status": status, "images": ["/assets/result.png"]}):
                self.assertEqual(self.call("canvas_check_generation", task_id="t")["result"]["status"], status)

    def test_new_generation_binds_submitted_task_to_created_node(self):
        with patch.object(generation, "_agent_tool_create_generation_node", return_value={"ok": True, "node_id": "b", "canvas_id": self.cid}), patch.object(generation.myridtv_agent_state, "_agent_get_canvas", return_value=(self.cid, self.current())), patch.object(generation, "_agent_submit_generation", return_value={"ok": True, "task_id": "task"}) as submit, patch.object(generation, "_agent_add_pending_task_to_node"):
            result = generation._agent_tool_generate_images({"prompt": "test", "canvas_id": self.cid})
            self.assertEqual(submit.call_args.args[0]["node_id"], "b")
            self.assertEqual(result["canvas_id"], self.cid)


if __name__ == "__main__":
    unittest.main()
