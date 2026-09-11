# kk-mix

基于 FFmpeg 的 Windows 批量视频混剪工具。PySide6 + Fluent Design 界面，15 个批处理功能页，一键打包为免安装绿色版。

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

## 功能一览

| 功能 | 说明 |
|---|---|
| 左右分屏合并 | 两个文件夹按序配对，`hstack` 左右拼成 1080×1080；支持图片输入 |
| 转场拼接 | N 个文件夹按序取第 i 个视频拼接，20 种 `xfade` 转场 + `acrossfade` 音频过渡，自动统一分辨率/帧率 |
| 字幕转场拼接 | 在转场拼接基础上，每个文件夹配多行文案，经 [Index-TTS](docs/index-tts-api.md) 合成配音，片段自动对齐配音时长 |
| 批量分割 | 按固定秒数切段，可选同时导出 MP3、保留末尾余数片段 |
| 画中画合成 | 前景视频叠加到背景视频，预设位置 + 缩放比例 |
| 批量变速/倒放 | 0.1x–5x 变速，可倒放，音频同步 |
| 批量旋转/翻转 | 90°/180°/270° 旋转与水平/垂直翻转 |
| 批量添加水印 | 图片水印，预设位置 + 透明度 + 缩放 |
| 批量调整音量 | 0.1x–10x 倍率 |
| 批量添加标题 | 系统字体（中文名友好）、颜色、字号（像素/百分比）、按视频宽度自动换行，标题可来自 TXT 逐行分配 |
| 批量填充音乐 | 用指定音频替换视频音轨，或与原声混合 |
| 批量裁剪比例 | 9:16 / 16:9 / 1:1 等居中裁剪，视频与图片均支持 |
| 批量压缩 | 指定目标码率，可选 H.265 编码 |
| 批量格式转换 | 转为 mp4 / avi / mov / mkv |
| 批量提取帧 | 按间隔抽帧为图片 |

通用能力：暂停 / 停止、实时日志与导出、极速模式（`ultrafast`）、统一码率或 CRF 控制、完成后一键打开输出目录。

## 快速开始（源码运行）

### 环境要求

