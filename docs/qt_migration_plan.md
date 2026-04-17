# kk-mix Qt 迁移方案

> 将 `kk.py`（Tkinter/ttk）迁移到 `kk_qt.py`（**PySide6 + PySide6-Fluent-Widgets**）的完整执行方案。
> 对应代码骨架：`kk_qt.py`（已完成主窗口 + VolumeTab PoC）。
> 适用版本：`v9.6.0-qt`，Windows 11，Python 3.14，FFmpeg 捆绑。

---

## 1. 迁移目标

| 维度 | 现状（Tkinter） | 目标（Qt + Fluent） |
|---|---|---|
| UI 风格 | ttk + `Accent.TButton`，默认扁平不统一 | Windows 11 Fluent Design（侧边导航 + 卡片 + InfoBar） |
| 线程模型 | `threading.Thread(daemon=True)` + `root.update()` | `QThread` 子类 + `Signal` |
| 状态变量 | `tk.StringVar` / `DoubleVar` / `BooleanVar` | `LineEdit.text()` / `DoubleSpinBox.value()` / `CheckBox.isChecked()`（直接读控件） |
| 跨线程日志 | `self.processing_lock` + `Text.insert` + `root.update()` | `log_signal.emit` → 主线程槽 `QPlainTextEdit.appendPlainText` |
| 对话框 | `messagebox.showinfo/error` | `InfoBar.success/error/warning`（非阻塞，顶部浮层） |
| 文件选择 | `filedialog.askdirectory / askopenfilename` | `QFileDialog.getExistingDirectory / getOpenFileName` |
| 模态弹窗 | `tk.Toplevel + grab_set` | `MessageBoxBase` 子类 |
| Tab 切换 | 手写 `tab_bar + content_area` 双排 | `NavigationInterface` 侧边栏（滚动，支持 60+ 项） |
| 打包 | Tkinter + PIL + ttk | 移除 Tkinter/PIL，改为 PySide6 + qfluentwidgets |

**不改动的部分**：
- `_license_core.pyx`（授权核心，沿用现有 Cython 编译产物）
- `ffmpeg.exe` / `ffprobe.exe` 的捆绑与调用方式（`subprocess.run`）
- `settings.json` 的字段与存储位置
- 所有 FFmpeg 命令行参数（只搬逻辑，不改 filter 语法）

---

## 2. 目标目录结构

```
kk-mix/
├── kk.py                     # 旧版（迁移期保留可并行运行）
├── kk_qt.py                  # 新版入口（主窗口 + 注册所有 Tab）
├── qt/                       # 新增：Qt 版本代码模块
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── ffmpeg_helper.py  # _find_ffmpeg / _make_startupinfo / 公用 ffmpeg 参数构造
│   │   ├── batch_worker.py   # BatchWorker 基类 + BatchControl
│   │   ├── paths.py          # _resource_path / _settings_path / VIDEO_EXTS
│   │   └── license.py        # LicenseDialog + check_license
│   ├── tabs/
│   │   ├── __init__.py
│   │   ├── base.py           # BaseTab 基类
│   │   ├── merge.py          # MergeTab + MergeWorker
│   │   ├── split.py
│   │   ├── concat.py
│   │   ├── pip.py
│   │   ├── speed.py
│   │   ├── rotate.py
│   │   ├── watermark.py
│   │   ├── volume.py
│   │   ├── convert.py
│   │   ├── extract.py
│   │   ├── music.py
│   │   ├── title.py
│   │   ├── crop.py
│   │   └── compress.py
│   └── settings_window_qt.py # 全局设置窗口（对应 settings_window.py）
├── _license_core.pyx         # 不变
├── _license_core.*.pyd       # 不变
├── ffmpeg.exe / ffprobe.exe  # 不变
├── assets/
├── docs/
│   └── qt_migration_plan.md  # 本文件
├── build_qt.cmd              # 新增：Qt 版打包脚本
└── kk_qt.spec                # 新增：Qt 版 PyInstaller spec
```

> PoC 阶段 `kk_qt.py` 把所有代码放一个文件；按本方案在迁移时拆分到 `qt/` 目录以降低单文件行数。

---

## 3. 架构映射（全局）

### 3.1 类与调用关系

