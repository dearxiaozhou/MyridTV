# -*- coding: utf-8 -*-
"""comfy_flow_service._collect_outputs 视频/预览图互斥单测（2026-09-30）。

背景：MMH3 等工作流同时有视频输出节点（VHS VideoCombine）和预览图输出节点
（PreviewImage/SaveImage 出 ComfyUI_temp 截图）。旧逻辑两者都收进 job.images /
job.videos，前端 runComfyWorkflowJob 用 resultMediaUrls 合并后统一盖 kind=video，
PNG 被标成 output-2.mp4 的"假视频"黑卡，节点还因多产物变成 Videos 打组态。
修复：有视频就只回视频（与前端 supervisor 兜底口径一致）。
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, APP_ROOT)

import comfy_flow_service as fs  # noqa: E402


def _fake_saver(base, item, prompt_id, kind, canvas_title="", canvas_id=""):
    return f"/assets/output/test_{kind}/{item.get('filename', 'x')}"


def _history(images_nodes=(), video_nodes=()):
    """构造 ComfyUI /history 形状的 outputs。每个元素是 (node_id, keys) 元组。"""
    outputs = {}
    for node_id, keys in images_nodes:
        outputs[node_id] = {"images": [{"filename": f"img_{node_id}.png", "type": "temp"}]}
        for key in keys or []:
            outputs[node_id][key] = [{"filename": f"vid_{node_id}.{key}"}]
    for node_id, keys in video_nodes:
        outputs[node_id] = {}
        for key in keys or []:
            outputs[node_id][key] = [{"filename": f"vid_{node_id}.{key}"}]
    return {"outputs": outputs}


class CollectOutputsTests(unittest.TestCase):
    def setUp(self):
        self._old_saver = fs._ASSET_SAVER
        fs._ASSET_SAVER = _fake_saver

    def tearDown(self):
        fs._ASSET_SAVER = self._old_saver

    def _collect(self, history):
        job = fs.ComfyJob("t1", "MMH3.json", {})
        fs.MANAGER._collect_outputs(job, history)
        return job

    def test_video_and_preview_image_only_video_kept(self):
        # 复现 2026-09-30 MMH3：视频节点 + ComfyUI_temp 预览图节点 → 只回视频
        job = self._collect(_history(images_nodes=[("11", ())], video_nodes=[("20", ("gifs",))]))
        self.assertNotEqual(job.status, fs.STATUS_ERROR)
        self.assertEqual(len(job.videos), 1)
        self.assertEqual(job.images, [])

    def test_image_only_workflow_keeps_images(self):
        job = self._collect(_history(images_nodes=[("11", ()), ("12", ())]))
        self.assertEqual(len(job.images), 1)  # 多图节点取最后一个
        self.assertEqual(job.videos, [])

    def test_multiple_video_nodes_take_last(self):
        job = self._collect(_history(video_nodes=[("20", ("gifs",)), ("21", ("videos",))]))
        self.assertEqual(len(job.videos), 1)
        self.assertEqual(job.images, [])

    def test_empty_outputs_is_error(self):
        job = self._collect({"outputs": {}})
        self.assertEqual(job.status, fs.STATUS_ERROR)
        self.assertFalse(job.images)
        self.assertFalse(job.videos)

    def test_repeated_output_descriptor_does_not_repeat_image(self):
        history = _history(images_nodes=[('11', ())])
        item = history['outputs']['11']['images'][0]
        history['outputs']['11']['images'].append(dict(item))
        job = self._collect(history)
        self.assertEqual(len(job.images), 1)



if __name__ == "__main__":
    unittest.main()
