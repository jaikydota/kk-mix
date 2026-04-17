"""转场拼接。对应 kk.py 中的 create_concat_tab / batch_concat_operation / _concat_with_transition。

UI 特点：
  - 文件夹列表可动态增删，前 5 行固定不可删
  - xfade + acrossfade 链式拼接
  - 输入先归一化到第一段视频的分辨率/帧率
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    DoubleSpinBox,
    FluentIcon,
    LineEdit,
    PushButton,
    ScrollArea,
    StrongBodyLabel,
)

from qt.core.app_settings import AppSettings
from qt.core.batch_worker import BatchControl, BatchWorker
from qt.core.ffmpeg_helper import probe_duration, probe_resolution_fps, probe_video_info
from qt.core.paths import VIDEO_EXTS, ensure_dir, list_media

from .base import BaseTab


# 显示名 → ffmpeg xfade transition 名
_TRANSITIONS: list[tuple[str, str]] = [
    ("淡入淡出", "fade"),
    ("淡入黑场", "fadeblack"),
    ("淡入白场", "fadewhite"),
    ("向左擦除", "wipeleft"),
    ("向右擦除", "wiperight"),
    ("向上擦除", "wipeup"),
    ("向下擦除", "wipedown"),
    ("向左滑动", "slideleft"),
    ("向右滑动", "slideright"),
    ("向上滑动", "slideup"),
    ("向下滑动", "slidedown"),
    ("向左平滑", "smoothleft"),
    ("向右平滑", "smoothright"),
    ("向上平滑", "smoothup"),
    ("向下平滑", "smoothdown"),
    ("圆形展开", "circleopen"),
    ("圆形收缩", "circleclose"),
    ("径向扫描", "radial"),
    ("溶解", "dissolve"),
    ("像素化", "pixelize"),
]

_MIN_FIXED_ROWS = 5


class ConcatWorker(BatchWorker):
    def __init__(self, ffmpeg_path, ctrl: BatchControl, settings: AppSettings,
                 folders: list[str], output: str,
                 transition_duration: float, transition_type: str):
        super().__init__(ffmpeg_path, ctrl, settings)
        self.folders = folders
        self.output = output
        self.td = transition_duration
        self.transition_type = transition_type

    def run_batch(self) -> tuple[bool, str]:
        ensure_dir(self.output)
        all_videos: list[list[str]] = []
        for folder in self.folders:
            vids = list_media(folder, VIDEO_EXTS)
            all_videos.append(vids)

        min_count = min((len(v) for v in all_videos), default=0)
        if min_count == 0:
            self.log("✗ 有文件夹中没有视频文件")
            return False, "无视频文件"

        bar = "=" * 60
        self.log(f"\n{bar}\n开始批量转场拼接   文件夹数: {len(self.folders)}   每组视频数: {min_count}\n{bar}")

        temp_dir = os.path.join(self.output, "_concat_temp_resize")
        ensure_dir(temp_dir)

        success = 0
        try:
            for i in range(min_count):
                if self.ctrl.wait_if_paused():
                    self.log("已手动停止"); break

                group = [os.path.join(self.folders[j], all_videos[j][i]) for j in range(len(self.folders))]
                out_name = f"concat_{i+1:03d}.mp4"
                out_path = os.path.join(self.output, out_name)

                self.log(f"\n[{i+1}/{min_count}] 拼接 {len(group)} 个视频")
                normalized = self._normalize_group(group, temp_dir, i)
                if self._concat_with_transition(normalized, out_path):
                    success += 1
                    size_mb = os.path.getsize(out_path) / 1024 / 1024
                    self.log(f"  ✓ 成功: {out_name} ({size_mb:.1f} MB)")
                else:
                    self.log(f"  ✗ 失败")

                self.set_progress((i + 1) / min_count * 100)
                self.set_status(f"转场拼接中 {i+1}/{min_count}")
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
                self.log("  临时文件夹已清理")

        self.log(f"\n{bar}\n完成！成功生成 {success}/{min_count} 个视频\n{bar}")
        return success > 0, f"成功 {success}/{min_count}"

    # ─── 归一化 ───
    def _normalize_group(self, group: list[str], temp_dir: str, group_idx: int) -> list[str]:
        ref_w, ref_h, ref_fps = probe_resolution_fps(self.ffmpeg_path, group[0])
        self.log(f"    基准分辨率: {ref_w}x{ref_h}，帧率: {ref_fps}fps")

        any_needs_norm = False
        for k in range(1, len(group)):
            _w, _h, _fps = probe_resolution_fps(self.ffmpeg_path, group[k])
            if (_w != ref_w or _h != ref_h) or (round(_fps, 3) != round(ref_fps, 3)):
                any_needs_norm = True
                break

        preset = self.preset()
        normalized: list[str] = []
        for k, src in enumerate(group):
            if k == 0:
                _, _, _, src_has_audio = probe_video_info(self.ffmpeg_path, src)
                w, h, src_fps = ref_w, ref_h, ref_fps
            else:
                w, h, src_fps, src_has_audio = probe_video_info(self.ffmpeg_path, src)

            need_resize = (w != ref_w or h != ref_h)
            need_fps = (round(src_fps, 3) != round(ref_fps, 3))
            force_reencode = (k == 0 and self.td > 0 and any_needs_norm)
            need_audio_fix = not src_has_audio

            if not need_resize and not need_fps and not force_reencode and not need_audio_fix:
                normalized.append(src)
                continue

            reasons = []
            if need_resize:
                reasons.append(f"分辨率 {w}x{h}→{ref_w}x{ref_h}")
            if need_fps:
                reasons.append(f"帧率 {src_fps}→{ref_fps}fps")
            if force_reencode and not need_resize and not need_fps:
                reasons.append("timebase 对齐（xfade）")
            if need_audio_fix:
                reasons.append("补充静音音频轨")
            self.log(f"    需要归一化 [{k+1}]: {', '.join(reasons)}")

            tmp_name = f"tmp_{group_idx:03d}_{k:02d}_{os.path.basename(src)}"
            tmp_path = os.path.join(temp_dir, tmp_name)
            vf = (f"scale={ref_w}:{ref_h}:force_original_aspect_ratio=increase,"
                  f"crop={ref_w}:{ref_h},setsar=1") if need_resize else "setsar=1"

            if need_audio_fix:
                cmd = [
                    self.ffmpeg_path, "-i", src,
                    "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                    "-vf", vf,
                    "-r", str(ref_fps),
                    "-c:v", "libx264", "-preset", preset, *self.quality_args(),
                    "-c:a", "aac", "-shortest",
                    "-threads", "0", "-y", tmp_path,
                ]
            else:
                cmd = [
                    self.ffmpeg_path, "-i", src,
                    "-vf", vf,
                    "-r", str(ref_fps),
                    "-c:v", "libx264", "-preset", preset, *self.quality_args(),
                    "-c:a", "aac", "-threads", "0", "-y", tmp_path,
                ]
            r = self.run_cmd(cmd, timeout=600)
            if r.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                normalized.append(tmp_path)
            else:
                self.log(f"    ✗ 归一化失败，使用原始文件: {os.path.basename(src)}")
                normalized.append(src)
        return normalized

    # ─── 核心拼接 ───
    def _concat_with_transition(self, videos: list[str], out_path: str) -> bool:
        try:
            if len(videos) == 1:
                shutil.copy2(videos[0], out_path)
                return True

            n = len(videos)
            preset = self.preset()
            inputs: list[str] = []
            for v in videos:
                inputs += ["-i", v]

            if self.td <= 0:
                setsar = ";".join(f"[{i}:v]setsar=1[sv{i}]" for i in range(n))
                streams = "".join(f"[sv{i}][{i}:a]" for i in range(n))
                filter_complex = f"{setsar};{streams}concat=n={n}:v=1:a=1[vout][aout]"
            else:
                durations = []
                for v in videos:
                    d = probe_duration(self.ffmpeg_path, v)
                    if d <= 0:
                        self.log(f"    ✗ 无法获取时长: {os.path.basename(v)}")
                        return False
                    durations.append(d)
                    self.log(f"    时长: {os.path.basename(v)} = {d:.2f}s")

                td = self.td
                min_dur = min(durations)
                if td >= min_dur:
                    td = round(min_dur * 0.4, 3)
                    self.log(f"    ⚠ 转场时长超过最短片段，自动调整为 {td:.2f}s")

                parts = [f"[{i}:v]setsar=1[sv{i}]" for i in range(n)]
                prev_v = "[sv0]"
                prev_a = "[0:a]"
                offset = 0.0
                for i in range(1, n):
                    offset += durations[i - 1] - td
                    is_last = (i == n - 1)
                    out_v = "[vout]" if is_last else f"[v{i}]"
                    out_a = "[aout]" if is_last else f"[a{i}]"
                    parts.append(
                        f"{prev_v}[sv{i}]xfade=transition={self.transition_type}"
                        f":duration={td:.3f}:offset={offset:.3f}{out_v}"
                    )
                    parts.append(f"{prev_a}[{i}:a]acrossfade=d={td:.3f}{out_a}")
                    prev_v, prev_a = out_v, out_a
                filter_complex = ";".join(parts)

            cmd = [self.ffmpeg_path, *inputs,
                   "-filter_complex", filter_complex,
                   "-map", "[vout]", "-map", "[aout]",
                   "-c:v", "libx264", "-preset", preset, *self.quality_args(),
                   "-c:a", "aac", "-threads", "0", "-y", out_path]

            r = self.run_cmd(cmd, timeout=900)
            if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return True
            if os.path.exists(out_path) and os.path.getsize(out_path) == 0:
                os.remove(out_path)
            tail = (r.stderr or "")[-400:]
            if tail:
                self.log(f"    stderr: {tail.strip()}")
            return False
        except Exception as e:
            self.log(f"  ✗ 异常: {e}")
            return False


class ConcatTab(BaseTab):
    NAME = "concat"
    TITLE = "转场拼接"
    ICON = FluentIcon.LINK

    def build_form(self):
        # 文件夹列表（可动态增减）
        self.form_layout.addWidget(StrongBodyLabel("视频文件夹（按顺序拼接）", self), 0, 0, 1, 3)

        self.rows: list[dict] = []
        list_holder = QFrame(self)
        list_holder.setObjectName("concatListHolder")
        list_v = QVBoxLayout(list_holder)
        list_v.setContentsMargins(0, 0, 0, 0)
        list_v.setSpacing(6)

        self.rows_container = QWidget(list_holder)
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(6)

        scroll = ScrollArea(list_holder)
        scroll.setWidget(self.rows_container)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(210)
        scroll.setMaximumHeight(260)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        list_v.addWidget(scroll)

        action_bar = QHBoxLayout()
        action_bar.setSpacing(10)
        add_btn = PushButton("＋ 添加文件夹", self, FluentIcon.ADD)
        add_btn.clicked.connect(self._add_row)
        action_bar.addWidget(add_btn)
        hint = BodyLabel(f"可无限添加，至少保留 {_MIN_FIXED_ROWS} 个", self)
        hint.setStyleSheet("color: #8a8a8a;")
        action_bar.addWidget(hint)
        action_bar.addStretch(1)
        list_v.addLayout(action_bar)

        self.form_layout.addWidget(list_holder, 1, 0, 1, 3)

        # 初始 5 行
        for _ in range(_MIN_FIXED_ROWS):
            self._add_row()

        # 输出文件夹
        self.output = LineEdit(self)
        self.output.setText(
            os.path.join(os.path.expanduser("~"), "Desktop", "视频输出")
        )
        self._add_folder_row(2, "输出文件夹", self.output, is_output=True)

        # 转场时长
        self.td = DoubleSpinBox(self)
        self.td.setRange(0.0, 10.0)
        self.td.setValue(0.5)
        self.td.setSingleStep(0.1)
        self.td.setDecimals(2)
        self.td.setSuffix(" 秒")
        self._add_param_row(3, "转场时长", self.td, hint="0 = 无转场，直接拼接")

        # 转场类型
        self.transition = ComboBox(self)
        for label, _ in _TRANSITIONS:
            self.transition.addItem(label)
        self.transition.setCurrentIndex(0)
        self._add_param_row(4, "转场类型", self.transition)

    # ─── 动态行 ───
    def _add_row(self):
        idx = len(self.rows)
        row_widget = QFrame(self.rows_container)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        label = BodyLabel(f"文件夹 {idx + 1}", row_widget)
        label.setMinimumWidth(70)

        line_edit = LineEdit(row_widget)
        line_edit.setPlaceholderText("选择要拼接的视频所在文件夹")

        browse_btn = PushButton("浏览", row_widget, FluentIcon.FOLDER)
        browse_btn.clicked.connect(lambda _=False, le=line_edit: self._browse_folder(le, False))

        remove_btn = PushButton("✕", row_widget)
        remove_btn.setFixedWidth(36)
        remove_btn.clicked.connect(lambda _=False, w=row_widget: self._remove_row(w))

        row_layout.addWidget(label)
        row_layout.addWidget(line_edit, 1)
        row_layout.addWidget(browse_btn)
        row_layout.addWidget(remove_btn)

        self.rows_layout.addWidget(row_widget)
        self.rows.append({
            "widget": row_widget, "label": label, "line_edit": line_edit, "remove_btn": remove_btn,
        })
        self._refresh_rows()

    def _remove_row(self, widget: QFrame):
        idx = next((i for i, r in enumerate(self.rows) if r["widget"] is widget), -1)
        if idx < 0:
            return
        if idx < _MIN_FIXED_ROWS:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.warning(
                "不能移除",
                f"前 {_MIN_FIXED_ROWS} 个文件夹不能删除",
                parent=self.main, position=InfoBarPosition.TOP,
            )
            return
        self.rows_layout.removeWidget(widget)
        widget.setParent(None)
        widget.deleteLater()
        self.rows.pop(idx)
        self._refresh_rows()

    def _refresh_rows(self):
        for i, row in enumerate(self.rows):
            row["label"].setText(f"文件夹 {i + 1}")
            row["remove_btn"].setVisible(i >= _MIN_FIXED_ROWS)

    # ─── 构建 worker ───
    def build_worker(self):
        folders = [r["line_edit"].text().strip() for r in self.rows]
        folders = [f for f in folders if f]
        if not folders:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.warning("参数不完整", "至少填写一个视频文件夹",
                            parent=self.main, position=InfoBarPosition.TOP)
            return None

        out = self.output.text().strip()
        if not self._require_folder(out, "输出文件夹"):
            return None
        for f in folders:
            if not self._require_dir_exists(f, f"文件夹「{f}」"):
                return None

        transition_type = _TRANSITIONS[self.transition.currentIndex()][1]
        return ConcatWorker(
            self.main.ffmpeg_path, self.main.ctrl, self.main.settings,
            folders, out, float(self.td.value()), transition_type,
        )
