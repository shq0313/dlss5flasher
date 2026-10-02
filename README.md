# dlss5flasher
点点星星吧
面向 Windows / NVIDIA 的本地视频增强工作台：定位当前帧、调节神经增强、划线比较原图与结果，保存图片或渲染并导出整段视频。目前为早期预览阶段。

Local video enhancement workbench for Windows and NVIDIA GPUs, with adjustable frame previews, before/after comparison, image saving and video export. The NR runtime must be supplied by the user. This is an early preview, not a real-time enhanced video player.
开发契机是本人在刷视频的时候，刷到了一个讲主机游戏利用采集卡在pc用上dlss5，于是乎决定按照这个逻辑开发一个播放器，加上我自己在玩游戏的时候用过相关的插件
**当前定位：Windows x64 / NVIDIA 显卡专属。** NVIDIA 驱动由用户自行准备，软件不负责安装或更新驱动； AMD 显卡适配目前在尝试适配中。显卡与 NR 运行库的兼容性以实际验证记录为准。

**NR 运行库需自行下载：**Releases 发布包不附带 `nvngx_dlssnr.dll`。（我研究研究怎么弄一个下载页）适配自己显卡的 DLL 放到 `runtime/DLSS-NR/1.3/bin/`，或启动后点击右上角“运行库”选择它。缺少它时可以打开界面，但无法渲染。不保证任意来源的同名 DLL 可用。
nvngx_dlssnr.dll需要选择好自己的显卡版本，目前30 40 50系已经测试成功
## 启动

