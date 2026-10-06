"""Qwen edit output must survive unused reference slots being bypassed."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from comfy_flow_compiler import compile_prompt


class QwenEditOutputTest(unittest.TestCase):
    def test_one_to_six_references_keep_independent_output_size(self):
        workflow = json.loads((ROOT / '_internal/workflows/custom/Qwen-2.1-图生图.json').read_text(encoding='utf-8'))
        info = json.loads((ROOT / 'tests/comfy_oi_subset.json').read_text(encoding='utf-8'))
        info.update({
            'LoadImage': {'output': ['IMAGE'], 'input': {'required': {'image': ['STRING', {}]}}},
            'GetImageSize': {'output': ['INT', 'INT'], 'input': {'required': {'image': ['IMAGE', {}]}}},
            'EmptyLatentImage': {'output': ['LATENT'], 'input': {'required': {'width': ['INT', {}], 'height': ['INT', {}]}}},
        })
        slots = ['86', '90', '91', '128', '190', '191']
        for count in range(1, 7):
            with self.subTest(reference_count=count):
                compiled, _ = compile_prompt(workflow, {}, {s: 'bypass' for s in slots[count:]}, info)
                self.assertIn('71', compiled)
                self.assertEqual(compiled['85']['inputs']['latent_image'], ['154', 0])
                self.assertEqual(compiled['154']['inputs']['width'], ['155', 0])
                self.assertEqual(compiled['154']['inputs']['height'], ['155', 1])
                self.assertEqual(compiled['71']['inputs']['images'], ['120', 0])


if __name__ == '__main__':
    unittest.main()
