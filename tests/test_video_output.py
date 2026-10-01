import tempfile
import unittest
from pathlib import Path
from app.engine import Token, Cancelled
from app.video_output import publish_video


class VideoOutputTests(unittest.TestCase):
    def test_publish_preserves_bytes_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / 'cache.mp4', Path(folder) / 'saved.mp4'
            source.write_bytes(bytes(range(256)) * 1024)
            publish_video(source, target, Token())
            self.assertEqual(target.read_bytes(), source.read_bytes())
            with self.assertRaises(ValueError):
                publish_video(source, target, Token())
            self.assertEqual(target.read_bytes(), source.read_bytes())

    def test_cancelled_copy_leaves_no_partial_output(self):
        class CancelDuringCopy(Token):
            calls = 0
            def check(self):
                self.calls += 1
                if self.calls == 3:
                    self.cancel()
                super().check()
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / 'cache.mp4', Path(folder) / 'saved.mp4'
            source.write_bytes(b'x' * (5 * 1024 * 1024))
            with self.assertRaises(Cancelled):
                publish_video(source, target, CancelDuringCopy())
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(folder).iterdir()), [source])
