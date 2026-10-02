from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QRectF, Signal, QObject, QTimer, QUrl
from PySide6.QtGui import QColor, QPainter, QPen, QImage, QFont, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QDoubleSpinBox, QComboBox, QFileDialog, QMessageBox,
    QFrame, QScrollArea, QCheckBox, QProgressBar, QButtonGroup, QSizePolicy,
    QDialog, QTextBrowser,
)

from .engine import (
    ROOT, WORK, Parameters, Token, Cancelled, FrameReader, DlssRuntime,
    inspect_video, load_runtime, save_settings,
)

from .workbench_ui import STYLE
from .video_output import publish_video
from .render_progress import FrameTimeEstimate, progress_text



def label(text, name=None):
    item = QLabel(text)
    if name:
        item.setObjectName(name)
    return item


def button(text, callback=None, name=None):
    item = QPushButton(text)
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    if callback:
        item.clicked.connect(callback)
    if name:
        item.setObjectName(name)
    return item


def qimage(image):
    image = image.convert("RGB")
    return QImage(image.tobytes(), image.width, image.height, image.width * 3,
                  QImage.Format.Format_RGB888).copy()


class CompareCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.original = None
        self.processed = None
        self.mode = "compare"
        self.split = 0.5
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0.0
        self.drag = None
        self.hover = False
        self.note = "导入视频，开始调节当前帧"
        self.setMinimumSize(360, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    def set_images(self, original, processed=None):
        self.original = qimage(original) if original is not None else None
        self.processed = qimage(processed) if processed is not None else None
        self.update()

    def fit(self):
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0.0
        self.update()

    def image_rect(self):
        if self.original is None:
            return QRectF()
        ratio = min((self.width() - 32) / self.original.width(),
                    (self.height() - 32) / self.original.height()) * self.zoom
        w, h = self.original.width() * ratio, self.original.height() * ratio
        return QRectF((self.width() - w) / 2 + self.pan_x,
                      (self.height() - h) / 2 + self.pan_y, w, h)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#101214"))
        if self.original is None:
            p.setPen(QColor("#6c8797"))
            p.setFont(QFont("Microsoft YaHei UI", 40))
            p.drawText(self.rect().adjusted(0, -65, 0, 0), Qt.AlignmentFlag.AlignCenter, "＋")
            p.setFont(QFont("Microsoft YaHei UI", 13))
            p.setPen(QColor("#c2d2dc"))
            p.drawText(self.rect().adjusted(0, 45, 0, 0), Qt.AlignmentFlag.AlignCenter, "把视频拖到这里，或点击「导入视频」")
            p.setFont(QFont("Microsoft YaHei UI", 10))
            p.setPen(QColor("#7993a3"))
            p.drawText(self.rect().adjusted(0, 104, 0, 0), Qt.AlignmentFlag.AlignCenter, "当前帧调参  /  DLSS 超分与增强  /  滑动对比")
            return
        rect = self.image_rect()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.mode == "result" and self.processed is not None:
            p.drawImage(rect, self.processed)
        else:
            p.drawImage(rect, self.original)
            if self.mode == "compare" and self.processed is not None:
                x = rect.left() + rect.width() * self.split
                p.save()
                p.setClipRect(QRectF(x, rect.top(), rect.right() - x, rect.height()))
                p.drawImage(rect, self.processed)
                p.restore()
                p.setPen(QPen(QColor("#ffffff"), 1.5))
                p.drawLine(int(x), int(max(rect.top(), 0)), int(x), int(min(rect.bottom(), self.height())))
                if self.hover:
                    y = self.height() / 2
                    p.setBrush(QColor("#ffffff"))
                    p.drawEllipse(QRectF(x - 14, y - 14, 28, 28))
                    p.setPen(QColor("#815f36"))
                    p.setFont(QFont("Segoe UI", 12))
                    p.drawText(QRectF(x - 14, y - 14, 28, 28), Qt.AlignmentFlag.AlignCenter, "↔")
        p.setFont(QFont("Microsoft YaHei UI", 9))
        tags = [(16, "原始画面" if self.mode != "result" else "DLSS 结果")]
        if self.mode == "compare" and self.processed is not None:
            tags.append((self.width() - 100, "DLSS 增强"))
        for x, text in tags:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(12, 25, 33, 190))
            p.drawRoundedRect(QRectF(x, 14, 84, 25), 4, 4)
            p.setPen(QColor("#e3f1f4"))
            p.drawText(QRectF(x, 14, 84, 25), Qt.AlignmentFlag.AlignCenter, text)
        if self.note:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(12, 25, 33, 210))
            p.drawRoundedRect(QRectF(12, self.height() - 38, self.width() - 24, 27), 4, 4)
            p.setPen(QColor("#d1e3eb"))
            p.drawText(QRectF(22, self.height() - 38, self.width() - 44, 27), Qt.AlignmentFlag.AlignVCenter, self.note)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.drag = event.position()

    def mouseReleaseEvent(self, _event):
        self.drag = None

    def mouseMoveEvent(self, event):
        if self.drag is not None:
            delta = event.position() - self.drag
            self.pan_x += delta.x()
            self.pan_y += delta.y()
            self.drag = event.position()
        else:
            rect = self.image_rect()
            if rect.width() > 0:
                self.split = min(1.0, max(0.0, (event.position().x() - rect.left()) / rect.width()))
        self.update()

    def enterEvent(self, _event):
        self.hover = True
        self.update()

    def leaveEvent(self, _event):
        self.hover = False
        self.update()

    def wheelEvent(self, event):
        self.zoom = min(8.0, max(0.25, self.zoom * (1.12 if event.angleDelta().y() > 0 else 1 / 1.12)))
        self.update()


