import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch, MagicMock

import av
import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication

from app.engine import Token, Cancelled, VideoInfo, Parameters, DEFAULT_RUNTIME, ffmpeg_tool
from app.processing import WorkstationRuntime
from app.video_encoder import create_video_stream
from app.window import MainWindow


class EncoderTests(unittest.TestCase):
    def test_cpu_roundtrip_preserves_count_rate_size_and_colors(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'encoded.mp4'
            with av.open(str(path), 'w') as dest:
                stream = create_video_stream(dest, 96, 64, Fraction(30000, 1001), 'libx264')
                for i in range(5):
                    rgb = np.full((64, 96, 3), (30, 90, 170), np.uint8)
                    frame = av.VideoFrame.from_ndarray(rgb, format='rgb24').reformat(
                        format='yuv420p', dst_colorspace='ITU709')
                    frame.pts, frame.time_base = i, Fraction(1001, 30000)
                    for packet in stream.encode(frame): dest.mux(packet)
                for packet in stream.encode(): dest.mux(packet)
            with av.open(str(path)) as media:
                self.assertEqual(media.streams.video[0].average_rate, Fraction(30000, 1001))
                frames = list(media.decode(video=0))
                self.assertEqual(len(frames), 5)
                self.assertEqual((frames[0].width, frames[0].height), (96, 64))
                self.assertEqual(media.streams.video[0].codec_context.colorspace, 1)
                np.testing.assert_allclose(np.asarray(frames[0].to_image())[32, 48], [30, 90, 170], atol=5)

    def test_nvenc_failure_does_not_fall_back_silently(self):
        dest = MagicMock()
        dest.add_stream.side_effect = RuntimeError('device unavailable')
        with self.assertRaisesRegex(RuntimeError, 'CPU'):
            create_video_stream(dest, 1920, 1080, Fraction(30), 'h264_nvenc')
        self.assertEqual(dest.add_stream.call_count, 1)
        with self.assertRaises(ValueError):
            create_video_stream(dest, 96, 64, Fraction(30), 'untrusted')

    def test_encoder_failure_precedes_nr_and_leaves_no_result(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/'source.mp4', Path(folder)/'target.mp4'
            with av.open(str(source), 'w') as dest:
                stream = create_video_stream(dest, 96, 64, Fraction(24), 'libx264')
                for packet in stream.encode(av.VideoFrame.from_image(Image.new('RGB', (96,64)))):
                    dest.mux(packet)
                for packet in stream.encode(): dest.mux(packet)
            info = VideoInfo(str(source), 96, 64, 1, Fraction(24), 1/24, True, False)
            runtime = WorkstationRuntime(DEFAULT_RUNTIME)
            with patch.object(runtime, 'validate'), patch.object(runtime, 'frame') as nr, \
                 patch('app.processing.create_video_stream', side_effect=RuntimeError('NVENC unavailable')):
                with self.assertRaisesRegex(RuntimeError, 'NVENC'):
                    runtime.export(info, Parameters(scale=1), target, Token(), lambda *_: None,
                                   encoder='h264_nvenc')
                nr.assert_not_called()
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(folder).iterdir()), [source])

    def test_choice_invalidates_video_but_preserves_still_preview(self):
        qt = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            source, encoded = Path(folder)/'source.mp4', Path(folder)/'encoded.mp4'
            source.touch(); encoded.touch()
            window = MainWindow()
            try:
                window.info = VideoInfo(str(source), 96, 64, 12, Fraction(24), .5, True, False)
                window.source = Image.new('RGB', (96,64))
                preview = Image.new('RGB', (192,128))
                window.rendered = preview
                window.rendered_video = (window.video_key(), str(encoded))
                self.assertTrue(window.video_ready())
                self.assertEqual(window.encoder_combo.currentData(), 'h264_nvenc')
                generation = window.generation
                window.encoder_combo.setCurrentIndex(1)
                self.assertFalse(window.video_ready())
                self.assertFalse(window.export_button.isEnabled())
                self.assertIs(window.rendered, preview)
                self.assertEqual(window.generation, generation)
                self.assertFalse(window.render_timer.isActive())
                window.encoder_combo.setCurrentIndex(0)
                self.assertTrue(window.video_ready())
            finally: window.close()

    def test_explicit_ffmpeg_path_and_probe_sibling(self):
        with tempfile.TemporaryDirectory() as folder:
            ffmpeg, probe = Path(folder)/'ffmpeg.exe', Path(folder)/'ffprobe.exe'
            ffmpeg.touch(); probe.touch()
            with patch.dict(os.environ, {'FFMPEG_EXE':str(ffmpeg), 'FFPROBE_EXE':''}):
                self.assertEqual(Path(ffmpeg_tool('ffmpeg')), ffmpeg)
                self.assertEqual(Path(ffmpeg_tool('ffprobe')), probe)
            with patch.dict(os.environ, {'FFMPEG_EXE':str(ffmpeg)+'-missing'}):
                with self.assertRaisesRegex(RuntimeError, 'FFMPEG_EXE'):
                    ffmpeg_tool('ffmpeg')


if __name__ == '__main__':
    unittest.main()