```
kk.py (旧)                                    kk_qt.py (新)
────────────────────────────────────────────  ─────────────────────────────────────────
FFmpegVideoEditorApp                          MainWindow(QMainWindow)
  self.root (Tk)                              (self 自己)
  self.processing_lock (RLock)                不需要，Signal 已串行
  self.current_operation (str)                self.current_worker (BatchWorker | None)
  self.is_paused / is_stopped (bool)          self.ctrl: BatchControl
  self.progress_var (DoubleVar)               self.progress (ProgressBar)
  self.status_var (StringVar)                 self.status_label (BodyLabel)
  self.log_text (tk.Text)                     self.log_view (TextEdit)
  self.pause_btn / stop_btn                   self.pause_btn / stop_btn (PushButton)

  create_widgets()                            _build_ui() + _register_tabs()
  create_<name>_tab(parent)                   qt/tabs/<name>.py : <Name>Tab.build_form()
  start_<name>()                              <Name>Tab._on_start() (基类实现)
  batch_<name>_operation()                    <Name>Worker.run_batch()
  _<name>_ffmpeg(...)                         <Name>Worker._<name>_ffmpeg(...)

  self.log(msg) (加锁 + update())             self.log_signal.emit(msg) + 主线程槽
  self.update_status(msg)                     self.status_signal.emit(msg)
  self.progress_var.set(v)                    self.progress_signal.emit(v)
  self.check_pause_stop() (sleep 循环)        self.ctrl.wait_if_paused()
  self.set_controls_state(bool)               MainWindow.run_worker + _on_worker_finished
  self.browse_folder(var, is_output)          BaseTab._browse_folder(line_edit, is_output)
  self.get_video_files(folder)                基类方法 list_media(folder, VIDEO_EXTS)
  self._run_cmd(cmd, timeout)                 BatchWorker.run_ffmpeg(cmd, timeout)
  self._preset() / _quality_args()            BatchWorker.encode_args(app_settings)
```

### 3.2 共享状态（AppSettings）

旧代码在 `__init__` 里集中声明了所有 `tk.*Var` 变量，通过 `settings_window.load_settings(self)` 注入。

**新代码用 `dataclass` 集中管理全局设置**（迁移后通过 `MainWindow.settings` 访问）：

```python
# qt/core/app_settings.py
from dataclasses import dataclass, asdict, field
import json
from pathlib import Path

@dataclass
class AppSettings:
    mcp_url: str = "http://localhost:8400/mcp"
    llm_api_base: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o"
    verbose_log: bool = False
    thread_count: int = 1
    speed_priority: bool = True
    compress_video: bool = False
    bitrate: str = "2M"

    @classmethod
    def load(cls, path: Path) -> "AppSettings":
        if not path.exists():
            return cls()
        try:
            return cls(**json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return cls()

    def save(self, path: Path):
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2),
                        encoding="utf-8")
```

- 每个 `BatchWorker` 构造时从 `MainWindow.settings` 拷贝所需字段（避免跨线程读写）
- 设置窗口保存后调用 `MainWindow.on_settings_changed()` 刷新 UI 依赖项

---

## 4. Tkinter → Qt/Fluent 组件总映射表

这是迁移时的「查表依据」。所有 Tab 的组件都按此映射。

| Tkinter / ttk | PySide6 / qfluentwidgets | 关键 API 差异 |
|---|---|---|
| `tk.Tk` / `Toplevel` | `QMainWindow` / `QDialog` | `show()` / `exec()` 替代 `mainloop()` / `wait_window()` |
| `ttk.Notebook` | `NavigationInterface` + `QStackedWidget` | 用 `addItem(routeKey, icon, text, onClick)` 添加 |
| `ttk.Frame` | `QWidget` + 布局 | 需要显式 `QVBoxLayout` / `QHBoxLayout` |
| `ttk.LabelFrame(text=...)` | `CardWidget` + 顶部 `StrongBodyLabel` | Fluent 卡片，不直接有标题 |
| `ttk.Label(text=...)` | `BodyLabel(text)` / `StrongBodyLabel` / `SubtitleLabel` | |
| `ttk.Label(foreground='gray')` | `CaptionLabel` 或 `BodyLabel` + `setStyleSheet("color:#8a8a8a")` | |
| `ttk.Entry(textvariable=v)` | `LineEdit()` + `setText/text()` | 无 `textvariable` 双向绑定，直接 `text()` 读 |
| `ttk.Entry(..., show='*')` | `LineEdit().setEchoMode(QLineEdit.Password)` | |
| `ttk.Combobox(values=..., state='readonly')` | `ComboBox()` + `addItems()` + `setCurrentText()` | |
| `ttk.Combobox(state='normal')` | `EditableComboBox()` | |
| `ttk.Checkbutton(variable=v)` | `CheckBox()` + `isChecked()` | |
| `ttk.Radiobutton(variable=v, value=...)` | `RadioButton()` + `QButtonGroup` | Qt 需手动分组 |
| `ttk.Spinbox(from_=, to=)` | `SpinBox()` / `DoubleSpinBox()` | `setRange(min, max)` |
| `ttk.Button(text, command)` | `PushButton(text, parent, icon)` + `clicked.connect()` | |
| `ttk.Button(style='Accent.TButton')` | `PrimaryPushButton(text, parent, icon)` | |
| `tk.Button(bg=..., command=_pick_color)` | `PushButton` + `QColorDialog.getColor()` | |
| `tk.Canvas` + `Scrollbar` | `ScrollArea` + 内嵌 `QWidget` | Fluent 有 `SmoothScrollArea` |
| `tk.Text` | `PlainTextEdit` / `TextEdit` | `.append()` / `.toPlainText()` |
| `ttk.Progressbar(variable=v)` | `ProgressBar` | `setRange(0,100) + setValue()` |
| `messagebox.showinfo/error/warning` | `InfoBar.success/error/warning` | 非阻塞，顶部浮层 |
| `messagebox.askyesno` | `MessageBox("title", "msg", parent).exec()` | 返回 True/False |
| `tk.StringVar` 等 | 直接 `QWidget.text()` / `.value()` / `.isChecked()` | 无变量代理概念 |
| `.grid(row=, column=)` | `QGridLayout.addWidget(w, row, col)` | |
| `.pack(side='left')` | `QHBoxLayout.addWidget()` | |
| `filedialog.askdirectory()` | `QFileDialog.getExistingDirectory(parent, title, start)` | |
| `filedialog.askopenfilename(filetypes=)` | `QFileDialog.getOpenFileName(parent, title, start, filter)` | 过滤语法：`"图片 (*.png *.jpg)"` |
| `tkinter.colorchooser.askcolor()` | `QColorDialog.getColor(initial, parent)` | 返回 `QColor`，用 `.name()` 拿 `#rrggbb` |
| `ttk.Style().configure('Accent.TButton', ...)` | `setTheme(Theme.AUTO/LIGHT/DARK)` | qfluentwidgets 全局主题 |
| `root.iconbitmap(path)` | `window.setWindowIcon(QIcon(path))` | |
| `root.update()` / `update_idletasks()` | 不需要 | Qt 事件循环自动刷新 |
| `widget.after(ms, fn)` | `QTimer.singleShot(ms, fn)` | |

