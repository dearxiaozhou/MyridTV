import copy
import unittest

from comfy_flow_compiler import CompileError, compile_prompt, describe_workflow


def node(kind, **inputs):
    return {'class_type': kind, 'inputs': inputs}


INFO = {
    'LoadImage': {'output': ['IMAGE'], 'input': {'required': {'image': ['STRING', {}]}}},
    'GetImageSize': {'output': ['INT', 'INT'], 'input': {'required': {'image': ['IMAGE', {}]}}},
    'EmptyImage': {'output': ['IMAGE'], 'input': {'required': {'width': ['INT', {}], 'height': ['INT', {}]}}},
    'SaveImage': {'output_node': True, 'input': {'required': {'images': ['IMAGE', {}]}}},
    'PreviewImage': {'output_node': True, 'input': {'required': {'images': ['IMAGE', {}]}}},
    'CustomResult': {'output_node': True, 'output': ['IMAGE'], 'input': {'required': {'images': ['IMAGE', {}]}}},
}


class OutputProtectionTest(unittest.TestCase):
    def graph(self):
        return {'1': node('LoadImage', image='missing.png'),
                '2': node('GetImageSize', image=['1', 0]),
                '3': node('EmptyImage', width=['2', 0], height=['2', 1]),
                '4': node('SaveImage', images=['3', 0])}

    def test_missing_size_reference_rejected_with_dependency_path(self):
        graph = self.graph()
        before = copy.deepcopy(graph)
        with self.assertRaisesRegex(CompileError, r'#1 LoadImage.*#2 GetImageSize.*#4 SaveImage'):
            compile_prompt(graph, {}, {'1': 'bypass'}, INFO)
        self.assertEqual(graph, before)

    def test_partial_main_output_loss_is_not_silently_accepted(self):
        graph = self.graph()
        graph.update({'5': node('EmptyImage', width=64, height=64),
                      '6': node('SaveImage', images=['5', 0])})
        with self.assertRaisesRegex(CompileError, '无法安全裁剪'):
            compile_prompt(graph, {}, {'1': 'bypass'}, INFO)

    def test_unused_preview_can_be_removed(self):
        graph = {'1': node('LoadImage', image='missing.png'),
                 '2': node('PreviewImage', images=['1', 0]),
                 '3': node('EmptyImage', width=64, height=64),
                 '4': node('SaveImage', images=['3', 0])}
        result, _ = compile_prompt(graph, {}, {'1': 'bypass'}, INFO)
        self.assertNotIn('2', result)
        self.assertIn('4', result)

    def test_preview_only_output_is_protected(self):
        graph = self.graph()
        graph['4']['class_type'] = 'PreviewImage'
        with self.assertRaises(CompileError):
            compile_prompt(graph, {}, {'1': 'bypass'}, INFO)

    def test_custom_output_is_protected_even_when_connected(self):
        graph = self.graph()
        graph['4']['class_type'] = 'CustomResult'
        graph['5'] = node('SaveImage', images=['4', 0])
        items = {item['id']: item for item in describe_workflow(graph, INFO)}
        self.assertTrue(items['4']['is_output'])
        with self.assertRaises(CompileError):
            compile_prompt(graph, {}, {'1': 'bypass'}, INFO)

    def test_explicit_output_disable_with_another_output_is_allowed(self):
        graph = self.graph()
        graph.update({'5': node('EmptyImage', width=64, height=64),
                      '6': node('SaveImage', images=['5', 0])})
        result, _ = compile_prompt(graph, {}, {'1': 'bypass', '4': 'bypass'}, INFO)
        self.assertIn('6', result)

    def test_safe_bypass_rewiring_keeps_output(self):
        graph = {'1': node('EmptyImage', width=64, height=64),
                 '2': node('ImageEffect', image=['1', 0]),
                 '3': node('SaveImage', images=['2', 0])}
        info = {**INFO, 'ImageEffect': {'output': ['IMAGE'], 'input': {'required': {'image': ['IMAGE', {}]}}}}
        result, _ = compile_prompt(graph, {}, {'2': 'bypass'}, info)
        self.assertEqual(result['3']['inputs']['images'], ['1', 0])

    def test_no_output_after_explicit_disable_is_rejected(self):
        with self.assertRaisesRegex(CompileError, '没有可执行的输出'):
            compile_prompt(self.graph(), {}, {'4': 'bypass'}, INFO)

    def test_declared_non_output_save_prefix_is_not_an_output(self):
        info = {**INFO, 'SaveIntermediate': {'output_node': False}}
        items = describe_workflow({'1': node('SaveIntermediate')}, info)
        self.assertFalse(items[0]['is_output'])


if __name__ == '__main__':
    unittest.main()
