"""
测试 LLM 翻译功能
读取 settings.json 中的 API 配置，逐句翻译并打印结果。
运行方式：
    uv run python tests/test_llm_translate.py
"""

import json
import sys
import time
from pathlib import Path

# 找到 settings.json（在项目根目录）
ROOT = Path(__file__).parent.parent
settings_path = ROOT / "settings.json"

if not settings_path.exists():
    print(f"[ERROR] 找不到 settings.json: {settings_path}")
    sys.exit(1)

with open(settings_path, encoding="utf-8") as f:
    settings = json.load(f)

API_BASE = settings.get("llm_api_base", "https://api.openai.com/v1")
API_KEY  = settings.get("llm_api_key", "")
MODEL    = settings.get("llm_model", "gpt-4o")

print(f"API Base : {API_BASE}")
print(f"Model    : {MODEL}")
print(f"API Key  : {API_KEY[:8]}...{API_KEY[-4:] if len(API_KEY) > 12 else ''}")
print("-" * 60)

try:
    import openai
except ImportError:
    print("[ERROR] 未安装 openai，请执行：uv add openai")
    sys.exit(1)

client = openai.OpenAI(base_url=API_BASE, api_key=API_KEY)

# 测试句子（中文 → 英文）
TEST_SENTENCES = [
    "大家好，今天我们来聊一聊人工智能的最新进展。",
    "这个视频将介绍如何使用 FFmpeg 处理视频文件。",
    "希望对大家有所帮助，谢谢收看！",
]

TARGET_LANG = "en"
LANG_MAP = {"zh": "中文", "en": "英文", "ja": "日文", "ko": "韩文"}
lang_name = LANG_MAP.get(TARGET_LANG, TARGET_LANG)


def translate_one(text: str) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": (
                f"将以下文本翻译为{lang_name}，保持原文含义，"
                f"只输出译文，不要解释。\n{text}"
            ),
        }],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


print(f"共 {len(TEST_SENTENCES)} 句，目标语言: {TARGET_LANG} ({lang_name})\n")

all_ok = True
for i, text in enumerate(TEST_SENTENCES, 1):
    print(f"[{i}/{len(TEST_SENTENCES)}] 原文: {text}")
    t0 = time.time()
    try:
        result = translate_one(text)
        elapsed = time.time() - t0
        print(f"         译文: {result}")
        print(f"         耗时: {elapsed:.2f}s")
    except Exception as e:
        all_ok = False
        print(f"         [FAIL] {e}")
    print()

print("-" * 60)
if all_ok:
    print("[PASS] 所有句子翻译成功")
else:
    print("[FAIL] 部分句子翻译失败，请检查 API 配置")
    sys.exit(1)
