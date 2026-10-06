"""Security and rollback checks for the static update path."""

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import myridtv_updater as updater


class StaticUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / "app"
        self.app.mkdir()
        (self.app / "VERSION").write_text("V0.9.14\n", encoding="utf-8")
        (self.app / "_internal/static/css").mkdir(parents=True)
        self.target = self.app / "_internal/static/css/example.css"
        self.target.write_bytes(b"old css")
        self.key = Ed25519PrivateKey.generate()
        public = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.public_file = self.root / "public.pub"
        self.public_file.write_text(base64.b64encode(public).decode(), encoding="ascii")
        self.blob = self.root / "blob"
        self.blob.write_bytes(b"new css")
        self.feed = self.root / "manifest.json"
        self.state_root = self.root / "userdata"
        self.env = mock.patch.dict("os.environ", {"MYRIDTV_USER_DATA_DIR": str(self.state_root)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def manifest(self, *, url=None, digest=None, path="_internal/static/css/example.css"):
        data = self.blob.read_bytes()
        item = {
            "path": path,
            "sha256": digest or updater.sha256(data),
            "size": len(data),
            "url": url or self.blob.as_uri(),
        }
        manifest = {"schema": 1, "version": "V0.9.15", "files": [item]}
        manifest["signature"] = base64.b64encode(self.key.sign(updater.canonical_payload(manifest))).decode("ascii")
        self.feed.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest

    def test_only_changed_file_downloaded_and_state_written(self):
        self.manifest()
        result = updater.check_once(self.app, self.feed.as_uri(), self.public_file, allow_local=True)
        self.assertEqual(result["downloaded_files"], 1)
        self.assertEqual(self.target.read_bytes(), b"new css")
        self.assertEqual(updater.current_version(self.app), "V0.9.15")
        result = updater.check_once(self.app, self.feed.as_uri(), self.public_file, allow_local=True)
        self.assertEqual(result["downloaded_files"], 0)

    def test_signature_and_digest_fail_closed(self):
        manifest = self.manifest()
        manifest["version"] = "V0.9.16"
        self.feed.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(Exception):
            updater.check_once(self.app, self.feed.as_uri(), self.public_file, allow_local=True)
        self.assertEqual(self.target.read_bytes(), b"old css")
        self.manifest(digest="0" * 64)
        with self.assertRaises(ValueError):
            updater.check_once(self.app, self.feed.as_uri(), self.public_file, allow_local=True)
        self.assertEqual(self.target.read_bytes(), b"old css")

    def test_rollback_if_commit_fails(self):
        self.manifest()
        with mock.patch.object(updater, "write_state", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                updater.check_once(self.app, self.feed.as_uri(), self.public_file, allow_local=True)
        self.assertEqual(self.target.read_bytes(), b"old css")

    def test_traversal_rejected(self):
        self.manifest(path="_internal/static/../data/app_config.json")
        with self.assertRaises(ValueError):
            updater.check_once(self.app, self.feed.as_uri(), self.public_file, allow_local=True)
        self.assertEqual(self.target.read_bytes(), b"old css")

    def test_recovers_interrupted_install_on_next_check(self):
        backup = updater.update_dir(self.app) / "backups/V0.9.14/_internal/static/css/example.css"
        backup.parent.mkdir(parents=True)
        backup.write_bytes(b"old css")
        updater.write_json_atomic(updater.journal_path(self.app), {
            "previous_version": "V0.9.14",
            "previous_state": {},
            "files": [{"path": "_internal/static/css/example.css", "existed": True}],
        })
        self.target.write_bytes(b"half-installed")
        self.manifest()
        result = updater.check_once(self.app, self.feed.as_uri(), self.public_file, allow_local=True)
        self.assertEqual(result["downloaded_files"], 1)
        self.assertEqual(self.target.read_bytes(), b"new css")
        self.assertFalse(updater.journal_path(self.app).exists())


if __name__ == "__main__":
    unittest.main()
