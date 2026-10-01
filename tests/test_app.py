import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import tempfile
import threading
import time
import unittest
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF, Qt, QEvent
from PySide6.QtGui import QMouseEvent

from app.engine import (Parameters, FrameReader, Token, Cancelled, VideoInfo,
                        inspect_video, ffmpeg_tool, run_checked, ROOT)
from app.window import MainWindow, CompareCanvas, STYLE


class VideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / "frames.mp4"
        with av.open(str(cls.path), "w") as out:
            stream = out.add_stream("libx264", rate=24)
            stream.width, stream.height = 96, 64
            stream.pix_fmt = "yuv420p"
            for index in range(12):
                pixels = np.zeros((64, 96, 3), dtype=np.uint8)
                pixels[:, :, 0] = index * 18
                frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
                frame.pts, frame.time_base = index, Fraction(1, 24)
                for packet in stream.encode(frame):
                    out.mux(packet)
            for packet in stream.encode():
                out.mux(packet)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_seek_matches_sequential_decode(self):
        token = Token()
        info = inspect_video(self.path, token)
        self.assertEqual(info.frames, 12)
        self.assertEqual(info.fps, Fraction(24))
        with av.open(str(self.path)) as video:
            expected = [np.asarray(x.to_image()) for x in video.decode(video=0)]
        reader = FrameReader()
        try:
            for index in (0, 1, 9, 3, 4, 11, 0):
                np.testing.assert_array_equal(np.asarray(reader.read(info, index, token)), expected[index])
        finally:
            reader.close()

    def test_process_cancellation_is_bounded(self):
        token = Token()
        timer = threading.Timer(0.2, token.cancel)
        timer.start()
        start = time.monotonic()
        with self.assertRaises(Cancelled):
            run_checked([sys.executable, "-c", "import time; time.sleep(15)"], token)
        timer.join()
        self.assertLess(time.monotonic() - start, 3)

    def test_bundled_ffmpeg_precedes_system(self):
        self.assertTrue(Path(ffmpeg_tool("ffmpeg")).is_relative_to(ROOT))


class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setStyleSheet(STYLE)

    def test_comparison_clips_same_coordinates(self):
        canvas = CompareCanvas()
        canvas.resize(640, 420)
        canvas.set_images(Image.new("RGB", (200, 100), "red"), Image.new("RGB", (400, 200), "blue"))
        canvas.note = ""
        canvas.split = 0.5
        canvas.show()
        self.qt.processEvents()
        image = canvas.grab().toImage()
        self.assertGreater(image.pixelColor(200, 200).red(), 240)
        self.assertGreater(image.pixelColor(440, 200).blue(), 240)
        event = QMouseEvent(QEvent.Type.MouseMove, QPointF(160, 200), QPointF(160, 200),
                            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        canvas.mouseMoveEvent(event)
        self.assertLess(canvas.split, 0.3)
        canvas.close()

    def test_stale_result_cannot_replace_new_request(self):
        window = MainWindow()
        window.auto_render.setChecked(False)
        window.info = VideoInfo("unused.mp4", 32, 32, 10, Fraction(24), 10 / 24, True, False)
        window.source = Image.new("RGB", (32, 32), "red")
        window.generation = 5
        window.on_result(4, "render", (0, Parameters(), Image.new("RGB", (64, 64), "blue"), 1))
        self.assertIsNone(window.rendered)
        window.on_result(5, "render", (0, Parameters(), Image.new("RGB", (64, 64), "blue"), 1))
        self.assertIsNotNone(window.rendered)
        window.rows["structure"].spin.setValue(1.4)
        self.assertAlmostEqual(window.parameters().structure, 1.4)
        self.assertIsNone(window.rendered)
        self.assertIsNone(window.canvas.processed)
        window.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