### 4.1 常用惯用写法片段

**文件夹选择行**（所有 Tab 都用到）——BaseTab 已封装 `_add_folder_row`：
```python
self.video_folder = LineEdit(self)
self._add_folder_row(row=0, label="视频文件夹", line_edit=self.video_folder, is_output=False)
```

**单选组**（ttk.Radiobutton 替代）：
```python
from PySide6.QtWidgets import QButtonGroup
from qfluentwidgets import RadioButton

self.mode_group = QButtonGroup(self)
rb1 = RadioButton("视频", self); rb1.setChecked(True)
rb2 = RadioButton("图片", self)
self.mode_group.addButton(rb1, id=0)
self.mode_group.addButton(rb2, id=1)
# 取值：("video", "image")[self.mode_group.checkedId()]
```

**下拉框**：
```python
from qfluentwidgets import ComboBox
cb = ComboBox(self)
cb.addItems(["9:16", "16:9", "1:1"])
cb.setCurrentText("9:16")
# 取值：cb.currentText()
```

**颜色选择**：
```python
from PySide6.QtWidgets import QColorDialog
from PySide6.QtGui import QColor

def _pick_color(self):
    color = QColorDialog.getColor(QColor(self.color_hex), self, "选择字体颜色")
    if color.isValid():
        self.color_hex = color.name()
        self.color_btn.setStyleSheet(f"background:{self.color_hex}")
```

**带浮动提示的 InfoBar**：
```python
InfoBar.success("完成", f"成功 {n}/{total}", parent=self.main,
                position=InfoBarPosition.TOP_RIGHT, duration=3000)
```

---

## 5. 每个 Tab 的迁移方案

> 每小节给出三张表：**控件映射**、**Worker 参数**、**对应 kk.py 源码定位**。Worker 参数即构造函数签名，填完表就能一比一搬 ffmpeg 逻辑。

### 5.1 merge — 左右分屏合并

- `kk.py` 对应：`create_merge_tab` L1232，`batch_merge_operation` L3229，`_merge_with_ffmpeg` L3497

| 旧变量/控件 | 新控件 | 类型 | 默认值 |
|---|---|---|---|
| `folder1_path` | `LineEdit folder1` | str 路径 | "" |
| `folder2_path` | `LineEdit folder2` | str 路径 | "" |
| `output_path` | `LineEdit output` | str 路径 | `~/Desktop/视频输出` |
| `audio_source` (Radiobutton) | `QButtonGroup` + 3×RadioButton | `"folder1"/"folder2"/"none"` | `"folder1"` |
| `image_duration` | `SpinBox` (1-60) | int 秒 | 5 |
| 开始按钮 | `PrimaryPushButton` |

**Worker**：`MergeWorker(ffmpeg_path, ctrl, folder1, folder2, output, audio_source, image_duration, encode_args)`

### 5.2 split — 批量分割视频

- 对应：`create_split_tab` L1258，`batch_split_operation` L3293

