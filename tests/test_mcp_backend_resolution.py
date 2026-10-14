import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from myridtv_mcp_client import backend_base


class McpBackendResolution(unittest.TestCase):
    def test_config_change_is_followed_without_reimport(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'MYRIDTV_MCP_BASE':''}):
            path = Path(tmp) / 'config.json'
            path.write_text(json.dumps({'proxy':{'base_url':'http://127.0.0.1:3113/'}}))
            self.assertEqual(backend_base(path),'http://127.0.0.1:3113')
            path.write_text(json.dumps({'proxy':{'port':3114}}))
            self.assertEqual(backend_base(path),'http://127.0.0.1:3114')
            with patch.dict(os.environ, {'MYRIDTV_MCP_BASE':'http://127.0.0.1:4000/'}):
                self.assertEqual(backend_base(path),'http://127.0.0.1:4000')


if __name__ == '__main__':
    unittest.main()
