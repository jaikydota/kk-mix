# 需求文档：视频配音翻译功能

## 一、背景与目标

在现有 `kk.py` 的多标签页批处理视频编辑工具中，新增**视频配音翻译** Tab。

功能目标：给定一批视频文件，自动完成语音转录、翻译、TTS 配音合成，输出带有译制配音和烧录字幕的视频。

技术依赖：
- 本地 ffmpeg（通过 `_find_ffmpeg()` 获取）
- Mix MCP 服务（通过 `settings.json` 中的 `mcp_url` 连接）
- OpenAI 兼容 LLM API（通过 `settings.json` 中的 `llm_*` 参数连接）

详细流程参见：`docs/guide/video_translation_flow.md`

---

## 二、新增 Tab：视频翻译

### 2.1 Tab 基本信息

| 属性 | 值 |
|---|---|
| Tab 标识键 | `translate` |
| Tab 显示名称 | 视频翻译 |
| UI 创建函数 | `create_translate_tab(self, parent)` |
| 批处理启动函数 | `start_translate(self)` |
| 批处理主函数 | `batch_translate_operation(self)` |

### 2.2 UI 变量（在 `__init__` 中新增）

```python
# 视频翻译
self.translate_folder = tk.StringVar()       # 原始视频文件夹
self.translate_output = tk.StringVar()       # 输出文件夹
self.translate_target_lang = tk.StringVar(value="zh")  # 目标语言：zh / en
```

### 2.3 UI 布局（`create_translate_tab`）

```
行 0：[Label: 视频文件夹:]  [Entry: translate_folder]  [Button: 浏览]
行 1：[Label: 输出文件夹:]  [Entry: translate_output]  [Button: 浏览]
行 2：LabelFrame "翻译设置"
        [Label: 目标语言:]  [Combobox: 中文(zh) / 英文(en)]
行 3：[Button: 开始批量翻译配音  (Accent.TButton)]
```

参照 `create_volume_tab` 的实现风格，`columnconfigure(1, weight=1)` 使输入框自适应宽度。

### 2.4 线程启动（`start_translate`）

```python
def start_translate(self):
    thread = threading.Thread(target=self.batch_translate_operation)
    thread.daemon = True
    thread.start()
```

### 2.5 批处理主函数（`batch_translate_operation`）

**职责**：收集 UI 参数、遍历视频文件、对每个文件依次执行 11 步翻译流程、更新进度和日志。

**执行流程**：

```
1. 读取 translate_folder、translate_output、translate_target_lang
2. 校验参数（文件夹不能为空，MCP URL 不能为空，LLM 参数不能为空）
3. 创建任务临时目录：{项目根目录}/temp/{YYYYMMDD_HHMMSS}/
4. os.makedirs(output_folder, exist_ok=True)
5. video_files = self.get_video_files(translate_folder)
6. 遍历 video_files：
   for idx, video_file in enumerate(video_files, 1):
       if self.check_pause_stop(): break
       video_temp_dir = os.path.join(task_temp_dir, Path(video_file).stem)
       os.makedirs(video_temp_dir, exist_ok=True)
       success = self._translate_video(video_path, output_folder, video_temp_dir, target_lang)
       self.progress_var.set((idx / len(video_files)) * 100)
7. 完成汇报
```

**校验逻辑**：
- `translate_folder` 为空 → `messagebox.showerror` 提示
- `translate_output` 为空 → `messagebox.showerror` 提示
- `self.mcp_url.get()` 为空 → 提示"请在设置中配置 MCP 地址"
- `self.llm_api_key.get()` 为空 → 提示"请在设置中配置 LLM API Key"

### 2.6 单视频翻译函数（`_translate_video`）

**签名**：
```python
def _translate_video(self, input_path, output_folder, temp_dir, target_lang) -> bool
```

在内部按顺序执行 11 个步骤，每步完成后调用 `self.log()`，任意步骤失败则返回 `False`：

