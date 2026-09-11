# Index-TTS 语音合成服务接口文档

## 概述

Index-TTS 是一个支持参考音色克隆的语音合成服务，通过上传参考音频来定义音色，然后基于该音色合成任意文本的语音。

**服务地址：** 由你自行部署的 Index-TTS 服务，例如 `http://<your-index-tts-host>`

> **注意：** 所有请求均须在 HTTP Header 中携带 `api-key` 进行鉴权。

---

## 鉴权说明

所有接口请求头需包含以下参数：

| 请求头字段 | 类型   | 必填 | 说明         |
|------------|--------|------|--------------|
| `api-key`  | string | 是   | 服务访问密钥 |

**示例：**
```
api-key: your_api_key_here
```

---

## 接口列表

| 接口           | 方法 | 地址                                                        | 说明             |
|----------------|------|-------------------------------------------------------------|------------------|
| 上传参考音频   | POST | `http://<your-index-tts-host>/upload`      | 上传克隆音色所需的参考音频文件 |
| 语音合成       | POST | `http://<your-index-tts-host>/tts_url`     | 基于参考音色合成文本语音       |

---

## 接口详情

### 1. 上传参考音频

上传用于音色克隆的参考 WAV 音频文件。支持一次上传多个文件。

**请求地址**

```
POST http://<your-index-tts-host>/upload
```

**请求头**

| 字段           | 值                            | 说明         |
|----------------|-------------------------------|--------------|
| `api-key`      | `your_api_key_here`           | 服务访问密钥 |
| `Content-Type` | `multipart/form-data`         | 表单上传格式 |

**请求参数（multipart/form-data）**

| 字段名     | 类型     | 必填 | 说明                                                          |
|---------|--------|----|-------------------------------------------------------------|
| `files` | file   | 是  | WAV 音频文件（可重复多次指定该字段以上传多个文件）                                 |
| `paths` | string | 是  | 文件在服务端的保存路径，格式为 `{你的目录名}/{文件名}.wav`（可重复多次指定，与 `files` 一一对应） |

> **说明：**
> - 音频文件格式须为 WAV，建议时长 5～30 秒，音质清晰无噪音。
> - `paths` 字段与 `files` 字段按顺序一一对应。
> - 后续合成接口的 `audio_paths` 参数使用此处指定的 `paths` 值来引用参考音频。

**响应示例**

```json
{
  "status": "ok",
  "saved": [
    "assets/your_dir/温柔亲和.wav",
    "assets/your_dir/参考音2.wav"
  ]
}
```

**响应字段说明**

| 字段     | 类型         | 说明                         |
|----------|--------------|------------------------------|
| `status` | string       | 状态，成功为 `"ok"`          |
| `saved`  | string array | 服务端实际保存的文件路径列表 |

**cURL 示例**

```bash
# 上传单个参考音频
curl -X POST http://<your-index-tts-host>/upload \
  -H "api-key: your_api_key_here" \
  -F "files=@温柔亲和.wav" \
  -F "paths=your_dir/温柔亲和.wav"

# 上传多个参考音频
curl -X POST http://<your-index-tts-host>/upload \
  -H "api-key: your_api_key_here" \
  -F "files=@温柔亲和.wav" \
  -F "paths=your_dir/温柔亲和.wav" \
  -F "files=@参考音2.wav" \
  -F "paths=your_dir/参考音2.wav"
```

**Python 示例**

```python
import httpx

api_key = "your_api_key_here"
upload_url = "http://<your-index-tts-host>/upload"

with open("温柔亲和.wav", "rb") as f:
    audio_bytes = f.read()

response = httpx.post(
    upload_url,
    headers={"api-key": api_key},
    files=[("files", ("温柔亲和.wav", audio_bytes, "audio/wav"))],
    data={"paths": "your_dir/温柔亲和.wav"},
)
print(response.json())
# {"status": "ok", "saved": ["assets/your_dir/温柔亲和.wav"]}
```

---

### 2. 语音合成

基于已上传的参考音频，将输入文本合成为对应音色的语音，返回 WAV 格式音频二进制数据。

**请求地址**

```
POST http://<your-index-tts-host>/tts_url
```

**请求头**

| 字段           | 值                      | 说明         |
|----------------|-------------------------|--------------|
| `api-key`      | `your_api_key_here`     | 服务访问密钥 |
| `Content-Type` | `application/json`      | JSON 请求体  |

**请求参数（JSON Body）**

| 字段          | 类型         | 必填 | 说明                                                                                    |
|---------------|--------------|------|-----------------------------------------------------------------------------------------|
| `text`        | string       | 是   | 待合成的文本内容                                                                        |
| `audio_paths` | string array | 是   | 参考音频路径列表，对应上传时指定的 `paths` 值（如 `["your_dir/温柔亲和.wav"]`）。支持多个参考音混合，音色融合效果更自然 |
| `seed`        | integer      | 否   | 随机种子，指定后可使同一参考音的合成结果保持一致。同一段长文本分多次合成时，传相同 `seed` 可保证音色连贯 |

