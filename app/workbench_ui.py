"""Dark, preview-first workbench. Widgets use the existing request controller."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout, QComboBox,
                              QCheckBox, QSlider, QButtonGroup, QProgressBar, QSizePolicy, QGridLayout)

STYLE = """
QMainWindow, QWidget#root { background: #141618; }
QWidget { color: #ece9e3; font-family: 'Microsoft YaHei UI'; font-size: 12px; }
QFrame#header, QFrame#panel, QFrame#transport { background: #202326; border: 1px solid #34383c; border-radius: 7px; }
QLabel#brand { font-size: 18px; font-weight: 700; }
QLabel#muted { color: #969b9f; font-size: 11px; }
QLabel#section { font-weight: 600; font-size: 13px; color: #e6c18d; }
QLabel#badge { color: #deb27a; background: #332c24; border-radius: 4px; padding: 4px 9px; }
QPushButton { background: #262a2e; border: 1px solid #41464b; border-radius: 4px; padding: 5px 10px; }
QPushButton:hover { background: #353330; border-color: #c69c66; }
QPushButton:pressed, QPushButton:checked { background: #4a3b29; color: #f4d2a4; border-color: #c39b64; }
QPushButton:disabled { color: #64696d; background: #222528; border-color: #303438; }
QPushButton#primary { background: #dcb17a; border: none; color: #211c16; font-weight: 700; padding: 9px; }
QPushButton#primary:hover { background: #ebc897; }
QPushButton#primary:disabled { background: #5c5142; color: #a29581; }
QPushButton#quiet { border: none; background: transparent; color: #a5a6a5; padding: 3px; }
QComboBox, QDoubleSpinBox { background: #191c1f; border: 1px solid #3c4146; border-radius: 4px; padding: 3px 5px; min-height: 17px; }
QComboBox QAbstractItemView { background: #262a2e; selection-background-color: #665038; color: #ece9e3; }
QSlider::groove:horizontal { height: 3px; background: #42464a; border-radius: 1px; }
QSlider::sub-page:horizontal { background: #d5aa73; }
QSlider::handle:horizontal { width: 10px; height: 10px; margin: -5px 0; border: 1px solid #e4c293; background: #e0b780; border-radius: 5px; }
QSlider::sub-page:horizontal:disabled { background: #605749; }
QCheckBox { spacing: 6px; }
QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid #626465; background: #191c1f; border-radius: 3px; }
QCheckBox::indicator:checked { background: #d8ad76; border-color: #e9cda5; image: none; }
QScrollArea { border: none; background: transparent; }
QProgressBar { background: #33383d; border: none; border-radius: 2px; max-height: 5px; }
QProgressBar::chunk { background: #d9ac72; }
QToolTip { background: #33383d; color: #f5ede2; border: 1px solid #6e6150; padding: 8px; }
"""


def build(w):
    from .window import label, button, CompareCanvas, SliderRow
    root = QWidget()
    root.setObjectName('root')
    w.setCentralWidget(root)
    outer = QVBoxLayout(root)
    outer.setContentsMargins(16, 12, 16, 8)
    outer.setSpacing(9)
    header = QHBoxLayout()
    header.addWidget(label('D', 'badge'))
    header.addWidget(label('dlss5flasher', 'brand'))
    header.addSpacing(20)
    header.addWidget(label('画面工作台', 'section'))
    header.addStretch()
    header.addWidget(label('DX12  ·  本地处理', 'muted'))
    header.addWidget(button('许可', w.show_licenses, 'quiet'))
    header.addWidget(button('运行库', w.choose_runtime, 'quiet'))
    w.import_button = button('＋  导入视频', w.choose_video)
    header.addWidget(w.import_button)
    outer.addLayout(header)

    toolbar = QHBoxLayout()
    w.filename = label('导入一段视频，从当前帧开始调节', 'muted')
    w.filename.setMaximumWidth(440)
    toolbar.addWidget(w.filename)
    toolbar.addStretch()
    w.frame_badge = label('当前帧预览', 'muted')
    toolbar.addWidget(w.frame_badge)
    outer.addLayout(toolbar)
    w.canvas = CompareCanvas()
    w.canvas.setMinimumHeight(230)
    w.canvas.setToolTip('移动鼠标划线对比 · 滚轮缩放 · 中键拖动平移')
    outer.addWidget(w.canvas, 1)
    view = QHBoxLayout()
    w.view_group = QButtonGroup(w)
    for key, text in [('original', '原图'), ('compare', '划线对比'), ('result', '增强')]:
        item = button(text)
        item.setCheckable(True)
        item.setChecked(key == 'compare')
        item.clicked.connect(lambda _checked=False, mode=key: w.set_view(mode))
        w.view_group.addButton(item)
        view.addWidget(item)
    view.addWidget(label('鼠标移动即可对比', 'muted'))
    view.addStretch()
    view.addWidget(button('适应窗口', w.canvas.fit))
    outer.addLayout(view)

    w.transport = QFrame()
    w.transport.setObjectName('transport')
    transport = QVBoxLayout(w.transport)
    transport.setContentsMargins(12, 5, 12, 7)
    transport.setSpacing(3)
    w.timeline = QSlider(Qt.Orientation.Horizontal)
    w.timeline.setRange(0, 0)
    w.timeline.valueChanged.connect(w.seek_changed)
    transport.addWidget(w.timeline)
    controls = QHBoxLayout()
    controls.addWidget(button('‹', lambda: w.step(-1)))
    w.play_button = button('播放', w.toggle_play)
    w.play_button.setToolTip('静音播放原片用于定位；暂停后处理当前帧')
    controls.addWidget(w.play_button)
    controls.addWidget(button('›', lambda: w.step(1)))
    w.time_label = label('00:00.000 / 00:00.000')
    controls.addWidget(w.time_label)
    controls.addStretch()
    w.frame_label = label('帧  — / —', 'muted')
    controls.addWidget(w.frame_label)
    controls.addWidget(label('定位播放 · 静音', 'muted'))
    transport.addLayout(controls)
    outer.addWidget(w.transport)

    w.parameters_widget = QWidget()
    cards = QHBoxLayout(w.parameters_widget)
    cards.setContentsMargins(0, 0, 0, 0)
    cards.setSpacing(10)
    def card(title):
        widget = QFrame()
        widget.setObjectName('panel')
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)
        layout.addWidget(label(title, 'section'))
        cards.addWidget(widget, 1)
        return widget, layout
    _, neural = card('01  神经增强')
    _, light = card('02  光影与色彩')
    w.output_controls, output = card('03  处理与输出')
    w.rows = {}
    def slider(layout, key, title, default, low, high, hint):
        row = SliderRow(title, default, low, high, hint)
        row.setMinimumWidth(240)
        if key in ('global_tone', 'color', 'detail'):
            row.changed.connect(lambda: w.parameters_changed(preview_delay=60))
        else:
            row.changed.connect(w.parameters_changed)
        w.rows[key] = row
        layout.addWidget(row)
        return row
    def combo(layout, title, items):
        line = QHBoxLayout()
        line.addWidget(label(title))
        control = QComboBox()
        control.addItems(items)
        line.addWidget(control, 1)
        layout.addLayout(line)
        return control
    w.style_combo = combo(neural, '风格', ['默认', '自然', '电影'])
    slider(neural, 'intensity', '整体增强', 1.5, 0, 2, '控制 NR 的整体改动强度，较高数值可能改变原貌。')
    slider(neural, 'structure', '结构细节', 1, 0, 2, '控制材质、纹理和局部结构的增强力度。')
    slider(neural, 'skin', '人物结构', 0, 0, 2, '自动识别人像区域后调整其结构；数值越高，改动通常越明显，并非保护程度越高。')
    w.mask_check = QCheckBox('自动识别人像区域')
    w.mask_check.setChecked(True)
    neural.addWidget(w.mask_check)
    neural.addStretch()
    w.profile_label = label('当前帧调参 · 参数变化后自动处理', 'muted')
    neural.addWidget(w.profile_label)
    slider(light, 'global_tone', '全局光影 · 混合', 1, 0, 2, '调整 NR 带来的大范围明暗变化，保留细节变化。1 为原始 NR 结果。此项由工作台实现。')
    slider(light, 'local_tone', '局部光影', 1, 0, 2, '调整 NR 对局部明暗、光照和对比关系的处理强度。')
    white_switch = QHBoxLayout()
    w.white_check = QCheckBox('启用 Diffuse White')
    w.white_check.setChecked(False)
    w.white_check.setToolTip('试验参考白换算，可能改变对比度或产生发灰；完整颜色适配尚待验证。关闭后恢复标准颜色处理。')
    white_switch.addWidget(w.white_check)
    white_switch.addWidget(label('实验性功能', 'muted'))
    white_switch.addStretch()
    light.addLayout(white_switch)
    white = slider(light, 'white', 'Diffuse White / nits', 100, 40, 500, '参考白亮度。仅开启实验开关时参与处理；不是显示器背光。当前使用线性参考白换算供对照试验，完整颜色适配尚待验证。')
    white.spin.setDecimals(0)
    white.spin.setSingleStep(5)
    white.setEnabled(False)
    w.white_check.toggled.connect(white.setEnabled)
    w.white_check.toggled.connect(w.parameters_changed)
    slider(light, 'color', '增强色彩', 1, 0, 1, '1 保留 NR 色彩；0 按增强后的亮度等比例缩放原片 RGB，保留原片色彩比例。超出 SDR 范围的高光最终仍会裁切。')
    light.addStretch()
    light.addWidget(button('恢复全部默认值', w.reset_parameters, 'quiet'))
    w.scale_combo = combo(output, '输出倍率', ['1× · 仅 NR', '2× · RTX 超分 + NR', '4× · RTX 超分 + NR'])
    w.scale_combo.setCurrentIndex(1)
    w.pass_combo = combo(output, 'NR 处理次数', ['1 次', '2 次', '3 次', '4 次'])
    w.pass_combo.setToolTip('真正连续运行 1～4 次 NR；每层拥有独立的时序历史。次数越多，显存和耗时越高。')
    w.motion_combo = combo(output, '运动估计', ['NVIDIA 光流', '关闭光流'])
    w.motion_combo.setToolTip('使用相邻帧估计运动。单帧预览会先读入最多 2 帧历史；全片导出连续处理。')
    slider(output, 'detail', '与原图混合', 1, 0, 1, '0 为超分后的原图，1 为完整 NR 结果。')
    w.output_size = label('导入视频后显示输出尺寸', 'muted')
    output.addWidget(w.output_size)
    w.auto_render = QCheckBox('调参后自动预览当前帧')
    w.auto_render.setChecked(True)
    w.auto_render.toggled.connect(w.auto_changed)
    output.addWidget(w.auto_render)
    actions = QGridLayout()
    actions.setColumnStretch(0, 1)
    actions.setColumnStretch(1, 1)
    w.render_button = button('渲染当前帧', w.render_current)
    w.render_video_button = button('渲染视频', w.render_video)
    w.save_frame_button = button('保存当前图片', w.save_frame)
    w.export_button = button('导出视频', w.export_video, 'primary')
    w.render_video_button.setToolTip('按当前参数处理整段视频。完成后点击“导出视频”选择保存位置；关闭软件会清理临时结果。')
    w.export_button.setToolTip('先渲染视频，再保存已完成的结果；修改参数后需重新渲染视频。')
    for index, control in enumerate((w.render_button, w.render_video_button, w.save_frame_button, w.export_button)):
        control.setFixedHeight(36)
        control.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        actions.addWidget(control, index // 2, index % 2)
    output.addLayout(actions)
    output.addWidget(label('MP4 / H.264 · 保留原音轨', 'muted'))
    for control in (w.style_combo, w.scale_combo, w.pass_combo, w.motion_combo):
        control.currentIndexChanged.connect(w.parameters_changed)
    w.mask_check.toggled.connect(w.parameters_changed)
    outer.addWidget(w.parameters_widget)

    w.progress = QProgressBar()
    w.progress.setTextVisible(False)
    w.progress.setVisible(False)
    outer.addWidget(w.progress)
    footer = QHBoxLayout()
    w.status = label('● 就绪 · 导入 SDR 视频开始', 'muted')
    w.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    footer.addWidget(w.status, 1)
    w.cancel_button = button('取消任务', w.cancel_job, 'quiet')
    w.cancel_button.setVisible(False)
    footer.addWidget(w.cancel_button)
    footer.addWidget(button('查看日志', w.show_log, 'quiet'))
    footer.addWidget(label('ITER-003', 'muted'))
    outer.addLayout(footer)
    w.update_buttons()
