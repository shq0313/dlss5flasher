"""Explicit H.264 encoder selection; never silently switch the user's choice."""
from fractions import Fraction


ENCODERS = (
    ('h264_nvenc', 'GPU 硬件编码（NVENC）'),
    ('libx264', 'CPU 编码（x264）'),
)


def create_video_stream(destination, width, height, fps, encoder='libx264'):
    if encoder not in dict(ENCODERS):
        raise ValueError('不支持的视频编码器。')
    try:
        stream = destination.add_stream(encoder, rate=fps)
        stream.width, stream.height, stream.pix_fmt = width, height, 'yuv420p'
        stream.time_base = Fraction(1, 1) / fps
        context = stream.codec_context
        context.time_base = stream.time_base
        context.color_primaries = 1
        context.color_trc = 1
        context.colorspace = 1
        context.color_range = 1  # limited-range BT.709, matching the frame conversion
        if encoder == 'h264_nvenc':
            context.bit_rate = 0
            stream.options = {'preset': 'p5', 'tune': 'hq', 'rc': 'vbr', 'cq': '19'}
        else:
            stream.options = {'crf': '18', 'preset': 'fast'}
        # Open the actual encoder at the requested size before any DLSS work.
        # A list of supported codec names alone cannot establish device availability.
        context.open()
        return stream
    except Exception as exc:
        if encoder == 'h264_nvenc':
            raise RuntimeError('无法启动 NVENC 硬件编码，请在“视频编码”下拉框选择 CPU 编码后重试。'
                               '\n可能是编码会话占用、输出尺寸或当前编码库不支持。\n' + str(exc)) from exc
        raise
