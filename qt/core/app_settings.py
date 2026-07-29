"""全局配置：对应 kk.py 中散落的 tk.*Var + settings.json。

用 dataclass 集中管理，Worker 构造时按需拷贝字段避免跨线程读写。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class AppSettings:
    # TTS 语音服务（字幕转场拼接的配音合成）
    tts_base_url: str = ""
    tts_api_key: str = ""

    # 调试
    verbose_log: bool = False

    # 性能与稳定性
    thread_count: int = 1
    speed_priority: bool = True    # ultrafast 极速模式
    compress_video: bool = False   # 使用 -b:v 码率控制
    bitrate: str = "2M"

    @classmethod
    def load(cls, path: Path) -> "AppSettings":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            field_names = {f for f in cls.__dataclass_fields__}
            clean = {k: v for k, v in data.items() if k in field_names}
            # thread_count 在旧版可能存成字符串
            if "thread_count" in clean:
                try:
                    clean["thread_count"] = int(clean["thread_count"])
                except (TypeError, ValueError):
                    clean["thread_count"] = 1
            return cls(**clean)
        except Exception:
            return cls()

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
