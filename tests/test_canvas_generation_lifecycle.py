from pathlib import Path
import subprocess
import unittest


class GenerationLifecycleContract(unittest.TestCase):
    def test_generation_contract(self):
        result = subprocess.run(['node', str(Path(__file__).with_suffix('.cjs'))],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
