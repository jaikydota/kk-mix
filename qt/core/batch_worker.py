"""批处理线程基类与控制器。

BatchWorker 替代 kk.py 中的 `threading.Thread + root.update()` 模型：
 - 子类实现 run_batch() -> (success, summary)
 - 通过 self.log / self.set_progress / self.set_status 向主线程汇报
 - 使用 self.ctrl.wait_if_paused() 处理暂停 / 停止
"""
from __future__ import annotations

from qt.core.i18n import tr

import subprocess

from PySide6.QtCore import QThread, Signal

from .app_settings import AppSettings
from .ffmpeg_helper import encode_preset, quality_args
from .paths import make_startupinfo


class BatchControl:
    """跨线程共享的暂停/停止标志。"""

    def __init__(self) -> None:
        self.paused = False
        self.stopped = False

    def reset(self) -> None:
        self.paused = False
        self.stopped = False

    def wait_if_paused(self) -> bool:
        """阻塞直到 resume 或 stop；返回 True 表示应终止循环。"""
        while self.paused and not self.stopped:
            QThread.msleep(200)
        return self.stopped


class BatchWorker(QThread):
    """所有批处理线程的基类。"""

    log_signal = Signal(str)
    progress_signal = Signal(float)      # 0 ~ 100
    status_signal = Signal(str)
    finished_signal = Signal(bool, str)  # (success, summary)

    def __init__(self, ffmpeg_path: str, ctrl: BatchControl, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.ffmpeg_path = ffmpeg_path
        self.ctrl = ctrl
        self.output_dir: str = ""
        # 拷贝快照，避免跨线程读写
        self.settings = AppSettings(**{**settings.__dict__})

    # ─── 子类覆写 ───
    def run_batch(self) -> tuple[bool, str]:
        raise NotImplementedError

    # ─── 线程入口 ───
    def run(self) -> None:  # noqa: D401  (Qt 约定)
        try:
            ok, summary = self.run_batch()
            self.finished_signal.emit(ok, summary)
        except Exception as e:
            self.log(tr("✗ 批处理异常: {0}").format(e))
            self.finished_signal.emit(False, str(e))

    # ─── 提供给子类的便捷方法 ───
    def log(self, msg: str) -> None:
        self.log_signal.emit(msg)

    def set_progress(self, v: float) -> None:
        self.progress_signal.emit(v)

    def set_status(self, msg: str) -> None:
        self.status_signal.emit(msg)

    def preset(self) -> str:
        return encode_preset(self.settings.speed_priority)

    def quality_args(self) -> list[str]:
        return quality_args(self.settings.compress_video, self.settings.bitrate)

    def run_cmd(self, cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
        """统一执行子进程命令（隐藏黑窗 + 屏蔽编码异常）。"""
        if self.settings.verbose_log:
            self.log(f"[CMD] {' '.join(str(x) for x in cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            startupinfo=make_startupinfo(),
            encoding="utf-8",
            errors="ignore",
        )
        if self.settings.verbose_log:
            if result.stdout and result.stdout.strip():
                self.log(f"[STDOUT] {result.stdout.strip()}")
            if result.stderr and result.stderr.strip():
                self.log(f"[STDERR] {result.stderr.strip()}")
            if result.returncode != 0:
                self.log(f"[EXIT] returncode={result.returncode}")
        return result