| 旧变量 | 新控件 | 默认值 |
|---|---|---|
| `split_folder` | `LineEdit` | "" |
| `split_duration` | `SpinBox` (1-3600) 秒 | 30 |
| `split_output` | `LineEdit` | "" |
| `audio_output_path` | `LineEdit`（可选） | "" |
| `keep_remainder` | `CheckBox` | True |
| `extract_audio` | `CheckBox` | False |

**Worker**：`SplitWorker(ffmpeg_path, ctrl, folder, duration, video_out, audio_out, keep_remainder, extract_audio, encode_args)`

### 5.3 concat — 视频转场拼接

- 对应：`create_concat_tab` L1283，`batch_concat_operation` L3649
- **动态增删文件夹行**是这个 Tab 的难点，Qt 有更优雅的实现

| 旧控件 | 新控件 |
|---|---|
| `tk.Canvas + Scrollbar + 动态 Frame 列表` | `SmoothScrollArea` + `QVBoxLayout`（容器） |
| 5 个固定 + 动态添加行 | 用列表 `self.folder_rows: list[LineEdit]`，每行一个小 `QWidget` |
| `添加文件夹` 按钮 | `PushButton("＋ 添加文件夹", FluentIcon.ADD)` |
| 删除按钮（仅动态行） | `TransparentToolButton(FluentIcon.CLOSE)` |
| `concat_transition` (DoubleVar) | `DoubleSpinBox` (0-5, step 0.1) |
| `concat_transition_type` (Combobox) | `ComboBox` + `addItems([...])` |

**Worker**：`ConcatWorker(ffmpeg_path, ctrl, folders: list[str], output, transition_sec, transition_type, encode_args)`

> 转场类型的中英混合值（`"淡入淡出-fade"`）沿用，内部用 `split("-")[-1]` 取 ffmpeg 关键字。

### 5.4 pip — 画中画合成

- 对应：`create_pip_tab` L1390，`batch_pip_operation` L3915，`_pip_ffmpeg` L3984

| 旧变量 | 新控件 | 备注 |
|---|---|---|
| `pip_bg_folder` / `pip_fg_folder` / `pip_output` | 3×`LineEdit` | |
| `pip_position` | `ComboBox` | `["top_left","top_right","bottom_left","bottom_right"]` |
| `pip_scale` (0.1-1.0) | `DoubleSpinBox` (0.1-1.0, step 0.05) | |

**Worker**：`PipWorker(ffmpeg_path, ctrl, bg_folder, fg_folder, output, position, scale, encode_args)`

### 5.5 speed — 批量变速/倒放

- 对应：`create_speed_tab` L1417，`batch_speed_operation` L4045，`_speed_change_ffmpeg` L4110

| 旧变量 | 新控件 |
|---|---|
| `speed_folder` / `speed_output` | 2×`LineEdit` |
| `speed_factor` (0.1-5.0) | `DoubleSpinBox` step=0.1 默认 1.5 |
| `speed_reverse` | `CheckBox("倒放视频")` |

**Worker**：`SpeedWorker(ffmpeg_path, ctrl, folder, output, factor, reverse, encode_args)`

### 5.6 rotate — 批量旋转/翻转

- 对应：`create_rotate_tab` L1441，`batch_rotate_operation` L1914，`_rotate_video_ffmpeg` L1977

| 旧变量 | 新控件 |
|---|---|
| `rotate_folder` / `rotate_output` | 2×`LineEdit` |
| `rotate_angle` | `ComboBox` `["90","180","270","hflip","vflip"]` |

**Worker**：`RotateWorker(ffmpeg_path, ctrl, folder, output, angle, encode_args)`

### 5.7 watermark — 批量添加水印

- 对应：`create_watermark_tab` L1464，`batch_watermark_operation` L2021，`_watermark_video_ffmpeg` L2091

| 旧变量 | 新控件 |
|---|---|
| `watermark_video_folder` | `LineEdit` + `PushButton("浏览文件夹")` |
| `watermark_image_path` | `LineEdit` + `PushButton("浏览图片")` — 用 `QFileDialog.getOpenFileName` 过滤 `"图片 (*.png *.jpg *.jpeg)"` |
| `watermark_output` | `LineEdit` |
| `watermark_position` | `ComboBox` 5 项（含 `center`） |
| `watermark_opacity` (0.1-1.0) | `DoubleSpinBox` step=0.05 默认 0.8 |
| `watermark_scale` (0.05-0.5) | `DoubleSpinBox` step=0.01 默认 0.2 |

**Worker**：`WatermarkWorker(ffmpeg_path, ctrl, video_folder, image_path, output, position, opacity, scale, encode_args)`

### 5.8 volume — 批量调整音量 ✅ 已完成

PoC 样例，`kk_qt.py.VolumeTab / VolumeWorker` 即可作为迁移模板。

### 5.9 convert — 批量格式转换

- 对应：`create_convert_tab` L1517，`batch_convert_operation` L2251

