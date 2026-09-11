"""生成 README 用的界面截图（中英各一套）到 docs/screenshots/<lang>/。

用法: uv run python tools/make_screenshots.py

要点：
  - 走 Windows 原生 QPA 而不是 offscreen：offscreen 不加载系统字体，中文会渲染成方框
  - 窗口设 WA_DontShowOnScreen：布局/绘制照常进行，但不会在屏幕上闪一下
  - 「批处理完成」那张是真的跑了一遍格式转换（ffmpeg testsrc 生成 3 个测试视频），
    日志和完成提示都是真实输出；本机没有 ffmpeg 时跳过这一张
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from qfluentwidgets import Theme, setTheme  # noqa: E402

setTheme(Theme.LIGHT)

from qt.core import i18n  # noqa: E402
from qt.main_window import MainWindow  # noqa: E402
from qt.settings_window import SettingsDialog  # noqa: E402

OUT = ROOT / "docs" / "screenshots"

# 表单里的示例内容（纯示意，不会真的读取这些路径）
SAMPLE = {
    "zh": {
        "folders": [r"D:\素材\口播镜头", r"D:\素材\产品特写", r"D:\素材\使用场景"],
        "narration": [
            "这款保温杯采用 316 不锈钢内胆，保温可达 12 小时",
            "杯盖一键开合，单手操作不漏水",
            "三种配色，通勤、健身、露营都合适",
        ],
        "title": "夏日新品 · 限时 8 折",
    },
    "en": {
        "folders": [r"D:\footage\talking-head", r"D:\footage\product-closeups", r"D:\footage\lifestyle"],
        "narration": [
            "This tumbler uses a 316 stainless steel liner and keeps drinks hot for 12 hours",
            "One-touch lid, opens with one hand and never leaks",
            "Three colours, made for commuting, the gym and camping",
        ],
        "title": "Summer Drop · 20% Off",
    },
}


def wait(ms: int) -> None:
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def tab_by_name(win: MainWindow, name: str):
    for i in range(win.stack.count()):
        t = win.stack.widget(i)
        if getattr(t, "NAME", None) == name:
            return i, t
    raise KeyError(name)


def show_tab(win: MainWindow, name: str):
    i, t = tab_by_name(win, name)
    win.stack.setCurrentIndex(i)
    win.nav.setCurrentItem(name)
    wait(150)
    return t


def grab(win: MainWindow, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wait(120)
    win.grab().save(str(path))
    print("  ✓", path.relative_to(ROOT))


def make_test_videos(ffmpeg: str, folder: Path, n: int = 3) -> bool:
    """用 ffmpeg testsrc 生成几个 2 秒的小视频，供“真实跑一遍”用。"""
    colors = ["testsrc", "smptebars", "rgbtestsrc"]
    for i in range(n):
        out = folder / f"clip_{i + 1:02d}.mp4"
        cmd = [ffmpeg, "-f", "lavfi", "-i", f"{colors[i % len(colors)]}=d=2:s=640x360:r=25",
               "-pix_fmt", "yuv420p", "-y", str(out)]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0 or not out.exists():
            return False
    return True


def shoot(lang: str) -> None:
    i18n.set_language(lang)
    s = SAMPLE[lang]
    out = OUT / lang
    print(f"[{lang}]")

    win = MainWindow()
    MainWindow._instance = win
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    wait(400)
    win.nav.panel.expand()
    wait(900)

    # 1) 总览：首页
    show_tab(win, "merge")
    grab(win, out / "overview.png")

    # 2) 转场拼接：填 3 个文件夹 + 选转场
    t = show_tab(win, "concat")
    for row, folder in zip(t.rows, s["folders"]):
        row["line_edit"].setText(folder)
    t.transition.setCurrentIndex(18)   # 溶解 / Dissolve（_TRANSITIONS 第 19 项）
    t.td.setValue(0.6)
    grab(win, out / "concat.png")

    # 3) 字幕转场拼接：文件夹 + 配音文案
    t = show_tab(win, "subtitle_concat")
    for row, folder, line in zip(t.rows, s["folders"], s["narration"]):
        row["line_edit"].setText(folder)
        row["text_edit"].setPlainText(line)
    grab(win, out / "narrated_concat.png")

    # 4) 批量标题
    t = show_tab(win, "title")
    t.fixed_text.setText(s["title"])
    t.video_folder.setText(s["folders"][0])
    grab(win, out / "title.png")

    # 5) 全局设置对话框（用 show 而非 exec，避免阻塞）
    show_tab(win, "merge")
    dlg = SettingsDialog(win)
    dlg.show()
    wait(300)
    grab(win, out / "settings.png")
    dlg.close()
    wait(150)

    # 6) 真实跑一遍：格式转换 3 个测试视频，日志展开 + 完成提示
    if win.ffmpeg_path:
        work = Path(tempfile.mkdtemp(prefix="kkmix_shot_"))
        src = work / ("素材" if lang == "zh" else "clips")
        src.mkdir()
        if make_test_videos(win.ffmpeg_path, src):
            t = show_tab(win, "convert")
            t.video_folder.setText(str(src))
            t.output_folder.setText(str(work / ("输出" if lang == "zh" else "output")))
            t.target_format.setCurrentText("mov")
            win._set_log_mode("normal")
            worker = t.build_worker()
            if worker is not None:
                win.run_worker(worker, trigger_btn=t.start_btn)
                deadline = time.time() + 120
                while win.current_worker is not None and time.time() < deadline:
                    wait(50)
                wait(400)   # 让完成 InfoBar 画出来
                grab(win, out / "batch_done.png")
        shutil.rmtree(work, ignore_errors=True)
    else:
        print("  (未找到 ffmpeg，跳过 batch_done.png)")

    win.close()
    wait(100)


if __name__ == "__main__":
    for lang in ("zh", "en"):
        shoot(lang)
    print("done ->", OUT.relative_to(ROOT))
