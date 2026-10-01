"""Estimate frame processing time from worker-side completion timestamps."""
import math


class FrameTimeEstimate:
    def __init__(self):
        self.previous = None
        self.seconds = 0.0
        self.samples = 0

    def update(self, current, total, completed_at):
        # The first completion only starts the clock: startup is not a sample.
        if self.previous is not None and 2 <= current <= 11:
            self.seconds += max(0.0, completed_at - self.previous)
            self.samples += 1
        self.previous = completed_at
        if current >= total:
            return 0.0
        # Short clips cannot collect ten samples; use those available from #2.
        if not self.samples or (total >= 11 and current < 11):
            return None
        return (self.seconds / self.samples) * (total - current)


def progress_text(current, total, remaining=None):
    prefix = f'正在渲染视频 · {current} / {total} 帧 · {current / total:.0%}'
    if current >= total:
        return prefix + ' · 预计剩余 00:00:00 · 正在合并音频并验证输出…'
    if remaining is None:
        return prefix + ' · 预计剩余：计算中…'
    seconds = max(0, math.ceil(remaining))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return prefix + f' · 预计剩余 {hours:02d}:{minutes:02d}:{seconds:02d}'
