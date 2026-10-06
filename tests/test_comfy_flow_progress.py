# -*- coding: utf-8 -*-
"""comfy_flow_service 工作流级进度合成单测（2026-09-30）。

背景：ComfyUI ws 的 progress 事件只是「单个节点内部」的步进（采样器 step 8/20），
多阶段工作流（I2V→upscale→…）第一阶段跑满会把 job.progress 顶到 100，进入下一
阶段又跌回低值 —— 前端进度环表现为「任务没跑完圈就满了又缩回」（用户视角=失效）。
修复：已完成节点数 + 当前节点内部步进，除以输出节点依赖闭包的总数，且只升不降。
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, APP_ROOT)

import comfy_flow_service as fs  # noqa: E402


def _fake_prompt():
    """两阶段工作流：load→encode→sample1→sample2(upscale)→decode→save，外加孤立节点。"""
    return {
        "10": {"class_type": "CheckpointLoaderSimple", "inputs": {}},
        "11": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["10", 0]}},
        "19": {"class_type": "KSampler", "inputs": {"model": ["10", 0], "positive": ["11", 0]}},
        "30": {"class_type": "KSampler", "inputs": {"model": ["10", 0], "image": ["19", 0]}},
        "20": {"class_type": "VAEDecode", "inputs": {"samples": ["30", 0]}},
        "21": {"class_type": "SaveImage", "inputs": {"images": ["20", 0]}},
        "99": {"class_type": "OrphanNode", "inputs": {}},  # 不在任何输出的依赖里
    }


class CountExecutableNodesTests(unittest.TestCase):
    def test_closure_excludes_orphans(self):
        # 闭包 = 6（10→11→19→30→20→21），孤立节点 99 不计入分母
        self.assertEqual(fs._count_executable_nodes(_fake_prompt()), 6)

    def test_empty_prompt(self):
        self.assertEqual(fs._count_executable_nodes({}), 0)

    def test_fallback_without_output_nodes(self):
        # 找不到输出节点时退回全图节点数
        self.assertEqual(fs._count_executable_nodes({"1": {"class_type": "KSampler", "inputs": {}}}), 1)


class MultiStageProgressTests(unittest.TestCase):
    def _run_two_stage(self):
        job = fs.ComfyJob("t1", "MMH3.json", _fake_prompt())
        job._total_nodes = fs._count_executable_nodes(job.prompt)

        def feed(kind, node=None, value=None, mx=None):
            if kind == "executing":
                fs._advance_comfy_node(job, node)
            elif kind == "progress":
                job.progress = fs._compose_comfy_progress(job, float(value) / float(mx) * 100)
            elif kind == "executed" and node:
                job._done_nodes.add(node)
                # 与 comfy_flow_service on_message 的 executed 分支一致：节点完成也推进度
                if job._total_nodes > 1:
                    job.progress = max(job.progress, min(99, int(len(job._done_nodes) / job._total_nodes * 100)))
                else:
                    job.progress = max(job.progress, 99)

        seq = []
        feed("executing", node="10")
        feed("executed", node="10")
        feed("executing", node="11")
        feed("executed", node="11")
        feed("executing", node="19")
        for i in range(1, 21):  # 阶段1采样 20 步
            feed("progress", node="19", value=i, mx=20)
            seq.append(job.progress)
        stage1_end = seq[-1]
        feed("executed", node="19")
        feed("executing", node="30")
        for i in range(1, 21):  # 阶段2采样 20 步
            feed("progress", node="30", value=i, mx=20)
            seq.append(job.progress)
        stage2_end = seq[-1]
        # 收尾三节点（快速、无 progress 事件）
        feed("executed", node="30")
        feed("executing", node="20"); feed("executed", node="20")
        feed("executing", node="21"); feed("executed", node="21")
        return seq, stage1_end, stage2_end, job.progress

    def test_stage1_full_never_reaches_100(self):
        seq, stage1_end, _, _ = self._run_two_stage()
        self.assertLess(stage1_end, 100, "阶段1跑满就 100 = 旧 bug 复现")
        self.assertEqual(stage1_end, 50, "阶段1跑满应 3/6=50%")

    def test_monotonic_never_regresses(self):
        seq, _, _, _ = self._run_two_stage()
        for a, b in zip(seq, seq[1:]):
            self.assertGreaterEqual(b, a, f"进度回退：{a} → {b}")

    def test_final_capped_at_99(self):
        _, _, _, final = self._run_two_stage()
        self.assertEqual(final, 99, "全部节点执行完应封顶 99（100 留给真正收尾）")

    def test_sampled_values(self):
        seq, _, stage2_end, _ = self._run_two_stage()
        self.assertEqual(seq[9], 41, "阶段1中点应 (2+0.5)/6≈41%")
        self.assertEqual(seq[29], 58, "阶段2中点应 (3+0.5)/6≈58%")
        self.assertEqual(stage2_end, 66, "阶段2末步应 (3+1)/6≈66%（随后续节点 executed 推到 99）")


class FallbackTests(unittest.TestCase):
    def test_single_node_linear(self):
        """单节点工作流：退回节点内部步进线性显示。"""
        job = fs.ComfyJob("t2", "single.json", {"1": {"class_type": "KSampler", "inputs": {}}})
        job._total_nodes = fs._count_executable_nodes(job.prompt)
        out = []
        for i in range(0, 101, 25):
            job.progress = fs._compose_comfy_progress(job, float(i))
            out.append(job.progress)
        self.assertEqual(out, [0, 25, 50, 75, 99])

    def test_restored_job_without_total(self):
        """重启恢复的旧 job（无 _total_nodes）：不炸、封顶 99。"""
        job = fs.ComfyJob("t3", "old.json", {})
        self.assertEqual(job._total_nodes, 0)
        self.assertEqual(fs._compose_comfy_progress(job, 50), 50)
        self.assertEqual(fs._compose_comfy_progress(job, 100), 99)
        self.assertEqual(fs._compose_comfy_progress(job, 100), 99)


if __name__ == "__main__":
    unittest.main()
