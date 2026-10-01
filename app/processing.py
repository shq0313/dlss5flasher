"""Persistent local DX12 NR and RTX Video workers, shared by preview and export."""
from __future__ import annotations
import multiprocessing as mp
import threading
import time
import tempfile
import hashlib
from dataclasses import asdict
from fractions import Fraction
from pathlib import Path
import av
import numpy as np
from PIL import Image
from .engine import ROOT, WORK, Token, ffmpeg_tool, run_checked
from .native_worker import worker


def to_linear(rgb):
    value = rgb.astype(np.float32) / 255
    return srgb_to_linear(value)


def srgb_to_linear(value):
    """Decode normalized display RGB, including the float16 NR output."""
    value = np.maximum(value, 0).astype(np.float32)
    return np.where(value <= .04045, value / 12.92, ((value + .055) / 1.055) ** 2.4)


def from_linear(value):
    value = np.maximum(value, 0)
    rgb = np.where(value <= .0031308, value * 12.92, 1.055 * value ** (1 / 2.4) - .055)
    return np.uint8(np.clip(np.rint(rgb * 255), 0, 255))


class Session:
    def __init__(self, kind, runtime):
        self.kind, self.runtime = kind, runtime
        self.process = self.pipe = None
        self.profile = None

    def stop(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(3)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(3)
            self.process.close()
            self.process = None
        if self.pipe is not None:
            self.pipe.close()
            self.pipe = None

    def call(self, pixels, params, token, reset=True):
        token.check()
        if self.kind == 'nr' and self.profile != params.white_enabled:
            # A colour-contract change needs a fresh NGX session and history.
            self.stop()
            self.profile = params.white_enabled
        if self.process is None or not self.process.is_alive():
            self.stop()
            ctx = mp.get_context('spawn')
            self.pipe, child = ctx.Pipe()
            self.process = ctx.Process(target=worker, args=(child, self.kind, self.runtime), daemon=True)
            self.process.start()
            child.close()
        # Sending and receiving large frames can block; poll a helper while the
        # owner retains cancellation and deadline control over the child.
        reply, errors = [], []
        completed = threading.Event()
        connection = self.pipe
        def exchange():
            try:
                connection.send((pixels, asdict(params), reset))
                reply.append(connection.recv())
            except BaseException as exc:
                errors.append(str(exc))
            finally:
                completed.set()
        transfer = threading.Thread(target=exchange, daemon=True)
        transfer.start()
        try:
            start = time.monotonic()
            while not completed.wait(.025):
                token.check()
                if time.monotonic() - start > 120:
                    raise RuntimeError(f'{self.kind} 超过 120 秒没有返回，已终止原生进程。')
            token.check()
            if errors:
                raise RuntimeError(f'{self.kind} 原生进程退出：{errors[0]}')
            ok, value = reply[0]
            if not ok:
                raise RuntimeError(value)
            return value
        except BaseException:
            self.stop()
            transfer.join(3)
            raise


class WorkstationRuntime:
    def __init__(self, executable):
        self.executable = Path(executable)
        runtime = str(self.executable.parent / 'nvngx_dlssnr.dll')
        self.nr = Session('nr', runtime)
        self.sr = Session('vsr', runtime)
        self.cached_source = self.cached_upscale = self.cached_scale = None
        self.preview_key = self.preview_buffers = None

    def validate(self):
        nr_dll = self.executable.parent / 'nvngx_dlssnr.dll'
        if not nr_dll.is_file():
            raise RuntimeError('发布包不附带 NR 运行库。请自行准备匹配显卡的 nvngx_dlssnr.dll，'
                               '放入 runtime/DLSS-NR/1.3/bin/，或点击右上角“运行库”选择它。')
        for path in (ROOT / 'runtime/dlssnr_host_v2.dll', self.executable.parent / 'nvngx_dlssnr.dll',
                     ROOT / 'runtime/RTX-Video/vsr_host.dll', ROOT / 'runtime/RTX-Video/nvngx_vsr.dll'):
            if not path.is_file():
                raise RuntimeError(f'缺少本地运行库：{path}')

    def close(self):
        self.nr.stop()
        self.sr.stop()
        self.cached_source = self.cached_upscale = None
        self.preview_key = self.preview_buffers = None

    def frame(self, original, params, token, reset, cache=False, remember=False):
        token.check()
        if params.scale not in (1, 2, 4) or not 1 <= params.passes <= 4 or not 40 <= params.white <= 500:
            raise ValueError('倍率、处理次数或参考白超出支持范围。')
        rgba = np.array(original.convert('RGBA'))
        if params.scale != 1:
            if cache and self.cached_scale == params.scale and self.cached_source is not None and np.array_equal(rgba, self.cached_source):
                upscaled = self.cached_upscale
            else:
                upscaled = self.sr.call(rgba, params, token)
                if cache:
                    self.cached_source, self.cached_upscale, self.cached_scale = rgba, upscaled, params.scale
            rgba = upscaled
        linear = to_linear(rgba[:, :, :3])
        nr_input = np.ones(rgba.shape, dtype=np.float16)
        # SDR is already display-referred: the NR texture contains encoded
        # sRGB, even though its storage format is RGBA16F. Do not send scRGB
        # luminance or apply an HDR paper-white transform to this signal.
        nr_input[:, :, :3] = rgba[:, :, :3].astype(np.float32) / 255
        if params.white_enabled:
            # Explicit opt-in to the old reference-white experiment, NOT a
            # verified RenoDX Diffuse White implementation. Default stays sRGB.
            nr_input[:, :, :3] = linear * (params.white / 80)
        enhanced = self.nr.call(nr_input, params, token, reset=reset)
        result = (enhanced[:, :, :3].astype(np.float32) * (80 / params.white)
                  if params.white_enabled else srgb_to_linear(enhanced[:, :, :3]))
        if remember:
            self.preview_buffers = linear, result
        return self.compose(linear, result, params, token)

    @staticmethod
    def compose(linear, result, params, token):
        # This runtime ignores the experimental GlobalToneStrength key. Use an
        # explicit, app-owned low-frequency luminance blend, never a dummy slider.
        if params.global_tone != 1:
            delta_luma = (result - linear) @ np.array([.2126, .7152, .0722], np.float32)
            h, w = delta_luma.shape
            coarse = Image.fromarray(delta_luma).resize((max(1, round(w / max(w, h) * 16)),
                                                        max(1, round(h / max(w, h) * 16))), Image.Resampling.BOX)
            broad = np.asarray(coarse.resize((w, h), Image.Resampling.BILINEAR))
            result = result + broad[:, :, None] * (params.global_tone - 1)
        # Preserve source chroma if requested; retain NR's luminance adjustments.
        if params.color < 1:
            weights = np.array([.2126, .7152, .0722], np.float32)
            original_luma = linear @ weights
            processed_luma = result @ weights
            # Scale source RGB together: adding an equal amount to all channels
            # lifts blacks and dilutes chroma when NR brightens the source.
            ratio = processed_luma / np.maximum(original_luma, 1e-8)
            preserved = linear * ratio[:, :, None]
            # Absolute black has no chromaticity; NR can still add illumination.
            preserved = np.where((original_luma <= 1e-8)[:, :, None],
                                 processed_luma[:, :, None], preserved)
            result = preserved * (1 - params.color) + result * params.color
        result = linear + (result - linear) * params.detail
        token.check()
        return Image.fromarray(from_linear(result))

    def render(self, original, params, token, history=()):
        self.validate()
        WORK.mkdir(exist_ok=True)
        start = time.perf_counter()
        raw_settings = {k: v for k, v in asdict(params).items()
                        if k not in ('global_tone', 'color', 'detail', 'sr_preset', 'white')}
        if params.white_enabled:
            raw_settings['white'] = params.white
        digest = hashlib.blake2b(digest_size=20)
        digest.update(repr(raw_settings).encode())
        for frame in (*history, original):
            digest.update(str(frame.size).encode())
            digest.update(frame.convert('RGB').tobytes())
        key = digest.digest()
        if key == self.preview_key and self.preview_buffers is not None:
            result = self.compose(*self.preview_buffers, params, token)
            return result, time.perf_counter() - start
        self.preview_key = None
        for index, frame in enumerate(history):
            self.frame(frame, params, token, reset=index == 0)
        result = self.frame(original, params, token, reset=not history, cache=True, remember=True)
        self.preview_key = key
        return result, time.perf_counter() - start

    def export(self, info, params, output_path, token, progress):
        self.validate()
        token.check()
        out = Path(output_path).resolve()
        if out == Path(info.path).resolve() or out.exists():
            raise ValueError('请选择一个新的输出文件，不能覆盖已有文件。')
        w, h = int(info.width * params.scale), int(info.height * params.scale)
        if w % 2 or h % 2:
            raise ValueError('H.264 输出宽高必须为偶数。')
        out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.dlss-export-', dir=out.parent) as directory:
            temp = Path(directory)
            video, combined = temp / 'video.mp4', temp / 'complete.mp4'
            with av.open(info.path) as source, av.open(str(video), 'w') as dest:
                stream = dest.add_stream('libx264', rate=info.fps)
                stream.width, stream.height, stream.pix_fmt = w, h, 'yuv420p'
                stream.options = {'crf': '18', 'preset': 'fast'}
                stream.codec_context.color_primaries = 1
                stream.codec_context.color_trc = 1
                stream.codec_context.colorspace = 1
                count, first = 0, None
                for frame in source.decode(video=0):
                    token.check()
                    timestamp = frame.pts * frame.time_base if frame.pts is not None else None
                    if timestamp is None:
                        raise ValueError('源视频缺少帧时间戳。')
                    first = timestamp if first is None else first
                    if abs(timestamp - first - Fraction(count, 1) / info.fps) > Fraction(1, 4) / info.fps:
                        raise ValueError('检测到可变帧率，已停止导出。')
                    result = self.frame(frame.to_image(), params, token, reset=count == 0)
                    encoded = av.VideoFrame.from_image(result).reformat(format='yuv420p', dst_colorspace='ITU709')
                    encoded.pts, encoded.time_base = count, 1 / info.fps
                    for packet in stream.encode(encoded):
                        dest.mux(packet)
                    count += 1
                    progress(count, info.frames)
                if count != info.frames:
                    raise ValueError(f'源视频声明 {info.frames} 帧，实际解码 {count} 帧。')
                for packet in stream.encode():
                    dest.mux(packet)
            run_checked([ffmpeg_tool('ffmpeg'), '-v', 'error', '-nostdin', '-i', str(video), '-i', info.path,
                         '-map', '0:v:0', '-map', '1:a?', '-c', 'copy', '-map_metadata', '1',
                         '-movflags', '+faststart', str(combined)], token, timeout=600)
            with av.open(str(combined)) as check:
                count = 0
                if info.has_audio and not check.streams.audio:
                    raise RuntimeError('音频轨道验证失败。')
                for frame in check.decode(video=0):
                    token.check()
                    if (frame.width, frame.height) != (w, h):
                        raise RuntimeError('导出尺寸验证失败。')
                    count += 1
                if count != info.frames:
                    raise RuntimeError('导出帧数验证失败。')
            token.check()
            combined.rename(out)
        return str(out)