| 旧变量 | 新控件 |
|---|---|
| `convert_folder` / `convert_output` | 2×`LineEdit` |
| `convert_format` | `ComboBox` `["mp4","avi","mov","mkv"]` |

**Worker**：`ConvertWorker(ffmpeg_path, ctrl, folder, output, target_format, encode_args)`

### 5.10 extract — 批量提取帧

- 对应：`create_extract_tab` L1539，`batch_extract_operation` L2360

| 旧变量 | 新控件 |
|---|---|
| `extract_folder` / `extract_output` | 2×`LineEdit` |
| `extract_interval`（秒） | `SpinBox` (1-600) 默认 5 |

**Worker**：`ExtractFramesWorker(ffmpeg_path, ctrl, folder, output, interval_sec)`

### 5.11 music — 填充音乐

- 对应：`create_music_tab` L1559，`batch_music_operation` L2460

| 旧变量 | 新控件 |
|---|---|
| `music_video_folder` | `LineEdit` |
| `music_audio_folder` | `LineEdit`（含视频/音乐） |
| `music_output_folder` | `LineEdit` |
| `music_keep_original_audio` | `CheckBox` |

**Worker**：`MusicFillWorker(ffmpeg_path, ctrl, video_folder, audio_folder, output, keep_original_audio, encode_args)`

### 5.12 title — 视频添加标题

**最复杂**的 Tab，包含字体选择、字号单位切换、颜色选择、文字来源切换。

- 对应：`create_title_tab` L1580，`batch_title_operation` L2639，`_title_ffmpeg` L3132

| 旧控件 | 新控件 | 备注 |
|---|---|---|
| `title_video_folder` / `title_output_folder` | 2×`LineEdit` | |
| 字体下拉 + 刷新按钮 | `ComboBox` + `TransparentToolButton(FluentIcon.SYNC)` | `_get_system_fonts` 从 L1803 整体搬到 `qt/core/fonts.py` |
| 字号单位切换 (`%` / `px`) | `SegmentedWidget` 或 `QButtonGroup` + 2×RadioButton | qfluentwidgets 有 `SegmentedWidget` 更美观 |
| `title_fontsize` | `DoubleSpinBox`（根据单位切换范围和默认值） | `%`: 1-50 默认 5；`px`: 8-500 默认 30 |
| `title_y_percent` | `DoubleSpinBox` (0-100) 默认 8 | |
| 颜色预览按钮 + 4 预设 | `PushButton` 带 `setStyleSheet("background:...")` + `QColorDialog` | |
| `title_text_mode` (Radio) | `SegmentedWidget`（"固定文字" / "从TXT读取"） | |
| 固定文字输入框 | `LineEdit`，按 mode 显示/隐藏 | |
| TXT 文件选择 | `LineEdit` + `PushButton("浏览")` 过滤 `"文本 (*.txt)"` | |

**模式切换**：用 `QStackedWidget` 装「固定文字 Panel」和「TXT 文件 Panel」，比 `grid_remove/grid` 更干净。

**Worker**：`TitleWorker(ffmpeg_path, ctrl, video_folder, output_folder, font_path, text_mode, title_text, txt_file, fontsize, fontsize_unit, y_percent, font_color, encode_args)`

### 5.13 crop — 批量裁剪比例

- 对应：`create_crop_tab` L1699，`batch_crop_operation` L2795，`_crop_ffmpeg` L2911

| 旧变量 | 新控件 |
|---|---|
| `crop_mode` (视频/图片) | `SegmentedWidget` 或 2×RadioButton |
| `crop_video_folder` / `crop_output_folder` | 2×`LineEdit` |
| `crop_ratio`（7 个 Radio） | `SegmentedWidget`（`["9:16","16:9","18:9","1:1","4:3","3:4","21:9"]`）或 `ComboBox` |

**Worker**：`CropWorker(ffmpeg_path, ctrl, folder, output, ratio, mode, encode_args)` — mode 决定是 ffmpeg 视频裁剪还是 PIL 图片裁剪。

### 5.14 compress — 批量压缩视频

- 对应：`create_compress_tab` L1727，`batch_compress_operation` L2979，`_compress_ffmpeg` L3076

| 旧变量 | 新控件 |
|---|---|
| `compress_folder` / `compress_output` | 2×`LineEdit` |
| `compress_br` | `EditableComboBox`（支持自定义输入），`addItems(["1M","2M（推荐）","3M","5M","8M","10M"])` |
| `compress_h265` | `CheckBox("使用 H.265 编码（体积更小，不勾选则使用 H.264）")` 默认勾选 |

**码率校验**：沿用旧的 `_validate_bitrate` 逻辑，放到 `on_editingFinished` 槽里。

**Worker**：`CompressWorker(ffmpeg_path, ctrl, folder, output, bitrate, use_h265, encode_args)`

---

## 6. settings 模块迁移

`settings_window.py` → `qt/settings_window_qt.py`。

