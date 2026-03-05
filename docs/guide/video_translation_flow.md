# 视频配音翻译流程分析

## 一、参考项目分析：KrillinAI

参考项目位于 `examples/KrillinAI`，为 Go 语言实现的视频字幕翻译 Web 服务。核心翻译流程由 `internal/service/subtitle_service.go` 中的 `StartSubtitleTask` 函数统一调度，运行在独立 goroutine 中。

### 1.1 KrillinAI 整体流程

```
输入（本地文件路径 / YouTube / Bilibili URL）
        │
        ▼  Step 1  linkToFile（link2file.go）
   origin_audio.mp3  +  origin_video.mp4
        │
        ▼  Step 2  audioToSubtitle（audio2subtitle.go）
   ┌──────────────────────────────────────────────────────────┐
   │  2a. GetSplitPoints()     寻找音频静音分割点              │
   │  2b. ClipAudio()          按分割点切分为小段音频（并行）   │
   │  2c. Transcription()      Whisper 转录，获取词级时间戳    │
   │  2d. splitTextAndTranslateV2()  LLM 翻译（上下文感知）   │
   │  2e. generateSrtWithTimestamps()  时间戳对齐              │
   │  2f. splitSrt()           生成 origin / target / bilingual SRT │
   └──────────────────────────────────────────────────────────┘
        │
        ▼  Step 3  srtFileToSpeech（srt2speech.go）[可选，启用 TTS 时执行]
   逐段 TTS 合成 → 时长调整（atempo/anullsrc）→ concat → tts_final_audio.wav
   → ReplaceAudioInVideo → video_with_tts.mp4
        │
        ▼  Step 4  embedSubtitles（srt_embed.go）[可选，启用字幕烧录时执行]
   SRT → ASS（srtToAss）→ ffmpeg -vf "ass=..." → horizontal/vertical_embed.mp4
        │
        ▼  Step 5  uploadSubtitles（upload_subtitle.go）
   词语替换、注册下载 URL、任务状态置为 Success
```

### 1.2 各步骤详解

#### Step 1 — 输入处理（linkToFile）

- 本地文件：`ffmpeg -i video -vn -ar 44100 -ac 2 -ab 192k -f mp3 audio.mp3` 提取音频
- YouTube/Bilibili：`yt-dlp` 下载音频和视频
- 输出：`origin_audio.mp3`（必须）、`origin_video.mp4`（字幕烧录时需要）

#### Step 2 — 音频转字幕（audioToSubtitle）

KrillinAI 使用 Go channel + errgroup 构建并发流水线：

**2a. 智能分割点（split_audio.go）**

`GetSplitPoints` 在每个名义切割点（每 N 秒）的 ±8 秒范围内，通过滑动窗口分析音频能量，找到最安静的时刻作为实际切割点，避免在单词中间截断。

**2b. 音频切分**

`ClipAudio()` 使用 ffmpeg 将 `origin_audio.mp3` 切分为 `split_audio_NNN.mp3` 系列文件，CPU 核数个并发 worker。

**2c. 语音转录**

`Transcription()` 调用 `Transcriber` 接口，支持以下后端：

| 后端 | 配置值 | 实现 |
|---|---|---|
| OpenAI Whisper API | `openai` | `pkg/whisper/whisper.go` |
| faster-whisper（本地） | `fasterwhisper` | `pkg/fasterwhisper/transcription.go` |
| whisper.cpp（本地） | `whispercpp` | `pkg/whispercpp/transcription.go` |
| WhisperKit（macOS） | `whisperkit` | `pkg/whisperkit/transcription.go` |
| 阿里云 ASR | `aliyun` | `pkg/aliyun/asr.go` |

所有后端返回统一结构：
```json
{
  "language": "zh",
  "text": "完整转录文本",
  "words": [{"num": 1, "text": "希望", "start": 0.0, "end": 0.42}]
}
```
**词级时间戳**是后续字幕时间对齐的关键数据。

**2d. LLM 翻译（splitTextAndTranslateV2）**