从 [Releases](https://github.com/shq0313/dlss5flasher/releases) 下载可用的 Windows 便携包，完整解压到可写目录，再双击根目录 **启动.bat**。便携包内置 Python、Python 依赖和 FFmpeg，不依赖 ComfyUI 或系统 Python。GitHub 的“Source code”下载只有源码，不能当作便携包直接启动。

```powershell
.\python_embeded\python.exe .\launch.py
```

## 使用

1. 导入或拖入视频。
2. 使用时间线或左右按钮定位。播放用于静音浏览原片，暂停后处理选中的帧。
3. 下方三组卡片调参，停手后自动预览（模型参数约 350 毫秒，合成参数约 60 毫秒防抖）；只展示最新参数对应的结果。取消勾选“自动预览”可改为点击“渲染当前帧”。
4. 鼠标移动进行左原图／右增强划线对比；滚轮缩放、中键平移、“适应窗口”复位。
5. 四个等大按钮按两行两列排列：“渲染当前帧”处理选中帧，“保存当前图片”保存增强 PNG 与参数 JSON；“渲染视频”按当前参数处理整段视频，“导出视频”选择保存位置、复制已经渲染完成的结果，不重复推理或编码。
6. 整段视频渲染完成后才能导出；修改参数、素材或运行库后需重新渲染。临时结果只在当前软件窗口内保留，关闭软件前请导出。单帧素材不启用视频按钮。
7. 渲染进度百分比后显示预计剩余时间（HH:MM:SS）：取第 2～11 帧的平均耗时乘以剩余帧数，排除首帧初始化耗时。收集样本时显示“计算中”；不足 11 帧的短视频从第 2 帧起使用已有样本。该时间只估算逐帧渲染，最后的音频合并和输出验证会单独提示。

视频输出为 H.264 / MP4。“视频编码”下拉框可选 **GPU 硬件编码（NVENC）** 或 **CPU 编码（x264）**，默认 GPU。NVENC 使用 P5 / HQ / VBR / CQ 19，CPU 保留 CRF 18 / fast；两套质量数值不等价，不保证相同画质或文件大小。两种方式的 DLSS 增强都在显卡上执行。GPU 编码不可用时提示手动选择 CPU，不会自动替换选择；本版未做速度对比测试。

切换编码方式不影响当前帧预览，需要重新渲染整段视频后导出。输出保留源帧率和可复制到 MP4 的原音轨；不会覆盖源视频或已有目标。字幕、章节、额外视频轨道不保留。

## 控件的真实含义

| 控件 | 实现与说明 |
| --- | --- |
| 风格、整体增强 | NR 原生风格与强度；高强度不等于更还原。 |
| 结构细节、局部光影 | NR 原生纹理／结构和局部明暗参数。 |
| 人物结构、自动识别人像区域 | NR SkinStructureStrength 与 UseAutoMask；数值不是“保护程度”，识别效果依赖素材和运行库。 |
| Diffuse White / nits | 旁设“启用 Diffuse White”开关并标注“实验性功能”，默认关闭。关闭使用修复后的 SDR 颜色路径，参考白数值不参与处理；开启试用线性参考白换算，可能改变对比度／发灰，完整颜色适配尚待验证。恢复默认值会关闭开关。 |
| 全局光影·混合 | 本应用调节 NR 带来的大范围亮度变化。当前 DLL 不响应 GlobalToneStrength，因此使用应用自身的亮度混合处理。 |
| 增强色彩 | 0 按增强亮度等比例缩放原片 RGB，1 使用 NR 色彩；超出 SDR 显示范围的高光仍可能裁切。 |
| 与原图混合 | 0 为超分原图，1 为完整 NR 结果。 |
| NR 处理次数 | 1～4 个独立 Feature 连续计算，每层有独立历史，增加时间和显存。 |
| 输出倍率 | 1× 仅 NR；2×／4× 使用 RTX Video Super Resolution，再执行 DLSS NR。旧 DLSS SR 的 1.5×／3× 不在新界面中。 |
| 运动估计 | NVIDIA 硬件光流或关闭。预览最多读入 2 帧历史，导出连续处理。 |

光影混合、增强色彩、原图混合可复用当前帧的浮点增强结果，无需重新运行 NR。其他模型参数改变后重建 Feature，引擎进程保持常驻。

## 实测与边界

RTX 5060 / studio驱动 616.92：576×320 测试帧单次 NR 调参约 0.22～0.25 秒，缓存合成约 0.02 秒，4 次 NR 约 0.90 秒；人像 640×960 → 1280×1920、含两帧历史的 GUI 预览约 2.58～2.68 秒。这些数据包含对应测试的处理开销，不是纯 GPU 推理指标，不能推广到所有素材。

当前由 Qt 显示，DX12 负责推理，尚不是解码、推理、显示全驻留显卡的原生播放器。尚未实现实时增强播放、音频播放、HDR 文件、RAFT、批量队列、 游戏滤镜。后续会作为更新指标，并且添加re滤镜（其实批量队列很快就能弄好，看一下反响吧，有人留言我就做了）

## 便携目录

```text
启动.bat / launch.py             入口
python_embeded/                 内置 Python 及依赖
ffmpeg-8.0.1-full_build/         本地视频工具
runtime/dlssnr_host_v2.dll       本项目编译的 DX12 NR 宿主
runtime/DLSS-NR/1.3/bin/         用户自行放入 NR DLL
runtime/RTX-Video/              RTX Video VSR 运行库
app/                           界面、处理、隔离进程与光流代码
native/                        宿主源码及构建脚本
licenses/                      上游源码许可
output/                        默认视频导出目录
.work/                         临时文件与诊断日志
docs/                          使用与发布说明
```

路径按项目根目录解析。顶部“运行库”直接选择 `nvngx_dlssnr.dll`；VSR 和本项目宿主使用项目内副本。便携包不包含旧版 CLI、DLSS SR DLL 或其他显卡的 NR 压缩包。

## 验证与原生构建

```powershell
.\python_embeded\python.exe -m unittest discover -s tests -v
# 原生 NR 宿主：需要 MSVC 与 third_party/NVIDIA-DLSS 中的 SDK
cmd /c native\host_v2\build.bat
```

日常运行不需要编译器或 SDK。随包 VSR 运行库已与 RTX Video SDK 1.1.0 的 x64 正式版核对一致；原生 VSR 宿主的重新构建需要另行准备该 SDK。

源码环境可用 Python 3.13 安装 `requirements-lock.txt`，另行准备 FFmpeg、原生宿主及运行库。自动化单元测试不代表所有显卡均可运行。

FFmpeg CLI 支持用 `FFMPEG_EXE` / `FFPROBE_EXE` 环境变量指定可执行文件的完整路径；否则寻找随包目录、根目录，再寻找系统 PATH。指定 FFmpeg 时也会查找同目录的 FFprobe。该设置只替换命令行工具，PyAV 内置媒体库保持独立；无需额外安装 imageio-ffmpeg。

## 许可与致谢

项目自有代码采用 [MIT License](LICENSE)。便携包中的 Qt／PySide6、FFmpeg、Python 和 NVIDIA VSR 等第三方组件仍受各自上游许可约束，不属于本项目的 MIT 授权范围。详情见 [第三方声明](THIRD_PARTY_NOTICES.md)、随包 `licenses/` 和 [依赖源码说明](docs/依赖源码说明.md)，也可点击软件右上角“许可”查看。发布包不包含 `nvngx_dlssnr.dll`，需用户自行准备。本项目与 NVIDIA 无隶属或官方背书关系。