class SliderRow(QWidget):
    changed = Signal()

    def __init__(self, title, value, minimum=0, maximum=2, hint=""):
        super().__init__()
        self.default = value
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        top = QHBoxLayout()
        title_widget = label(title)
        title_widget.setToolTip(hint)
        top.addWidget(title_widget)
        top.addStretch()
        self.spin = QDoubleSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setDecimals(2)
        self.spin.setSingleStep(0.05)
        self.spin.setFixedWidth(76)
        self.spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.spin.setKeyboardTracking(False)
        self.spin.setStyleSheet("min-height:16px; padding:3px 5px;")
        if minimum == -1:
            self.spin.setSpecialValueText("自动")
        self.spin.setValue(value)
        top.addWidget(self.spin)
        reset = button("重置", lambda: self.spin.setValue(self.default), "quiet")
        reset.setFixedWidth(30)
        reset.setToolTip("恢复默认值")
        top.addWidget(reset)
        layout.addLayout(top)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(round(minimum * 100), round(maximum * 100))
        self.slider.setValue(round(value * 100))
        self.slider.setToolTip(hint)
        self.slider.valueChanged.connect(self.from_slider)
        self.spin.valueChanged.connect(self.from_spin)
        layout.addWidget(self.slider)

    def from_slider(self, value):
        self.spin.blockSignals(True)
        self.spin.setValue(value / 100)
        self.spin.blockSignals(False)
        self.changed.emit()

    def from_spin(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(round(value * 100))
        self.slider.blockSignals(False)
        self.changed.emit()

    def value(self):
        return self.spin.value()


class Events(QObject):
    result = Signal(int, str, object)
    progress = Signal(int, int, int, object)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("dlss5flasher")
        self.resize(1440, 960)
        self.setMinimumSize(1120, 850)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dlss-worker")
        self.events = Events()
        self.events.result.connect(self.on_result)
        self.events.progress.connect(self.on_progress)
        self.reader = FrameReader()
        self.runtime_path = load_runtime()
        self.runtime = DlssRuntime(self.runtime_path)
        self.generation = 0
        self.active_kind = None
        self.token = Token()
        self.info = None
        self.index = 0
        self.source = None
        self.rendered = None
        self.rendered_params = None
        self.rendered_index = None
        self.playing = False
        self.exporting = False
        WORK.mkdir(exist_ok=True)
        self.video_cache = tempfile.TemporaryDirectory(prefix='rendered-video-', dir=WORK)
        self.rendered_video = None
        self.closed = False
        self.last_error = None
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(350)
        self.render_timer.timeout.connect(self.render_current)
        self.seek_timer = QTimer(self)
        self.seek_timer.setSingleShot(True)
        self.seek_timer.setInterval(90)
        self.seek_timer.timeout.connect(self.decode_selected)
        self.play_timer = QTimer(self)
        self.play_timer.setSingleShot(True)
        self.play_timer.timeout.connect(self.next_play_frame)
        self.build_ui()
        self.setAcceptDrops(True)
        self.show_runtime_hint()

    def show_runtime_hint(self):
        dll = Path(self.runtime_path).parent / 'nvngx_dlssnr.dll'
        if not dll.is_file():
            self.status.setText('尚未添加 NR 运行库 · 点击右上角“运行库”选择 nvngx_dlssnr.dll')
            self.canvas.note = '请先添加对应显卡的 nvngx_dlssnr.dll · 默认位置：runtime/DLSS-NR/1.3/bin/'
            self.canvas.update()

    def build_ui(self):
        from .workbench_ui import build
        build(self)

    def parameters(self):
        return Parameters(scale=(1, 2, 4)[self.scale_combo.currentIndex()],
                          white_enabled=self.white_check.isChecked(),
                          style=self.style_combo.currentIndex(), passes=self.pass_combo.currentIndex() + 1,
                          auto_mask=self.mask_check.isChecked(), motion=("nvofa", "off")[self.motion_combo.currentIndex()],
                          **{key: row.value() for key, row in self.rows.items()})

    def update_buttons(self):
        ready = self.info is not None and self.source is not None and not self.exporting
        self.render_button.setEnabled(ready and not self.playing)
        self.save_frame_button.setEnabled(ready and self.rendered is not None)
        self.render_video_button.setEnabled(ready and not self.playing and self.info.frames > 1)
        self.export_button.setEnabled(ready and not self.playing and self.video_ready())
        self.transport.setEnabled(self.info is not None and not self.exporting)
        self.import_button.setEnabled(not self.exporting)
        self.parameters_widget.setEnabled(not self.exporting)
        self.output_controls.setEnabled(not self.exporting)

    def set_view(self, mode):
        self.canvas.mode = mode
        self.canvas.update()

    def request(self, kind, operation):
        self.token.cancel()
        self.token = Token()
        token = self.token
        self.generation += 1
        generation = self.generation
        self.active_kind = kind
        self.cancel_button.setVisible(True)

        def execute():
            try:
                token.check()
                value = operation(token, generation)
                if not self.closed:
                    self.events.result.emit(generation, kind, value)
            except Cancelled:
                pass
            except Exception as exc:
                WORK.mkdir(exist_ok=True)
                (WORK / "last-error.log").write_text(traceback.format_exc(), encoding="utf-8")
                if not self.closed:
                    self.events.result.emit(generation, "error", (kind, str(exc)))

        self.executor.submit(execute)

    def choose_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择视频", "", "视频 (*.mp4 *.mkv *.mov *.avi *.webm *.m4v);;所有文件 (*)")
        if path:
            self.open_video(path)

    def open_video(self, path):
        if self.exporting:
            return
        self.stop_playback()
        self.render_timer.stop()
        self.seek_timer.stop()
        self.info = self.source = self.rendered = None
        self.canvas.set_images(None)
        self.filename.setText(Path(path).name)
        self.filename.setToolTip(str(path))
        self.status.setText("正在读取视频信息与第一帧…")
        self.update_buttons()

        def read(token, _gen):
            info = inspect_video(path, token)
            return info, self.reader.read(info, 0, token)
        self.request("open", read)

    def seek_changed(self, _value):
        if self.info is None or self.exporting:
            return
        self.stop_playback()
        self.token.cancel()
        self.render_timer.stop()
        self.invalidate_result("正在定位新画面…")
        self.source = None
        self.update_buttons()
        self.seek_timer.start()

    def decode_selected(self):
        if not self.info:
            return
        target, info = self.timeline.value(), self.info
        self.status.setText(f"正在读取第 {target + 1} 帧…")
        self.request("frame", lambda token, _gen: (target, self.reader.read(info, target, token)))

    def step(self, delta):
        if self.info:
            self.timeline.setValue(max(0, min(self.info.frames - 1, self.timeline.value() + delta)))

    def stop_playback(self):
        self.playing = False
        self.play_timer.stop()
        if hasattr(self, "play_button"):
            self.play_button.setText("播放")

    def toggle_play(self):
        if not self.info or self.exporting:
            return
        if self.playing:
            self.stop_playback()
            self.token.cancel()
            self.generation += 1
            self.timeline.blockSignals(True)
            self.timeline.setValue(self.index)
            self.timeline.blockSignals(False)
            self.render_current()
        else:
            self.render_timer.stop()
            self.seek_timer.stop()
            self.playing = True
            self.play_button.setText("暂停")
            self.invalidate_result("静音定位播放 · 暂停后渲染当前帧")
            self.next_play_frame()
        self.update_buttons()

    def next_play_frame(self):
        if not self.playing or not self.info:
            return
        if self.index >= self.info.frames - 1:
            self.stop_playback()
            self.render_current()
            return
        target, info = self.index + 1, self.info
        self.request("play", lambda token, _gen: (target, self.reader.read(info, target, token)))

    def invalidate_result(self, note):
        self.rendered = None
        self.rendered_params = None
        self.canvas.processed = None
        self.canvas.note = note
        self.canvas.update()
        self.save_frame_button.setEnabled(False)

    def auto_changed(self, checked):
        if checked:
            self.parameters_changed()
        else:
            self.render_timer.stop()

    def parameters_changed(self, *_args, preview_delay=350):
        if not hasattr(self, "auto_render"):
            return
        self.render_timer.setInterval(preview_delay)
        self.stop_playback()
        if self.active_kind in ("render", "play"):
            self.token.cancel()
            self.generation += 1
            self.active_kind = None
            self.cancel_button.setVisible(False)
        self.profile_label.setText("自定义参数 · 所有已启用控件直接生效")
        self.update_output_size()
        if self.info:
            self.invalidate_result("参数已更新 · 等待当前帧渲染")
            self.status.setText("参数已更新；连续拖动结束后处理最新数值。")
            if self.auto_render.isChecked() and self.source is not None:
                self.render_timer.start()
            elif self.source is None and self.active_kind != "frame":
                self.seek_timer.start()
        self.update_buttons()

    def reset_parameters(self):
        for row in self.rows.values():
            row.spin.setValue(row.default)
        self.style_combo.setCurrentIndex(0)
        self.pass_combo.setCurrentIndex(0)
        self.motion_combo.setCurrentIndex(0)
        self.mask_check.setChecked(True)
        self.white_check.setChecked(False)
        self.scale_combo.setCurrentIndex(1)
        self.encoder_combo.setCurrentIndex(0)
        self.parameters_changed()
        self.profile_label.setText("默认参数 · 所有已启用控件直接生效")

    def update_output_size(self):
        if self.info:
            scale = self.parameters().scale
            self.output_size.setText(f"{self.info.width} × {self.info.height}  →  {round(self.info.width * scale)} × {round(self.info.height * scale)}")

    def render_current(self):
        self.render_timer.stop()
        if self.source is None or self.playing or self.exporting:
            return
        source, params, index = self.source.copy(), self.parameters(), self.index
        runtime = self.runtime
        self.invalidate_result("正在渲染当前帧 · 首次运行包含引擎初始化")
        self.status.setText(f"正在渲染第 {index + 1} 帧 · {params.scale:g}× · 可继续调整参数")

        info = self.info
        def render(token, _gen):
            history = [self.reader.read(info, i, token) for i in range(max(0, index - 2), index)] if params.motion != 'off' else []
            image, elapsed = runtime.render(source, params, token, history=history)
            return index, params, image, elapsed
        self.request("render", render)

    def on_result(self, generation, kind, value):
        if generation != self.generation or self.closed or self.token.event.is_set():
            return
        self.active_kind = None
        self.cancel_button.setVisible(False)
        if kind == "error":
            operation, message = value
            self.last_error = message
            self.stop_playback()
            self.exporting = False
            self.progress.setVisible(False)
            self.status.setText("处理未完成 · " + message.splitlines()[0][:100])
            self.canvas.note = "处理未完成，当前显示原图 · 点击底部「查看日志」了解原因"
            self.canvas.update()
            if operation in ("open", "export", "render_video"):
                QMessageBox.warning(self, "处理未完成", message[-2400:])
        elif kind == "open":
            self.info, self.source = value
            self.index = 0
            self.timeline.blockSignals(True)
            self.timeline.setRange(0, self.info.frames - 1)
            self.timeline.setValue(0)
            self.timeline.blockSignals(False)
            self.canvas.fit()
            self.show_current()
            if self.auto_render.isChecked():
                self.render_timer.start()
        elif kind in ("frame", "play"):
            self.index, self.source = value
            self.timeline.blockSignals(True)
            self.timeline.setValue(self.index)
            self.timeline.blockSignals(False)
            self.show_current()
            if kind == "play" and self.playing:
                self.play_timer.start(max(1, round(1000 / float(self.info.fps))))
            elif self.auto_render.isChecked():
                self.render_timer.start()
        elif kind == "render":
            self.rendered_index, self.rendered_params, self.rendered, elapsed = value
            self.canvas.set_images(self.source, self.rendered)
            self.canvas.note = "移动鼠标划线对比 · 当前帧已处理 · 渲染视频可处理整段视频"
            self.status.setText(f"● 渲染完成 · 第 {self.index + 1} 帧 · {self.rendered.width} × {self.rendered.height} · 耗时 {elapsed:.2f} 秒")
        elif kind == "render_video":
            previous = self.rendered_video
            self.rendered_video = value
            if previous is not None:
                self.executor.submit(Path(previous[1]).unlink, missing_ok=True)
            self.exporting = False
            self.progress.setVisible(False)
            self.status.setText("● 视频渲染完成 · 点击“导出视频”保存 · 关闭软件会清理临时结果")
        elif kind == "export":
            self.exporting = False
            self.progress.setVisible(False)
            self.status.setText("● 视频已导出 · " + str(value))
            QMessageBox.information(self, "导出完成", f"视频已保存：\n{value}\n\n已验证视频帧数，音频使用原轨道复制。")
        self.update_buttons()

    @staticmethod
    def clock_text(seconds):
        total_ms = round(seconds * 1000)
        minutes, remainder = divmod(total_ms, 60000)
        return f"{minutes:02}:{remainder // 1000:02}.{remainder % 1000:03}"

    def show_current(self):
        self.canvas.set_images(self.source)
        self.canvas.note = "静音定位播放 · 暂停后渲染当前帧" if self.playing else "当前显示原图 · 等待渲染"
        self.frame_label.setText(f"帧  {self.index + 1} / {self.info.frames}")
        self.frame_badge.setText(f"{self.info.width} × {self.info.height}  ·  {float(self.info.fps):g} fps  ·  SDR")
        self.time_label.setText(f"{self.clock_text(self.index / float(self.info.fps))} / {self.clock_text(self.info.duration)}")
        self.status.setText("● 已读取当前帧 · 调节下方参数查看效果")
        self.update_output_size()

    def save_frame(self):
        if self.rendered is None or self.rendered_params is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存增强帧", str(ROOT / f"frame_{self.index + 1:06}.png"), "PNG (*.png)")
        if path:
            try:
                self.rendered.save(path, format="PNG")
                Path(path).with_suffix(".settings.json").write_text(json.dumps({
                    "source": self.info.path, "frame_index": self.rendered_index,
                    "parameters": asdict(self.rendered_params), "preview_mode": "two_frame_history" if self.rendered_params.motion != "off" else "independent_still",
                }, ensure_ascii=False, indent=2), encoding="utf-8")
                self.status.setText("● 当前帧与参数已保存 · " + path)
            except Exception as exc:
                QMessageBox.warning(self, "保存失败", str(exc))

    def video_key(self):
        if self.info is None:
            return None
        try:
            stat = Path(self.info.path).stat()
        except OSError:
            return None
        return (self.info.path, stat.st_size, stat.st_mtime_ns, self.parameters(), self.runtime_path,
                self.encoder_combo.currentData())

    def encoder_changed(self):
        # Encoding is independent of still-frame inference and its preview cache.
        self.status.setText('视频编码已切换 · 重新渲染视频后生效 · 当前帧预览不受影响')
        self.update_buttons()

    def video_ready(self):
        return (self.rendered_video is not None and self.rendered_video[0] == self.video_key()
                and Path(self.rendered_video[1]).is_file())

    def render_video(self):
        if self.info is None or self.info.frames <= 1 or self.exporting:
            return
        self.stop_playback()
        self.render_timer.stop()
        self.seek_timer.stop()
        params, info, key = self.parameters(), self.info, self.video_key()
        encoder = self.encoder_combo.currentData()
        runtime = self.runtime
        path = Path(self.video_cache.name) / f'{uuid.uuid4().hex}.mp4'
        self.exporting = True
        self.progress.setVisible(True)
        self.progress.setRange(0, info.frames)
        self.progress.setValue(0)
        self.status.setText(f'正在渲染整段视频 · {self.encoder_combo.currentText()} · 可取消')
        self.update_buttons()

        def render(token, gen):
            estimate = FrameTimeEstimate()
            def report(current, total):
                remaining = estimate.update(current, total, time.perf_counter())
                self.events.progress.emit(gen, current, total, remaining)
            runtime.export(info, params, path, token, report, encoder=encoder)
            token.check()
            return key, str(path)
        self.request("render_video", render)

    def export_video(self):
        if self.info is None or self.exporting or not self.video_ready():
            return
        output_dir = ROOT / "output"
        output_dir.mkdir(exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "导出增强视频（保留原片）",
                    str(output_dir / f"{Path(self.info.path).stem}_DLSS_{time.strftime('%H%M%S')}.mp4"), "MP4 (*.mp4)")
        if not path:
            return
        if Path(path).exists():
            QMessageBox.warning(self, "请选择新文件名", "这一版不覆盖已有视频，请使用新文件名。")
            return
        self.stop_playback()
        self.render_timer.stop()
        self.seek_timer.stop()
        cached = self.rendered_video[1]
        self.exporting = True
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.status.setText("正在保存已渲染的视频 · 无需重新渲染 · 可取消")
        self.update_buttons()
        self.request("export", lambda token, gen: publish_video(cached, path, token))

    def on_progress(self, generation, current, total, remaining=None):
        if generation == self.generation:
            self.progress.setValue(current)
            self.status.setText(progress_text(current, total, remaining) + ' · ' + self.encoder_combo.currentText())

    def cancel_job(self):
        self.token.cancel()
        self.generation += 1
        self.active_kind = None
        self.render_timer.stop()
        self.seek_timer.stop()
        self.stop_playback()
        self.exporting = False
        self.progress.setVisible(False)
        self.cancel_button.setVisible(False)
        self.status.setText("已取消任务 · 未完成的视频不会发布")
        self.canvas.note = "已取消任务"
        self.canvas.update()
        self.update_buttons()

    def choose_runtime(self):
        if self.exporting:
            return
        path, _ = QFileDialog.getOpenFileName(self, "选择对应显卡的 nvngx_dlssnr.dll", str(Path(self.runtime_path).parent), "NR 运行库 (nvngx_dlssnr.dll);;旧版入口 (video2dlssnr.exe)")
        if path:
            try:
                DlssRuntime(path).validate()
                self.token.cancel()
                old = self.runtime
                self.executor.submit(old.close)
                self.runtime_path = path
                self.runtime = DlssRuntime(path)
                save_settings(path)
                self.parameters_changed()
                self.status.setText('● 已选择 NR 运行库 · ' + str(Path(path).parent / 'nvngx_dlssnr.dll'))
            except Exception as exc:
                QMessageBox.warning(self, "运行库无效", str(exc))

    def show_licenses(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('dlss5flasher · 第三方许可')
        dialog.resize(820, 620)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser(dialog)
        browser.setOpenLinks(False)
        browser.anchorClicked.connect(lambda url: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(ROOT) + '/').resolved(url)))
        browser.document().setBaseUrl(QUrl.fromLocalFile(str(ROOT) + '/'))
        notice = ROOT / 'THIRD_PARTY_NOTICES.md'
        browser.setMarkdown(notice.read_text(encoding='utf-8-sig') if notice.exists()
                            else '缺少 THIRD_PARTY_NOTICES.md，请保持软件目录完整。')
        layout.addWidget(browser)
        layout.addWidget(button('关闭', dialog.accept))
        dialog.exec()

    def show_log(self):
        path = WORK / "last-error.log"
        if not path.exists():
            path = WORK / "last-runtime.log"
        text = path.read_text(encoding="utf-8")[-8000:] if path.exists() else "暂无运行日志。"
        box = QMessageBox(self)
        box.setWindowTitle("运行诊断")
        box.setText(self.last_error or "最近一次处理日志")
        box.setDetailedText(text)
        box.exec()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.exporting:
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.open_video(urls[0].toLocalFile())

    def closeEvent(self, event):
        self.closed = True
        self.token.cancel()
        self.render_timer.stop()
        self.seek_timer.stop()
        self.play_timer.stop()
        self.executor.submit(self.reader.close)
        self.executor.submit(self.runtime.close)
        self.executor.submit(self.video_cache.cleanup)
        self.executor.shutdown(wait=False, cancel_futures=False)
        event.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", nargs="?")
    options = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    if options.video:
        QTimer.singleShot(100, lambda: window.open_video(options.video))
    sys.exit(app.exec())
