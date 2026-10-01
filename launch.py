"""Project-local dependencies; never modifies the ComfyUI Python installation."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

if __name__ == "__main__":
    try:
        from app.window import main
        main()
    except Exception:
        import traceback
        import ctypes
        (ROOT / "startup-error.log").write_text(traceback.format_exc(), encoding="utf-8")
        ctypes.windll.user32.MessageBoxW(None, "启动失败，详情已写入项目目录的 startup-error.log。", "dlss5flasher", 0x10)
        raise
