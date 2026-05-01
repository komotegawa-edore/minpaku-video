from __future__ import annotations

import logging
from collections.abc import Callable

from minpaku_video.clients.claude import ClaudeClient
from minpaku_video.clients.elevenlabs import ElevenLabsClient
from minpaku_video.clients.voicevox import VoicevoxClient
from minpaku_video.generators.metadata import generate_metadata
from minpaku_video.generators.script import generate_scripts
from minpaku_video.generators.video import generate_video
from minpaku_video.models.project import PipelineStage, ProjectState, TTSEngine
from minpaku_video.pipeline.state import StateManager
from minpaku_video.utils.display import console, print_error, print_success

logger = logging.getLogger(__name__)

# ステージ実行順序
STAGE_ORDER = [
    PipelineStage.PAGES_IMPORTED,
    PipelineStage.SCRIPTS_READY,
    PipelineStage.AUDIO_GENERATED,
    PipelineStage.VIDEO_GENERATED,
    PipelineStage.METADATA_GENERATED,
]

# ステージ名の日本語マッピング
STAGE_LABELS = {
    PipelineStage.PAGES_IMPORTED: "ページインポート",
    PipelineStage.SCRIPTS_READY: "スクリプト生成",
    PipelineStage.AUDIO_GENERATED: "音声生成",
    PipelineStage.VIDEO_GENERATED: "動画生成",
    PipelineStage.METADATA_GENERATED: "メタデータ生成",
}


class PipelineOrchestrator:
    def __init__(
        self,
        state: ProjectState,
        state_manager: StateManager,
        *,
        from_stage: PipelineStage | None = None,
        auto_confirm: bool = False,
        on_progress: Callable[[str, float], None] | None = None,
    ) -> None:
        self._state = state
        self._sm = state_manager
        self._from_stage = from_stage
        self._auto_confirm = auto_confirm
        self._on_progress = on_progress
        self._claude: ClaudeClient | None = None

    def _report_progress(self, message: str, progress: float) -> None:
        """進捗コールバックを呼び出す（設定されている場合）。"""
        if self._on_progress:
            self._on_progress(message, progress)

    async def run(self) -> None:
        """パイプラインを実行する。"""
        try:
            start_idx = self._get_start_index()
            total_stages = len(STAGE_ORDER) - start_idx

            for i in range(start_idx, len(STAGE_ORDER)):
                target_stage = STAGE_ORDER[i]
                stage_num = i - start_idx + 1
                base_progress = (stage_num - 1) / total_stages
                self._report_progress(
                    STAGE_LABELS.get(target_stage, target_stage.value),
                    base_progress,
                )
                await self._run_stage(target_stage, base_progress, 1.0 / total_stages)

            self._report_progress("完了", 1.0)
            print_success("パイプライン完了!")
            console.print(f"  コスト合計: ${self._state.total_cost_usd():.4f}")

        finally:
            if self._claude:
                await self._claude.close()

    def _get_start_index(self) -> int:
        if self._from_stage:
            # from_stage で指定されたステージから開始
            try:
                return STAGE_ORDER.index(self._from_stage)
            except ValueError:
                return 0

        # 現在のステージの次から開始
        current_idx = self._state.stage.index
        for i, stage in enumerate(STAGE_ORDER):
            if stage.index > current_idx:
                return i
        return len(STAGE_ORDER)

    async def _run_stage(
        self,
        target_stage: PipelineStage,
        base_progress: float = 0.0,
        stage_weight: float = 1.0,
    ) -> None:
        console.print(f"\n[bold blue]▶ ステージ: {target_stage.value}[/bold blue]")

        if target_stage == PipelineStage.SCRIPTS_READY:
            await self._stage_scripts(base_progress, stage_weight)
        elif target_stage == PipelineStage.AUDIO_GENERATED:
            await self._stage_audio(base_progress, stage_weight)
        elif target_stage == PipelineStage.VIDEO_GENERATED:
            await self._stage_video()
        elif target_stage == PipelineStage.METADATA_GENERATED:
            await self._stage_metadata()

    async def _get_claude(self) -> ClaudeClient:
        if self._claude is None:
            self._claude = ClaudeClient()
        return self._claude

    async def _stage_scripts(
        self, base_progress: float = 0.0, stage_weight: float = 1.0
    ) -> None:
        """スクリプト生成ステージ。"""
        # 全ページのスクリプトが準備済みなら skip
        if all(p.script_ready for p in self._state.pages):
            logger.info("全ページのスクリプト生成済み、スキップ")
            self._sm.update_stage(self._state, PipelineStage.SCRIPTS_READY)
            return

        claude = await self._get_claude()

        total_pages = len(self._state.pages)
        for i, page in enumerate(self._state.pages):
            if not page.script_ready:
                page_progress = base_progress + (i / total_pages) * stage_weight
                self._report_progress(
                    f"スクリプト生成 ({i + 1}/{total_pages}ページ)",
                    page_progress,
                )

        await generate_scripts(self._state, self._sm, claude)
        self._sm.update_stage(self._state, PipelineStage.SCRIPTS_READY)

    async def _stage_audio(
        self, base_progress: float = 0.0, stage_weight: float = 1.0
    ) -> None:
        """音声生成ステージ。"""
        audio_dir = self._sm.audio_dir()

        if self._state.tts_engine == TTSEngine.ELEVENLABS:
            tts = ElevenLabsClient(voice_id=self._state.voice_id or None)
        else:
            tts = VoicevoxClient(speaker_id=self._state.speaker_id)

        total_pages = len(self._state.pages)
        for i, page in enumerate(self._state.pages):
            if page.audio_ready:
                logger.info(f"ページ {page.number}: 音声生成済み、スキップ")
                continue

            if not page.script:
                raise ValueError(
                    f"ページ {page.number} のスクリプトがありません"
                )

            page_progress = base_progress + (i / total_pages) * stage_weight
            self._report_progress(
                f"音声生成 ({i + 1}/{total_pages}ページ)",
                page_progress,
            )

            audio_file = f"page_{page.number:02d}.mp3"
            output_path = audio_dir / audio_file

            segment = await tts.generate_speech(
                text=page.script,
                output_path=output_path,
                page_number=page.number,
            )

            page.audio_file = audio_file
            page.audio_ready = True
            page.duration_seconds = segment.duration_seconds
            self._sm.save(self._state)

            console.print(
                f"  ページ {page.number}: {segment.duration_seconds:.1f}秒"
            )

        self._sm.update_stage(self._state, PipelineStage.AUDIO_GENERATED)

    async def _stage_video(self) -> None:
        """動画生成ステージ。"""
        output_path = await generate_video(self._state, self._sm)
        self._sm.update_stage(self._state, PipelineStage.VIDEO_GENERATED)
        console.print(f"  出力: {output_path}")

    async def _stage_metadata(self) -> None:
        """メタデータ生成ステージ。"""
        claude = await self._get_claude()
        output_path = await generate_metadata(self._state, self._sm, claude)
        self._sm.update_stage(self._state, PipelineStage.METADATA_GENERATED)
        console.print(f"  出力: {output_path}")
