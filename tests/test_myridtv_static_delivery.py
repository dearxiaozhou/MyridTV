# -*- coding: utf-8 -*-
"""Regression coverage for automatic cache versions on managed static assets."""
import tempfile
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import myridtv_static_delivery as delivery


class StaticVersionPatchingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        static_dir = self.root / "static"
        static_dir.mkdir()
        self.page = static_dir / "smart-canvas.html"
        self.old_patches = delivery._STATIC_PATCHES
        self.old_getter = delivery._static_version_getter
        delivery.configure(self.root, lambda: "build-42")

    def tearDown(self):
        delivery._STATIC_PATCHES = self.old_patches
        delivery._static_version_getter = self.old_getter
        self.temp.cleanup()

    def test_discovers_unlisted_local_cb_assets_and_is_idempotent(self):
        self.page.write_text(
            '\n'.join([
                '<script src="/static/js/canvas-viewport-engine.js?cb=known"></script>',
                '<script src="/static/js/new-controller.js?cb=new-v1"></script>',
                '<link href="/static/css/new-module.css?cb=style-v1" rel="stylesheet">',
                '<iframe data-src="/static/canvas.html?cb=page-v3"></iframe>',
                '<script src="/static/js/new-double.js?cb=double&v=stale"></script>',
                '<script src="/static/js/canvas-render-scheduler.js?v=stale"></script>',
                '<script src="/static/js/unlisted-v.js?v=manual"></script>',
                '<script src="https://cdn.example.test/vendor.js?cb=external"></script>',
            ]),
            encoding="utf-8",
        )

        delivery.patch_static_versions_once()
        first = self.page.read_text(encoding="utf-8")
        delivery.patch_static_versions_once()
        second = self.page.read_text(encoding="utf-8")

        self.assertEqual(first, second)
        self.assertIn('/static/js/canvas-viewport-engine.js?cb=known&v=build-42', first)
        self.assertIn('/static/js/new-controller.js?cb=new-v1&v=build-42', first)
        self.assertIn('/static/css/new-module.css?cb=style-v1&v=build-42', first)
        self.assertIn('/static/canvas.html?cb=page-v3&v=build-42', first)
        self.assertIn('/static/js/new-double.js?cb=double&v=build-42', first)
        self.assertIn('/static/js/canvas-render-scheduler.js?v=build-42', first)
        self.assertIn('/static/js/unlisted-v.js?v=manual', first)
        self.assertIn('https://cdn.example.test/vendor.js?cb=external', first)


if __name__ == "__main__":
    unittest.main(verbosity=2)
