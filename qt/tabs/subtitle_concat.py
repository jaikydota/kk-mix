"""字幕转场拼接。

与「转场拼接」的区别：
  - 每个视频文件夹配多行文字，文字经 Index-TTS 合成为配音（音色由固定参考音克隆）；
    第 i 组视频用第 i 行，行数不足时循环使用
  - 每个片段的时长与其配音对齐：视频短于语音则循环补足，长于语音则裁剪
  - 片段原声被丢弃，音轨完全替换为 TTS 配音
  - 视频用 xfade 链式转场；配音按顺序直连、不做淡入淡出——每个片段（末段除外）
    视频尾部额外循环 td 秒专门用于转场重叠，语音互不侵占
"""
from __future__ import annotations

from qt.core.i18n import tr

import os
import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    DoubleSpinBox,
    FluentIcon,
    LineEdit,
    PlainTextEdit,
    PushButton,
    ScrollArea,
    StrongBodyLabel,
)

from qt.core.app_settings import AppSettings
from qt.core.batch_worker import BatchControl, BatchWorker
from qt.core.ffmpeg_helper import probe_duration, probe_resolution_fps
from qt.core.paths import VIDEO_EXTS, ensure_dir, list_media
from qt.core.tts_client import TTSClient, TTSError

from .base import BaseTab
from .concat import _TRANSITIONS

_MIN_FIXED_ROWS = 5


