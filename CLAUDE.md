# CLAUDE.md

## Project Overview

minpaku-video is a Python CLI tool that automates the production of slide-based YouTube videos for a Japanese vacation rental (民泊) management channel. It takes a PDF of slides as input, generates narration, synthesizes audio, and assembles the final video.

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate && pip install -e .

# CLI entry point
minpaku-video <command>

# Create a new project from a PDF
minpaku-video new slides.pdf --title "【民泊】タイトル" [--script narration.txt] [--voice elevenlabs|voicevox] [--speaker george]

# Run pipeline
minpaku-video run <project_id> [--from-stage script|audio|video|metadata] [--yes]

# List projects / check status
minpaku-video list
minpaku-video status <project_id>
```

There are no tests or linting configured in this project.

## Architecture

### Pipeline Stages (sequential)

```
PDF → ページ画像(PNG) → ナレーション原稿 → 音声(MP3) → 動画(MP4) → メタデータ
```

1. **Import** — PyMuPDF converts PDF pages to PNG (runs during `new`)
2. **Script** — Claude Vision generates narration per page, or user provides text
3. **Audio** — ElevenLabs or VOICEVOX synthesizes MP3 per page
4. **Video** — ffmpeg combines images + audio into a single MP4
5. **Metadata** — Claude generates YouTube title, description, tags

### Key Modules

- **`cli.py`** — Typer-based CLI entry point
- **`config.py`** — Settings singleton from `.env`
- **`models/project.py`** — `ProjectState`, `PipelineStage`, `PageInfo`
- **`pipeline/orchestrator.py`** — Drives all stages
- **`pipeline/state.py`** — `StateManager` for project creation and persistence
- **`clients/claude.py`** — Anthropic API with Vision support
- **`clients/elevenlabs.py`** — ElevenLabs TTS
- **`clients/voicevox.py`** — VOICEVOX TTS (local)
- **`generators/pdf_import.py`** — PDF to PNG conversion
- **`generators/script.py`** — Narration script generation/loading
- **`generators/video.py`** — ffmpeg video assembly
- **`generators/metadata.py`** — YouTube metadata generation

### External Dependencies

- **ffmpeg** — Required for video generation. Install via `brew install ffmpeg`
- **Anthropic API** — Script/metadata generation (Claude Vision)
- **ElevenLabs API** — Text-to-speech
- **VOICEVOX** — Local TTS engine (optional alternative)

### Project State & Output

Each project is identified by an 8-char UUID hex. All artifacts go to `output/<project_id>/`:
- `state.json` — Serialized `ProjectState`
- `pages/page_NN.png` — Extracted slide images
- `scripts/page_NN.txt` — Per-page narration scripts
- `audio/page_NN.mp3` — Per-page audio files
- `video/output.mp4` — Final assembled video
- `metadata.md` — YouTube metadata

### Conventions

- Async throughout — orchestrator, clients, generators use `async/await`
- File writes use atomic helpers from `utils/filesystem.py`
- User-provided script files use `---` as page separator
- TTS engine is fixed per project for voice consistency
- Page-level resumability via `PageInfo.script_ready` / `audio_ready` flags
