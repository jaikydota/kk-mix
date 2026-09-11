"""极简 i18n：以中文原文为 key，`tr(key)` 返回当前语言的文本。

约定：
  - 所有用户可见文本（控件文字、提示、日志）都写成 tr("中文")；
    带变量的用 tr("成功 {0}/{1}").format(a, b)，不要用 f-string
  - 中文是源语言，缺少译文时原样返回中文，不会崩
  - 译文表按语言放在 translations_<lang>.py，例如 translations_en.py 的 EN 字典
  - 模块级 / 类级的常量（如 TITLE、选项列表）保持中文，在使用处再 tr()，
    否则切换语言后不会更新
"""
from __future__ import annotations

SUPPORTED = ("zh", "en")
LANGUAGE_NAMES = {"zh": "简体中文", "en": "English"}

_lang = "zh"
_tables: dict[str, dict[str, str]] = {}


def set_language(lang: str) -> None:
    global _lang
    _lang = lang if lang in SUPPORTED else "zh"


def current() -> str:
    return _lang


def detect_system_language() -> str:
    """系统区域为中文时返回 zh，其余返回 en。"""
    try:
        from PySide6.QtCore import QLocale
        return "zh" if QLocale.system().name().lower().startswith("zh") else "en"
    except Exception:
        return "zh"


def _table(lang: str) -> dict[str, str]:
    if lang not in _tables:
        if lang == "en":
            from .translations_en import EN
            _tables[lang] = EN
        else:
            _tables[lang] = {}
    return _tables[lang]


def tr(key: str) -> str:
    if _lang == "zh":
        return key
    return _table(_lang).get(key, key)