| 旧区域 | 新实现 |
|---|---|
| `tk.Toplevel` 模态窗 | 继承 `MessageBoxBase`（自带遮罩、居中）或用 `QDialog` + `setWindowModality(Qt.ApplicationModal)` |
| `ttk.LabelFrame("MCP 服务配置")` | `CardWidget` + `StrongBodyLabel` 标题 |
| `ttk.LabelFrame("LLM 翻译配置")` | 同上，API Key 用 `PasswordLineEdit` |
| `ttk.LabelFrame("调试选项")` | `SwitchButton`（Fluent 风格开关，比 CheckBox 好看） |
| `ttk.LabelFrame("性能与稳定性")` | 线程数用 `SpinBox`，极速/压缩用 `SwitchButton`，码率 `ComboBox` |
| `ttk.LabelFrame("授权信息")` | 机器码只读 `LineEdit` + 复制按钮；剩余天数用 `BodyLabel` 设颜色 |
| 保存/取消按钮 | `MessageBoxBase` 的 `yesButton/cancelButton` |

**推荐**：用 qfluentwidgets 的 **SettingCard** 家族组件（`OptionsSettingCard`, `SwitchSettingCard`, `PushSettingCard`）更符合 Fluent 设计，不过需要做一层适配。初期先用通用控件即可。

**数据流**：
```
SettingsDialog 打开 → 从 MainWindow.settings (AppSettings) 读初值
用户修改 → 点保存 → 写回 AppSettings + AppSettings.save(_settings_path())
关闭 → MainWindow.on_settings_changed() 通知在运行的 Worker（不生效，下次任务才读）
```

---

## 7. license 模块迁移

`show_license_dialog` (kk.py L62) → `qt/core/license.py`。

PoC 版 `kk_qt.py` 已给出 `LicenseDialog(MessageBoxBase)` 和 `check_license(parent)`，实际迁移时把它移到 `qt/core/license.py` 即可，无需改造。

设置窗口里的「授权信息」板块也复用同一套 API：`_license_core.get_machine_id/load_license/verify_auth_code/get_license_info`。

---

## 8. 打包配置调整

### 8.1 `kk_qt.spec`（新增）

```python
# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for kk_qt.py (Qt 版本)

a = Analysis(
    ['kk_qt.py'],
    pathex=[],
    binaries=[
        ('ffmpeg.exe', '.'),
        ('ffprobe.exe', '.'),
        ('_license_core.cp314-win_amd64.pyd', '.'),
    ],
    datas=[
        ('assets\\logo.ico', 'assets'),
        ('assets\\logo.png', 'assets'),
        ('docs\\使用前必看.txt', 'docs'),
    ],
    hiddenimports=[
        '_license_core',
        # cryptography（sidbekey / 授权核心依赖）
        'cryptography',
        'cryptography.hazmat.primitives.ciphers',
        'cryptography.hazmat.primitives.ciphers.algorithms',
        'cryptography.hazmat.primitives.ciphers.modes',
        'cryptography.hazmat.primitives.padding',
        'cryptography.hazmat.backends',
        'cryptography.hazmat.backends.openssl',
        # PySide6 / qfluentwidgets 不需要手加 hidden-import（PyInstaller 5.6+ 已有 hook）
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 显式排除旧版依赖，减小体积
        'tkinter',
        'PIL',            # 若新版代码不再用 Pillow，排除它；若裁剪图片仍用则保留
        'PIL.ImageTk',
        'PyQt5',
        'PyQt6',
        'PySide2',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='kk',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # 无黑窗
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\logo.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[
        # PySide6 的部分 Qt DLL 不能 upx，否则启动崩溃
        'Qt6Core.dll',
        'Qt6Gui.dll',
        'Qt6Widgets.dll',
        'Qt6Svg.dll',
        'Qt6Network.dll',
        'Qt6DBus.dll',
        # qfluentwidgets 的资源文件
        'shiboken6.abi3.pyd',
    ],
    name='kk',
)
```

### 8.2 `build_qt.cmd`（新增，基于现有 `build.cmd` 改造）