| 步骤 | 日志前缀 | 调用 |
|---|---|---|
| Step 1 提取音频 | `[1/11] 提取音频...` | ffmpeg subprocess |
| Step 2 人声分离 | `[2/11] 人声分离（Demucs）...` | `asyncio.run(_mcp_separate())` |
| Step 3 截取参考音色 | `[3/11] 截取参考音色（8秒）...` | ffmpeg subprocess |
| Step 4 语音转录 | `[4/11] 语音转录（Whisper）...` | `asyncio.run(_mcp_transcribe())` |
| Step 5 LLM 翻译 | `[5/11] LLM 翻译 → {target_lang}...` | `_llm_translate()` |
| Step 6 生成 SRT | `[6/11] 生成 SRT 字幕...` | 纯 Python 文件写入 |
| Step 7 TTS 合成 | `[7/11] TTS 批量合成...` | `asyncio.run(_mcp_tts_batch())` |
| Step 8 时长对齐 | `[8/11] 时长对齐...` | ffmpeg subprocess（逐段） |
| Step 9 音轨拼接 | `[9/11] 音轨拼接...` | ffmpeg subprocess（concat） |
| Step 10 音频混合 | `[10/11] 混合背景音乐...` | ffmpeg subprocess（amix） |
| Step 11 合成输出 | `[11/11] 合成最终视频...` | ffmpeg subprocess |

**输出文件命名**：
- SRT：`{原文件名}_translated_{lang}.srt`（保存在 `output_folder`）
- MP4：`{原文件名}_translated_{lang}.mp4`（保存在 `output_folder`）

### 2.7 MCP 调用封装

所有 MCP 调用封装为独立 async 函数，通过 `asyncio.run()` 在 daemon thread 中同步调用：

```python
async def _mcp_separate(audio_path, mcp_url):
    """Demucs 人声分离，返回 (vocals_bytes, no_vocals_bytes)"""

async def _mcp_transcribe(audio_path, mcp_url):
    """Whisper 转录，返回 segments 列表"""

async def _mcp_tts_batch(texts, ref_voice_path, mcp_url):
    """TTS 批量合成，返回 wav_bytes 列表"""
```

轮询间隔：Demucs/TTS 使用 5 秒，Whisper 使用 3 秒。超时时间统一设为 600 秒。

### 2.8 LLM 翻译函数（`_llm_translate`）

使用 `openai` 库（OpenAI 兼容接口）：

```python
def _llm_translate(self, texts: list[str], target_lang: str) -> list[str]:
```

- 从 `self.llm_api_base`、`self.llm_api_key`、`self.llm_model` 读取配置
- 目标语言映射：`{"zh": "中文", "en": "英文"}`
- 逐句调用，Prompt 模板：
  ```
  将以下文本翻译为{目标语言}，保持原文含义，只输出译文，不要解释。
  {原文}
  ```
- 失败时重试 3 次，最终失败时返回原文（不中断流程）

---

## 三、设置窗口扩展

### 3.1 新增 LLM 配置区块（`settings_window.py`）

在现有 MCP 地址配置区块下方，新增 LLM 配置区块：

```
LabelFrame "LLM 翻译配置"
  行 0：[Label: API Base:]   [Entry: llm_api_base]
  行 1：[Label: API Key:]    [Entry: llm_api_key  (show='*')]
  行 2：[Label: 模型:]       [Entry: llm_model]
```

`llm_api_key` 输入框使用 `show='*'` 隐藏明文。

### 3.2 UI 变量（在 `kk.py` 的 `__init__` 中新增）

```python
self.llm_api_base = tk.StringVar(value="https://api.openai.com/v1")
self.llm_api_key = tk.StringVar()
self.llm_model = tk.StringVar(value="gpt-4o")
```

### 3.3 设置持久化（`settings.json`）

**位置**：与 `kk.py` / `kk.exe` 同级目录，文件名 `settings.json`。

**数据结构**：
```json
{
  "mcp_url": "http://localhost:8400/mcp",
  "llm_api_base": "https://api.openai.com/v1",
  "llm_api_key": "",
  "llm_model": "gpt-4o"
}
```

**读取（应用启动时，在 `__init__` 末尾调用）**：

```python
def _load_settings(self):
    settings_path = Path(sys.argv[0]).parent / "settings.json"
    if settings_path.exists():
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.mcp_url.set(data.get("mcp_url", "http://localhost:8400/mcp"))
        self.llm_api_base.set(data.get("llm_api_base", "https://api.openai.com/v1"))
        self.llm_api_key.set(data.get("llm_api_key", ""))
        self.llm_model.set(data.get("llm_model", "gpt-4o"))
```

