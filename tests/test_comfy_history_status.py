# -*- coding: utf-8 -*-
"""history.status 判定契约单测（2026-10-01）。

背景（Codex 代码审查发现，本轮修复）：ComfyUI 官方 PromptQueue.task_done
**成功和失败都会落 history**（execution.py 的 ExecutionStatus：
status_str / completed / messages），所以「history 非空」乃至「outputs 非空」
都不能当作成功。执行期炸掉时，前面节点已经出的预览图照样躺在 outputs 里。

旧实现只看 outputs，于是：
  - 任务实际失败 → 画布报「完成」，还把预览图当产物回填（"假成功"）；
  - 卡死恢复按 prompt_id 认领时，把失败任务的 temp 预览图领回来（"删掉又来"）。

本测试锁死判定契约：
  1. status_str 为 error / completed 为 False → 失败，且 outputs 里的东西一律不收；
  2. 没有 status 字段（老版本）→ 保持旧行为，不凭空判失败；
  3. recent-outputs 不得返回失败任务的产物；
  4. HTTP 错误响应体里的 node_errors 必须被解析出来（不再只剩「HTTP Error 400」）。
"""
from __future__ import annotations

import io
import json
import os
import sys
import unittest
import urllib.error
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, APP_ROOT)

import comfy_flow_service  # noqa: E402
import myridtv_comfy  # noqa: E402


PROMPT_ID = "82b4e140-7802-44bb-ab2d-65216619e389"


def _history(outputs=None, status=None):
    entry = {"outputs": outputs if isinstance(outputs, dict) else {}}
    if status is not None:
        entry["status"] = status
    return entry


def _preview_outputs():
    """执行期炸掉时 outputs 里残留的东西：PreviewImage 出的过程预览图。"""
    return {
        "275": {"images": [{"filename": "ComfyUI_temp_275_00001_.png", "type": "temp"}]},
        "276": {"images": [{"filename": "ComfyUI_temp_276_00001_.png", "type": "temp"}]},
    }


def _fake_save_asset(item, prompt_id, kind, canvas_title="", canvas_id=""):
    return f"/assets/output/test/{kind}/{item.get('filename', 'x')}"


class HistoryFailureReasonTests(unittest.TestCase):
    def test_success_status_passes(self):
        self.assertEqual(
            comfy_flow_service.history_failure_reason(
                _history(_preview_outputs(), {"status_str": "success", "completed": True, "messages": []})
            ),
            "",
        )

    def test_error_status_with_previews_is_failure(self):
        """核心回归：outputs 里有预览图，但 status 说 error → 必须判失败。"""
        reason = comfy_flow_service.history_failure_reason(
            _history(
                _preview_outputs(),
                {
                    "status_str": "error",
                    "completed": True,
                    "messages": [["167", {"exception_message": "NoneType not subscriptable"}]],
                },
            )
        )
        self.assertTrue(reason, "有 error status 却判成了成功")
        self.assertIn("失败", reason)
        self.assertIn("167", reason)
        self.assertIn("NoneType", reason)

    def test_completed_false_is_failure(self):
        reason = comfy_flow_service.history_failure_reason(
            _history(_preview_outputs(), {"status_str": "success", "completed": False, "messages": []})
        )
        self.assertTrue(reason)

    def test_missing_status_keeps_legacy_behavior(self):
        """老版本不带 status 字段：保守放行，不凭空判失败（避免误伤）。"""
        self.assertEqual(comfy_flow_service.history_failure_reason(_history(_preview_outputs())), "")

    def test_non_dict_history(self):
        self.assertTrue(comfy_flow_service.history_failure_reason(None))
        self.assertTrue(comfy_flow_service.history_failure_reason([]))


