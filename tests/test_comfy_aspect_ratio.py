import copy
import unittest
from unittest.mock import patch

import comfy_flow_compiler as compiler
import myridtv_comfy


CHOICES = ["1:1 (Square)", "9:16 (Portrait Widescreen)", "16:9 (Widescreen)"]


class AspectRatioTest(unittest.TestCase):
    def graph(self, value="1:1 (Square)"):
        return {"29": {"class_type": "ResolutionSelector", "inputs": {"aspect_ratio": value}},
                "22": {"class_type": "SaveImage", "inputs": {"images": ["29", 0]}}}

    def metadata(self, legacy=False, choices=CHOICES):
        spec = [choices, {}] if legacy else ["COMBO", {"options": choices}]
        return {"ResolutionSelector": {"input": {"required": {"aspect_ratio": spec}}}}

    def test_saved_canvas_override_both_metadata_formats(self):
        for legacy in (False, True):
            source = self.graph()
            before = copy.deepcopy(source)
            result, _ = compiler.compile_prompt(source, {"29": {"aspect_ratio": " 9 : 16 "}},
                                                object_info=self.metadata(legacy))
            self.assertEqual(result["29"]["inputs"]["aspect_ratio"], CHOICES[1])
            self.assertEqual(source, before)

    def test_does_not_guess_or_replace_other_values(self):
        for value in ("4:5", "original", CHOICES[1], ["30", 0]):
            graph = self.graph(value)
            compiler.normalize_aspect_ratios(graph, self.metadata())
            self.assertEqual(graph["29"]["inputs"]["aspect_ratio"], value)
        graph = self.graph("9:16")
        compiler.normalize_aspect_ratios(graph, self.metadata(choices=["9:16 (A)", "9:16 (B)"]))
        self.assertEqual(graph["29"]["inputs"]["aspect_ratio"], "9:16")

    def test_all_node_types_and_input_names(self):
        graph = {"1": {"class_type": "OtherPlugin", "inputs": {
            "ratio": "16:9", "画面比例": "9:16", "prompt": "9:16"}}}
        metadata = {"OtherPlugin": {"input": {
            "required": {"ratio": [list(CHOICES), {}], "prompt": ["STRING", {}]},
            "optional": {"画面比例": ["COMBO", {"options": CHOICES}]}}}}
        compiler.normalize_aspect_ratios(graph, metadata)
        self.assertEqual(graph["1"]["inputs"]["ratio"], CHOICES[2])
        self.assertEqual(graph["1"]["inputs"]["画面比例"], CHOICES[1])
        self.assertEqual(graph["1"]["inputs"]["prompt"], "9:16")
        graph["1"]["inputs"]["ratio"] = "16:9"
        metadata["OtherPlugin"]["input"]["required"]["ratio"][0].append("16:9")
        compiler.normalize_aspect_ratios(graph, metadata)
        self.assertEqual(graph["1"]["inputs"]["ratio"], "16:9")

    def test_workflow_run_fields_and_params_paths(self):
        record = {"workflow": self.graph(), "config": {"fields": [
            {"id": "ratio", "node": "29", "input": "aspect_ratio", "type": "text"}]}}
        for payload in ({"fields": {"ratio": "9:16"}},
                        {"params": {"29": {"aspect_ratio": "9:16"}}}):
            with patch.object(myridtv_comfy, "_r_read_workflow_record", return_value=record), \
                 patch.object(myridtv_comfy.comfy_flow_service, "load_object_info", return_value=self.metadata()), \
                 patch.object(myridtv_comfy, "comfy_check_media_files"):
                result = myridtv_comfy.build_comfy_workflow_prompt("test", payload)
            self.assertEqual(result["29"]["inputs"]["aspect_ratio"], CHOICES[1])


if __name__ == "__main__":
    unittest.main()