**保存（点击"保存"按钮时触发，在 `settings_window.py` 的 `on_save` 中调用）**：

```python
def _save_settings(app):
    settings_path = Path(sys.argv[0]).parent / "settings.json"
    data = {
        "mcp_url": app.mcp_url.get(),
        "llm_api_base": app.llm_api_base.get(),
        "llm_api_key": app.llm_api_key.get(),
        "llm_model": app.llm_model.get(),
    }
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
```

---

## 四、中间文件管理

### 4.1 目录规范

```
{kk.py 所在目录}/
└── temp/
    └── {YYYYMMDD_HHMMSS}/           ← 任务目录，批处理开始时创建
        ├── {视频文件名_1}/
        │   ├── origin_audio.mp3     Step 1 输出
        │   ├── vocals.wav           Step 2 输出
        │   ├── no_vocals.wav        Step 2 输出
        │   ├── ref_voice.wav        Step 3 输出（8秒参考音色）
        │   ├── tts_seg_0.wav        Step 7 输出（各段 TTS 原始音频）
        │   ├── tts_seg_1.wav
        │   ├── ...
        │   ├── tts_aligned_0.wav    Step 8 输出（时长对齐后）
        │   ├── tts_aligned_1.wav
        │   ├── ...
        │   ├── tts_final.wav        Step 9 输出（拼接后完整音轨）
        │   ├── mixed_audio.wav      Step 10 输出（混合背景音乐后）
        │   └── subtitles.ass        Step 11 中间文件（ASS 字幕）
        └── {视频文件名_2}/
            └── ...
```

### 4.2 生命周期

- 中间文件**任务完成后保留**，不自动清理
- `temp/` 目录由用户手动清理
- 如需重新处理同一视频，再次运行会在新的时间戳目录下生成新的文件，不会覆盖历史记录

---

## 五、字幕样式规范

SRT → ASS 转换使用以下默认样式：

| 属性 | 值 |
|---|---|
| 字体 | Arial（或系统默认无衬线字体） |
| 字号 | 24 |
| 颜色 | 白色（&H00FFFFFF） |
| 描边颜色 | 黑色（&H00000000） |
| 描边宽度 | 2 |
| 位置 | 底部居中（Alignment=2） |
| 垂直边距 | 20px |

后续可根据需要在 `_srt_to_ass()` 函数中扩展样式参数。

---

## 六、错误处理策略

| 场景 | 处理方式 |
|---|---|
| 单个视频某步失败 | `self.log("✗ 失败: ...")` 记录错误，跳过该视频，继续处理下一个 |
| MCP 服务不可达 | 抛出异常，`self.log` 记录，当前视频标记失败 |
| LLM 翻译单句失败 | 重试 3 次，仍失败则保留原文，继续翻译下一句 |
| TTS 合成失败 | 记录错误，当前视频标记失败 |
| ffmpeg 命令失败 | 记录 stderr 后 500 字符，当前视频标记失败 |
| 输出目录无写权限 | 启动时校验，弹出错误对话框 |

---

## 七、依赖项

| 依赖 | 用途 | 安装 |
|---|---|---|
| `fastmcp` | MCP 客户端 | `pip install fastmcp` |
| `openai` | LLM 翻译调用 | `pip install openai` |

以上依赖需添加到项目的 `requirements.txt`（如有）。

---

## 八、开发顺序建议

1. `settings_window.py`：新增 LLM 配置区块 + `settings.json` 持久化读写
2. `kk.py` `__init__`：新增 3 个 LLM 变量 + 调用 `_load_settings()`
3. `kk.py`：实现 MCP 异步调用封装函数（`_mcp_separate`、`_mcp_transcribe`、`_mcp_tts_batch`）
4. `kk.py`：实现 `_llm_translate()`
5. `kk.py`：实现 `_translate_video()`（11 步核心逻辑）
6. `kk.py`：实现 `create_translate_tab()` + `start_translate()` + `batch_translate_operation()`
7. 在 `create_widgets()` 中注册新 Tab
