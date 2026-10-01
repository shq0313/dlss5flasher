import unittest
from app.render_progress import FrameTimeEstimate, progress_text


class RenderProgressTests(unittest.TestCase):
    def test_uses_exactly_frames_two_through_eleven(self):
        estimate = FrameTimeEstimate()
        # A long first frame must not contaminate the ten measured frames.
        clock = 500
        self.assertIsNone(estimate.update(1, 100, clock))
        for frame in range(2, 12):
            clock += frame  # samples 2..11 seconds, mean 6.5
            remaining = estimate.update(frame, 100, clock)
            if frame < 11:
                self.assertIsNone(remaining)
        self.assertEqual(remaining, 6.5 * 89)
        # A much slower later frame must not change the fixed sample mean.
        self.assertEqual(estimate.update(12, 100, clock + 1000), 6.5 * 88)
        self.assertEqual(estimate.update(100, 100, clock + 2000), 0)

    def test_short_clip_and_fresh_task(self):
        estimate = FrameTimeEstimate()
        self.assertIsNone(estimate.update(1, 8, 100))
        self.assertEqual(estimate.update(2, 8, 102), 12)
        self.assertEqual(estimate.update(3, 8, 106), 15)
        self.assertEqual(estimate.update(8, 8, 116), 0)
        self.assertIsNone(FrameTimeEstimate().update(1, 8, 999))

    def test_display_format_and_finishing_stage(self):
        self.assertIn('计算中', progress_text(2, 344))
        self.assertIn('50% · 预计剩余 01:01:02', progress_text(50, 100, 3661.2))
        self.assertIn('25:00:00', progress_text(50, 100, 90000))
        self.assertIn('00:00:01', progress_text(99, 100, .1))
        self.assertIn('100% · 预计剩余 00:00:00 · 正在合并音频', progress_text(100, 100))


if __name__ == '__main__':
    unittest.main()
