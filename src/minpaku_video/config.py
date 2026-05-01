from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

TTS_CHUNK_SIZE = 5000


class Settings:
    def __init__(self) -> None:
        self.anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
        self.elevenlabs_api_key: str = os.environ.get("ELEVENLABS_API_KEY", "")

        self.claude_model: str = os.environ.get(
            "CLAUDE_MODEL", "claude-sonnet-4-20250514"
        )
        self.claude_max_tokens: int = int(
            os.environ.get("CLAUDE_MAX_TOKENS", "8192")
        )

        self.elevenlabs_voice_id: str = os.environ.get(
            "ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb"
        )
        self.elevenlabs_model_id: str = os.environ.get(
            "ELEVENLABS_MODEL_ID", "eleven_v3"
        )

        self.voicevox_url: str = os.environ.get(
            "VOICEVOX_URL", "http://localhost:50021"
        )
        self.voicevox_default_speaker: int = int(
            os.environ.get("VOICEVOX_DEFAULT_SPEAKER", "3")
        )

        self.output_dir: Path = Path(
            os.environ.get("OUTPUT_DIR", str(OUTPUT_DIR))
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
