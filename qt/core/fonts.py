"""Windows 系统字体枚举，保留 kk.py 中的中英文命名策略。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


_KNOWN_CHINESE_FONTS = {
    "Microsoft YaHei":            "微软雅黑",
    "Microsoft YaHei UI":         "微软雅黑 UI",
    "Microsoft YaHei Light":      "微软雅黑 细体",
    "Microsoft YaHei UI Light":   "微软雅黑 UI 细体",
    "SimSun":                     "宋体",
    "NSimSun":                    "新宋体",
    "SimSun-ExtB":                "宋体-ExtB",
    "SimSun-ExtG":                "宋体-ExtG",
    "SimHei":                     "黑体",
    "FangSong":                   "仿宋",
    "KaiTi":                      "楷体",
    "FangSong_GB2312":            "仿宋_GB2312",
    "KaiTi_GB2312":               "楷体_GB2312",
    "DengXian":                   "等线",
    "DengXian Light":             "等线 Light",
    "LiSu":                       "隶书",
    "YouYuan":                    "幼圆",
    "STSong":                     "华文宋体",
    "STZhongsong":                "华文中宋",
    "STFangsong":                 "华文仿宋",
    "STKaiti":                    "华文楷体",
    "STHupo":                     "华文琥珀",
    "STXihei":                    "华文细黑",
    "STCaiyun":                   "华文彩云",
    "STLiti":                     "华文隶书",
    "STXingkai":                  "华文行楷",
    "STXinwei":                   "华文新魏",
    "FZShuTi":                    "方正舒体",
    "FZYaoTi":                    "方正姚体",
    "Adobe Heiti Std R":          "Adobe 黑体 Std R",
    "Adobe Kaiti Std R":          "Adobe 楷体 Std R",
    "Adobe Song Std L":           "Adobe 宋体 Std L",
    "Adobe Fangsong Std R":       "Adobe 仿宋 Std R",
}


def _label_has_chinese(s: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" or "\u3400" <= c <= "\u4dbf" for c in s)


def list_system_fonts() -> dict[str, str]:
    """返回 {显示标签: 字体绝对路径}，顺序已按中英文排好。

    直接读 Windows 注册表，和 kk.py 中的 _get_system_fonts 保持一致。
    非 Windows 或读取失败时回退到扫描 Fonts 目录。
    """
    if sys.platform != "win32":
        return {}

    fonts_dir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Fonts")
    font_map: dict[str, str] = {}
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
        )
        i = 0
        while True:
            try:
                display_name, filename, _ = winreg.EnumValue(key, i)
                i += 1
                path = filename if os.path.isabs(filename) else os.path.join(fonts_dir, filename)
                if os.path.exists(path) and Path(path).suffix.lower() in (".ttf", ".otf", ".ttc"):
                    eng = display_name.replace(" (TrueType)", "").replace(" (OpenType)", "").strip()
                    matched = [cn for ek, cn in sorted(
                        _KNOWN_CHINESE_FONTS.items(), key=lambda x: -len(x[0])
                    ) if ek in eng]
                    seen, unique_cn = set(), []
                    for c in matched:
                        if c not in seen:
                            seen.add(c)
                            unique_cn.append(c)
                    cn_part = " & ".join(unique_cn)
                    label = f"{cn_part} ({eng})" if cn_part else eng
                    font_map[label] = path
            except OSError:
                break
        winreg.CloseKey(key)
    except Exception:
        for fname in sorted(os.listdir(fonts_dir)):
            if fname.lower().endswith((".ttf", ".otf", ".ttc")):
                font_map[Path(fname).stem] = os.path.join(fonts_dir, fname)

    chinese = sorted(k for k in font_map if _label_has_chinese(k))
    others = sorted(k for k in font_map if not _label_has_chinese(k))
    return {k: font_map[k] for k in chinese + others}


def wrap_title_text(text: str, fontsize: int, video_width: int, margin_ratio: float = 0.08) -> list[str]:
    """按视频宽度和字体大小动态换行。"""
    import unicodedata

    usable_px = video_width * (1.0 - 2 * margin_ratio)

    def char_px(ch: str) -> float:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            return fontsize * 1.15
        return fontsize * 0.65

    lines: list[str] = []
    current = ""
    current_w = 0.0
    for ch in text:
        w = char_px(ch)
        if current_w + w <= usable_px:
            current += ch
            current_w += w
        else:
            if current:
                lines.append(current)
            current = ch
            current_w = w
    if current:
        lines.append(current)
    return lines or [text]
