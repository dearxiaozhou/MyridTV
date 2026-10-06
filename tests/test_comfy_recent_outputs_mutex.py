# -*- coding: utf-8 -*-
"""recent_comfy_outputs 视频/预览图互斥单测（2026-10-01）。

背景（接 2026-09-30 _collect_outputs 修复）：MMH3 等视频工作流同时有 VHS 视频输出
节点和 PreviewImage 过程预览节点（ComfyUI_temp_*.png）。后端重启导致轮询中断后，
前端「卡死恢复 recoverStuckComfyNodes」走 /api/comfyui/recent-outputs 按 prompt_id
认领产出；若 recent-outputs 把 images(预览图) 和 videos 一起返回，前端旧口径
「images 优先」就会把 temp 预览图当产出回填视频节点——用户删掉后 images 变空、
comfyPromptId 仍在，下一轮恢复又填回来，表现为「一直给我填图片，删掉又来」。
修复：recent_comfy_outputs 有视频就清空 images（与 _collect_outputs 同口径），
前端恢复也改为 videos 优先。
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, APP_ROOT)

import myridtv_comfy  # noqa: E402


def _history_entry(images_nodes=(), video_nodes=()):
    """构造 ComfyUI /history 单条记录形状。images_nodes/video_nodes 为 node_id 列表。"""
    outputs = {}
    for node_id in images_nodes:
        outputs[str(node_id)] = {"images": [{"filename": f"ComfyUI_temp_{node_id}_00001_.png", "type": "temp"}]}
    for node_id in video_nodes:
        outputs[str(node_id)] = {"gifs": [{"filename": f"learned_latent_{node_id}-audio.mp4", "type": "output", "subfolder": "MiniMaxH3"}]}
    return {"status": {"status_str": "success"}, "outputs": outputs}


def _fake_asset_url(base, item, prompt_id, kind="image", **_kw):
    return f"/assets/output/test/{prompt_id}/{kind}/{item.get('filename', 'x')}"


class RecentOutputsMutexTests(unittest.TestCase):
    def test_recovery_reuses_job_canvas_folder(self):
        pid = '82b4e140-7802-44bb-ab2d-65216619e389'
        history = {pid: _history_entry(images_nodes=[11])}
        item = history[pid]['outputs']['11']['images'][0]
        history[pid]['outputs']['11']['images'].append(dict(item))
        with mock.patch.object(myridtv_comfy, 'comfy_instance_base', return_value='http://127.0.0.1:8188'), \
             mock.patch.object(myridtv_comfy, 'comfy_request_json', return_value=history), \
             mock.patch.object(myridtv_comfy, 'comfy_output_asset_url', return_value='/assets/output/canvas/images/test.png') as saver, \
             mock.patch.object(myridtv_comfy.comfy_flow_service.MANAGER, 'list_jobs', return_value=[{
                 'prompt_id': pid, 'meta': {'canvas_id': '123', 'canvas_title': 'Test'}}]):
            result = myridtv_comfy.recent_comfy_outputs()
        saver.assert_called_with('http://127.0.0.1:8188', item, pid, 'image', canvas_title='Test', canvas_id='123')
        self.assertEqual(result['outputs'][0]['images'], ['/assets/output/canvas/images/test.png'])

    def _run(self, history_entry, prompt_id="82b4e140-7802-44bb-ab2d-65216619e389"):
        history = {prompt_id: history_entry}
        with mock.patch.object(myridtv_comfy, "comfy_instance_base", lambda: "http://127.0.0.1:8188"), \
             mock.patch.object(myridtv_comfy, "comfy_request_json", lambda base, path, method="GET", payload=None, timeout=120: history), \
             mock.patch.object(myridtv_comfy, "comfy_output_asset_url", _fake_asset_url), \
             mock.patch.object(myridtv_comfy.comfy_flow_service.MANAGER, "list_jobs", lambda limit=100: [{"prompt_id": prompt_id}]):
            return myridtv_comfy.recent_comfy_outputs({"limit": 6})

    def test_video_workflow_previews_not_returned(self):
        # 复现 2026-10-01 豆包系列画布：1 视频 + 3 张 temp 预览图 → 只回视频
        result = self._run(_history_entry(images_nodes=[275, 276, 277], video_nodes=[226]))
        rows = result["outputs"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]["videos"]), 1)
        self.assertEqual(rows[0]["images"], [])

    def test_image_only_workflow_keeps_previews(self):
        # 纯图像工作流（无视频输出）时，PreviewImage 仍是合法产出，不能误伤
        result = self._run(_history_entry(images_nodes=[11]))
        rows = result["outputs"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]["images"]), 1)
        self.assertEqual(rows[0]["videos"], [])

    def test_unknown_prompt_filtered(self):
        # 非 MyridTV 提交的任务（如 ComfyUI 网页手动跑）不进 recent-outputs
        with mock.patch.object(myridtv_comfy, "comfy_instance_base", lambda: "http://127.0.0.1:8188"), \
             mock.patch.object(myridtv_comfy, "comfy_request_json", lambda base, path, method="GET", payload=None, timeout=120: {"abc": _history_entry(images_nodes=[11])}), \
             mock.patch.object(myridtv_comfy.comfy_flow_service.MANAGER, "list_jobs", lambda limit=100: [{"prompt_id": "other"}]):
            result = myridtv_comfy.recent_comfy_outputs({"limit": 6})
        self.assertEqual(result["outputs"], [])


if __name__ == "__main__":
    unittest.main()
