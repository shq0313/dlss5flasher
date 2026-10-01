# 第三方组件与许可

项目自有代码采用 MIT。以下第三方组件适用各自原始许可，不被本项目 MIT 许可证重新授权。完整版权与许可文本随包保留于 [licenses](licenses/README.md) 和各依赖的安装目录。

| 组件 | 版本与用途 | 原始许可／声明 |
| --- | --- | --- |
| CPython | 3.13.12，内置解释器 | [PSF 及附带组件许可](licenses/CPython/LICENSE.txt) |
| Qt / PySide6 Essentials / Shiboken6 | 6.11.2，桌面界面 | [LGPLv3](licenses/Qt/LGPL-3.0-only.txt)、[GPLv3](licenses/Qt/GPL-3.0-only.txt) 及 Qt 源码中的模块、第三方许可；动态库保持独立 |
| PyAV | 17.0.1，媒体读写 | [BSD 原许可](licenses/PyAV/LICENSE.txt)；内置 FFmpeg 与编码库另适用原许可，不能只按 PyAV 的 BSD 或 DLL 自报 LGPL 判断 |
| FFmpeg / FFprobe CLI | Gyan 8.0.1 full build | [GPLv3](licenses/FFmpeg-CLI/LICENSE.txt)、[上游构建记录](licenses/FFmpeg-CLI/UPSTREAM_BUILD.txt) |
| NumPy | 2.3.2，数组运算 | [原许可及所含依赖声明](licenses/NumPy/LICENSE.txt) |
| Pillow | 12.2.0，图像处理 | [原许可及所含依赖声明](licenses/Pillow/LICENSE.txt) |
| 原生宿主及光流辅助代码 | DX12 推理与运动估计 | [原版权与 MIT 许可](licenses/DLSS5Tool-MIT.txt)、[NVIDIA Optical Flow ABI 许可](licenses/NVIDIA-OpticalFlow.txt)；源文件声明保留 |
| NVIDIA DLSS / NGX SDK | 原生宿主的编译依赖 | [NVIDIA RTX SDKs 原许可](licenses/NVIDIA-RTX-SDK.txt) |
| NVIDIA RTX Video VSR | SDK 1.1.0 x64 正式版，视频超分 | [SDK 自带原许可 PDF](licenses/NVIDIA-RTX-Video-SDK.pdf)；随包 DLL 与该 SDK 文件 SHA256 一致且 NVIDIA 签名有效 |

## Qt / LGPL 用户权利

本软件使用 LGPL 授权的 Qt 库。相应库保持动态链接，用户可依其许可修改、替换兼容版本，并为调试这些修改进行必要的逆向工程。NVIDIA 专有组件的限制只适用于相应 NVIDIA 组件，不用于限制 Qt 或其他 LGPL 组件赋予用户的权利。

## NVIDIA 组件

NVIDIA RTX、NVIDIA GeForce RTX 及其他相关名称属于 NVIDIA。SDK 组件的使用和分发受上述 NVIDIA 原许可及补充条款约束；本项目与 NVIDIA 无隶属关系，也不表示官方背书。原生宿主使用 NVIDIA DLSS / NGX SDK，视频超分使用 NVIDIA RTX Video SDK。

发布包不包含 `nvngx_dlssnr.dll`、旧版 CLI、DLSS SR DLL 或显卡代际 NR 压缩包。NR 运行库需用户从有权提供的来源自行取得；本项目不授予该文件的使用或再分发权。“社区项目”不是上游许可的豁免条件。

## 对应源码及构建资料

已收集的版本、来源、校验方式和未决事项见 [依赖源码说明](docs/依赖源码说明.md)。发布目录另有第三方源码资料包，包含 Qt、PySide6、CPython、PyAV、FFmpeg 主源码、相关构建配方和已核对的依赖源码。该资料包不包含 NVIDIA SDK 二进制或 NR DLL，不将尚未取得的完整构建材料标成已具备。
