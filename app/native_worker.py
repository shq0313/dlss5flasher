"""Process-isolated DX12 sessions. Only the local parent can send requests."""
from __future__ import annotations
import ctypes as C
import traceback
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
P, I, F, W = C.c_void_p, C.c_int, C.c_float, C.c_wchar_p


def bind(lib, name, result, *args):
    fn = getattr(lib, name)
    fn.restype, fn.argtypes = result, list(args)
    return fn


def worker(connection, kind, runtime):
    """All native state belongs to this child; a blocked GPU can be terminated."""
    lib = None
    dimensions = None
    flow = None
    previous = None
    try:
        if kind == 'nr':
            lib = C.CDLL(str(ROOT / 'runtime/dlssnr_host_v2.dll'))
            initialize = bind(lib, 'dlssnr_init', I, I, I, I, W, W)
            create = bind(lib, 'dlssnr_create_feature', I, I, I, I)
            configure = bind(lib, 'dlssnr_configure', None, I, I, I, I, I)
            format_options = bind(lib, 'dlssnr_configure_format', None, I, I)
            format_options(1, 0)  # RGBA16F storage, encoded SDR sRGB; HDR flag off.
            options = bind(lib, 'dlssnr_set_options', None, I, I, F, F, F, F, I, I, I, I, F, F)
            extra = bind(lib, 'workstation_nr_passes', None, I)
            process = bind(lib, 'dlssnr_process', I, P, P, P, P, I)
            shutdown = bind(lib, 'dlssnr_shutdown', None)
        else:
            lib = C.CDLL(str(ROOT / 'runtime/RTX-Video/vsr_host.dll'))
            initialize = bind(lib, 'vsr_init', I, I, I, I, I, I, W, W)
            process = bind(lib, 'vsr_process', I, P, P)
            shutdown = bind(lib, 'vsr_shutdown', None)
        while True:
            message = connection.recv()
            if message is None:
                break
            rgba, params, reset = message
            h, w = rgba.shape[:2]
            if kind == 'vsr':
                scale = int(params['scale'])
                if dimensions != (w, h, scale):
                    if not initialize(w, h, scale, 4, 0, str(ROOT / 'runtime/RTX-Video'), str(ROOT / '.work/vsr.log')):
                        raise RuntimeError('RTX Video 初始化失败，详见 .work/vsr.log')
                    dimensions = (w, h, scale)
                output = np.empty((h * scale, w * scale, 4), np.uint8)
                success = process(rgba.ctypes.data, output.ctypes.data)
            else:
                changed = dimensions != (w, h)
                if changed:
                    if dimensions is None:
                        format_options(1, 1 if params.get('white_enabled', False) else 0)
                    if dimensions is None and not initialize(w, h, 0, runtime, str(ROOT / '.work/native-nr.log')):
                        raise RuntimeError('NR 初始化失败，详见 .work/native-nr.log')
                    dimensions = (w, h)
                    reset = True
                    previous = None
                    if flow:
                        flow.close()
                        flow = None
                use_flow = params['motion'] == 'nvofa'
                motion = None
                if use_flow:
                    from .vendor.nvofa import OpticalFlow, align_size
                    factor = min(1, 512 / max(w, h))
                    fw, fh = align_size(round(w * factor), round(h * factor))
                    rgb = rgba[:, :, :3].astype(np.float32)
                    if params.get('white_enabled', False):
                        rgb = rgb * (80 / params['white'])
                        rgb = np.where(rgb <= .0031308, rgb * 12.92,
                                       1.055 * np.maximum(rgb, 0) ** (1 / 2.4) - .055)
                    current = np.asarray(Image.fromarray(np.uint8(np.clip(np.rint(rgb * 255), 0, 255)))
                                         .resize((fw, fh), Image.Resampling.BILINEAR)).copy()
                    if not reset and previous is not None:
                        # A large discontinuity is a cut, not a temporal neighbour.
                        reset = np.abs(current.astype(np.float32) - previous).mean() > 55
                    if not reset and previous is not None:
                        if flow is None:
                            flow = OpticalFlow(fw, fh)
                        small = flow.calculate(current, previous)
                        motion = np.stack([np.asarray(Image.fromarray(small[:, :, i]).resize((w, h), Image.Resampling.BILINEAR))
                                           * (w / fw if i == 0 else h / fh) for i in range(2)], axis=-1).astype(np.float32)
                    previous = current
                else:
                    previous = None
                configure(0 if use_flow else 1, 1, 1, 1, 0)
                options(0, params['style'], params['intensity'], params['local_tone'], params['structure'],
                        params['skin'], int(params['auto_mask']), 0, 1 if use_flow else 0, 0, 1., 1.)
                extra(int(params['passes']))
                if changed and not create(w, h, 0):
                    raise RuntimeError('NR 创建失败，详见 .work/native-nr.log')
                output = np.empty_like(rgba)
                success = process(rgba.ctypes.data, motion.ctypes.data if motion is not None else None,
                                  None, output.ctypes.data, int(reset))
            if not success:
                raise RuntimeError(f'{kind} 处理失败；没有使用普通缩放替代。请查看 .work 日志。')
            connection.send((True, output))
    except EOFError:
        pass
    except BaseException:
        try:
            connection.send((False, traceback.format_exc()))
        except (OSError, EOFError):
            pass
    finally:
        if flow:
            flow.close()
        if lib is not None and 'shutdown' in locals():
            shutdown()
        connection.close()
