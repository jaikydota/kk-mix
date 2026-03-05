import os
import asyncio
import base64
import json
import locale
import threading
import tempfile
import subprocess
import shutil
from pathlib import Path
from tkinter import ttk, messagebox


# ──────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────

def create_speech_tab(app, parent):
    """创建视频配音标签页"""
    pad = {"padx": 10, "pady": 5}

    ttk.Label(parent, text="视频文件夹:").grid(row=0, column=0, sticky="w", **pad)
    ttk.Entry(parent, textvariable=app.speech_video_folder, width=45).grid(row=0, column=1, padx=5)
    ttk.Button(parent, text="浏览",
               command=lambda: app.browse_folder(app.speech_video_folder)).grid(row=0, column=2, padx=5)

    ttk.Label(parent, text="文案文件夹:").grid(row=1, column=0, sticky="w", **pad)
    ttk.Entry(parent, textvariable=app.speech_text_folder, width=45).grid(row=1, column=1, padx=5)
    ttk.Button(parent, text="浏览",
               command=lambda: app.browse_folder(app.speech_text_folder)).grid(row=1, column=2, padx=5)

    ttk.Label(parent, text="参考音频文件夹:").grid(row=2, column=0, sticky="w", **pad)
    ttk.Entry(parent, textvariable=app.speech_ref_voice_folder, width=45).grid(row=2, column=1, padx=5)
    ttk.Button(parent, text="浏览",
               command=lambda: app.browse_folder(app.speech_ref_voice_folder)).grid(row=2, column=2, padx=5)

    ttk.Label(parent, text="输出文件夹:").grid(row=3, column=0, sticky="w", **pad)
    ttk.Entry(parent, textvariable=app.speech_output_folder, width=45).grid(row=3, column=1, padx=5)
    ttk.Button(parent, text="浏览",
               command=lambda: app.browse_folder(app.speech_output_folder, True)).grid(row=3, column=2, padx=5)

    ttk.Checkbutton(parent, text="保留原音频（与配音混合）",
                    variable=app.speech_keep_audio).grid(
        row=4, column=0, columnspan=3, sticky="w", padx=10, pady=2)

    ttk.Button(parent, text="开始配音",
               command=lambda: start_speech(app)).grid(
        row=5, column=0, columnspan=3, pady=15)

    parent.columnconfigure(1, weight=1)


# ──────────────────────────────────────────────
# 启动入口
# ──────────────────────────────────────────────

def start_speech(app):
    thread = threading.Thread(target=_batch_speech_operation, args=(app,))
    thread.daemon = True
    thread.start()


# ──────────────────────────────────────────────
# 批处理主逻辑
# ──────────────────────────────────────────────

