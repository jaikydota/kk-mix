"""批量填充音乐。对应 kk.py 中的 batch_music_operation / _music_replace_ffmpeg。"""
from __future__ import annotations

from qt.core.i18n import tr

import os
import shutil
from pathlib import Path

from qfluentwidgets import CheckBox, FluentIcon, LineEdit

from qt.core.app_settings import AppSettings
from qt.core.batch_worker import BatchControl, BatchWorker
from qt.core.paths import AUDIO_EXTS, VIDEO_EXTS, ensure_dir, list_media

from .base import BaseTab


class MusicWorker(BatchWorker):
    def __init__(self, ffmpeg_path, ctrl: BatchControl, settings: AppSettings,
                 video_folder: str, audio_folder: str, output_folder: str,
                 keep_original: bool):
        super().__init__(ffmpeg_path, ctrl, settings)
        self.video_folder = video_folder
        self.audio_folder = audio_folder
        self.output_folder = output_folder
        self.output_dir = output_folder
        self.keep_original = keep_original

    def run_batch(self) -> tuple[bool, str]:
        ensure_dir(self.output_folder)
        video_files = list_media(self.video_folder, VIDEO_EXTS)
        if not video_files:
            self.log(tr("✗ 视频文件夹中没有视频"))
            return False, tr("无视频文件")

        source_files = list_media(self.audio_folder, VIDEO_EXTS | AUDIO_EXTS)
        if not source_files:
            self.log(tr("✗ 音乐文件夹中没有音频/视频"))
            return False, tr("无音频文件")

        bar = "=" * 60
        self.log(tr('\n{0}\n开始填充音乐   视频数: {1}   音乐源: {2}\n{3}').format(bar, len(video_files), len(source_files), bar))

        temp_dir = os.path.join(self.output_folder, "_temp")
        ensure_dir(temp_dir)

        music_files: list[str] = []
        try:
            # 从视频源提取音频（若为视频），其余直接使用
            for idx, name in enumerate(source_files, 1):
                if self.ctrl.wait_if_paused():
                    self.log(tr("已手动停止")); break
                src = os.path.join(self.audio_folder, name)
                ext = Path(name).suffix.lower()
                if ext in AUDIO_EXTS:
                    music_files.append(src)
                    self.log(tr("  音频文件直接使用: {0}").format(name))
                elif ext in VIDEO_EXTS:
                    tmp = os.path.join(temp_dir, f"extract_{idx:03d}.aac")
                    self.log(tr("  从视频提取音频: {0}").format(name))
                    if self._extract_audio_only(src, tmp):
                        music_files.append(tmp)
                    else:
                        self.log(tr("    ✗ 提取失败，跳过: {0}").format(name))

            if not music_files:
                self.log(tr("✗ 未能获取任何可用音乐文件"))
                return False, tr("无可用音乐")

            while len(music_files) < len(video_files):
                music_files.append(music_files[-1])

            mode_label = tr("混合模式（保留原声）") if self.keep_original else tr("替换模式（移除原声）")
            self.log(tr('\n音频模式: {0}\n开始合并...').format(mode_label))

            success = 0
            total = len(video_files)
            for idx, (vf, af) in enumerate(zip(video_files, music_files), 1):
                if self.ctrl.wait_if_paused():
                    self.log(tr("已手动停止")); break

                v_path = os.path.join(self.video_folder, vf)
                out_name = f"music_{idx:03d}_{Path(vf).stem}.mp4"
                out_path = os.path.join(self.output_folder, out_name)

                self.log(f"[{idx}/{total}] {vf} + {os.path.basename(af)}")
                if self._replace_audio(v_path, af, out_path):
                    success += 1
                    size_mb = os.path.getsize(out_path) / 1024 / 1024
                    self.log(tr("  ✓ 成功: {0} ({1:.1f} MB)").format(out_name, size_mb))
                else:
                    self.log(tr("  ✗ 失败: {0}").format(vf))

                self.set_progress(idx / total * 100)
                self.set_status(tr("填充音乐中 {0}/{1}").format(idx, total))

            self.log(tr('\n{0}\n完成！成功处理 {1}/{2} 个视频\n{3}').format(bar, success, total, bar))
            return success > 0, tr("成功 {0}/{1}").format(success, total)

        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
                self.log(tr("已清理临时文件"))

    def _extract_audio_only(self, in_path: str, out_path: str) -> bool:
        try:
            cmd = [self.ffmpeg_path, "-i", in_path, "-vn", "-c:a", "aac", "-y", out_path]
            r = self.run_cmd(cmd, timeout=300)
            return r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0
        except Exception:
            return False

    def _replace_audio(self, v_path: str, a_path: str, out_path: str) -> bool:
        try:
            if self.keep_original:
                cmd = [
                    self.ffmpeg_path,
                    "-i", v_path, "-i", a_path,
                    "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=shortest[aout]",
                    "-map", "0:v", "-map", "[aout]",
                    "-c:v", "copy", "-c:a", "aac",
                    "-shortest", "-y", out_path,
                ]
            else:
                cmd = [
                    self.ffmpeg_path,
                    "-i", v_path, "-i", a_path,
                    "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac",
                    "-shortest", "-y", out_path,
                ]
            r = self.run_cmd(cmd, timeout=600)
            if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return True
            tail = (r.stderr or "")[-400:]
            if tail:
                self.log(f"    stderr: {tail.strip()}")
            return False
        except Exception as e:
            self.log(tr("  ✗ 异常: {0}").format(e))
            return False


class MusicTab(BaseTab):
    NAME = "music"
    TITLE = "批量填充音乐"
    ICON = FluentIcon.MUSIC

    def build_form(self):
        self.video_folder = LineEdit(self)
        self._add_folder_row(0, tr("视频文件夹"), self.video_folder)

        self.audio_folder = LineEdit(self)
        self._add_folder_row(1, tr("音乐文件夹"), self.audio_folder,
                             placeholder=tr("可放 音频文件 或 视频文件（自动提取音频）"))

        self.output_folder = LineEdit(self)
        self.output_folder.setText(
            os.path.join(os.path.expanduser("~"), "Desktop", tr("视频输出"))
        )
        self._add_folder_row(2, tr("输出文件夹"), self.output_folder, is_output=True)

        self.keep_original = CheckBox(tr("保留原视频音频（与新音频混合）"), self)
        self._add_param_row(3, tr("音频模式"), self.keep_original,
                            hint=tr("不勾选则替换原声"))

    def build_worker(self):
        vf = self.video_folder.text().strip()
        af = self.audio_folder.text().strip()
        out = self.output_folder.text().strip()
        keep = self.keep_original.isChecked()

        if not self._require_folder(vf, tr("视频文件夹")) \
           or not self._require_folder(af, tr("音乐文件夹")) \
           or not self._require_folder(out, tr("输出文件夹")) \
           or not self._require_dir_exists(vf, tr("视频文件夹")) \
           or not self._require_dir_exists(af, tr("音乐文件夹")):
            return None

        return MusicWorker(
            self.main.ffmpeg_path, self.main.ctrl, self.main.settings,
            vf, af, out, keep,
        )
