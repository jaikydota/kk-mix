# Mix MCP 客户端使用文档

Mix MCP 将四个 AI 推理服务（音频分离、语音识别、语音合成、视频去字幕）聚合为一个统一的 MCP 端点，客户端只需连接路由器即可调用全部功能。

---

## 目录

- [架构概览](#架构概览)
- [服务管理](#服务管理)
- [连接方式](#连接方式)
- [通用异步任务模型](#通用异步任务模型)
- [工具参考](#工具参考)
  - [Demucs — 音频人声分离](#demucs--音频人声分离)
  - [Whisper — 语音转文字](#whisper--语音转文字)
  - [TTS — 文字转语音](#tts--文字转语音)
  - [Watermark — 视频去字幕](#watermark--视频去字幕)
- [完整客户端示例](#完整客户端示例)
- [错误处理](#错误处理)
- [文件传输规范](#文件传输规范)

---

## 架构概览

```
客户端 (fastmcp.Client)
       │
       ▼  HTTP  port 8400
┌─────────────────────┐
│   Mix MCP Router    │  router/proxy_server.py
└──────┬──────────────┘
       │ 内部代理到各后端
       ├─── port 8401  Demucs      (音频人声分离)
       ├─── port 8402  Whisper     (语音转文字)
       ├─── port 8403  IndexTTS2   (文字转语音)
       └─── port 8404  Watermark   (视频去字幕)
```

客户端仅需连接 **port 8400**（路由器），无需直接访问各后端服务。

---

## 服务管理

```bash
# 启动全部服务（后端 + 路由器）
bash start.sh

# 仅启动后端，跳过路由器
bash start.sh --no-router

# 查看服务状态（RUNNING/STOPPED/端口UP/DOWN/日志路径）
bash status.sh

# 停止全部服务（先停路由器，再停后端）
bash stop.sh
```

服务启动顺序：四个后端就绪后才启动路由器，避免路由器因后端未就绪而失败。
PID 文件保存在 `.pids/` 目录，日志保存在各服务目录下（如 `integrations/demucs-service/demucs-service.log`）。

---

## 连接方式

路由器默认监听 `http://0.0.0.0:8400/mcp`，使用 FastMCP HTTP transport。

### Python（推荐）

```python
from fastmcp import Client

async with Client("http://localhost:8400/mcp") as client:
    tools = await client.list_tools()
    result = await client.call_tool("工具名", {参数})
```

### 环境变量覆盖

```bash
ROUTER_URL=http://127.0.0.1:8400/mcp python your_script.py
```

---

## 通用异步任务模型

所有推理工具均为**异步任务**，流程如下：

```
1. 调用提交工具  →  返回 task_id (UUID)
2. 轮询 query_task(task_id)  →  status: pending / running / completed / failed
3. status == completed 后，调用 get_result(task_id)  →  返回结果
```

### TaskInfo 结构（query_task 返回值）

```json
{
  "task_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "status": "completed",
  "created_at": "2026-03-05T10:00:00.000000",
  "completed_at": "2026-03-05T10:00:30.000000",
  "result": { ... },
  "error": null
}
```

| 字段 | 说明 |
|---|---|
| `status` | `pending` / `running` / `completed` / `failed` |
| `result` | 完成后的结果描述（不含文件内容本身） |
| `error` | 失败时的错误信息 |

### 通用轮询辅助函数

```python
import asyncio
from fastmcp import Client

async def poll_until_done(
    client: Client,
    query_tool: str,       # 带前缀的 query_task 工具名
    task_id: str,
    timeout: float = 300.0,
    interval: float = 3.0,
) -> dict:
    elapsed = 0.0
    while elapsed < timeout:
        result = await client.call_tool(query_tool, {"task_id": task_id})
        info: dict = result.data
        if info.get("status") in ("completed", "failed"):
            return info
        await asyncio.sleep(interval)
        elapsed += interval
    raise TimeoutError(f"Task {task_id!r} did not finish within {timeout}s")
```

---

## 工具参考

路由器对所有工具名加前缀，规则：`{服务key}_{原工具名}`

| 服务 | 前缀 | 后端端口 |
|---|---|---|
| Demucs | `demucs_service_` | 8401 |
| Whisper | `whisper_` | 8402 |
| IndexTTS2 | `tts_` | 8403 |
| Watermark | `watermark_` | 8404 |

---

### Demucs — 音频人声分离

#### `demucs_service_separate_audio`

提交音频分离任务，返回 `task_id`。

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `audio_bytes` | bytes (base64) | 必填 | 输入音频文件原始字节（mp3/wav/flac 等） |
| `model` | str | `"htdemucs"` | 模型名：`htdemucs` / `htdemucs_ft` / `htdemucs_6s` / `mdx` / `mdx_extra` |
| `two_stems` | bool | `true` | `true`：分离为 vocals + no_vocals；`false`：分离为 vocals + drums + bass + other |

#### `demucs_service_query_task`

| 参数 | 类型 | 说明 |
|---|---|---|
| `task_id` | str | 由 `separate_audio` 返回 |

完成后 `result.files` 为 stem 名到文件名的映射，如 `{"vocals": "vocals.wav", "no_vocals": "no_vocals.wav"}`。

#### `demucs_service_get_result`

下载指定 stem 的 WAV 文件字节。

| 参数 | 类型 | 说明 |
|---|---|---|
| `task_id` | str | 任务 ID |
| `stem` | str | stem 名，如 `"vocals"` / `"no_vocals"` / `"drums"` / `"bass"` / `"other"` |

**返回**：WAV 文件的原始 bytes（或 base64 字符串，取决于 FastMCP 版本）。

---

### Whisper — 语音转文字

#### `whisper_transcribe_audio`

提交转录任务，返回 `task_id`。

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `audio_bytes` | bytes (base64) | 必填 | 输入音频文件字节（mp3/wav/flac 等） |
| `model_size` | str | `"large-v3"` | 模型：`tiny` / `base` / `small` / `medium` / `large-v2` / `large-v3` |
| `beam_size` | int | `5` | Beam search 宽度，越大越准但越慢 |
| `language` | str \| null | `null` | ISO-639-1 语言代码（如 `"zh"` / `"en"` / `"ja"`），空值自动识别 |

#### `whisper_query_task`

同通用 `query_task`，参数：`task_id`。

#### `whisper_get_result`

返回转录结果 JSON 字典。

| 参数 | 类型 | 说明 |
|---|---|---|
| `task_id` | str | 任务 ID |

**返回结构**：

```json
{
  "language": "zh",
  "language_probability": 0.99,
  "duration": 8.01,
  "segments": [
    {
      "start": 0.0,
      "end": 3.06,
      "text": "希望我们每个人都过得很开心"
    }
  ]
}
```

---

### TTS — 文字转语音

基于 IndexTTS2，支持零样本声音克隆和情感控制。

#### `tts_generate_voice`

单条文本合成，返回 `task_id`。

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `text` | str | 必填 | 要合成的文本 |
| `prompt_voice_bytes` | bytes (base64) | 必填 | 参考音频（用于声音克隆）的 WAV 字节 |
| `emo_text` | str \| null | `null` | 情感描述文本（如 `"happy excited"`） |
| `emo_alpha` | float | `0.7` | 情感混合强度 `[0.0, 1.0]` |

#### `tts_generate_voice_batch`

批量文本合成，返回 `task_id`。

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `texts` | list[str] | 必填 | 待合成文本列表 |
| `prompt_voice_bytes_list` | bytes \| list[bytes] | 必填 | 单个参考音频（应用到全部文本）或与 `texts` 等长的列表 |
| `emo_text` | str \| null | `null` | 全局情感描述 |
| `emo_alpha` | float | `0.7` | 情感混合强度 |

#### `tts_query_task`

同通用 `query_task`，参数：`task_id`。

单条任务完成后 `result` 为 `{"output_file": "output.wav"}`；
批量任务完成后 `result` 为 `{"output_files": {"output_0": "output_0.wav", ...}, "count": N}`。

#### `tts_get_result`

下载单条合成结果的 WAV 字节（base64 编码）。

| 参数 | 类型 | 说明 |
|---|---|---|
| `task_id` | str | 由 `generate_voice` 返回的任务 ID |

#### `tts_get_result_batch_item`

下载批量合成结果中指定条目的 WAV 字节（base64 编码）。

| 参数 | 类型 | 说明 |
|---|---|---|
| `task_id` | str | 由 `generate_voice_batch` 返回的任务 ID |
| `index` | int | 0-based 索引 |

---

### Watermark — 视频去字幕

#### `watermark_remove_subtitle`

提交字幕/水印消除任务，返回 `task_id`。

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `video_bytes` | bytes (base64) | 必填 | 输入视频文件字节（mp4/mkv/avi 等） |
| `mode` | str | `"sttn"` | 修复算法：`sttn`（快，适合真人视频）/ `lama`（适合动画）/ `propainter`（最高质量，GPU 消耗大） |
| `sub_area` | list[int] \| null | `null` | 可选检测区域 `[x_min, y_min, x_max, y_max]`，空值全帧检测 |

#### `watermark_query_task`

同通用 `query_task`，参数：`task_id`。

#### `watermark_get_result`

下载处理后的视频字节（base64 编码）。

| 参数 | 类型 | 说明 |
|---|---|---|
| `task_id` | str | 由 `remove_subtitle` 返回的任务 ID |

**返回**：MP4 文件的 base64 编码字符串，解码后即为完整视频文件。

---

## 完整客户端示例

### 1. 音频人声分离（Demucs）

```python
import asyncio, base64
from fastmcp import Client

async def separate_vocals(audio_path: str, output_path: str):
    audio_b64 = base64.b64encode(open(audio_path, "rb").read()).decode()

    async with Client("http://localhost:8400/mcp") as client:
        # 提交任务（vocals + no_vocals 两轨分离）
        result = await client.call_tool(
            "demucs_service_separate_audio",
            {"audio_bytes": audio_b64, "model": "htdemucs", "two_stems": True},
        )
        task_id: str = result.data
        print(f"Task submitted: {task_id}")

        # 轮询等待完成
        while True:
            info = (await client.call_tool(
                "demucs_service_query_task", {"task_id": task_id}
            )).data
            print(f"Status: {info['status']}")
            if info["status"] == "completed":
                break
            if info["status"] == "failed":
                raise RuntimeError(f"Task failed: {info['error']}")
            await asyncio.sleep(3)

        # 下载人声
        wav_data = (await client.call_tool(
            "demucs_service_get_result",
            {"task_id": task_id, "stem": "vocals"},
        )).data
        if isinstance(wav_data, str):
            wav_data = base64.b64decode(wav_data)
        open(output_path, "wb").write(wav_data)
        print(f"Saved: {output_path}")

asyncio.run(separate_vocals("input.wav", "vocals.wav"))
```

### 2. 语音转文字（Whisper）

```python
import asyncio, base64, json
from fastmcp import Client

async def transcribe(audio_path: str):
    audio_b64 = base64.b64encode(open(audio_path, "rb").read()).decode()

    async with Client("http://localhost:8400/mcp") as client:
        result = await client.call_tool(
            "whisper_transcribe_audio",
            {"audio_bytes": audio_b64, "language": "zh"},
        )
        task_id: str = result.data

        while True:
            info = (await client.call_tool(
                "whisper_query_task", {"task_id": task_id}
            )).data
            if info["status"] == "completed":
                break
            if info["status"] == "failed":
                raise RuntimeError(info["error"])
            await asyncio.sleep(3)

        data = (await client.call_tool(
            "whisper_get_result", {"task_id": task_id}
        )).data
        print(f"Language: {data['language']}  Duration: {data['duration']:.1f}s")
        for seg in data["segments"]:
            print(f"  [{seg['start']:.2f}s → {seg['end']:.2f}s]  {seg['text']}")

asyncio.run(transcribe("audio.wav"))
```

### 3. 文字转语音（TTS）

```python
import asyncio, base64
from fastmcp import Client

async def generate_tts(text: str, prompt_wav: str, output_path: str):
    prompt_b64 = base64.b64encode(open(prompt_wav, "rb").read()).decode()

    async with Client("http://localhost:8400/mcp") as client:
        result = await client.call_tool(
            "tts_generate_voice",
            {"text": text, "prompt_voice_bytes": prompt_b64},
        )
        task_id: str = result.data

        while True:
            info = (await client.call_tool(
                "tts_query_task", {"task_id": task_id}
            )).data
            if info["status"] == "completed":
                break
            if info["status"] == "failed":
                raise RuntimeError(info["error"])
            await asyncio.sleep(3)

        wav_b64 = (await client.call_tool(
            "tts_get_result", {"task_id": task_id}
        )).data
        open(output_path, "wb").write(base64.b64decode(wav_b64))
        print(f"Saved: {output_path}")

asyncio.run(generate_tts("今天天气真好。", "reference.wav", "output.wav"))
```

### 4. 视频去字幕（Watermark）

```python
import asyncio, base64
from fastmcp import Client

async def remove_subtitles(video_path: str, output_path: str):
    video_b64 = base64.b64encode(open(video_path, "rb").read()).decode()

    async with Client("http://localhost:8400/mcp") as client:
        result = await client.call_tool(
            "watermark_remove_subtitle",
            {"video_bytes": video_b64, "mode": "sttn"},
        )
        task_id: str = result.data
        print(f"Task submitted: {task_id}  (may take several minutes)")

        while True:
            info = (await client.call_tool(
                "watermark_query_task", {"task_id": task_id}
            )).data
            print(f"Status: {info['status']}")
            if info["status"] == "completed":
                break
            if info["status"] == "failed":
                raise RuntimeError(info["error"])
            await asyncio.sleep(5)

        mp4_b64 = (await client.call_tool(
            "watermark_get_result", {"task_id": task_id}
        )).data
        open(output_path, "wb").write(base64.b64decode(mp4_b64))
        print(f"Saved: {output_path}")

asyncio.run(remove_subtitles("input.mp4", "output_clean.mp4"))
```

---

## 错误处理

| 场景 | 行为 |
|---|---|
| `query_task` 传入不存在的 task_id | 返回 `{"error": "Task ... not found."}` |
| `get_result` 时任务尚未完成 | 抛出异常（`ValueError: Task ... is not completed yet`） |
| 任务失败（`status == "failed"`） | `info["error"]` 包含完整 traceback |
| `get_result_batch_item` 索引越界 | 抛出异常 |

推荐在代码中检查 `status == "failed"` 时记录 `info["error"]` 以便排查问题。

---

## 文件传输规范

所有文件均以 **base64 编码字符串** 传入/传出（FastMCP HTTP transport 的约束）。

```python
import base64

# 发送文件
file_b64 = base64.b64encode(Path("input.wav").read_bytes()).decode()

# 接收文件（get_result 返回值可能是 bytes 或 base64 str，需兼容两种）
def decode_result(data) -> bytes:
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return base64.b64decode(data)
    raise TypeError(f"Unexpected type: {type(data)}")
```

### 各工具输入/输出格式

| 工具 | 输入格式 | 输出格式 |
|---|---|---|
| `demucs_service_separate_audio` | audio: base64 bytes | task_id: str |
| `demucs_service_get_result` | — | WAV: bytes 或 base64 str |
| `whisper_transcribe_audio` | audio: base64 bytes | task_id: str |
| `whisper_get_result` | — | JSON dict |
| `tts_generate_voice` | prompt_voice: base64 bytes | task_id: str |
| `tts_get_result` | — | WAV: base64 str |
| `tts_get_result_batch_item` | — | WAV: base64 str |
| `watermark_remove_subtitle` | video: base64 bytes | task_id: str |
| `watermark_get_result` | — | MP4: base64 str |

---

## 参考

- FastMCP 官方文档：https://gofastmcp.com
- 客户端示例脚本：`tests/scripts/`
- 服务管理：`start.sh` / `stop.sh` / `status.sh`
