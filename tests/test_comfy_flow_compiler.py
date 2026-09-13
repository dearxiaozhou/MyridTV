"""comfy_flow_compiler 的单测。

用真实工作流（_internal/workflows/Krea2参考生成三视图.json）和真实 object_info 子集
（tests/comfy_oi_subset.json）验证 bypass / mute / 覆盖三条路径。

数据文件缺失时自动降级为从本地 ComfyUI 的 /object_info 重新抽取子集。
"""

from __future__ import annotations

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, APP_ROOT)

from comfy_flow_compiler import (  # noqa: E402
    CompileError,
    _is_link,
    compile_prompt,
    describe_workflow,
)

WORKFLOW_PATH = os.path.join(APP_ROOT, "_internal", "workflows", "Krea2参考生成三视图.json")
OI_SUBSET_PATH = os.path.join(HERE, "comfy_oi_subset.json")
OI_FULL_PATH = os.path.join(APP_ROOT, "_cu_oi.json")


def _load_object_info():
    if os.path.exists(OI_SUBSET_PATH):
        with open(OI_SUBSET_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    if os.path.exists(OI_FULL_PATH):
        with open(OI_FULL_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    raise unittest.SkipTest("缺少 object_info 数据，无法运行编译器测试")


def _load_workflow():
    if not os.path.exists(WORKFLOW_PATH):
        raise unittest.SkipTest("缺少工作流文件：Krea2参考生成三视图.json")
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


class LinkDetectionTest(unittest.TestCase):
    def test_recognises_links(self):
        self.assertTrue(_is_link(["3", 0]))
        self.assertTrue(_is_link(("12", 1)))

    def test_rejects_non_links(self):
        self.assertFalse(_is_link("ComfyUI"))
        self.assertFalse(_is_link(123))
        self.assertFalse(_is_link([1, 2]))            # 上游 id 必须是字符串
        self.assertFalse(_is_link(["3"]))             # 长度必须是 2
        self.assertFalse(_is_link(["3", 0, 1]))       # 长度必须是 2
        self.assertFalse(_is_link(None))
        # 布尔值是 int 的子类，不能当成槽位序号
        self.assertFalse(_is_link(["3", True]))


class NoopCompileTest(unittest.TestCase):
    def setUp(self):
        self.workflow = _load_workflow()
        self.object_info = _load_object_info()

    def test_empty_modes_returns_equivalent_graph(self):
        compiled, report = compile_prompt(self.workflow, {}, {}, self.object_info)
        self.assertEqual(set(compiled.keys()), set(self.workflow.keys()))
        self.assertEqual(compiled, self.workflow)
        self.assertEqual(report["rewired"], [])
        self.assertEqual(report["bypassed"], [])
        self.assertEqual(report["muted"], [])

    def test_source_graph_is_not_mutated(self):
        snapshot = json.dumps(self.workflow, sort_keys=True, ensure_ascii=False)
        compile_prompt(self.workflow, {"8": {"text": "hello"}}, {"13": "bypass"}, self.object_info)
        self.assertEqual(json.dumps(self.workflow, sort_keys=True, ensure_ascii=False), snapshot)

    def test_overrides_are_applied(self):
        compiled, report = compile_prompt(
            self.workflow, {"8": {"text": "三个人物设定表"}}, {}, self.object_info
        )
        self.assertEqual(compiled["8"]["inputs"]["text"], "三个人物设定表")
        self.assertEqual(report["overridden"], [{"node": "8", "input": "text"}])

    def test_override_on_missing_node_is_ignored(self):
        compiled, _report = compile_prompt(self.workflow, {"999": {"x": 1}}, {}, self.object_info)
        self.assertNotIn("999", compiled)
        self.assertEqual(set(compiled.keys()), set(self.workflow.keys()))


class BypassTest(unittest.TestCase):
    def setUp(self):
        self.workflow = _load_workflow()
        self.object_info = _load_object_info()

    def test_bypass_style_transfer_rewires_to_upstream_model(self):
        """旁路 13（Krea2StyleTransfer）后，10.model 应改接 5[0]（同为 MODEL）。"""
        compiled, report = compile_prompt(self.workflow, {}, {"13": "bypass"}, self.object_info)
        self.assertNotIn("13", compiled)
        self.assertEqual(compiled["10"]["inputs"]["model"], ["5", 0])
        rewired = [r for r in report["rewired"] if r["node"] == "10" and r["input"] == "model"]
        self.assertEqual(len(rewired), 1)
        self.assertEqual(rewired[0]["from"], ["13", 0])
        self.assertEqual(rewired[0]["to"], ["5", 0])

    def test_bypass_upscaler_rewires_save_image(self):
        """旁路 20（SeedVR2VideoUpscaler）后，22.images 应改接 19[0]（同为 IMAGE）。"""
        compiled, report = compile_prompt(self.workflow, {}, {"20": "bypass"}, self.object_info)
        self.assertNotIn("20", compiled)
        self.assertEqual(compiled["22"]["inputs"]["images"], ["19", 0])
        self.assertIn("20", report["bypassed"])

    def test_bypass_chain_skips_consecutive_bypassed_nodes(self):
        """同时旁路 19 和 20，22.images 应一路回溯到 11[0]。"""
        compiled, report = compile_prompt(
            self.workflow, {}, {"19": "bypass", "20": "bypass"}, self.object_info
        )
        self.assertNotIn("19", compiled)
        self.assertNotIn("20", compiled)
        self.assertEqual(compiled["22"]["inputs"]["images"], ["11", 0])
        self.assertIn("19", report["bypassed"])
        self.assertIn("20", report["bypassed"])

    def test_bypass_output_node_is_dropped_cleanly(self):
        """旁路输出节点 12（SaveImage）不应影响其他分支。"""
        compiled, _report = compile_prompt(self.workflow, {}, {"12": "bypass"}, self.object_info)
        self.assertNotIn("12", compiled)
        self.assertIn("22", compiled)
        self.assertEqual(compiled["11"]["inputs"]["samples"], ["10", 0])

    def test_bypassing_unknown_node_is_ignored(self):
        compiled, report = compile_prompt(self.workflow, {}, {"999": "bypass"}, self.object_info)
        self.assertEqual(set(compiled.keys()), set(self.workflow.keys()))
        self.assertEqual(report["bypassed"], [])


class MuteTest(unittest.TestCase):
    def setUp(self):
        self.workflow = _load_workflow()
        self.object_info = _load_object_info()

    def test_mute_cascades_to_all_downstream(self):
        """禁用 11（VAEDecode）应连带删掉 12 / 19 / 20 / 21 / 22。"""
        compiled, report = compile_prompt(self.workflow, {}, {"11": "mute"}, self.object_info)
        for node_id in ("11", "12", "19", "20", "21", "22"):
            self.assertNotIn(node_id, compiled, f"节点 {node_id} 应被级联删除")
        for node_id in ("10", "13", "18"):
            self.assertIn(node_id, compiled, f"节点 {node_id} 是上游，应保留")
        self.assertEqual(set(report["muted"]), {"11", "12", "19", "20", "21", "22"})

    def test_mute_leaf_output_only_removes_itself(self):
        compiled, report = compile_prompt(self.workflow, {}, {"21": "mute"}, self.object_info)
        self.assertNotIn("21", compiled)
        self.assertIn("20", compiled)
        self.assertIn("22", compiled)
        self.assertEqual(report["muted"], ["21"])

    def test_mute_whole_graph_raises(self):
        all_muted = {node_id: "mute" for node_id in self.workflow}
        with self.assertRaises(CompileError):
            compile_prompt(self.workflow, {}, all_muted, self.object_info)


class MixedTest(unittest.TestCase):
    def setUp(self):
        self.workflow = _load_workflow()
        self.object_info = _load_object_info()

    def test_override_and_bypass_together(self):
        compiled, report = compile_prompt(
            self.workflow,
            {"8": {"text": "自定义提示词"}},
            {"13": "bypass"},
            self.object_info,
        )
        self.assertEqual(compiled["8"]["inputs"]["text"], "自定义提示词")
        self.assertEqual(compiled["10"]["inputs"]["model"], ["5", 0])
        self.assertNotIn("13", compiled)
        self.assertTrue(report["overridden"])
        self.assertTrue(report["rewired"])

    def test_all_workflows_compile_without_modes(self):
        """ regressions：所有内置工作流在无开关时都能原样编译。"""
        folder = os.path.join(APP_ROOT, "_internal", "workflows")
        if not os.path.isdir(folder):
            raise unittest.SkipTest("缺少 workflows 目录")
        checked = 0
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".json") or name.endswith(".config.json"):
                continue
            path = os.path.join(folder, name)
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict) or "nodes" in data:
                continue  # 跳过 UI 格式的老文件
            compiled, _report = compile_prompt(data, {}, {}, self.object_info)
            self.assertEqual(set(compiled.keys()), set(data.keys()), name)
            checked += 1
        self.assertGreater(checked, 0)


class DescribeTest(unittest.TestCase):
    def setUp(self):
        self.workflow = _load_workflow()
        self.object_info = _load_object_info()

    def test_lists_every_node_with_title(self):
        items = describe_workflow(self.workflow, self.object_info)
        self.assertEqual(len(items), len(self.workflow))
        for item in items:
            self.assertTrue(item["title"], f"节点 {item['id']} 缺少标题")
            self.assertTrue(item["class_type"])

    def test_marks_output_nodes(self):
        items = {item["id"]: item for item in describe_workflow(self.workflow, self.object_info)}
        self.assertTrue(items["12"]["is_output"])
        self.assertTrue(items["22"]["is_output"])
        self.assertFalse(items["10"]["is_output"])

    def test_prefs_override_name_and_hidden(self):
        items = describe_workflow(self.workflow, self.object_info, {"8": {"name": "正向提示词", "hidden": True}})
        target = next(item for item in items if item["id"] == "8")
        self.assertEqual(target["title"], "正向提示词")
        self.assertTrue(target["hidden"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
