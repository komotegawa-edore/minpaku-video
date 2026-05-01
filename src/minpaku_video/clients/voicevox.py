from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx
from mutagen.mp3 import MP3

from minpaku_video.config import get_settings
from minpaku_video.models.audio import AudioSegment

logger = logging.getLogger(__name__)


class VoicevoxClient:
    def __init__(self, speaker_id: int | None = None) -> None:
        settings = get_settings()
        self._base_url = settings.voicevox_url
        self._speaker_id = speaker_id or settings.voicevox_default_speaker

    async def generate_speech(
        self,
        text: str,
        output_path: Path,
        page_number: int,
    ) -> AudioSegment:
        """テキストからWAV音声を生成し、MP3に変換する。"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # VOICEVOX はWAVを出力するので、一旦WAVで保存してからffmpegでMP3に変換
        wav_path = output_path.with_suffix(".wav")

        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. 音声合成用のクエリを作成
            query_response = await client.post(
                f"{self._base_url}/audio_query",
                params={"text": text, "speaker": self._speaker_id},
            )
            query_response.raise_for_status()
            query_data = query_response.json()

            # 2. 音声合成
            synthesis_response = await client.post(
                f"{self._base_url}/synthesis",
                params={"speaker": self._speaker_id},
                json=query_data,
            )
            synthesis_response.raise_for_status()

            wav_path.write_bytes(synthesis_response.content)

        # 3. WAV → MP3 変換
        await self._convert_to_mp3(wav_path, output_path)
        wav_path.unlink(missing_ok=True)

        duration = _get_mp3_duration(output_path)
        file_size = output_path.stat().st_size

        logger.info(
            f"VOICEVOX ページ{page_number}: {duration:.1f}秒, {len(text)}文字"
        )

        return AudioSegment(
            page_number=page_number,
            file_name=output_path.name,
            duration_seconds=duration,
            file_size_bytes=file_size,
        )

    async def _convert_to_mp3(self, wav_path: Path, mp3_path: Path) -> None:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(wav_path),
            "-codec:a", "libmp3lame",
            "-b:a", "192k",
            str(mp3_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg WAV→MP3 変換失敗: {stderr.decode()}")


def _get_mp3_duration(path: Path) -> float:
    try:
        audio = MP3(path)
        return audio.info.length
    except Exception:
        return 0.0