class SubtitleConcatWorker(BatchWorker):
    def __init__(self, ffmpeg_path, ctrl: BatchControl, settings: AppSettings,
                 folders: list[str], texts: list[list[str]], output: str,
                 transition_duration: float, transition_type: str):
        super().__init__(ffmpeg_path, ctrl, settings)
        self.folders = folders
        self.texts = texts
        self.output = output
        self.output_dir = output
        self.td = transition_duration
        self.transition_type = transition_type

    def run_batch(self) -> tuple[bool, str]:
        ensure_dir(self.output)
        all_videos: list[list[str]] = []
        for folder in self.folders:
            all_videos.append(list_media(folder, VIDEO_EXTS))

        min_count = min((len(v) for v in all_videos), default=0)
        if min_count == 0:
            self.log(tr("✗ 有文件夹中没有视频文件"))
            return False, tr("无视频文件")

        n = len(self.folders)
        bar = "=" * 60
        self.log(tr('\n{0}\n开始批量字幕转场拼接   文件夹数: {1}   每组视频数: {2}\n{3}').format(bar, n, min_count, bar))

        temp_dir = os.path.join(self.output, "_subconcat_temp")
        ensure_dir(temp_dir)

        # 每个文件夹实际用到的文字行数：行数多于视频数时多余的行用不到
        used_counts = [min(len(lines), min_count) for lines in self.texts]
        total_tts = sum(used_counts)
        total_steps = total_tts + min_count
        success = 0
        try:
            # 1) 参考音 + 逐文件夹逐行合成配音（整批共用，同一 seed 保证音色一致）
            tts = TTSClient(self.settings.tts_base_url, self.settings.tts_api_key)
            self.set_status(tr("上传参考音…"))
            self.log(tts.ensure_reference())

            speech_files: list[list[str]] = []
            speech_durs: list[list[float]] = []
            done = 0
            for j, lines in enumerate(self.texts):
                used = used_counts[j]
                if len(lines) > used:
                    self.log(tr("文件夹 {0}: 文字 {1} 行 > 视频 {2} 个，仅前 {3} 行会用到").format(j + 1, len(lines), min_count, used))
                elif used < min_count:
                    self.log(tr("文件夹 {0}: 文字 {1} 行 < 视频 {2} 个，循环使用").format(j + 1, used, min_count))
                folder_files: list[str] = []
                folder_durs: list[float] = []
                for k in range(used):
                    if self.ctrl.wait_if_paused():
                        self.log(tr("已手动停止"))
                        return False, tr("已停止")
                    done += 1
                    self.set_status(tr("合成语音 {0}/{1}").format(done, total_tts))
                    text = lines[k]
                    self.log(tr("[TTS {0}/{1}] 文件夹{2} 第{3}行: {4}{5}").format(done, total_tts, j + 1, k + 1, text[:40], '…' if len(text) > 40 else ''))
                    wav = os.path.join(temp_dir, f"speech_{j:02d}_{k:03d}.wav")
                    tts.synthesize(text, wav)
                    d = probe_duration(self.ffmpeg_path, wav)
                    if d <= 0:
                        self.log(tr("✗ 无法获取语音时长"))
                        return False, tr("TTS 失败")
                    folder_files.append(wav)
                    folder_durs.append(d)
                    self.log(tr("  ✓ 语音时长 {0:.2f}s").format(d))
                    self.set_progress(done / total_steps * 100)
                speech_files.append(folder_files)
                speech_durs.append(folder_durs)

            # 转场时长安全钳制（对齐/偏移都依赖它，需在生成片段前定死）
            if self.td > 0 and n > 1:
                min_speech = min(d for durs in speech_durs for d in durs)
                if self.td >= min_speech:
                    self.td = round(min_speech * 0.4, 3)
                    self.log(tr("⚠ 转场时长超过最短语音，自动调整为 {0:.2f}s").format(self.td))
                self.log(tr("转场 {0:.2f}s：各片段尾部延长 {1:.2f}s 画面用于转场重叠，配音顺序直连、不做淡入淡出").format(self.td, self.td))

            # 2) 逐组：片段对齐配音时长（末段外加转场余量）→ 视频转场 + 配音直连
            for i in range(min_count):
                if self.ctrl.wait_if_paused():
                    self.log(tr("已手动停止"))
                    break

                group = [os.path.join(self.folders[j], all_videos[j][i]) for j in range(n)]
                out_name = f"sub_concat_{i+1:03d}.mp4"
                out_path = os.path.join(self.output, out_name)

                self.log(tr('\n[{0}/{1}] 生成 {2} 个配音片段并拼接').format(i + 1, min_count, len(group)))
                ref_w, ref_h, ref_fps = probe_resolution_fps(self.ffmpeg_path, group[0])
                self.log(tr("    基准分辨率: {0}x{1}，帧率: {2}fps").format(ref_w, ref_h, ref_fps))

                segments: list[str] = []
                group_speeches: list[str] = []
                ok_all = True
                for j, src in enumerate(group):
                    k = i % used_counts[j]
                    group_speeches.append(speech_files[j][k])
                    pad = self.td if (self.td > 0 and j < n - 1) else 0.0
                    seg = os.path.join(temp_dir, f"seg_{i:03d}_{j:02d}.mp4")
                    self.log(tr("    片段 {0} ← 第 {1} 行文字（语音 {2:.2f}s）").format(j + 1, k + 1, speech_durs[j][k]))
                    if not self._build_segment(src, speech_durs[j][k] + pad,
                                               ref_w, ref_h, ref_fps, seg):
                        self.log(tr("    ✗ 片段生成失败: {0}").format(os.path.basename(src)))
                        ok_all = False
                        break
                    segments.append(seg)

                if ok_all and self._concat_segments(segments, group_speeches, out_path):
                    success += 1
                    size_mb = os.path.getsize(out_path) / 1024 / 1024
                    self.log(tr("  ✓ 成功: {0} ({1:.1f} MB)").format(out_name, size_mb))
                else:
                    self.log(tr("  ✗ 失败"))

                for seg in segments:
                    try:
                        os.remove(seg)
                    except OSError:
                        pass

                self.set_progress((n + i + 1) / total_steps * 100)
                self.set_status(tr("字幕转场拼接中 {0}/{1}").format(i + 1, min_count))
        except TTSError as e:
            self.log(f"✗ {e}")
            return False, tr("TTS 失败")
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
                self.log(tr("  临时文件夹已清理"))

        self.log(tr('\n{0}\n完成！成功生成 {1}/{2} 个视频\n{3}').format(bar, success, min_count, bar))
        return success > 0, tr("成功 {0}/{1}").format(success, min_count)

    # ─── 片段与配音对齐（纯视频，无音轨） ───
    def _build_segment(self, video: str, dur: float,
                       w: int, h: int, fps: float, out_path: str) -> bool:
        """把 video 循环/裁剪到 dur 秒并归一化到 w×h/fps，丢弃原音轨。"""
        src_dur = probe_duration(self.ffmpeg_path, video)
        if src_dur <= 0:
            self.log(tr("    ✗ 无法获取时长: {0}").format(os.path.basename(video)))
            return False
        if src_dur < dur:
            self.log(tr("    片段 {0:.2f}s < 目标 {1:.2f}s，循环补足").format(src_dur, dur))
        else:
            self.log(tr("    片段 {0:.2f}s ≥ 目标 {1:.2f}s，裁剪对齐").format(src_dur, dur))

        vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
              f"crop={w}:{h},setsar=1")
        cmd = [
            self.ffmpeg_path,
            "-stream_loop", "-1", "-i", video,
            "-t", f"{dur:.3f}",
            "-vf", vf,
            "-r", str(fps),
            "-an",
            "-c:v", "libx264", "-preset", self.preset(), *self.quality_args(),
            "-pix_fmt", "yuv420p",
            "-threads", "0", "-y", out_path,
        ]
        r = self.run_cmd(cmd, timeout=900)
        if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return True
        tail = (r.stderr or "")[-300:]
        if tail:
            self.log(f"    stderr: {tail.strip()}")
        return False

    # ─── 拼接：视频 xfade 转场链 + 配音顺序直连 ───
    def _concat_segments(self, videos: list[str], speeches: list[str], out_path: str) -> bool:
        """视频走转场链；音频为各段配音首尾相接（无淡入淡出）。

        片段 j（末段除外）比其配音长 td 秒，xfade 恰好吃掉这段余量，
        因此视频总长 = 配音总长，语音与画面天然对齐。
        """
        try:
            n = len(videos)
            preset = self.preset()
            inputs: list[str] = []
            for v in videos:
                inputs += ["-i", v]
            for s in speeches:
                inputs += ["-i", s]

            afmt = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"
            aparts = [f"[{n+i}:a]{afmt}[sa{i}]" for i in range(n)]
            astreams = "".join(f"[sa{i}]" for i in range(n))
            aconcat = f"{astreams}concat=n={n}:v=0:a=1[aout]"

            if n == 1 or self.td <= 0:
                setsar = ";".join(f"[{i}:v]setsar=1[sv{i}]" for i in range(n))
                vstreams = "".join(f"[sv{i}]" for i in range(n))
                vconcat = f"{vstreams}concat=n={n}:v=1:a=0[vout]"
                filter_complex = ";".join([setsar, *aparts, vconcat, aconcat])
            else:
                durations: list[float] = []
                for v in videos:
                    d = probe_duration(self.ffmpeg_path, v)
                    if d <= 0:
                        self.log(tr("    ✗ 无法获取时长: {0}").format(os.path.basename(v)))
                        return False
                    durations.append(d)

                parts = [f"[{i}:v]setsar=1[sv{i}]" for i in range(n)]
                prev_v = "[sv0]"
                offset = 0.0
                for i in range(1, n):
                    offset += durations[i - 1] - self.td
                    out_v = "[vout]" if i == n - 1 else f"[v{i}]"
                    parts.append(
                        f"{prev_v}[sv{i}]xfade=transition={self.transition_type}"
                        f":duration={self.td:.3f}:offset={offset:.3f}{out_v}"
                    )
                    prev_v = out_v
                filter_complex = ";".join([*parts, *aparts, aconcat])

            cmd = [self.ffmpeg_path, *inputs,
                   "-filter_complex", filter_complex,
                   "-map", "[vout]", "-map", "[aout]",
                   "-c:v", "libx264", "-preset", preset, *self.quality_args(),
                   "-c:a", "aac", "-shortest",
                   "-threads", "0", "-y", out_path]

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
            self.log(tr("  ✗ 异常: {0}").format(e))
            return False


