from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

TTS_CHUNK_SIZE = 5000

CONFIG_DIR = Path.home() / ".minpaku-video"
CONFIG_FILE = CONFIG_DIR / "config.json"


class Settings:
    def __init__(self) -> None:
        # ローカル設定ファイルから読み込み（あれば）
        saved = _load_saved_config()
        secrets = _load_streamlit_secrets()

        self.anthropic_api_key: str = (
            saved.get("anthropic_api_key")
            or secrets.get("ANTHROPIC_API_KEY", "")
            or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        self.elevenlabs_api_key: str = (
            saved.get("elevenlabs_api_key")
            or secrets.get("ELEVENLABS_API_KEY", "")
            or os.environ.get("ELEVENLABS_API_KEY", "")
        )

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


def set_api_keys(
    anthropic_key: str = "",
    elevenlabs_key: str = "",
    *,
    persist: bool = False,
) -> None:
    """APIキーを動的に設定し、シングルトンを更新する。"""
    global _settings
    _settings = None  # リセットして再構築
    settings = get_settings()

    if anthropic_key:
        settings.anthropic_api_key = anthropic_key
    if elevenlabs_key:
        settings.elevenlabs_api_key = elevenlabs_key

    if persist:
        _save_config(
            anthropic_api_key=settings.anthropic_api_key,
            elevenlabs_api_key=settings.elevenlabs_api_key,
        )


def _load_streamlit_secrets() -> dict:
    """Streamlit Cloud の Secrets から読み込む（利用可能な場合）。"""
    try:
        import streamlit as st

        return dict(st.secrets)
    except Exception:
        return {}


def _load_saved_config() -> dict:
    """~/.minpaku-video/config.json から保存済み設定を読み込む。"""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_config(**kwargs: str) -> None:
    """設定を ~/.minpaku-video/config.json に保存する。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing = _load_saved_config()
    existing.update({k: v for k, v in kwargs.items() if v})
    CONFIG_FILE.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
