# kk-mix

**English** | [简体中文](README.zh-CN.md)

A Windows batch video editing toolkit powered by FFmpeg. PySide6 + Fluent Design UI, 15 batch operations, packable into a single portable folder.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

| Feature | Description |
|---|---|
| Split-screen merge | Pairs files from two folders in order and `hstack`s them into 1080×1080; images supported |
| Transition concat | Takes the i-th video from each of N folders and concatenates them with 20 `xfade` transitions + `acrossfade` audio crossfades; resolution/FPS normalized automatically |
| Narrated concat | Transition concat plus per-folder script lines synthesized into voice-over via [Index-TTS](docs/index-tts-api.md); every clip is auto-aligned to its narration length |
| Batch split | Cut into fixed-length segments, optionally exporting MP3 and keeping the trailing remainder |
| Picture-in-picture | Overlay a foreground video onto a background one with preset position and scale |
| Batch speed / reverse | 0.1x–5x speed change with synchronized audio, optional reverse |
| Batch rotate / flip | 90°/180°/270° rotation, horizontal and vertical flip |
| Batch watermark | Image watermark with preset position, opacity and scale |
| Batch volume | 0.1x–10x gain |
| Batch titles | System fonts (Chinese names resolved), color, size (pixels or % of height), auto line-wrap by video width; titles can be fed line-by-line from a TXT file |
| Batch background music | Replace the video's audio track with a given file, or mix it with the original |
| Batch aspect-ratio crop | Center-crop to 9:16 / 16:9 / 1:1 / 4:3 / 3:4 / 4:5 / 21:9, for both video and images |
| Batch compress | Target bitrate, optional H.265 |
| Batch format convert | Convert to mp4 / avi / mov / mkv |
| Batch frame extract | Grab one frame every N seconds |

Across all features: pause / stop, live log with export, turbo mode (`ultrafast`), shared bitrate-or-CRF control, and one-click "open output folder" when a job finishes.

## Quick Start (from source)

### Prerequisites

