from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from elevenlabs import AsyncElevenLabs, VoiceSettings
from mutagen.mp3 import MP3

from minpaku_video.config import get_settings, TTS_CHUNK_SIZE
from minpaku_video.models.audio import AudioSegment

logger = logging.getLogger(__name__)

_semaphore = asyncio.Semaphore(2)


class ElevenLabsClient:
    def __init__(self, voice_id: str | None = None) -> None:
        settings = get_settings()
        self._client = AsyncElevenLabs(api_key=settings.elevenlabs_api_key)
        self._voice_id = voice_id or settings.elevenlabs_voice_id
        self._model_id = settings.elevenlabs_model_id

    async def generate_speech(
        self,
        text: str,
        output_path: Path,
        page_number: int,
    ) -> AudioSegment:
        chunks = _split_text(text, TTS_CHUNK_SIZE)
        all_audio = bytearray()

        for i, chunk in enumerate(chunks):
            logger.info(
                f"TTS ページ{page_number}, チャンク {i + 1}/{len(chunks)} "
                f"({len(chunk)}文字)"
            )
            audio_data = await self._generate_chunk(chunk)
            all_audio.extend(audio_data)
            if i < len(chunks) - 1:
                await asyncio.sleep(0.5)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(bytes(all_audio))

        duration = _get_mp3_duration(output_path)
        file_size = output_path.stat().st_size

        return AudioSegment(
            page_number=page_number,
            file_name=output_path.name,
            duration_seconds=duration,
            file_size_bytes=file_size,
        )

    async def _generate_chunk(self, text: str) -> bytes:
        async with _semaphore:
            response = self._client.text_to_speech.convert(
                voice_id=self._voice_id,
                text=text,
                model_id=self._model_id,
                voice_settings=VoiceSettings(
                    stability=0.5,
                    similarity_boost=0.75,
                    style=0.0,
                    speed=1.0,
                ),
                output_format="mp3_44100_128",
            )
            audio_bytes = bytearray()
            async for chunk in response:
                audio_bytes.extend(chunk)
            return bytes(audio_bytes)


def _split_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current = text
    while current:
        if len(current) <= max_chars:
            chunks.append(current)
            break

        split_at = max_chars
        for delim in ["。", "！", "？", "\n"]:
            idx = current.rfind(delim, 0, max_chars)
            if idx > 0:
                split_at = idx + len(delim)
                break

        chunks.append(current[:split_at])
        current = current[split_at:]

    return chunks


def _get_mp3_duration(path: Path) -> float:
    try:
        audio = MP3(path)
        return audio.info.length
    except Exception:
        return 0.0