> **说明：**
> - `audio_paths` 中的路径填写上传时 `paths` 字段的值，带不带 `assets/` 前缀均可，服务端会自动处理。
> - 支持多参考音混合生成，数组中指定多个路径即可。

**响应**

| 内容类型      | 说明                              |
|---------------|-----------------------------------|
| `audio/wav`   | 响应体为合成后的 WAV 音频二进制数据，直接保存为 `.wav` 文件即可使用 |

**cURL 示例**

```bash
# 单个参考音合成
curl -X POST http://<your-index-tts-host>/tts_url \
  -H "api-key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{"text": "你好，欢迎使用语音合成服务", "audio_paths": ["your_dir/温柔亲和.wav"]}' \
  --output output.wav

# 多参考音混合合成（指定 seed 保证音色一致）
curl -X POST http://<your-index-tts-host>/tts_url \
  -H "api-key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "欢迎使用语音合成服务，今天天气真不错。",
    "audio_paths": ["your_dir/温柔亲和.wav", "your_dir/参考音2.wav"],
    "seed": 42
  }' \
  --output output.wav
```

**Python 示例**

```python
import httpx

api_key = "your_api_key_here"
tts_url = "http://<your-index-tts-host>/tts_url"

payload = {
    "text": "你好，欢迎使用语音合成服务",
    "audio_paths": ["your_dir/温柔亲和.wav"],
    "seed": 42,  # 可选，固定 seed 保证音色一致
}

response = httpx.post(
    tts_url,
    headers={"api-key": api_key},
    json=payload,
    timeout=120,  # TTS 推理可能耗时较长，建议超时时间设置 120s 以上
)
response.raise_for_status()

# 将返回的 WAV 二进制数据保存到文件
with open("output.wav", "wb") as f:
    f.write(response.content)

print("语音合成完成，已保存至 output.wav")
```

---

## 完整使用流程

```
1. 准备参考音频（WAV 格式，时长 5～30 秒，音质清晰）
           ↓
2. 调用 /upload 接口上传参考音频，记录 paths 中的路径
           ↓
3. 调用 /tts_url 接口，传入待合成文本和 audio_paths
           ↓
4. 接收返回的 WAV 二进制数据，保存为音频文件
```

**完整 Python 示例**

```python
import httpx

BASE_URL = "http://<your-index-tts-host>"
API_KEY = "your_api_key_here"
HEADERS = {"api-key": API_KEY}


def upload_reference_audio(file_path: str, remote_path: str) -> str:
    """上传参考音频，返回服务端路径"""
    with open(file_path, "rb") as f:
        audio_bytes = f.read()

    filename = file_path.split("/")[-1]
    resp = httpx.post(
        f"{BASE_URL}/upload",
        headers=HEADERS,
        files=[("files", (filename, audio_bytes, "audio/wav"))],
        data={"paths": remote_path},
        timeout=60,
    )
    resp.raise_for_status()
    print(f"上传成功: {resp.json()}")
    return remote_path


def generate_speech(text: str, audio_paths: list[str], output_path: str, seed: int | None = None) -> None:
    """合成语音并保存到文件"""
    payload = {"text": text, "audio_paths": audio_paths}
    if seed is not None:
        payload["seed"] = seed

    resp = httpx.post(
        f"{BASE_URL}/tts_url",
        headers=HEADERS,
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(resp.content)
    print(f"语音合成完成，已保存至 {output_path}")


if __name__ == "__main__":
    # Step 1: 上传参考音频
    remote_path = upload_reference_audio("温柔亲和.wav", "your_dir/温柔亲和.wav")

    # Step 2: 合成语音
    generate_speech(
        text="你好，欢迎使用语音合成服务，今天天气真不错。",
        audio_paths=[remote_path],
        output_path="output.wav",
        seed=42,
    )
```

---

## 错误说明

| HTTP 状态码 | 说明                                             |
|-------------|--------------------------------------------------|
| `200`       | 请求成功                                         |
| `400`       | 请求参数错误（如缺少必填字段、文件格式不正确等） |
| `401`       | `api-key` 缺失或无效                             |
| `500`       | 服务端内部错误（推理失败等）                     |

> 若接口返回非 200 状态码，请检查请求头中的 `api-key` 是否正确，以及请求参数格式是否符合要求。

---

## 注意事项

1. **音频格式**：参考音频须为 **WAV** 格式，建议时长 **5～30 秒**，录音环境安静，音质清晰。
2. **路径规范**：上传时 `paths` 建议统一使用 `your_dir/{文件名}.wav` 格式，合成时 `audio_paths` 填写对应值即可。
3. **超时设置**：语音合成推理耗时与文本长度正相关，客户端建议设置 **至少 120 秒**的超时时间。
4. **音色一致性**：同一批次的多段文本合成时，传入相同的 `seed` 值可确保音色风格一致。
5. **多参考音**：`audio_paths` 支持传入多个路径，服务端会融合多个参考音的音色特征进行合成。