1. 用标点符号将转录文本切分为句子
2. 超长句子通过 LLM 递归分割（`splitOriginLongSentence`）
3. 对每句翻译时提供 ±3 句上下文，提升连贯性和指代准确性
4. 调用 `ChatCompleter.ChatCompletion(prompt)` 执行翻译

**2e. 时间戳对齐（timestamps.go）**

`BaseLanguageMatcher.matchSentenceByStringAlignment` 方法：
1. 将所有词级 token 拼接为完整文本
2. 去除标点和空格后做字符级匹配
3. 将字符位置映射回词级时间戳，得到每句的起止时间
4. 精确匹配失败时使用模糊字符匹配兜底

**2f. SRT 生成**

拆分为三份文件：
- `origin_language_srt.srt`：源语言
- `target_language_srt.srt`：目标语言
- `bilingual_srt.srt`：双语（顺序可配置）

#### Step 3 — SRT 转语音（srtFileToSpeech）

1. 解析 SRT 文件，获取各段文本和时间区间
2. 可选：阿里云 CosyVoice 声音克隆
3. 并发调用 TTS，为每段字幕生成音频
4. 时长调整：
   - TTS 音频短于字幕区间 → `ffmpeg anullsrc` 追加静音
   - TTS 音频长于字幕区间 → `ffmpeg atempo` 加速
5. `ffmpeg concat` 拼接所有片段 → `tts_final_audio.wav`
6. `ffmpeg -map 0:v:0 -map 1:a:0` 替换视频音轨 → `video_with_tts.mp4`

TTS 后端：

| 后端 | 配置值 |
|---|---|
| 阿里云 NLS | `aliyun` |
| OpenAI TTS API | `openai` |
| Microsoft Edge TTS（本地） | `edge-tts` |

#### Step 4 — 字幕烧录（embedSubtitles）

1. `ffprobe` 检测视频分辨率
2. `srtToAss()` 将 SRT 转为 ASS 格式，定义 Major/Minor 字幕样式
3. `ffmpeg -vf "ass=formatted_subtitles.ass" -c:a aac -b:a 192k` 烧录字幕
4. 竖版视频额外执行 `convertToVertical()`（`scale=720:1280` + `pad`）

### 1.3 KrillinAI 与本项目的关键差异

| 特性 | KrillinAI | 本项目 |
|---|---|---|
| 语音分离 | 无（直接用原始音频转录） | Demucs 分离人声/背景音乐 |
| 转录输入 | 原始音频（含背景噪声） | 纯人声 `vocals.wav`（更准确） |
| 音频分割策略 | 智能静音点切分 + 多 worker 并发 | Whisper 直接处理完整人声 |
| TTS 参考音色 | 固定配置或声音克隆 API | 从人声截取 8 秒作为参考音色 |
| 最终音轨 | TTS 音轨替换全部原始音频 | TTS 音轨 + 背景音乐混合 |
| 字幕 | 双语 SRT 可选 | 单语 SRT（目标语言） |
| 水印去除 | 无 | 独立 Tab（不在翻译流程内） |

---

## 二、本项目适配流程

基于本项目的 MCP 工具集（详见 `docs/guide/mcp_client.md`），适配后的视频翻译流程共 11 步。

### 2.1 完整流程图

