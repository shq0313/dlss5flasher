"""Video I/O, cancellation, legacy CLI adapter and current native-runtime facade."""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".work"
DEFAULT_RUNTIME = ROOT / "runtime/DLSS-NR/1.3/bin/video2dlssnr.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Cancelled(Exception):
    pass


class Token:
    def __init__(self):
        self.event = threading.Event()

    def cancel(self):
        self.event.set()

    def check(self):
        if self.event.is_set():
            raise Cancelled("操作已取消")


@dataclass(frozen=True)
class Parameters:
    scale: float = 2.0
    style: int = 0
    intensity: float = 1.5
    structure: float = 1.0
    global_tone: float = 1.0
    local_tone: float = 1.0
    skin: float = 0.0
    detail: float = 1.0
    color: float = 1.0
    sr_preset: str = "default"
    white: float = 100.0
    white_enabled: bool = False
    passes: int = 1
    auto_mask: bool = True
    motion: str = "nvofa"

    def arguments(self):
        if self.scale not in (1.0, 1.5, 2.0, 3.0):
            raise ValueError("不支持的倍率")
        return [
            "--nr-scale", str(self.scale), "--nr-style", str(self.style),
            "--nr-preset", "0", "--nr-intensity", str(self.intensity),
            "--nr-local-structure", str(self.structure),
            "--nr-global-tone", str(self.global_tone),
            "--nr-local-tone", str(self.local_tone), "--nr-skin", str(self.skin),
            "--nr-detail", str(self.detail), "--nr-color", str(self.color),
            "--nr-ui-correction", "0", "--nr-sr-preset", self.sr_preset,
        ]


@dataclass
class VideoInfo:
    path: str
    width: int
    height: int
    frames: int
    fps: Fraction
    duration: float
    cfr: bool
    has_audio: bool


def ffmpeg_tool(name):
    bundled = ROOT / f"ffmpeg-8.0.1-full_build/bin/{name}.exe"
    if bundled.is_file():
        return str(bundled)
    found = shutil.which(name)
    if found:
        return found
    raise RuntimeError(f"找不到 {name}，请安装 FFmpeg 并加入 PATH。")


def run_checked(command, token, timeout=120, cwd=None):
    """File-backed logs avoid pipe deadlocks and retain native error diagnostics."""
    WORK.mkdir(exist_ok=True)
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(command, cwd=cwd, stdout=log, stderr=log,
                                creationflags=NO_WINDOW)
        start = time.monotonic()
        try:
            while proc.poll() is None:
                token.check()
                if time.monotonic() - start > timeout:
                    raise RuntimeError(f"处理超过 {timeout} 秒，已停止。")
                token.event.wait(0.04)
            token.check()
            log.seek(0)
            text = log.read().decode("utf-8", errors="replace")
            (WORK / "last-runtime.log").write_text(text, encoding="utf-8")
            if proc.returncode:
                raise RuntimeError(f"处理程序退出（{proc.returncode}）\n{text[-2200:]}")
            if "bilinear" in text.lower() and any(x in text.lower() for x in ("fallback", "falling", "finishing the rest")):
                raise RuntimeError("DLSS 超分未成功，程序尝试普通缩放；已拒绝把它作为 DLSS 结果。")
            return text
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            log.seek(0)
            (WORK / "last-runtime.log").write_text(log.read().decode("utf-8", errors="replace")[-16000:], encoding="utf-8")


def inspect_video(path, token):
    command = [ffmpeg_tool("ffprobe"), "-v", "error", "-show_entries",
               "stream=codec_type,width,height,pix_fmt,color_transfer,color_primaries,sample_aspect_ratio,avg_frame_rate,r_frame_rate,duration,nb_frames:stream_tags=rotate:stream_disposition=attached_pic:stream_side_data=rotation:format=duration",
               "-of", "json", str(path)]
    data = json.loads(run_checked(command, token, timeout=30))
    videos = [x for x in data["streams"] if x["codec_type"] == "video" and not x.get("disposition", {}).get("attached_pic")]
    if len(videos) != 1:
        raise ValueError("这一版支持包含一条视频轨道的文件。")
    stream = videos[0]
    fmt = stream.get("pix_fmt", "")
    if stream.get("color_transfer") in ("smpte2084", "arib-std-b67") or "bt2020" in stream.get("color_primaries", ""):
        raise ValueError("这一版先支持 SDR 视频；HDR 会在后续接入，避免预览颜色错误。")
    if any(x in fmt for x in ("10", "12", "16", "f32")):
        raise ValueError("这一版先支持 8-bit SDR 视频。")
    if stream.get("sample_aspect_ratio", "1:1") not in ("1:1", "N/A", "0:1"):
        raise ValueError("暂不支持非方形像素视频。")
    if float(stream.get("tags", {}).get("rotate", 0)) or any(float(x.get("rotation", 0)) for x in stream.get("side_data_list", [])):
        raise ValueError("暂不支持带旋转标签的视频，请先转换为正常方向。")
    fps = Fraction(stream.get("avg_frame_rate", "0/1"))
    if fps <= 0:
        raise ValueError("无法识别视频帧率。")
    duration = float(stream.get("duration", data.get("format", {}).get("duration", 0)))
    frames = int(stream.get("nb_frames", 0) or 0) if stream.get("nb_frames") != "N/A" else 0
    frames = frames or max(1, round(duration * float(fps)))
    cfr = Fraction(stream.get("r_frame_rate", str(fps))) == fps
    if not cfr:
        raise ValueError("这一版的逐帧定位和导出先支持固定帧率（CFR）视频。")
    return VideoInfo(str(Path(path).resolve()), stream["width"], stream["height"], frames, fps,
                     duration, cfr, any(x["codec_type"] == "audio" for x in data["streams"]))