def _batch_speech_operation(app):
    app.current_operation = "speech"
    app.set_controls_state(True)
    app.progress_var.set(0)

    tmp_dir = None
    try:
        video_folder = app.speech_video_folder.get().strip()
        text_folder = app.speech_text_folder.get().strip()
        ref_folder = app.speech_ref_voice_folder.get().strip()
        output_folder = app.speech_output_folder.get().strip()
        mcp_url = app.mcp_url.get().strip()
        keep_audio = app.speech_keep_audio.get()

        # ── 参数校验 ──
        if not all([video_folder, text_folder, ref_folder, output_folder]):
            messagebox.showerror("错误", "请填写全部文件夹路径！")
            return

        # ── 收集文件列表 ──
        video_files = _get_sorted_files(video_folder, app.video_extensions)
        text_files = _get_sorted_txt(text_folder)
        ref_files = _get_sorted_files(ref_folder, app.audio_extensions)

        if not video_files:
            messagebox.showerror("错误", "视频文件夹中未找到视频文件！")
            return
        if not text_files:
            messagebox.showerror("错误", "文案文件夹中未找到 .txt 文件！")
            return
        if not ref_files:
            messagebox.showerror("错误", "参考音频文件夹中未找到音频文件！")
            return

        if len(video_files) != len(text_files):
            messagebox.showerror(
                "错误",
                f"视频文件数（{len(video_files)}）与文案文件数（{len(text_files)}）不一致，请检查！"
            )
            return

        # 参考音频数量不足时，补齐最后一个
        while len(ref_files) < len(video_files):
            ref_files.append(ref_files[-1])

        os.makedirs(output_folder, exist_ok=True)
        tmp_dir = tempfile.mkdtemp(prefix="speech_tab_")

        total = len(video_files)
        app.log(f"\n{'='*60}")
        app.log(f"开始视频配音  共 {total} 对")
        app.log(f"MCP: {mcp_url}")
        app.log(f"{'='*60}\n")

        success_count = 0
        for idx, (vf, tf, rf) in enumerate(zip(video_files, text_files, ref_files), 1):
            if app.check_pause_stop():
                break

            video_path = os.path.join(video_folder, vf)
            text_path = os.path.join(text_folder, tf)
            ref_path = os.path.join(ref_folder, rf)
            output_name = f"dubbed_{idx:03d}_{Path(vf).stem}.mp4"
            output_path = os.path.join(output_folder, output_name)

            app.log(f"[{idx}/{total}] 视频: {vf}")
            app.log(f"         文案: {tf}  |  参考音频: {rf}")

            try:
                # 读取文案，按行拆分（忽略空行）
                lines = _read_text_lines(text_path)
                if not lines:
                    app.log("  ✗ 文案文件为空，跳过")
                    continue

                app.log(f"  文案共 {len(lines)} 行，开始 TTS 合成...")

                # 逐行 TTS
                ref_bytes = Path(ref_path).read_bytes()
                wav_segments = []
                tts_ok = True
                for line_idx, line in enumerate(lines, 1):
                    if app.check_pause_stop():
                        tts_ok = False
                        break
                    app.log(f"    TTS [{line_idx}/{len(lines)}]: {line[:40]}{'...' if len(line) > 40 else ''}")
                    seg_path = os.path.join(tmp_dir, f"seg_{idx:03d}_{line_idx:03d}.wav")
                    try:
                        wav_bytes = asyncio.run(_call_tts_line(line, ref_bytes, mcp_url))
                        Path(seg_path).write_bytes(wav_bytes)
                        wav_segments.append(seg_path)
                        app.log(f"    ✓ 第 {line_idx} 行合成完成")
                    except Exception as e:
                        app.log(f"    ✗ 第 {line_idx} 行 TTS 失败: {e}")
                        tts_ok = False
                        break

                if not tts_ok or not wav_segments:
                    app.log(f"  ✗ TTS 未完成，跳过视频: {vf}")
                    continue

                # 拼接 WAV 片段
                merged_wav = os.path.join(tmp_dir, f"merged_{idx:03d}.wav")
                if len(wav_segments) == 1:
                    merged_wav = wav_segments[0]
                else:
                    app.log(f"  拼接 {len(wav_segments)} 段音频...")
                    if not _concat_wav_files(app, wav_segments, merged_wav):
                        app.log(f"  ✗ 音频拼接失败，跳过视频: {vf}")
                        continue

                # 合并音频到视频
                app.log("  合并音频到视频...")
                if _merge_audio_to_video(app, video_path, merged_wav, output_path, keep_audio):
                    success_count += 1
                    app.log(f"  ✓ 完成: {output_name}")
                else:
                    app.log(f"  ✗ 合并失败: {vf}")

            except Exception as e:
                app.log(f"  ✗ 处理异常: {e}")

            app.progress_var.set((idx / total) * 100)
            app.update_status(f"配音中... {idx}/{total}")

        app.log(f"\n{'='*60}")
        app.log(f"完成！成功处理 {success_count}/{total} 个视频")
        app.log(f"{'='*60}")

        if success_count > 0:
            messagebox.showinfo("完成", f"成功配音 {success_count} 个视频！")

    except Exception as e:
        messagebox.showerror("错误", f"视频配音失败: {e}")
        app.log(f"✗ 错误: {e}")
    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            try:
                shutil.rmtree(tmp_dir)
            except Exception:
                pass
        app.set_controls_state(False)


# ──────────────────────────────────────────────
# TTS 异步调用
# ──────────────────────────────────────────────

