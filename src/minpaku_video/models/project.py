from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class PipelineStage(str, Enum):
    INITIALIZED = "initialized"
    PAGES_IMPORTED = "pages_imported"
    SCRIPTS_READY = "scripts_ready"
    AUDIO_GENERATED = "audio_generated"
    VIDEO_GENERATED = "video_generated"
    METADATA_GENERATED = "metadata_generated"

    @property
    def index(self) -> int:
        return list(PipelineStage).index(self)

    @property
    def next(self) -> PipelineStage | None:
        stages = list(PipelineStage)
        idx = stages.index(self)
        if idx + 1 < len(stages):
            return stages[idx + 1]
        return None


class TTSEngine(str, Enum):
    ELEVENLABS = "elevenlabs"
    VOICEVOX = "voicevox"


class PageInfo(BaseModel):
    number: int  # 1-indexed
    image_file: str  # "page_01.png"
    script: str | None = None
    script_ready: bool = False
    audio_file: str | None = None
    audio_ready: bool = False
    duration_seconds: float = 0.0


class CostEntry(BaseModel):
    stage: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ProjectState(BaseModel):
    project_id: str
    title: str
    pdf_path: str
    total_pages: int = 0
    tts_engine: TTSEngine = TTSEngine.ELEVENLABS
    voice_id: str = ""
    speaker_id: int = 3  # VOICEVOX用
    stage: PipelineStage = PipelineStage.INITIALIZED
    pages: list[PageInfo] = Field(default_factory=list)
    script_source: str = "generated"  # "provided" | "generated"
    costs: list[CostEntry] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def total_cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.costs)

    def add_cost(self, entry: CostEntry) -> None:
        self.costs.append(entry)
        self.updated_at = datetime.now(timezone.utc).isoformat()