```
输入：原始视频文件（.mp4 / .mkv / .avi 等）
        │
        ▼ Step 1  提取音频
   ffmpeg -i input.mp4 -vn -ar 44100 -ac 2 -ab 192k -f mp3
        → origin_audio.mp3
        │
        ▼ Step 2  人声分离（MCP: demucs_service_separate_audio）
   Demucs htdemucs 模型，two_stems=true
        → vocals.wav（纯人声）
        → no_vocals.wav（背景音乐/音效）
        │
        ▼ Step 3  截取参考音色
   ffmpeg -i vocals.wav -t 8 -c copy ref_voice.wav
        → ref_voice.wav（TTS 声音克隆参考，8 秒）
        │
        ▼ Step 4  语音转录（MCP: whisper_transcribe_audio）
   输入：vocals.wav，language=null（自动检测源语言）
        → 分段文本 + 时间戳
          [{"start": 0.0, "end": 3.2, "text": "..."}, ...]
        │
        ▼ Step 5  LLM 翻译（OpenAI 库，llm_api_base/key/model）
   逐段调用 LLM，Prompt 策略：
     "将以下文本翻译为{目标语言}，保持原文含义，只输出译文。\n{原文}"
        → 各段译文列表
        │
        ▼ Step 6  生成 SRT
   原始分段时间戳 + 译文 → 目标语言单语 SRT
        → {文件名}_translated_{lang}.srt
        │
        ▼ Step 7  TTS 批量合成（MCP: tts_generate_voice_batch）
   texts = 各段译文列表
   prompt_voice_bytes = ref_voice.wav 字节（单个参考音色应用到所有段）
        → 各段译文音频（tts_seg_0.wav, tts_seg_1.wav, ...）
        │
        ▼ Step 8  时长对齐
   对每段 tts_seg_N.wav，按 SRT 时间戳计算目标时长：
     - TTS 时长 < 字幕时长：ffmpeg anullsrc 追加静音
     - TTS 时长 > 字幕时长：ffmpeg atempo 加速（atempo 范围 [0.5, 2.0]，
       超出范围时链式使用，如 atempo=2.0,atempo=1.2）
        → 各段对齐后音频（tts_aligned_N.wav）
        │
        ▼ Step 9  音轨拼接
   按 SRT 时间戳顺序，在各段音频之间插入对应时长的静音（anullsrc），
   ffmpeg concat 拼接所有对齐片段
        → tts_final.wav（时长与原视频一致）
        │
        ▼ Step 10  音频混合
   ffmpeg -i tts_final.wav -i no_vocals.wav
         -filter_complex "[0:a][1:a]amix=inputs=2:duration=first:weights=1.5 1"
        → mixed_audio.wav（TTS 音轨为主，背景音乐为辅）
        │
        ▼ Step 11  合成输出
   11a. SRT → ASS（默认样式：白色字体，底部居中，黑色描边）
   11b. ffmpeg -i input.mp4 -i mixed_audio.wav
              -map 0:v:0 -map 1:a:0
              -vf "ass=subtitles.ass"
              -c:v libx264 -c:a aac -b:a 192k
        → {文件名}_translated_{lang}.mp4
```

### 2.2 各步骤 MCP 工具调用说明

#### Step 2 — Demucs 人声分离

```python
import asyncio, base64
from fastmcp import Client

async def separate_vocals(audio_path, mcp_url):
    audio_b64 = base64.b64encode(open(audio_path, "rb").read()).decode()
    async with Client(mcp_url) as client:
        task_id = (await client.call_tool(
            "demucs_service_separate_audio",
            {"audio_bytes": audio_b64, "model": "htdemucs", "two_stems": True}
        )).data
        # 轮询等待完成
        while True:
            info = (await client.call_tool(
                "demucs_service_query_task", {"task_id": task_id}
            )).data
            if info["status"] == "completed":
                break
            if info["status"] == "failed":
                raise RuntimeError(info["error"])
            await asyncio.sleep(3)
        # 分别下载 vocals 和 no_vocals
        vocals_data = (await client.call_tool(
            "demucs_service_get_result", {"task_id": task_id, "stem": "vocals"}
        )).data
        no_vocals_data = (await client.call_tool(
            "demucs_service_get_result", {"task_id": task_id, "stem": "no_vocals"}
        )).data
    return vocals_data, no_vocals_data
```

#### Step 4 — Whisper 语音转录

```python
async def transcribe_audio(audio_path, mcp_url):
    audio_b64 = base64.b64encode(open(audio_path, "rb").read()).decode()
    async with Client(mcp_url) as client:
        task_id = (await client.call_tool(
            "whisper_transcribe_audio",
            {"audio_bytes": audio_b64, "language": None}  # 自动检测源语言
        )).data
        while True:
            info = (await client.call_tool(
                "whisper_query_task", {"task_id": task_id}
            )).data
            if info["status"] == "completed":
                break
            if info["status"] == "failed":
                raise RuntimeError(info["error"])
            await asyncio.sleep(3)
        result = (await client.call_tool(
            "whisper_get_result", {"task_id": task_id}
        )).data
    # result["segments"] = [{"start": float, "end": float, "text": str}, ...]
    return result["segments"]
```