```cmd
@echo off
chcp 65001 >nul

echo ============================================
echo  [0/3] 编译 _license_core.pyd (Cython) ...
echo ============================================
uv run python setup_cython.py build_ext --inplace
if %ERRORLEVEL% NEQ 0 (
    echo Cython 编译失败
    pause & exit /b 1
)

for %%f in (_license_core*.pyd) do set PYD_FILE=%%f
if not defined PYD_FILE (
    echo 找不到 .pyd 文件 & pause & exit /b 1
)
echo Cython 编译成功: %PYD_FILE%

echo.
echo ============================================
echo  [1/3] 打包 kk_qt.py (Qt 版主程序) ...
echo ============================================
uv run pyinstaller ^
    --onedir ^
    --windowed ^
    --add-binary "ffmpeg.exe;." ^
    --add-binary "ffprobe.exe;." ^
    --add-binary "%PYD_FILE%;." ^
    --add-data "assets\logo.ico;assets" ^
    --add-data "assets\logo.png;assets" ^
    --add-data "docs\使用前必看.txt;docs" ^
    --hidden-import "_license_core" ^
    --hidden-import "cryptography" ^
    --hidden-import "cryptography.hazmat.primitives.ciphers" ^
    --hidden-import "cryptography.hazmat.primitives.ciphers.algorithms" ^
    --hidden-import "cryptography.hazmat.primitives.ciphers.modes" ^
    --hidden-import "cryptography.hazmat.primitives.padding" ^
    --hidden-import "cryptography.hazmat.backends" ^
    --hidden-import "cryptography.hazmat.backends.openssl" ^
    --exclude-module tkinter ^
    --exclude-module PIL.ImageTk ^
    --exclude-module PyQt5 ^
    --exclude-module PyQt6 ^
    --exclude-module PySide2 ^
    --icon "assets\logo.ico" ^
    --name kk ^
    --clean ^
    kk_qt.py

if %ERRORLEVEL% NEQ 0 ( echo 打包失败 & pause & exit /b 1 )
echo 主程序打包成功: dist\kk\

echo.
echo ============================================
echo  [2/3] 打包 keygen.py (不变) ...
echo ============================================
:: keygen 保持原 build.cmd 中的打包命令不动
:: ...（同旧 build.cmd 第 64-80 行）...

echo.
echo ============================================
echo  [3/3] 压缩 dist\kk\ ...
echo ============================================
timeout /t 5 /nobreak >nul
powershell -Command "$dt=Get-Date -Format 'yyyyMMdd-HHmmss'; $zip=\"dist\kk_qt_$dt.zip\"; Compress-Archive -Path 'dist\kk\*' -DestinationPath $zip -Force"

echo 完成。
pause
```

### 8.3 `pyproject.toml` 依赖调整

**新增运行依赖**：
```toml
dependencies = [
    "cryptography>=44.0.0",
    "fastmcp>=3.1.0",
    "moviepy==1.0.3",
    "numpy==2.0.2",
    "openai>=2.24.0",
    "pillow==11.3.0",

    # ↓ Qt 迁移新增
    "PySide6>=6.6",
    "PySide6-Fluent-Widgets>=1.5",
]
```

**可选**（如果后续确认旧版完全废弃）：移除 `pillow` 对 `ImageTk` 的依赖。目前 `crop_image` 模式可能还用 PIL 做图片裁剪，保留 `pillow` 即可。

### 8.4 体积预估

| 项 | 体积 |
|---|---|
| `dist/kk/` 旧版 (Tkinter) | ~120 MB（含 ffmpeg 84MB） |
| `dist/kk/` 新版 (PySide6) | ~200-230 MB（PySide6 本体约 80MB，qfluentwidgets 约 5MB） |

如果需要压缩体积：
- 启用 UPX（已开启）
- 删除不用的 Qt 模块：在 `excludes` 加 `PySide6.Qt3DCore`, `PySide6.QtCharts`, `PySide6.QtWebEngineCore`, `PySide6.QtMultimedia` 等
- 考虑用 Nuitka 代替 PyInstaller（后续优化，不在此次方案中）

---

## 9. 分阶段执行计划

建议按 **"一次一 Tab，每 Tab 立即可运行测试"** 节奏推进。每个 Tab 的工作量约 30-60 行 Python。

| 阶段 | 任务 | 预计工作量 | 可交付 |
|---|---|---|---|
| **P0** | 骨架就绪 | ✅ 已完成 | `kk_qt.py` 可启动，volume Tab 可跑 |
| **P1** | 拆分 `kk_qt.py` → `qt/` 模块化 | 0.5 天 | 目录结构成型，volume 正常 |
| **P2** | 迁移**简单 Tab**: volume/convert/extract/rotate/speed/watermark/pip | 1-1.5 天 | 7 个 Tab 可用 |
| **P3** | 迁移**中等 Tab**: merge/split/crop/compress/music | 1.5 天 | 12 个 Tab 可用 |
| **P4** | 迁移**复杂 Tab**: concat（动态行）/title（字体 + 颜色 + 文件模式） | 1 天 | 全部 Tab 可用 |
| **P5** | 迁移 `settings_window.py` → `settings_window_qt.py` | 0.5 天 | 设置窗口 Fluent 化 |
| **P6** | 打包调试：`kk_qt.spec` / `build_qt.cmd` 调通 | 0.5 天 | `dist/kk/` 可分发 |
| **P7** | 回归测试 + 性能验证 | 0.5 天 | 发布候选版本 |

> P1 之前的并行开发策略：`kk.py` 保持原封不动，用户双击运行选择哪个版本；待 P7 验收通过再下线 `kk.py`。

