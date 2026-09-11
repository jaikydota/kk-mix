# kk-mix — FFmpeg 批处理视频混剪工具（Qt 版）

面向 AI 助手 / 贡献者的项目约定。用户向文档见 README.md。

## 项目概览

- 语言：Python ≥ 3.10（开发用 3.14），入口 `kk_qt.py`，业务模块全部在 `qt/` 目录下
- UI：PySide6 + PySide6-Fluent-Widgets（Windows 11 Fluent 风格）
- 核心：调用 `ffmpeg.exe` / `ffprobe.exe` 完成视频处理（二进制不入库，放项目根目录或 PATH）
- 授权：`_license_core.pyx` → Cython 编译为 `.pyd`；种子与总开关由 `setup_cython.py` 在编译时从环境变量 / `build_secrets.env` 注入，源码只有占位符
- 授权校验默认**关闭**（`KK_LICENSE_ENABLED` 未设置），开关烧录在 `.pyd` 内，运行期不可篡改；判定统一走 `qt/core/license.py` 的 `licensing_active()`
- 打包：Cython → PyInstaller → `dist/kk_qt/`（内嵌 ffmpeg.exe + .pyd），脚本 `build_qt.cmd`
- 依赖管理：`uv`（运行命令统一用 `uv run python ...`）
- 版本号：唯一来源 `qt/core/paths.py` 的 `VERSION`，`pyproject.toml` 的 `version` 同步
- 界面语言：中英双语，`qt/core/i18n.py` 的 `tr()`，中文为源语言且为默认语言，英文表在 `qt/core/translations_en.py`
- 开源协议：MIT；Windows 平台

## 目录结构

```
kk-mix/
├── kk_qt.py                   # Qt 版入口（QApplication + License + MainWindow）
├── kk_qt.spec                 # PyInstaller 打包配置（.gitignore 中显式 !kk_qt.spec）
├── build_qt.cmd               # 一键打包：Cython → PyInstaller → ZIP
├── setup_cython.py            # Cython 编译脚本 + 密钥注入
├── keygen.py                  # 授权码生成器（Tkinter 独立工具，无访问口令，不可随程序分发）
├── _license_core.pyx          # 授权核心源码（含 @@占位符@@，编译时替换）
├── settings.example.json      # 配置模板；settings.json 本身已 gitignore
├── build_secrets.env.example  # 密钥模板；build_secrets.env 已 gitignore
├── docs/
│   └── index-tts-api.md       # Index-TTS 接口约定
├── assets/                    # logo.ico / logo.png；tts_reference.wav 用户自备（gitignore）
└── qt/
    ├── main_window.py         # 主窗口：NavigationInterface + QStackedWidget + 日志面板
    ├── settings_window.py     # 全局设置对话框（MessageBoxBase）
    ├── core/
    │   ├── paths.py           # VERSION / APP_TITLE / 扩展名集合 / resource_path / list_media
    │   ├── ffmpeg_helper.py   # find_ffmpeg / probe_* / encode_preset / quality_args
    │   ├── app_settings.py    # @dataclass AppSettings + JSON 持久化
    │   ├── batch_worker.py    # BatchControl + BatchWorker(QThread) 基类
    │   ├── tts_client.py      # Index-TTS 客户端（上传参考音 + 合成）
    │   ├── i18n.py            # tr() / set_language / detect_system_language
    │   ├── translations_en.py # 英文译文表 EN: {中文原文: 英文}
    │   ├── license.py         # LicenseDialog + check_license（无 .pyd 时开发模式放行）
    │   └── fonts.py           # list_system_fonts + wrap_title_text
    └── tabs/
        ├── base.py            # BaseTab 抽象基类
        ├── merge.py           # 左右分屏合并
        ├── concat.py          # 转场拼接（含 _TRANSITIONS 表）
        ├── subtitle_concat.py # 字幕转场拼接（TTS 配音对齐）
        ├── split.py / pip.py / speed.py / rotate.py / watermark.py / volume.py
        ├── title.py / music.py / crop.py / compress.py / convert.py / extract.py
├── tools/
│   └── check_i18n.py          # i18n 覆盖率检查（未包装中文 / 缺译文 / 占位符不一致）
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

3. 英文译文补进 qt/core/translations_en.py，运行 uv run python tools/check_i18n.py
4. README.md / README.zh-CN.md 功能表各加一行
```

## 关键约定

- **日志**：`self.log(msg)` 通过 Signal 线程安全输出，所有操作必须用它
- **FFmpeg 路径**：`find_ffmpeg()` 自动查找，禁止硬编码
- **批处理线程**：必须继承 `BatchWorker(QThread)`，禁止用 `threading.Thread`
- **暂停/停止**：`self.ctrl.wait_if_paused()` 检查标志，循环中调用
- **FFmpeg 执行**：`self.run_cmd(cmd)` 统一入口（隐藏黑窗 + 详细日志 + 编码容错）
- **输出目录**：Worker 必须设置 `self.output_dir`，完成后 InfoBar 可打开文件夹
- **设置管理**：`AppSettings` dataclass，JSON 持久化，Worker 构造时拷贝快照
- **i18n**：所有用户可见文本（控件、提示、日志）必须 `tr("中文")`；带变量用 `tr("…{0}…").format(x)`，禁止 f-string；
  模块级/类级常量（TITLE、选项列表）保持中文、在使用处 `tr()`；按中文匹配数据的逻辑加 `# i18n: skip`；
  提交前 `uv run python tools/check_i18n.py` 必须通过；
  语言切换会重建主窗口，表单内容靠 `BaseTab.capture_state / restore_state` 按控件顺序还原——
  新 Tab 只要用常规 qfluentwidgets 输入控件即可自动生效，动态行需提供 `self.rows` 和 `_add_row()`
- **密钥/凭据**：任何 API key、服务地址、加密种子、密码都不得写进仓库文件；
  运行期配置走 `settings.json`（gitignore），编译期密钥走 `build_secrets.env` / 环境变量
- **构建**：先 `uv run python setup_cython.py build_ext --inplace`，再 `build_qt.cmd`
- **打包排除**：`kk_qt.spec` 已排除 tkinter / moviepy / matplotlib 等无关大模块
- **UPX 白名单**：Qt6*.dll 和 VC Runtime 禁止 UPX 压缩（会导致启动崩溃）
- **窗口最小高度**：`NavigationInterface` 每加一项就抬高自身 `minimumHeight`（18 项约 870px），
  会把主窗口顶到小屏幕装不下。主窗口把 nav 包进 `QScrollArea`（`_sync_nav_width` 同步宽度），
  `BaseTab` 表单也整体放在滚动区里——这两处都别回退成直接 addWidget
- **依赖**：新增第三方库前确认确有引用；`pyproject.toml` 改动后运行 `uv lock`

## 已知待办

- `AppSettings.thread_count` 在设置界面可改，但所有 Worker 目前均为串行，尚未使用该值
- 英文模式下字体下拉仍显示中文字体名（`fonts.py` 的映射，字体名属专有名词，有意不译）

## 现有功能 Tab（15 个）

merge / concat / subtitle_concat / split / pip / speed / rotate / watermark / volume / title / music / crop / compress / convert / extract
