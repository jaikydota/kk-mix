"""Index-TTS 语音合成客户端。接口文档见 docs/index-tts-api.md。

服务地址与 api-key 由全局设置提供（AppSettings.tts_base_url / tts_api_key）。

流程：
  1. ensure_reference()  把本地参考音上传到服务端（每个进程只上传一次）
  2. synthesize()        引用服务端参考音路径合成语音，返回 WAV
"""
from __future__ import annotations

import os

import httpx

from .paths import resource_path

# 参考音：把你想克隆的音色 WAV 放到 assets/tts_reference.wav（不随仓库分发，见 README）
# 服务端实际保存为 assets/<REF_REMOTE_PATH>
REF_FILENAME = "tts_reference.wav"
REF_REMOTE_PATH = f"kk-mix/{REF_FILENAME}"

# 固定 seed 保证整批合成音色一致
DEFAULT_SEED = 42

_reference_uploaded = False


class TTSError(Exception):
    """TTS 上传或合成失败。"""


def local_reference_path() -> str:
    return resource_path(os.path.join("assets", REF_FILENAME))


class TTSClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self._headers = {"api-key": api_key}

    def ensure_reference(self) -> str:
        """把本地参考音上传到服务端，返回给日志用的说明文字。

        本地文件不存在时不报错（服务端可能已有该参考音），交由后续合成时兜底。
        每个进程只实际上传一次。
        """
        global _reference_uploaded
        if _reference_uploaded:
            return "参考音已就绪（本次已上传）"

        local = local_reference_path()
        if not os.path.exists(local):
            return f"本地未找到参考音 {REF_FILENAME}，将直接引用服务端已有文件"

        try:
            with open(local, "rb") as f:
                data = f.read()
            resp = httpx.post(
                f"{self.base_url}/upload",
                headers=self._headers,
                files=[("files", (REF_FILENAME, data, "audio/wav"))],
                data={"paths": REF_REMOTE_PATH},
                timeout=120,
            )
        except httpx.HTTPError as e:
            raise TTSError(f"参考音上传失败: {e}") from e

        if resp.status_code != 200:
            raise TTSError(f"参考音上传失败 {resp.status_code}: {resp.text[:200]}")

        _reference_uploaded = True
        saved = resp.json().get("saved", [])
        return f"参考音上传成功: {saved[0] if saved else REF_REMOTE_PATH}"

    def synthesize(self, text: str, out_path: str,
                   seed: int = DEFAULT_SEED, timeout: float = 300.0) -> None:
        """将 text 合成为语音并保存到 out_path（WAV）。失败抛 TTSError。"""
        payload = {"text": text, "audio_paths": [REF_REMOTE_PATH], "seed": seed}
        try:
            resp = httpx.post(
                f"{self.base_url}/tts_url",
                headers=self._headers,
                json=payload,
                timeout=timeout,
            )
        except httpx.HTTPError as e:
            raise TTSError(f"TTS 请求失败: {e}") from e

        if resp.status_code == 401:
            raise TTSError("TTS 鉴权失败(401)，请检查全局设置中的 API Key")
        if resp.status_code != 200:
            detail = resp.text[:200]
            if "No such file" in resp.text:
                detail = f"服务端缺少参考音 {REF_REMOTE_PATH}，请把参考音放到 assets 目录后重试"
            raise TTSError(f"TTS 服务返回 {resp.status_code}: {detail}")

        if not resp.content.startswith(b"RIFF"):
            ctype = resp.headers.get("content-type", "")
            raise TTSError(f"TTS 返回非 WAV 数据 ({ctype}): {resp.text[:200]}")

        with open(out_path, "wb") as f:
            f.write(resp.content)