---

## 10. 测试 Checklist

**每迁移一个 Tab，都要过一遍下面的清单**。

### 功能回归（对比 kk.py 输出一致）
- [ ] 准备 3-5 个测试素材（同时含 mp4/mov/异常文件名/中文名）
- [ ] 同样参数在旧版和新版各跑一次
- [ ] 输出文件大小、时长、画面对比（用 ffprobe `-show_streams`）

### 交互
- [ ] 「开始」按钮在处理中 disable，结束 enable
- [ ] 「暂停」→ 工作线程停在下一个文件前
- [ ] 「继续」→ 从暂停处继续
- [ ] 「停止」→ 3 秒内终止
- [ ] 进度条 0 → 100 平滑
- [ ] 日志按时间戳 `[HH:MM:SS]` 显示，自动滚到末尾
- [ ] 参数不全时弹 `InfoBar.warning` 而不是崩溃
- [ ] 路径含空格/中文字符正常工作

### 稳定性
- [ ] 批量 50+ 文件不卡 UI
- [ ] 关闭窗口时若有任务在跑，3 秒内优雅退出
- [ ] 连续触发「开始」10 次，只应有一个任务运行

### 打包
- [ ] `dist/kk/kk.exe` 双击启动 < 3 秒
- [ ] 无 `ModuleNotFoundError`
- [ ] 授权对话框能正常显示（`_license_core.pyd` 正确加载）
- [ ] `settings.json` 写在 exe 同目录
- [ ] 移到另一台**没装 Python** 的 Win10/11 上能直接跑
- [ ] zip 解压后目录里文件完整

---

## 11. 常见坑与避坑指南

### 11.1 线程相关
- **不能**在 Worker 里直接操作 QWidget（会崩溃）。只能 `emit Signal`。
- `QThread.msleep(ms)` 不会让 UI 卡顿，`time.sleep` 也可（反正在子线程）。
- `subprocess.run(..., capture_output=True)` 在子线程里完全安全。
- Worker 结束必须 `emit finished_signal`，否则主窗口以为还在跑，按钮不解锁。

### 11.2 qfluentwidgets 坑点
- `NavigationInterface.addItem` 要求每个子界面 `QWidget.setObjectName(唯一值)`，否则点击不切换。
- `FluentWindow` 内部直接嵌入自定义底部面板比较麻烦（`stackedWidget` 被其布局管控），本方案用 **自定义 QMainWindow + NavigationInterface** 规避。
- `InfoBar.success/error(...)` 的 `parent` 必须是顶层窗口（传 `self.main`），否则位置错乱。
- `setTheme(Theme.AUTO)` 需要 Windows 10 以上，否则回退到 LIGHT。

### 11.3 PyInstaller 坑点
- **不要** UPX PySide6 的 `Qt6*.dll` 和 `shiboken6.abi3.pyd`（见 8.1 的 `upx_exclude`）。
- `--exclude-module tkinter` 能减 ~8MB，迁移完成后务必加上。
- 中文路径问题：`subprocess` 需要 `encoding="utf-8", errors="ignore"`，Windows 默认 GBK 会解码失败。
- 启动时 `sys._MEIPASS` 路径的处理沿用 `_resource_path()`，不要改。

### 11.4 UI/UX 坑点
- **不要**把 `log()` 从 Worker 里直接调用（跨线程写 QWidget）——必须走 Signal。
- `QPlainTextEdit` 比 `TextEdit` 快得多，日志量大时优先用前者（PoC 用的 `TextEdit` 足够，后期可替换）。
- `DoubleSpinBox` 的 `step` 不要太小（0.001 这类），用户键盘调起来很慢。
- 超长标题（比如"批量添加水印并调整透明度"）在 NavigationInterface 会被省略，控制在 6-8 字以内。

### 11.5 编码相关
- `f"title={title_text}"` 这种构造 ffmpeg filter 字符串时，注意转义冒号 `\:`、逗号 `\,`、单引号 `\\'`（旧代码的 `_title_ffmpeg` 有处理，沿用即可）。
- `QFileDialog` 返回的路径在 Windows 是反斜杠，要统一用 `os.path.normpath` 或 `pathlib.Path` 处理。

---

## 12. 收尾

完整迁移完成后：
1. 把 `kk.py`、`settings_window.py`、`speech_tab.py` 移到 `legacy/` 目录（保留一个版本方便回溯）
2. `kk_qt.py` 改名 `kk.py`（对外可见的入口统一）
3. `build_qt.cmd` 改名 `build.cmd`
4. 更新 `feature.md` / README，标注 "v10.0 — Qt + Fluent UI"

---

**附：PoC 代码位置**
- 主窗口 & PoC Tab：`kk_qt.py`
- 本文件：`docs/qt_migration_plan.md`
- PoC 启动命令：`uv run python kk_qt.py`
