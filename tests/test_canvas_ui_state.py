"""Run the transient UI-state contract in the existing self-check gate."""
from pathlib import Path
import subprocess
import unittest


class CanvasUiStateContract(unittest.TestCase):
    def test_ui_state_contract(self):
        result = subprocess.run(['node', str(Path(__file__).with_suffix('.cjs'))],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