async def _call_tts_line(text: str, ref_voice_bytes: bytes, mcp_url: str) -> bytes:
    """调用 MCP TTS 合成单行文本，返回 WAV bytes"""
    from fastmcp import Client

    ref_b64 = base64.b64encode(ref_voice_bytes).decode()

    async with Client(mcp_url) as client:
        # 提交任务
        result = await client.call_tool(
            "tts_generate_voice",
            {"text": text, "prompt_voice_bytes": ref_b64},
        )
        task_id: str = _unwrap_data(result.data)

        # 轮询等待（最多 300 秒）
        timeout = 300.0
        elapsed = 0.0
        interval = 3.0
        while elapsed < timeout:
            raw = (await client.call_tool("tts_query_task", {"task_id": task_id})).data
            info = _unwrap_data(raw)
            status = info.get("status") if isinstance(info, dict) else None
            if status == "completed":
                break
            if status == "failed":
                raise RuntimeError(f"TTS 任务失败: {info.get('error')}")
            await asyncio.sleep(interval)
            elapsed += interval
        else:
            raise TimeoutError(f"TTS 任务超时（>{timeout}s），task_id={task_id}")

        # 下载结果
        wav_data = (await client.call_tool("tts_get_result", {"task_id": task_id})).data

    return _decode_bytes(_unwrap_data(wav_data))


def _unwrap_data(data):
    """fastmcp 有时返回未解析的 JSON 字符串，统一解包为 Python 对象"""
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    return data


def _decode_bytes(data) -> bytes:
    """兼容 bytes 和 base64 str 两种返回格式"""
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return base64.b64decode(data)
    raise TypeError(f"TTS 返回值类型不支持: {type(data)}")


# ──────────────────────────────────────────────
# FFmpeg 工具函数
# ──────────────────────────────────────────────

def _concat_wav_files(app, wav_list: list, output_wav: str) -> bool:
    """用 FFmpeg concat 拼接多段 WAV"""
    list_file = output_wav + ".txt"
    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for p in wav_list:
                # Windows 路径反斜杠需转义
                safe = p.replace("\\", "/")
                f.write(f"file '{safe}'\n")

        cmd = [
            app.ffmpeg_path, "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            output_wav,
        ]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            app.log(f"    ffmpeg concat 错误: {_decode_stderr(r.stderr)}")
            return False
        return True
    finally:
        if os.path.exists(list_file):
            os.remove(list_file)


def _merge_audio_to_video(app, video_path: str, wav_path: str,
                          output_path: str, keep_audio: bool) -> bool:
    """将 WAV 合并进视频；keep_audio=True 则混音，否则替换原音轨"""
    if keep_audio:
        cmd = [
            app.ffmpeg_path, "-y",
            "-i", video_path,
            "-i", wav_path,
            "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-shortest",
            output_path,
        ]
    else:
        cmd = [
            app.ffmpeg_path, "-y",
            "-i", video_path,
            "-i", wav_path,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-shortest",
            output_path,
        ]

    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        app.log(f"    ffmpeg merge 错误: {_decode_stderr(r.stderr)}")
        return False
    return True


# ──────────────────────────────────────────────
# 文件扫描工具
# ──────────────────────────────────────────────

def _get_sorted_files(folder: str, extensions: set) -> list:
    """返回文件夹中指定扩展名的文件名列表（排序）"""
    if not os.path.exists(folder):
        return []
    return sorted(f for f in os.listdir(folder) if Path(f).suffix.lower() in extensions)


def _get_sorted_txt(folder: str) -> list:
    """返回文件夹中所有 .txt 文件名列表（排序）"""
    return _get_sorted_files(folder, {".txt"})


def _read_text_lines(txt_path: str) -> list:
    """读取文案文件，按行拆分，过滤空行"""
    text = Path(txt_path).read_text(encoding="utf-8", errors="ignore")
    return [line.strip() for line in text.splitlines() if line.strip()]


def _decode_stderr(data: bytes) -> str:
    """优先 UTF-8 解码，失败时回退到系统编码，避免 Windows GBK 乱码"""
    for enc in ("utf-8", locale.getpreferredencoding(False), "gbk", "latin-1"):
        try:
            return data.decode(enc)[-300:]
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin-1", errors="replace")[-300:]
