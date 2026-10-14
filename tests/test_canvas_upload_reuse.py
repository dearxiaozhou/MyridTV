"""A canvas's existing image must not be copied back onto itself on import."""
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from myridtv_media_localize import save_uploaded_file


class CanvasUploadReuseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def upload(self, name='图片.png', content=b'first image', root=None):
        return save_uploaded_file({'file_name': name, 'content_type': 'image/png', 'data': content},
                                  root or self.root, '/assets/output/fixture', {'image': 'images'})

    def test_import_existing_image_leaves_bytes_and_timestamp_unchanged(self):
        directory = self.root / 'images'
        directory.mkdir()
        original = directory / '图片.png'
        original.write_bytes(b'first image')
        before = original.stat().st_mtime_ns
        result = self.upload()
        self.assertTrue(result['reused'])
        self.assertEqual(result['filename'], original.name)
        self.assertEqual(original.stat().st_mtime_ns, before)
        self.assertEqual(list(directory.iterdir()), [original])

    def test_same_name_different_bytes_never_overwrites_and_repeat_reuses_suffix(self):
        first = self.upload()
        second = self.upload(content=b'other image')
        third = self.upload(content=b'other image')
        self.assertFalse(first['reused'])
        self.assertFalse(second['reused'])
        self.assertNotEqual(first['url'], second['url'])
        self.assertEqual(second['url'], third['url'])
        self.assertTrue(third['reused'])
        self.assertEqual((self.root / 'images' / first['filename']).read_bytes(), b'first image')
        self.assertEqual(len(list((self.root / 'images').iterdir())), 2)

    def test_same_suffixed_source_name_reuses_exact_file(self):
        first = self.upload(name='图片-2.png')
        second = self.upload(name='图片-2.png')
        self.assertEqual(first['url'], second['url'])
        self.assertTrue(second['reused'])

    def test_existing_long_filename_is_reused_without_truncating_it(self):
        name = 'long-title-' * 10 + '.png'
        directory = self.root / 'images'
        directory.mkdir()
        (directory / name).write_bytes(b'first image')
        result = self.upload(name=name)
        self.assertTrue(result['reused'])
        self.assertEqual(result['filename'], name)
        self.assertEqual(len(list(directory.iterdir())), 1)

    def test_another_canvas_gets_its_own_copy(self):
        self.upload()
        result = self.upload(root=self.root / 'another-canvas')
        self.assertFalse(result['reused'])
        self.assertTrue((self.root / 'another-canvas/images/图片.png').exists())

    def test_concurrent_identical_imports_create_one_file(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.upload(), range(4)))
        self.assertEqual(len({r['url'] for r in results}), 1)
        self.assertEqual(sum(not r['reused'] for r in results), 1)
        self.assertEqual(len(list((self.root / 'images').iterdir())), 1)


if __name__ == '__main__':
    unittest.main()