class FrameReader:
    """Owned by one worker thread. Seeks to a keyframe, then decodes to target PTS."""
    def __init__(self):
        self.container = None
        self.path = None
        self.iterator = None
        self.index = -1

    def close(self):
        if self.container:
            self.container.close()
        self.container = None

    def read(self, info, index, token):
        token.check()
        if self.path != info.path or self.container is None:
            self.close()
            self.container = av.open(info.path)
            self.path, self.index = info.path, -1
            self.iterator = None
        stream = self.container.streams.video[0]
        origin = stream.start_time or 0
        target = Fraction(index, 1) / info.fps
        if self.iterator is None or index != self.index + 1:
            timestamp = origin + int(target / stream.time_base)
            self.container.seek(timestamp, stream=stream, backward=True, any_frame=False)
            self.iterator = self.container.decode(stream)
        for frame in self.iterator:
            token.check()
            if frame.pts is None:
                raise ValueError("视频帧缺少时间戳，无法精确定位。")
            relative = (frame.pts - origin) * stream.time_base
            if relative >= target - Fraction(1, 2) / info.fps:
                self.index = index
                return frame.to_image().convert("RGB")
        raise ValueError("该时间点没有可解码的视频帧。")


class LegacyRuntime:
    def __init__(self, executable):
        self.executable = Path(executable)

    def validate(self):
        required = [self.executable, *(self.executable.parent / n for n in
                    ("nvngx_dlss.dll", "nvngx_dlssnr.dll", "nvngx.dll_dlssnr.dll"))]
        missing = [x.name for x in required if not x.is_file()]
        if missing:
            raise RuntimeError("运行库不完整：" + "、".join(missing))

    def base(self):
        self.validate()
        return [str(self.executable), "--dll-dir", str(self.executable.parent)]

    def render(self, original, params, token):
        token.check()
        WORK.mkdir(exist_ok=True)
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="frame-", dir=WORK) as directory:
            folder = Path(directory)
            source = folder / "frame.png"
            original.save(source)
            command = self.base() + ["--nr-run", "--in", str(source), "--out", str(folder / "result")] + params.arguments()
            run_checked(command, token, cwd=self.executable.parent)
            result = folder / "result/frame.png_nr.png"
            if not result.is_file():
                raise RuntimeError("运行程序没有返回预期的渲染图像，请查看 .work/last-runtime.log。")
            with Image.open(result) as im:
                output = im.convert("RGB").copy()
            expected = (round(original.width * params.scale), round(original.height * params.scale))
            if output.size != expected:
                raise RuntimeError(f"输出尺寸异常：{output.size}，预期 {expected}")
            token.check()
            return output, time.perf_counter() - started

    def export(self, info, params, output_path, token, progress):
        """Persistent temporal runtime + bounded backpressure; original audio remux."""
        token.check()
        self.validate()
        out = Path(output_path).resolve()
        if out == Path(info.path).resolve():
            raise ValueError("不能覆盖源视频。")
        if out.exists():
            raise ValueError("目标文件已经存在，请换一个文件名。")
        width, height = round(info.width * params.scale), round(info.height * params.scale)
        if width % 2 or height % 2:
            raise ValueError("H.264 输出的宽高必须为偶数，请更换倍率。")
        out.parent.mkdir(parents=True, exist_ok=True)
        command = self.base() + ["--nr-video", "--nr-in", f"{info.width}x{info.height}",
                                "--nr-motion", "1", "--nr-motion-engine", "auto"] + params.arguments()
        with tempfile.TemporaryDirectory(prefix=".dlss-export-", dir=out.parent) as directory:
            temp = Path(directory)
            video = temp / "video.mp4"
            combined = temp / "complete.mp4"
            errors = queue.Queue()
            with (temp / "runtime.log").open("w+b") as log:
                proc = subprocess.Popen(command, cwd=self.executable.parent, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=log, creationflags=NO_WINDOW, bufsize=0)
                last_progress = [time.monotonic()]
                done = threading.Event()

                def watchdog():
                    while not done.wait(0.1):
                        if token.event.is_set() or time.monotonic() - last_progress[0] > 120:
                            if not token.event.is_set():
                                errors.put(RuntimeError("DLSS 连续 120 秒没有输出，已停止导出。"))
                            if proc.poll() is None:
                                proc.kill()
                            return

                def feed():
                    try:
                        with av.open(info.path) as source:
                            s = source.streams.video[0]
                            count, first = 0, None
                            for frame in source.decode(s):
                                token.check()
                                timestamp = frame.pts * frame.time_base if frame.pts is not None else None
                                if timestamp is None:
                                    raise ValueError("导出遇到缺少时间戳的视频帧。")
                                first = timestamp if first is None else first
                                if abs(timestamp - first - Fraction(count, 1) / info.fps) > Fraction(1, 4) / info.fps:
                                    raise ValueError("检测到可变帧率，已停止导出，避免音画不同步。")
                                data = memoryview(frame.to_ndarray(format="rgba").tobytes())
                                while data:
                                    token.check()
                                    written = proc.stdin.write(data)
                                    if not written:
                                        raise RuntimeError("DLSS 输入管道断开。")
                                    data = data[written:]
                                count += 1
                            if count != info.frames:
                                raise ValueError(f"源视频帧数变化：解码 {count}，声明 {info.frames}。")
                        proc.stdin.close()
                    except BaseException as exc:
                        errors.put(exc)
                        if proc.poll() is None:
                            proc.kill()

                sender = threading.Thread(target=feed, daemon=True)
                guard = threading.Thread(target=watchdog, daemon=True)
                try:
                    sender.start()
                    guard.start()
                    with av.open(str(video), "w") as dest:
                        stream = dest.add_stream("libx264", rate=info.fps)
                        stream.width, stream.height = width, height
                        stream.pix_fmt = "yuv420p"
                        stream.options = {"crf": "18", "preset": "fast"}
                        stream.codec_context.color_primaries = 1
                        stream.codec_context.color_trc = 1
                        stream.codec_context.colorspace = 1
                        for index in range(info.frames):
                            token.check()
                            remaining = width * height * 4
                            chunks = []
                            while remaining:
                                chunk = proc.stdout.read(remaining)
                                if not chunk:
                                    token.check()
                                    if not errors.empty():
                                        raise errors.get()
                                    raise RuntimeError(f"DLSS 在第 {index + 1} 帧停止输出。")
                                chunks.append(chunk)
                                remaining -= len(chunk)
                            data = np.frombuffer(b"".join(chunks), np.uint8).reshape(height, width, 4)
                            frame = av.VideoFrame.from_ndarray(data, format="rgba")
                            frame = frame.reformat(format="yuv420p", dst_colorspace="ITU709")
                            frame.pts, frame.time_base = index, 1 / info.fps
                            for packet in stream.encode(frame):
                                dest.mux(packet)
                            last_progress[0] = time.monotonic()
                            progress(index + 1, info.frames)
                        if proc.stdout.read(1):
                            raise RuntimeError("DLSS 输出了多余的帧数据。")
                        for packet in stream.encode():
                            dest.mux(packet)
                    proc.wait(timeout=30)
                    sender.join(timeout=5)
                    token.check()
                    if not errors.empty():
                        raise errors.get()
                    log.seek(0)
                    diagnostics = log.read().decode("utf-8", errors="replace")
                    WORK.mkdir(exist_ok=True)
                    (WORK / "last-export.log").write_text(diagnostics, encoding="utf-8")
                    if proc.returncode or "finishing the rest bilinear" in diagnostics.lower():
                        raise RuntimeError("DLSS 导出失败：\n" + diagnostics[-1800:])
                finally:
                    done.set()
                    if proc.poll() is None:
                        proc.kill()
                    proc.wait()
                    sender.join(timeout=5)
                    guard.join(timeout=2)
                    proc.stdout.close()
                    if not proc.stdin.closed:
                        proc.stdin.close()
            token.check()
            run_checked([ffmpeg_tool("ffmpeg"), "-v", "error", "-nostdin", "-i", str(video),
                         "-i", info.path, "-map", "0:v:0", "-map", "1:a?", "-c", "copy",
                         "-map_metadata", "1", "-movflags", "+faststart", str(combined)], token, timeout=600)
            with av.open(str(combined)) as check:
                count = 0
                for frame in check.decode(video=0):
                    token.check()
                    count += 1
                if count != info.frames:
                    raise RuntimeError("最终视频帧数验证失败。")
            token.check()
            # rename on Windows fails if destination appeared while the job ran.
            combined.rename(out)
        return str(out)


def save_settings(runtime):
    path = Path(runtime).resolve()
    stored = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    (ROOT / "settings.local.json").write_text(json.dumps({"runtime": stored}, ensure_ascii=False, indent=2), encoding="utf-8")


def load_runtime():
    try:
        value = json.loads((ROOT / "settings.local.json").read_text(encoding="utf-8"))
        path = Path(value.get("runtime", str(DEFAULT_RUNTIME)))
        return str(path if path.is_absolute() else ROOT / path)
    except (OSError, ValueError):
        return str(DEFAULT_RUNTIME)


class DlssRuntime:
    """Lazy facade keeps video utilities independent of native worker imports."""
    def __new__(cls, executable):
        from .processing import WorkstationRuntime
        return WorkstationRuntime(executable)
