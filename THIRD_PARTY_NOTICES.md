# 第三方组件与许可

项目自有代码采用 MIT，第三方组件分别适用原许可，不能整体重新授权为 MIT。Qt 动态库保持独立，用户可以替换兼容版本；对 LGPL 库的修改和调试适用其原许可。

| 组件 | 版本与来源 | 原许可位置 |
| --- | --- | --- |
| CPython | 3.13.12 x64 | PSF 等，python_embeded/LICENSE.txt |
| PySide6 Essentials / Shiboken6 / Qt | 6.11.2，PyPI | LGPLv3 / GPL 等，site-packages 内 dist-info/licenses 及包内声明 |
| PyAV | 17.0.1，官方 Windows wheel | BSD-3-Clause，av-17.0.1.dist-info/licenses；内置 FFmpeg DLL 自报 LGPLv3+，单独适用许可 |
| NumPy | 2.3.2 | numpy-2.3.2.dist-info/licenses，包含二进制依赖声明 |
| Pillow | 12.2.0 | pillow-12.2.0.dist-info/licenses |
| FFmpeg / FFprobe | Gyan 8.0.1 full build | GPLv3，ffmpeg-8.0.1-full_build/LICENSE；该目录 README.txt 保留精确提交和构建配置 |
| DLSS5Tool | https://github.com/banbanzhige/DLSS5Tool | MIT，licenses/DLSS5Tool-MIT.txt |
| NVIDIA Optical Flow API ABI | NVIDIA / DLSS5Tool | 源文件及 licenses/NVIDIA-OpticalFlow.txt |
| NVIDIA RTX SDK / DLSS SDK | https://github.com/NVIDIA/DLSS | NVIDIA 专有 SDK 许可，licenses/NVIDIA-RTX-SDK.txt |
| NVIDIA VSR | 来自 DLSS5Tool v2.3.3 完整包 | NVIDIA 专有运行库许可；VSR 宿主源码另适用 MIT |

native/host_v2、native/vsr_host、app/vendor/nvofa.py 基于 DLSS5Tool，保留上游版权和 MIT 声明。NR 宿主由本项目编译，VSR 宿主使用上游二进制并附对应源码。

NR DLL、旧版 video2dlssnr CLI、DLSS SR DLL、30 / 40 / 50 压缩包均不包含在候选包内。用户另行取得 NR 运行库并遵守其来源许可，本项目不授予该文件的使用或再分发权。

RenoDX / DXL 为交互和参数研究参考，当前没有复制其实现源码。本项目与 NVIDIA 无隶属或官方背书关系。

依赖源码与公开分发前的核验状态见 [依赖源码说明](docs/依赖源码说明.md)。保留许可证文件不等于已经完成所有二进制分发义务。
