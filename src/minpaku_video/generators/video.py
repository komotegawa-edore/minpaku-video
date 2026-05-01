from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from minpaku_video.models.project import ProjectState
from minpaku_video.pipeline.state import StateManager

logger = logging.getLogger(__name__)


async def generate_video(
    state: ProjectState,
    state_manager: StateManager,
) -> Path:
    """画像と音声を組み合わせて動画を生成する。"""
    pages_dir = state_manager.pages_dir()
    audio_dir = state_manager.audio_dir()
    video_dir = state_manager.video_dir()
    output_path = video_dir / "output.mp4"

    # ffmpeg の concat demuxer 用のファイルリストを作成
    segments: list[str] = []

    for page in state.pages:
        if not page.audio_ready or not page.audio_file:
            raise ValueError(f"ページ {page.number} の音声が準備されていません")

        image_path = pages_dir / page.image_file
        audio_path = audio_dir / page.audio_file

        if not image_path.exists():
            raise FileNotFoundError(f"画像が見つかりません: {image_path}")
        if not audio_path.exists():
            raise FileNotFoundError(f"音声が見つかりません: {audio_path}")

        # 各ページを個別の動画セグメントとして作成
        segment_path = video_dir / f"segment_{page.number:02d}.mp4"
        await _create_segment(image_path, audio_path, segment_path)
        segments.append(str(segment_path))

        logger.info(f"ページ {page.number}: セグメント作成完了")

    # セグメントを結合
    await _concat_segments(segments, output_path)

    # 一時セグメントファイルを削除
    for seg in segments:
        Path(seg).unlink(missing_ok=True)

    logger.info(f"動画生成完了: {output_path}")
    return output_path


async def _create_segment(
    image_path: Path, audio_path: Path, output_path: Path
) -> None:
    """1ページ分の画像+音声を動画セグメントにする。"""
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-shortest",
        str(output_path),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg セグメント作成失敗: {stderr.decode()}"
        )


async def _concat_segments(segments: list[str], output_path: Path) -> None:
    """複数のセグメントを1つの動画に結合する。"""
    # concat demuxer用のリストファイルを作成
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    ) as f:
        for seg in segments:
            f.write(f"file '{seg}'\n")
        list_path = f.name

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_path,
            "-c", "copy",
            str(output_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg 結合失敗: {stderr.decode()}"
            )
    finally:
        Path(list_path).unlink(missing_ok=True)
