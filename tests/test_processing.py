import unittest
from dataclasses import replace
import numpy as np
from PIL import Image
from app.engine import Parameters, Token, DEFAULT_RUNTIME
from app.processing import WorkstationRuntime, to_linear, from_linear


class EchoSession:
    def call(self, pixels, params, token, reset=True):
        return pixels.copy()


class ColorTests(unittest.TestCase):
    def test_nr_receives_display_rgb_and_decodes_display_output(self):
        captured = []
        class DisplaySession:
            def call(self, pixels, params, token, reset=True):
                captured.append(pixels.copy())
                result = np.ones_like(pixels)
                result[:, :, :3] = np.array([64, 128, 192], np.float32) / 255
                return result
        runtime = WorkstationRuntime(DEFAULT_RUNTIME)
        runtime.nr = DisplaySession()
        source = np.array([[[128, 64, 192], [0, 255, 20]]], np.uint8)
        result = runtime.frame(Image.fromarray(source), Parameters(scale=1), Token(), True)
        np.testing.assert_allclose(captured[0][:, :, :3], source / 255, atol=.00025)
        np.testing.assert_array_equal(captured[0][:, :, 3], 1)
        np.testing.assert_array_equal(np.asarray(result), [[[64, 128, 192], [64, 128, 192]]])

    def test_preserve_chroma_scales_source_rgb_without_adding_gray(self):
        source = np.array([[[.12, .06, .03], [0, 0, 0]]], np.float32)
        # A neutral NR result with twice the source luminance.
        luma = source @ np.array([.2126, .7152, .0722], np.float32)
        result = np.repeat((luma * 2)[:, :, None], 3, axis=2)
        result[0, 1] = .1
        output = WorkstationRuntime.compose(source, result, Parameters(color=0), Token())
        expected = source * 2
        expected[0, 1] = .1
        np.testing.assert_array_equal(np.asarray(output), from_linear(expected))
        raw = WorkstationRuntime.compose(source, result, Parameters(color=1), Token())
        np.testing.assert_array_equal(np.asarray(raw), from_linear(result))

    def test_reference_white_roundtrip_does_not_act_as_exposure(self):
        rgb = np.arange(256, dtype=np.uint8)[None, :, None].repeat(3, axis=2)
        runtime = WorkstationRuntime(DEFAULT_RUNTIME)
        runtime.nr = EchoSession()
        for enabled in (False, True):
            for white in (40, 48, 100, 292, 500):
                output = runtime.frame(Image.fromarray(rgb), Parameters(scale=1, white=white, white_enabled=enabled), Token(), reset=True)
                np.testing.assert_array_equal(np.asarray(output), rgb)

    def test_experimental_white_changes_input_only_when_enabled(self):
        captured = []
        class Capture:
            def call(self, pixels, params, token, reset=True):
                captured.append(pixels.copy())
                return pixels.copy()
        runtime = WorkstationRuntime(DEFAULT_RUNTIME)
        runtime.nr = Capture()
        rgb = np.array([[[128, 64, 192]]], np.uint8)
        for white in (48, 100):
            runtime.frame(Image.fromarray(rgb), Parameters(scale=1, white=white, white_enabled=True), Token(), True)
            np.testing.assert_allclose(captured[-1][:,:,:3], to_linear(rgb)*(white/80), rtol=.001)
        self.assertFalse(np.array_equal(captured[0], captured[1]))

    def test_srgb_roundtrip(self):
        values = np.arange(256, dtype=np.uint8)
        np.testing.assert_array_equal(from_linear(to_linear(values)), values)

    def test_zero_mix_returns_original_at_every_white(self):
        class AlterSession:
            def call(self, pixels, params, token, reset=True):
                return pixels * .7
        runtime = WorkstationRuntime(DEFAULT_RUNTIME)
        runtime.nr = AlterSession()
        original = np.random.default_rng(7).integers(0, 256, (40, 50, 3), dtype=np.uint8)
        for white in (48, 100, 292):
            output = runtime.frame(Image.fromarray(original), Parameters(scale=1, white=white, detail=0), Token(), reset=True)
            np.testing.assert_array_equal(np.asarray(output), original)

    def test_minimum_window_contains_controls(self):
        from PySide6.QtWidgets import QApplication
        from app.window import MainWindow
        app = QApplication.instance() or QApplication([])
        w = MainWindow()
        try:
            w.resize(w.minimumSize())
            w.show()
            app.processEvents()
            self.assertGreaterEqual(w.canvas.height(), 230)
            for control in (w.export_button, w.rows['white'], w.pass_combo, w.mask_check):
                point = control.mapTo(w, control.rect().bottomRight())
                self.assertLess(point.x(), w.width())
                self.assertLess(point.y(), w.height())
            self.assertFalse(w.rows['white'].isEnabled())
            self.assertFalse(w.parameters().white_enabled)
            w.white_check.setChecked(True)
            self.assertTrue(w.rows['white'].isEnabled())
            self.assertTrue(w.parameters().white_enabled)
            w.reset_parameters()
            self.assertFalse(w.rows['white'].isEnabled())
            self.assertFalse(w.parameters().white_enabled)
        finally:
            w.close()

if __name__ == '__main__':
    unittest.main()
