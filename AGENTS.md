# kk-mix — FFmpeg 批处理视频编辑工具（Qt 版）

## 项目概览

- 语言：Python 3.14，入口 `kk_qt.py`，业务模块全部在 `qt/` 目录下
- UI：PySide6 + PySide6-Fluent-Widgets（Windows 11 Fluent 风格）
- 核心：调用 `ffmpeg.exe` / `ffprobe.exe` 完成视频处理
- 授权：`_license_core.pyx` → Cython 编译为 `.pyd`（防反编译）
- 打包：Cython → PyInstaller → `dist/kk_qt/`（内嵌 ffmpeg.exe + .pyd）
- 依赖管理：`uv`（运行命令统一用 `uv run python ...`）
- 版本：v9.6，Windows 平台

## 目录结构

```
kk-mix/
├── kk_qt.py                   # Qt 版入口（QApplication + License + MainWindow）
├── kk_qt.spec                 # PyInstaller 打包配置
├── build_qt.cmd               # 一键打包：Cython → PyInstaller → ZIP
├── setup_cython.py            # Cython 编译脚本
├── keygen.py                  # 授权码生成器（独立工具）
├── _license_core.pyx          # 授权核心源码（禁止分发）
├── qt/
│   ├── main_window.py         # 主窗口：NavigationInterface + QStackedWidget + 日志面板
│   ├── settings_window.py     # 全局设置对话框（MessageBoxBase）
│   ├── core/
│   │   ├── paths.py           # 路径工具：resource_path / settings_path / list_media
│   │   ├── ffmpeg_helper.py   # FFmpeg 工具：find_ffmpeg / probe_* / encode_preset
│   │   ├── app_settings.py    # @dataclass AppSettings + JSON 持久化
│   │   ├── batch_worker.py    # BatchControl + BatchWorker(QThread) 基类
│   │   ├── license.py         # LicenseDialog(QDialog) + check_license
│   │   ├── readme.py          # ReadmeDialog(QDialog) + check_readme（首次启动必读）
│   │   └── fonts.py           # list_system_fonts + wrap_title_text
│   └── tabs/
│       ├── base.py            # BaseTab 抽象基类（所有功能 Tab 继承）
│       ├── merge.py           # 左右分屏合并
│       ├── concat.py          # 转场拼接（动态文件夹行 + xfade）
│       ├── split.py           # 批量分割视频
│       ├── pip.py             # 画中画合成
│       ├── speed.py           # 批量变速/倒放
│       ├── rotate.py          # 批量旋转/翻转
│       ├── watermark.py       # 批量添加水印
│       ├── volume.py          # 批量调整音量
│       ├── title.py           # 批量添加标题（字体/颜色/换行）
│       ├── music.py           # 批量填充音乐
│       ├── crop.py            # 批量裁剪比例
│       ├── compress.py        # 批量压缩视频
│       ├── convert.py         # 批量格式转换
│       └── extract.py         # 批量提取视频帧
└── old_kk/                    # 旧版 Tkinter 代码（归档，不再维护）
```

## 架构模式

```
kk_qt.py
└── MainWindow (qt/main_window.py)
    ├── NavigationInterface          # 左侧导航菜单
    ├── QStackedWidget               # 右侧内容区（每个 Tab 一页）
    │   └── BaseTab (qt/tabs/base.py)
    │       ├── build_form()         # 子类实现：填充表单控件
    │       └── build_worker()       # 子类实现：校验参数，返回 BatchWorker
    ├── 日志/进度/控制面板            # 底部 QSplitter
    └── run_worker(worker)           # 启动 QThread，连接信号
```

## 添加新功能 Tab 的标准流程

```
1. qt/tabs/<name>.py
   - class <Name>Worker(BatchWorker):
       def __init__(self, ...): self.output_dir = output_folder
       def run_batch(self) -> tuple[bool, str]: ...
   - class <Name>Tab(BaseTab):
       NAME / TITLE / ICON
       def build_form(self): ...    # 往 self.form_layout 填控件
       def build_worker(self): ...  # 校验参数，返回 Worker 或 None

2. qt/main_window.py → _register_tabs()
   - 导入 <Name>Tab
   - 添加到 tabs 列表
```

## 关键约定

- **日志**：`self.log(msg)` 通过 Signal 线程安全输出，所有操作必须用它
- **FFmpeg 路径**：`find_ffmpeg()` 自动查找，禁止硬编码
- **批处理线程**：必须继承 `BatchWorker(QThread)`，禁止用 `threading.Thread`
- **暂停/停止**：`self.ctrl.wait_if_paused()` 检查标志，循环中调用
- **FFmpeg 执行**：`self.run_cmd(cmd)` 统一入口（隐藏黑窗 + 详细日志 + 编码容错）
- **输出目录**：Worker 必须设置 `self.output_dir`，完成后 InfoBar 可打开文件夹
- **设置管理**：`AppSettings` dataclass，JSON 持久化，Worker 构造时拷贝快照
- **授权**：所有逻辑在 `_license_core.pyx`，禁止在 .py 文件中出现密钥/密码明文
- **构建**：先 `uv run python setup_cython.py build_ext --inplace`，再 `build_qt.cmd`
- **打包排除**：`kk_qt.spec` 已排除 tkinter / moviepy / matplotlib 等无关大模块
- **UPX 白名单**：Qt6*.dll 和 VC Runtime 禁止 UPX 压缩（会导致启动崩溃）

## 现有功能 Tab（14 个）

merge / concat / split / pip / speed / rotate / watermark / volume / title / music / crop / compress / convert / extract