- Windows 10/11 x64
- Python ≥ 3.10（开发使用 3.14）
- [uv](https://docs.astral.sh/uv/)（依赖管理，`pip install uv` 或官方安装脚本）
- `ffmpeg.exe` / `ffprobe.exe`（**不随仓库分发**，见下文）

### 步骤

```bash
git clone https://github.com/jaikydota/kk-mix.git
cd kk-mix

# 1. 安装依赖（自动创建 .venv）
uv sync

# 2. 放置 FFmpeg
#    从 https://www.gyan.dev/ffmpeg/builds/ 或 https://github.com/BtbN/FFmpeg-Builds/releases
#    下载 Windows 静态构建，把 ffmpeg.exe 和 ffprobe.exe 复制到项目根目录
#    （或加入系统 PATH，程序会按 项目目录 → PATH → C:\ffmpeg\bin 的顺序查找）

# 3. 运行
uv run python kk_qt.py        # 或双击 start.cmd
```

源码运行时**没有编译授权模块**，程序自动进入开发模式，跳过授权码验证。

### 配置

程序目录下的 `settings.json` 保存全局设置（也可在界面「全局设置」中修改）。仓库提供了 `settings.example.json`：

```bash
cp settings.example.json settings.json
```

| 字段 | 说明 |
|---|---|
| `tts_base_url` / `tts_api_key` | Index-TTS 服务地址与 api-key，仅「字幕转场拼接」需要 |
| `verbose_log` | 打印完整的 ffmpeg 命令与 stderr |
| `speed_priority` | `true` 用 `ultrafast` 预设，`false` 用 `medium` |
| `compress_video` / `bitrate` | 开启后用 `-b:v <bitrate>`，否则 `-crf 23` |

### 字幕转场拼接（TTS）

该功能需要一个自建的 Index-TTS 服务，接口约定见 [docs/index-tts-api.md](docs/index-tts-api.md)。此外：

1. 把用于音色克隆的参考音频放到 `assets/tts_reference.wav`（已 gitignore，不会被提交）；
2. 在「全局设置」填写服务地址和 api-key；
3. 首次运行会自动把参考音上传到服务端。

## 打包发布

打包产物是 `dist/kk_qt/` 目录（含 ffmpeg、授权模块 `.pyd`），可直接压缩分发给最终用户。

### 额外要求

- **Visual Studio Build Tools**（含「使用 C++ 的桌面开发」工作负载）——Cython 编译授权模块需要 MSVC
- `uv sync` 已同时安装 dev 依赖（Cython、PyInstaller）

### 一键打包

```bat
build_qt.cmd
```

流程：`setup_cython.py` 编译 `_license_core.pyx` → PyInstaller 打包主程序 → PyInstaller 打包 `keygen.exe` → 压缩为 `dist/kk_qt_<时间戳>.zip`。

也可以分步执行：

```bash
uv run python setup_cython.py build_ext --inplace   # 生成 _license_core.cp3xx-win_amd64.pyd
uv run pyinstaller kk_qt.spec --clean --noconfirm   # 生成 dist/kk_qt/
```

### 授权机制与密钥（发布前必读）

程序内置「一机一码」授权：机器码 = 主板 UUID + CPU ID 的 MD5；授权码 = AES-CBC 加密的 JSON（到期时间、绑定机器码）；`keygen.exe` 需管理员密码才能生成授权码。核心逻辑在 `_license_core.pyx`，编译为 `.pyd` 提高逆向门槛。

**仓库里不包含任何真实密钥。** `.pyx` 中的加密种子和管理员密码哈希是占位符，由 `setup_cython.py` 在编译时注入：

```bash
cp build_secrets.env.example build_secrets.env   # 已 gitignore
# 编辑 build_secrets.env：
#   KK_LICENSE_SEED=<一段随机长字符串>
#   KK_ADMIN_PASSWORD=<keygen 管理员密码>
build_qt.cmd
```

也可以直接用同名环境变量（优先级高于文件）。不设置时使用开发默认值（seed=`kk-mix-dev`，密码=`admin`），**仅供本地调试，切勿用于正式发布**。换了 seed 后，之前发出的授权码全部失效。

如果你不需要授权功能，直接删掉 `kk_qt.py` 中的 `check_license()` 调用即可，其余代码不依赖 `.pyd`。

## 项目结构

```
kk-mix/
├── kk_qt.py                 # 入口：QApplication → 授权检查 → MainWindow
├── kk_qt.spec               # PyInstaller 配置（UPX 白名单、排除模块）
├── build_qt.cmd             # 一键打包脚本
├── setup_cython.py          # Cython 编译 + 密钥注入
├── _license_core.pyx        # 授权核心（占位符，编译时注入真实密钥）
├── keygen.py                # 授权码生成器（Tkinter，独立打包）
├── settings.example.json    # 配置模板
├── build_secrets.env.example
├── assets/                  # logo；tts_reference.wav 需自行放置
├── docs/
│   └── index-tts-api.md     # TTS 服务接口约定
└── qt/
    ├── main_window.py       # 导航 + 页面栈 + 日志/进度/暂停停止面板
    ├── settings_window.py   # 全局设置对话框
    ├── core/
    │   ├── batch_worker.py  # BatchWorker(QThread) 基类、暂停/停止控制、统一 run_cmd
    │   ├── ffmpeg_helper.py # 查找 ffmpeg / ffprobe 探测 / 编码参数
    │   ├── app_settings.py  # AppSettings dataclass + JSON 持久化
    │   ├── paths.py         # 版本号、扩展名集合、资源路径
    │   ├── fonts.py         # 系统字体枚举（中文名映射）、标题自动换行
    │   ├── tts_client.py    # Index-TTS 客户端
    │   └── license.py       # 授权对话框
    └── tabs/                # 每个功能一个文件，均继承 BaseTab
```

### 添加一个新功能页

1. 新建 `qt/tabs/<name>.py`：
   - `class <Name>Worker(BatchWorker)`：实现 `run_batch() -> (success, summary)`，循环中调用 `self.ctrl.wait_if_paused()`，用 `self.run_cmd(cmd)` 执行 ffmpeg，设置 `self.output_dir`；
   - `class <Name>Tab(BaseTab)`：定义 `NAME / TITLE / ICON`，实现 `build_form()`（往 `self.form_layout` 填控件）和 `build_worker()`（校验参数并返回 Worker）。
2. 在 `qt/main_window.py` 的 `_register_tabs()` 列表中加入 `<Name>Tab(self)`。

更多约定见 [AGENTS.md](AGENTS.md)。

## 常见问题

**启动提示「未找到 FFmpeg」** — 确认 `ffmpeg.exe` 在项目根目录或 PATH 中；打包版会自动内嵌。

**打包后启动即崩溃** — 多半是 UPX 压缩了 Qt DLL。`kk_qt.spec` 已把 `Qt6*.dll` 和 VC 运行库加入 `upx_exclude`，新增 DLL 时同样要加白名单，或直接关掉 UPX。

**`setup_cython.py` 报找不到 `cl.exe`** — 未安装 MSVC Build Tools，或需要在「x64 Native Tools Command Prompt」中执行。

**添加标题时「字体加载失败」** — 选择的字体文件不是 TTF/OTF/TTC，或路径含特殊字符；换一个系统字体重试。

**字幕转场拼接报 401 / 缺少参考音** — 检查 `settings.json` 的 api-key；确认 `assets/tts_reference.wav` 存在（首次运行需上传）。

## 参与贡献

欢迎 Issue 和 PR。提交前请确保 `uv run python kk_qt.py` 能正常启动，且新功能页遵循上面的约定。

## 许可证

[MIT](LICENSE) © 2026 jaikydota

本项目使用 [FFmpeg](https://ffmpeg.org/)（LGPL/GPL，需自行下载）、[PySide6](https://doc.qt.io/qtforpython/)（LGPL）、[PySide6-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)（GPLv3，商业使用请注意其许可条款）。