class SubtitleConcatTab(BaseTab):
    NAME = "subtitle_concat"
    TITLE = "字幕转场拼接"
    ICON = FluentIcon.MICROPHONE

    def build_form(self):
        self.form_layout.addWidget(
            StrongBodyLabel(tr("视频文件夹（按顺序拼接，每个文件夹配一段配音文字）"), self), 0, 0, 1, 3)

        self.rows: list[dict] = []
        list_holder = QFrame(self)
        list_holder.setObjectName("subConcatListHolder")
        list_v = QVBoxLayout(list_holder)
        list_v.setContentsMargins(0, 0, 0, 0)
        list_v.setSpacing(6)

        self.rows_container = QWidget(list_holder)
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(10)

        scroll = ScrollArea(list_holder)
        scroll.setWidget(self.rows_container)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(280)
        scroll.setMaximumHeight(400)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        list_v.addWidget(scroll)

        action_bar = QHBoxLayout()
        action_bar.setSpacing(10)
        add_btn = PushButton(tr("＋ 添加文件夹"), self, FluentIcon.ADD)
        add_btn.clicked.connect(self._add_row)
        action_bar.addWidget(add_btn)
        hint = BodyLabel(tr("可无限添加，至少保留 {0} 个；留空的文件夹行自动跳过").format(_MIN_FIXED_ROWS), self)
        hint.setStyleSheet("color: #8a8a8a;")
        action_bar.addWidget(hint)
        action_bar.addStretch(1)
        list_v.addLayout(action_bar)

        self.form_layout.addWidget(list_holder, 1, 0, 1, 3)

        for _ in range(_MIN_FIXED_ROWS):
            self._add_row()

        # 输出文件夹
        self.output = LineEdit(self)
        self.output.setText(
            os.path.join(os.path.expanduser("~"), "Desktop", tr("视频输出"))
        )
        self._add_folder_row(2, tr("输出文件夹"), self.output, is_output=True)

        # 转场时长
        self.td = DoubleSpinBox(self)
        self.td.setRange(0.0, 10.0)
        self.td.setValue(0.5)
        self.td.setSingleStep(0.1)
        self.td.setDecimals(2)
        self.td.setSuffix(tr(" 秒"))
        self._add_param_row(3, tr("转场时长"), self.td, hint=tr("0 = 无转场，直接拼接"))

        # 转场类型
        self.transition = ComboBox(self)
        for label, _ in _TRANSITIONS:
            self.transition.addItem(tr(label))
        self.transition.setCurrentIndex(0)
        self._add_param_row(4, tr("转场类型"), self.transition)

    # ─── 动态行 ───
    def _add_row(self):
        idx = len(self.rows)
        row_widget = QFrame(self.rows_container)
        row_v = QVBoxLayout(row_widget)
        row_v.setContentsMargins(0, 0, 0, 0)
        row_v.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(8)
        label = BodyLabel(tr("文件夹 {0}").format(idx + 1), row_widget)
        label.setMinimumWidth(70)
        line_edit = LineEdit(row_widget)
        line_edit.setPlaceholderText(tr("选择要拼接的视频所在文件夹"))
        browse_btn = PushButton(tr("浏览"), row_widget, FluentIcon.FOLDER)
        browse_btn.clicked.connect(lambda _=False, le=line_edit: self._browse_folder(le, False))
        remove_btn = PushButton("✕", row_widget)
        remove_btn.setFixedWidth(36)
        remove_btn.clicked.connect(lambda _=False, w=row_widget: self._remove_row(w))
        top.addWidget(label)
        top.addWidget(line_edit, 1)
        top.addWidget(browse_btn)
        top.addWidget(remove_btn)
        row_v.addLayout(top)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        text_label = BodyLabel(tr("配音文字"), row_widget)
        text_label.setMinimumWidth(70)
        text_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        text_edit = PlainTextEdit(row_widget)
        text_edit.setPlaceholderText(
            tr("每行文字对应该文件夹的一个视频（TTS 转语音）；行数不足时循环使用"))
        text_edit.setFixedHeight(74)
        bottom.addWidget(text_label)
        bottom.addWidget(text_edit, 1)
        row_v.addLayout(bottom)

        self.rows_layout.addWidget(row_widget)
        self.rows.append({
            "widget": row_widget, "label": label,
            "line_edit": line_edit, "text_edit": text_edit, "remove_btn": remove_btn,
        })
        self._refresh_rows()

    def _remove_row(self, widget: QFrame):
        idx = next((i for i, r in enumerate(self.rows) if r["widget"] is widget), -1)
        if idx < 0:
            return
        if idx < _MIN_FIXED_ROWS:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.warning(
                tr("不能移除"),
                tr("前 {0} 个文件夹不能删除").format(_MIN_FIXED_ROWS),
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
            row["label"].setText(tr("文件夹 {0}").format(i + 1))
            row["remove_btn"].setVisible(i >= _MIN_FIXED_ROWS)

    # ─── 构建 worker ───
    def build_worker(self):
        from qfluentwidgets import InfoBar, InfoBarPosition

        s = self.main.settings
        if not s.tts_base_url.strip() or not s.tts_api_key.strip():
            InfoBar.warning(tr("TTS 未配置"), tr("请先在「全局设置」中填写 TTS 服务地址和 API Key"),
                            parent=self.main, position=InfoBarPosition.TOP)
            return None

        folders: list[str] = []
        texts: list[list[str]] = []
        for i, r in enumerate(self.rows):
            folder = r["line_edit"].text().strip()
            lines = [ln.strip() for ln in r["text_edit"].toPlainText().splitlines()
                     if ln.strip()]
            if not folder:
                continue
            if not lines:
                InfoBar.warning(tr("参数不完整"), tr("文件夹 {0} 未填写配音文字").format(i + 1),
                                parent=self.main, position=InfoBarPosition.TOP)
                return None
            folders.append(folder)
            texts.append(lines)

        if not folders:
            InfoBar.warning(tr("参数不完整"), tr("至少填写一个视频文件夹"),
                            parent=self.main, position=InfoBarPosition.TOP)
            return None

        out = self.output.text().strip()
        if not self._require_folder(out, tr("输出文件夹")):
            return None
        for f in folders:
            if not self._require_dir_exists(f, tr("文件夹「{0}」").format(f)):
                return None

        transition_type = _TRANSITIONS[self.transition.currentIndex()][1]
        return SubtitleConcatWorker(
            self.main.ffmpeg_path, self.main.ctrl, self.main.settings,
            folders, texts, out, float(self.td.value()), transition_type,
        )