- Windows 10/11 x64
- Python ≥ 3.10 (developed on 3.14)
- [uv](https://docs.astral.sh/uv/) for dependency management (`pip install uv`, or the official installer)
- `ffmpeg.exe` / `ffprobe.exe` — **not bundled with this repo**, see step 2

### Steps

#### 1. Clone and install dependencies

```bash
git clone https://github.com/jaikydota/kk-mix.git
cd kk-mix
uv sync
```

`uv sync` creates `.venv`, downloads a suitable Python if needed, and installs every dependency.

#### 2. Get FFmpeg (the only manual step)

All video processing is done by shelling out to `ffmpeg.exe` / `ffprobe.exe`. These are **not distributed with the repo** (they are large and separately licensed), so download an official **prebuilt Windows binary** — **no compiling required**.

| Source | Link | Which file |
|---|---|---|
| BtbN/FFmpeg-Builds (GitHub) | https://github.com/BtbN/FFmpeg-Builds/releases | `ffmpeg-master-latest-win64-gpl.zip` |
| gyan.dev | https://www.gyan.dev/ffmpeg/builds/ | `ffmpeg-release-full.7z` |

Unzip it, open the `bin` folder inside, and copy **both `ffmpeg.exe` and `ffprobe.exe`** into the project root:

```
kk-mix/
├── ffmpeg.exe      ← here
├── ffprobe.exe     ← here
├── kk_qt.py
├── pyproject.toml
└── qt/
```

Both filenames are already in `.gitignore`, so they will never be committed by accident.

> **You need both.** With `ffmpeg.exe` alone, duration and resolution probing fails and features like transition concat will not work.
>
> Alternatively, add the extracted `bin` folder to your system `PATH`. When running from source the actual lookup order is:
> **system `PATH` → `C:\ffmpeg\bin` → `C:\Program Files\ffmpeg\bin` → `D:\ffmpeg\bin` → project root**.
> Note that the project root is the *last* fallback — if another FFmpeg is already on your `PATH`, that one wins.

#### 3. Run

```bash
uv run python kk_qt.py        # or double-click start.cmd
```

When run from source there is **no compiled license module**, so the app automatically enters development mode and skips license-key verification.

> The app still launches without FFmpeg, but a persistent red "FFmpeg not found" banner appears and no processing feature will run.

### Language

The UI is available in **English** and **Simplified Chinese**. On first launch it follows your system locale; click **简体中文 / English** at the bottom of the left navigation bar to switch at any time — the window is rebuilt instantly and the log is preserved. The choice is saved as `language` in `settings.json`.

### Configuration

Global settings live in `settings.json` next to the program (editable in-app via **Global Settings**). A template is provided:

```bash
cp settings.example.json settings.json
```

| Field | Meaning |
|---|---|
| `language` | UI language: `"en"`, `"zh"`, or `""` to follow the system locale |
| `tts_base_url` / `tts_api_key` | Index-TTS endpoint and api-key; only needed by *Narrated concat* |
| `verbose_log` | Print the full ffmpeg command line and stderr |
| `speed_priority` | `true` uses the `ultrafast` preset, `false` uses `medium` |
| `compress_video` / `bitrate` | When enabled, encodes with `-b:v <bitrate>`; otherwise `-crf 23` |

The file is optional — without it the app falls back to these defaults.

### Narrated concat (TTS)

This feature needs a self-hosted Index-TTS service; the expected API is documented in [docs/index-tts-api.md](docs/index-tts-api.md). In addition:

1. Put the voice-cloning reference audio at `assets/tts_reference.wav` (gitignored, never committed);
2. Fill in the endpoint and api-key under **Global Settings**;
3. On first run the reference clip is uploaded to the server automatically.

Every other feature works without any of this.

## Building a Release

The build output is `dist/kk_qt/` — a self-contained folder (FFmpeg and the license `.pyd` embedded) that can be zipped and handed to end users.

### Extra requirements

- **Visual Studio Build Tools** with the "Desktop development with C++" workload — MSVC is required to Cython-compile the license module
- `uv sync` already installs the dev dependencies (Cython, PyInstaller)

### One-click build

```bat
build_qt.cmd
```

This runs: `setup_cython.py` compiles `_license_core.pyx` → PyInstaller packages the main app → PyInstaller packages `keygen.exe` → everything is zipped to `dist/kk_qt_<timestamp>.zip`.

Step by step instead:

```bash
uv run python setup_cython.py build_ext --inplace   # produces _license_core.cp3xx-win_amd64.pyd
uv run pyinstaller kk_qt.spec --clean --noconfirm   # produces dist/kk_qt/
```

### Licensing system and build secrets (read before releasing)

The app ships with a per-machine licensing scheme: the machine ID is an MD5 of the motherboard UUID plus CPU ID; a license key is an AES-CBC encrypted JSON blob (expiry date, bound machine ID); `keygen.exe` mints the keys. The logic lives in `_license_core.pyx` and is compiled to a `.pyd` to raise the bar for reverse engineering.

**No real secret is stored in this repo.** The encryption seed in the `.pyx` is a placeholder, injected at compile time by `setup_cython.py`:

```bash
cp build_secrets.env.example build_secrets.env   # gitignored
# edit build_secrets.env:
#   KK_LICENSE_SEED=<a long random string>
build_qt.cmd
```

An environment variable of the same name also works and takes priority. If it is not provided, the development default seed `kk-mix-dev` is used — **fine for local testing, never for a real release**. Changing the seed invalidates every previously issued license key.

`keygen.exe` has no access gate of its own, so **never ship it alongside the app** — anyone holding it can mint license keys for your build.

If you do not want licensing at all, just delete the `check_license()` call in `kk_qt.py`; nothing else depends on the `.pyd`.

## Project Layout

```
kk-mix/
├── kk_qt.py                 # Entry point: QApplication → license check → MainWindow
├── kk_qt.spec               # PyInstaller config (UPX exclusions, module excludes)
├── build_qt.cmd             # One-click build script
├── setup_cython.py          # Cython build + build-secret injection
├── _license_core.pyx        # Licensing core (placeholders replaced at compile time)
├── keygen.py                # License key generator (Tkinter, packaged separately)
├── settings.example.json    # Config template
├── build_secrets.env.example
├── assets/                  # Logo; place tts_reference.wav here yourself
├── docs/
│   └── index-tts-api.md     # TTS service API contract
└── qt/
    ├── main_window.py       # Navigation + page stack + log/progress/pause-stop panel
    ├── settings_window.py   # Global settings dialog
    ├── core/
    │   ├── batch_worker.py  # BatchWorker(QThread) base, pause/stop control, unified run_cmd
    │   ├── ffmpeg_helper.py # FFmpeg/ffprobe discovery, media probing, encoder args
    │   ├── app_settings.py  # AppSettings dataclass + JSON persistence
    │   ├── paths.py         # Version, extension sets, resource paths
    │   ├── fonts.py         # System font enumeration, title auto-wrap
    │   ├── tts_client.py    # Index-TTS client
    │   ├── i18n.py          # tr() + language switching
    │   ├── translations_en.py # English strings (keyed by the Chinese source text)
    │   └── license.py       # License dialog
    ├── tabs/                # One file per feature, all subclassing BaseTab
    └── tools/check_i18n.py  # i18n coverage check
```

### Adding a feature page

1. Create `qt/tabs/<name>.py`:
   - `class <Name>Worker(BatchWorker)` — implement `run_batch() -> (success, summary)`, call `self.ctrl.wait_if_paused()` inside the loop, run FFmpeg via `self.run_cmd(cmd)`, and set `self.output_dir`.
   - `class <Name>Tab(BaseTab)` — define `NAME / TITLE / ICON`, implement `build_form()` (add widgets to `self.form_layout`) and `build_worker()` (validate input, return the worker).
2. Append `<Name>Tab(self)` to the list in `_register_tabs()` in `qt/main_window.py`.
3. Write every user-visible string as `tr("中文")` (Chinese is the source language; use `tr("…{0}…").format(x)` instead of f-strings), add the English text to `qt/core/translations_en.py`, and run `uv run python tools/check_i18n.py` — it fails on any unwrapped or untranslated string.

More conventions in [AGENTS.md](AGENTS.md).

## FAQ

**"FFmpeg not found" on startup** — Make sure *both* `ffmpeg.exe` and `ffprobe.exe` are in place; see "Get FFmpeg" above. Packaged builds embed them automatically.

**Packaged build crashes immediately** — Usually UPX compressing a Qt DLL. `kk_qt.spec` already whitelists `Qt6*.dll` and the VC runtime under `upx_exclude`; add any new DLL there, or disable UPX entirely.

**`setup_cython.py` cannot find `cl.exe`** — MSVC Build Tools are not installed, or you need to run it from the "x64 Native Tools Command Prompt".

**`keygen.py` reports a missing `_license_core`** — The repo only ships the source `_license_core.pyx`. Build it first with `uv run python setup_cython.py build_ext --inplace`; the resulting `.pyd` is gitignored, so it must be rebuilt after a fresh clone (and after anything that cleans the project root).

**"Font failed to load" when adding titles** — The selected font is not a TTF/OTF/TTC, or its path contains special characters; pick another system font.

**Narrated concat returns 401 / missing reference audio** — Check the api-key in `settings.json`, and make sure `assets/tts_reference.wav` exists (it is uploaded on first run).

## Contributing

Issues and pull requests are welcome. Before submitting, make sure `uv run python kk_qt.py` still launches and that any new feature page follows the conventions above.

When editing the README, please update both [README.md](README.md) (English) and [README.zh-CN.md](README.zh-CN.md) (Chinese).

## License

[MIT](LICENSE) © 2026 jaikydota

This project builds on [FFmpeg](https://ffmpeg.org/) (LGPL/GPL, downloaded separately by the user), [PySide6](https://doc.qt.io/qtforpython/) (LGPL) and [PySide6-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) (GPLv3 — review its terms for commercial use).
