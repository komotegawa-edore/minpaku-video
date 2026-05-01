from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from minpaku_video.models.project import ProjectState
from minpaku_video.pipeline.state import StateManager

logger = logging.getLogger(__name__)

FPS = 30
GAP_DURATION = 1.5
XFADE_DURATION = 0.8

TRANSITION_AUDIO = Path(__file__).resolve().parent.parent / "assets" / "transition.mp3"
SCALE_PAD = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"

# 全セグメントで統一するエンコードパラメータ
_VIDEO_CODEC = [
    "-c:v", "libx264", "-preset", "fast",
    "-r", str(FPS), "-g", str(FPS),
    "-pix_fmt", "yuv420p",
]
_AUDIO_CODEC = [
    "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
]


async def generate_video(
    state: ProjectState,
    state_manager: StateManager,
) -> Path:
    pages_dir = state_manager.pages_dir()
    audio_dir = state_manager.audio_dir()
    video_dir = state_manager.video_dir()
    video_dir.mkdir(parents=True, exist_ok=True)
    output_path = video_dir / "output.mp4"
    temp_files: list[Path] = []

    n = len(state.pages)
    segments: list[Path] = []

    for i, page in enumerate(state.pages):
        if not page.audio_ready or not page.audio_file:
            raise ValueError(f"ページ {page.number} の音声が準備されていません")

        image_path = pages_dir / page.image_file
        audio_path = audio_dir / page.audio_file
        if not image_path.exists():
            raise FileNotFoundError(f"画像が見つかりません: {image_path}")
        if not audio_path.exists():
            raise FileNotFoundError(f"音声が見つかりません: {audio_path}")

        # ナレーション区間セグメント
        seg_path = video_dir / f"_seg_{i:02d}.mp4"
        await _create_narration_segment(image_path, audio_path, seg_path)
        segments.append(seg_path)
        temp_files.append(seg_path)
        logger.info(f"ページ {page.number}: ナレーションセグメント作成完了")

        # 最終ページ以外: トランジション区間
        if i < n - 1:
            next_image = pages_dir / state.pages[i + 1].image_file
            trans_path = video_dir / f"_trans_{i:02d}.mp4"
            await _create_transition_segment(image_path, next_image, trans_path)
            segments.append(trans_path)
            temp_files.append(trans_path)
            logger.info(f"ページ {page.number}→{page.number + 1}: トランジション作成完了")

    # セグメント検証（デバッグ）
    for seg in segments:
        dur = await _probe_duration(seg)
        logger.info(f"  {seg.name}: {dur:.3f}秒")

    # concat demuxer で結合（再エンコードなし）
    concat_list = video_dir / "_concat_list.txt"
    concat_list.write_text(
        "\n".join(f"file '{seg}'" for seg in segments) + "\n",
        encoding="utf-8",
    )
    temp_files.append(concat_list)

    await _concat_demuxer(concat_list, output_path)

    # 一時ファイル削除
    for f in temp_files:
        f.unlink(missing_ok=True)

    logger.info(f"動画生成完了: {output_path}")
    return output_path


async def _create_narration_segment(
    image_path: Path, audio_path: Path, output_path: Path
) -> None:
    """ナレーション区間: 静止画 + 音声 → MP4 セグメント"""
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-r", str(FPS), "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", SCALE_PAD,
        *_VIDEO_CODEC,
        *_AUDIO_CODEC,
        "-shortest",
        str(output_path),
    ]
    await _run_ffmpeg(cmd, f"ナレーション {output_path.name}")


async def _create_transition_segment(
    current_image: Path, next_image: Path, output_path: Path
) -> None:
    """トランジション区間: めくりアニメーション + 効果音 → MP4 (GAP_DURATION秒)"""
    sp = f"{SCALE_PAD},setsar=1,format=yuv420p"

    pre = (GAP_DURATION - XFADE_DURATION) / 2   # 0.35s — めくり前の静止
    input_dur = GAP_DURATION + XFADE_DURATION    # 各入力クリップの長さ（余裕を持たせる）

    # 効果音
    if TRANSITION_AUDIO.exists():
        audio_input = ["-i", str(TRANSITION_AUDIO)]
        audio_filter = "[2:a]aresample=44100,apad[aout]"
        logger.debug(f"効果音使用: {TRANSITION_AUDIO}")
    else:
        audio_input = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        audio_filter = "[2:a]acopy[aout]"
        logger.debug("効果音なし — 無音を使用")

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-r", str(FPS), "-t", f"{input_dur:.3f}", "-i", str(current_image),
        "-loop", "1", "-r", str(FPS), "-t", f"{input_dur:.3f}", "-i", str(next_image),
        *audio_input,
        "-filter_complex",
        (
            f"[0:v]{sp}[v0];"
            f"[1:v]{sp}[v1];"
            f"[v0][v1]xfade=transition=wipeleft:duration={XFADE_DURATION}:offset={pre:.3f}[vout];"
            f"{audio_filter}"
        ),
        "-map", "[vout]", "-map", "[aout]",
        *_VIDEO_CODEC,
        *_AUDIO_CODEC,
        "-t", f"{GAP_DURATION:.3f}",
        str(output_path),
    ]
    await _run_ffmpeg(cmd, f"トランジション {output_path.name}")


async def _concat_demuxer(concat_list: Path, output_path: Path) -> None:
    """concat demuxer でセグメントを結合（再エンコードなし）。"""
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]
    await _run_ffmpeg(cmd, "結合")


async def _probe_duration(path: Path) -> float:
    """ffprobe でファイルの長さ(秒)を取得。"""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        return float(stdout.decode().strip())
    except ValueError:
        return 0.0


async def _run_ffmpeg(cmd: list[str], label: str) -> None:
    logger.debug(f"ffmpeg実行 [{label}]: {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg {label}失敗: {stderr.decode()}")
