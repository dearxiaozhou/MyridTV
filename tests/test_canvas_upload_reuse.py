"""Existing canvas media must not be copied back onto itself on import."""
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

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

    def test_all_canvas_output_folders_reuse_without_overwriting(self):
        folders = {'image':'images','video':'videos','audio':'audios','*':'files'}
        for name, mime, folder in [('picture.png','image/png','images'),('clip.mp4','video/mp4','videos'),
                                   ('voice.wav','audio/wav','audios'),('notes.txt','text/plain','files')]:
            with self.subTest(folder=folder), patch('myridtv_media_localize.myridtv_video_codec.ensure_playable_video') as codec:
                directory = self.root / folder
                directory.mkdir()
                original = directory / name
                original.write_bytes(b'original bytes')
                before = original.stat().st_mtime_ns
                def upload(data=b'original bytes', root=self.root):
                    return save_uploaded_file({'file_name':name,'content_type':mime,'data':data},
                                              root, '/assets/output/fixture', folders)
                result = upload()
                self.assertTrue(result['reused'])
                self.assertEqual(result['filename'], name)
                self.assertEqual(original.stat().st_mtime_ns, before)
                self.assertEqual(list(directory.iterdir()), [original])
                codec.assert_not_called()  # Re-import must not mutate an existing video.
                changed = upload(b'different bytes')
                repeated = upload(b'different bytes')
                self.assertFalse(changed['reused'])
                self.assertTrue(repeated['reused'])
                self.assertEqual(changed['url'], repeated['url'])
                self.assertEqual(original.read_bytes(), b'original bytes')
                self.assertEqual(len(list(directory.iterdir())), 2)
                other = upload(root=self.root / ('other-'+folder))
                self.assertFalse(other['reused'])

    def test_concurrent_audio_imports_create_one_file(self):
        def upload(_):
            return save_uploaded_file({'file_name':'voice.wav','content_type':'audio/wav','data':b'audio'},
                                      self.root, '/assets/output/fixture', {'audio':'audios'})
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(upload, range(4)))
        self.assertEqual(sum(not r['reused'] for r in results), 1)
        self.assertEqual(len(list((self.root / 'audios').iterdir())), 1)

    def test_unknown_mime_keeps_aac_and_m4v_in_their_media_folders(self):
        for name, kind, folder in [('voice.aac','audio','audios'),('clip.m4v','video','videos')]:
            with self.subTest(name=name), patch('myridtv_media_localize.myridtv_video_codec.ensure_playable_video') as codec:
                directory=self.root / folder
                directory.mkdir()
                (directory / name).write_bytes(b'existing media')
                result=save_uploaded_file({'file_name':name,'content_type':'application/octet-stream','data':b'existing media'},
                                          self.root,'/assets/output/fixture',{'audio':'audios','video':'videos','*':'files'})
                self.assertEqual(result['kind'],kind)
                self.assertTrue(result['reused'])
                self.assertIn('/'+folder+'/',result['url'])
                self.assertFalse((self.root / 'files').exists())
                codec.assert_not_called()


if __name__ == '__main__':
    unittest.main()
