"""Publish an already rendered video, without rerendering or overwriting files."""
from pathlib import Path
import tempfile


def publish_video(source, destination, token):
    source, destination = Path(source), Path(destination)
    token.check()
    if destination.exists() or source.resolve() == destination.resolve():
        raise ValueError('请选择新的输出文件，不能覆盖已有文件。')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = None
    try:
        with source.open('rb') as incoming, tempfile.NamedTemporaryFile(
                prefix='.dlss-save-', suffix='.tmp', dir=destination.parent, delete=False) as outgoing:
            staging = Path(outgoing.name)
            while chunk := incoming.read(4 * 1024 * 1024):
                token.check()
                outgoing.write(chunk)
        token.check()
        if staging.stat().st_size != source.stat().st_size:
            raise RuntimeError('保存的视频大小不一致，请重试导出。')
        # Windows rename refuses an existing target, including one created
        # after the initial check. Only publish a fully copied file.
        staging.rename(destination)
        return str(destination)
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)