#### Step 7 — TTS 批量合成

```python
async def generate_tts_batch(texts, ref_voice_path, mcp_url):
    prompt_b64 = base64.b64encode(open(ref_voice_path, "rb").read()).decode()
    async with Client(mcp_url) as client:
        task_id = (await client.call_tool(
            "tts_generate_voice_batch",
            {"texts": texts, "prompt_voice_bytes_list": prompt_b64}
        )).data
        while True:
            info = (await client.call_tool(
                "tts_query_task", {"task_id": task_id}
            )).data
            if info["status"] == "completed":
                break
            if info["status"] == "failed":
                raise RuntimeError(info["error"])
            await asyncio.sleep(3)
        # 逐条下载各段音频
        wav_list = []
        count = info["result"]["count"]
        for i in range(count):
            wav_b64 = (await client.call_tool(
                "tts_get_result_batch_item",
                {"task_id": task_id, "index": i}
            )).data
            wav_list.append(base64.b64decode(wav_b64))
    return wav_list
```

### 2.3 中间文件目录结构

```
{项目根目录}/
└── temp/
    └── {YYYYMMDD_HHMMSS}/          ← 每次批处理任务的时间戳目录
        ├── {视频文件名_1}/
        │   ├── origin_audio.mp3
        │   ├── vocals.wav
        │   ├── no_vocals.wav
        │   ├── ref_voice.wav
        │   ├── tts_seg_0.wav
        │   ├── tts_seg_1.wav
        │   ├── ...
        │   ├── tts_aligned_0.wav
        │   ├── tts_aligned_1.wav
        │   ├── ...
        │   ├── tts_final.wav
        │   ├── mixed_audio.wav
        │   └── subtitles.ass
        └── {视频文件名_2}/
            └── ...
```

中间文件任务完成后**保留不清理**，便于排查问题。

### 2.4 与 KrillinAI 实现策略对比

| 方面 | KrillinAI 策略 | 本项目策略 | 原因 |
|---|---|---|---|
| 音频分割 | 智能静音点切分 + 多 worker | 不切分，整段送 Whisper | MCP Whisper 服务内部已处理长音频 |
| 转录准确性 | 原始混合音频 | 纯人声（Demucs 分离后） | 去除背景噪声，提升转录质量 |
| 背景音乐保留 | 不保留（全音轨替换） | 保留（amix 混合） | 保持视频的背景氛围 |
| TTS 音色 | 固定配置 / 声音克隆 API | 从人声截取 8 秒参考 | 复用原始说话人音色，零成本克隆 |
| 字幕格式 | 双语可选 | 单语（目标语言） | 简化输出，聚焦配音翻译场景 |

---

## 三、关键技术注意事项

### 3.1 atempo 范围限制

ffmpeg `atempo` 滤镜每个实例仅支持 `[0.5, 2.0]` 范围。需要更大倍速时须链式使用：

```
# 加速到 3.0 倍：atempo=2.0,atempo=1.5
# 减速到 0.3 倍：atempo=0.5,atempo=0.6
```

### 3.2 音频混合权重

`amix` 默认对所有输入等权重混合，建议 TTS 音轨权重略高于背景音乐：

```
-filter_complex "[0:a][1:a]amix=inputs=2:duration=first:weights=1.5 1"
```

### 3.3 concat 静音填充

各段 TTS 音频之间存在字幕间隔时间，需在 concat 前为每段追加对应时长的静音，确保整体音轨与视频时间轴完全对齐：

```python
gap_duration = next_segment_start - current_segment_end
# 用 anullsrc 生成 gap_duration 秒的静音并拼接到当前段尾部
```

### 3.4 asyncio 与 Tkinter 线程

MCP 客户端使用 `async/await`，而 kk.py 的批处理运行在 `threading.Thread` 中。使用 `asyncio.run()` 在 daemon thread 中创建独立事件循环，每个 MCP 调用封装为一个同步函数：

```python
def call_mcp_sync(coro):
    return asyncio.run(coro)
```