class CollectOutputsRejectsFailedHistory(unittest.TestCase):
    def _run(self, history):
        manager = comfy_flow_service.JobManager.__new__(comfy_flow_service.JobManager)
        job = comfy_flow_service.ComfyJob("job-1", "MMH3-2", {})
        job.prompt_id = PROMPT_ID
        with mock.patch.object(comfy_flow_service, "_save_asset", _fake_save_asset):
            manager._collect_outputs(job, history)
        return job

    def test_failed_history_with_previews_is_not_success(self):
        job = self._run(
            _history(
                _preview_outputs(),
                {"status_str": "error", "completed": True, "messages": [["167", {"exception_message": "boom"}]]},
            )
        )
        self.assertEqual(job.status, comfy_flow_service.STATUS_ERROR)
        self.assertEqual(job.images, [], "失败任务却把预览图收成了产物")
        self.assertEqual(job.videos, [])
        self.assertTrue(job.error)

    def test_successful_history_still_collects(self):
        job = self._run(
            _history(
                {"275": {"images": [{"filename": "out.png", "type": "output"}]}},
                {"status_str": "success", "completed": True, "messages": []},
            )
        )
        self.assertNotEqual(job.status, comfy_flow_service.STATUS_ERROR)
        self.assertEqual(len(job.images), 1)


class RecentOutputsSkipsFailedJobs(unittest.TestCase):
    def _run(self, history_entry):
        history = {PROMPT_ID: history_entry}
        with mock.patch.object(myridtv_comfy, "comfy_instance_base", lambda: "http://127.0.0.1:8188"), \
             mock.patch.object(myridtv_comfy, "comfy_request_json",
                               lambda base, path, method="GET", payload=None, timeout=120: history), \
             mock.patch.object(myridtv_comfy, "comfy_output_asset_url",
                               lambda base, item, prompt_id, kind="image", **_kw: f"/x/{kind}/{item.get('filename')}"), \
             mock.patch.object(myridtv_comfy.comfy_flow_service.MANAGER, "list_jobs",
                               lambda limit=100: [{"prompt_id": PROMPT_ID}]):
            return myridtv_comfy.recent_comfy_outputs({"limit": 6})

    def test_failed_prompt_not_offered_for_recovery(self):
        """卡死恢复不能从失败任务里领预览图回来（"删掉又来"的另一半根因）。"""
        result = self._run(
            _history(
                _preview_outputs(),
                {"status_str": "error", "completed": True, "messages": [["167", {"exception_message": "boom"}]]},
            )
        )
        self.assertEqual(result["outputs"], [])

    def test_successful_prompt_still_offered(self):
        result = self._run(
            _history(
                {"275": {"images": [{"filename": "out.png", "type": "output"}]}},
                {"status_str": "success", "completed": True, "messages": []},
            )
        )
        self.assertEqual(len(result["outputs"]), 1)


class HttpErrorBodyTests(unittest.TestCase):
    def _http_error(self, body_obj, code=400):
        raw = json.dumps(body_obj).encode("utf-8")
        return urllib.error.HTTPError(
            "http://127.0.0.1:8188/prompt", code, "Bad Request", {}, io.BytesIO(raw)
        )

    def test_node_errors_preserved(self):
        detail = comfy_flow_service._http_error_detail(
            self._http_error(
                {
                    "error": {"type": "prompt_validation_failed", "message": "validation failed"},
                    "node_errors": {"167": {"errors": [{"type": "value_not_in_list"}]}},
                }
            )
        )
        self.assertIn("400", detail)
        self.assertIn("validation failed", detail)
        self.assertIn("167", detail, "node_errors 丢了，排查就只剩 HTTP Error 400")
        self.assertIn("value_not_in_list", detail)

    def test_plain_text_body_falls_back(self):
        exc = urllib.error.HTTPError("http://x", 500, "Server Error", {}, io.BytesIO(b"<html>oops</html>"))
        detail = comfy_flow_service._http_error_detail(exc)  # body 只能读一次，别调两遍
        self.assertIn("500", detail)
        self.assertIn("oops", detail)


if __name__ == "__main__":
    unittest.main()
