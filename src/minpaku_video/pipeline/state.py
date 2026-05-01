from __future__ import annotations

import uuid
from pathlib import Path

from minpaku_video.config import get_settings
from minpaku_video.models.project import (
    CostEntry,
    PageInfo,
    PipelineStage,
    ProjectState,
    TTSEngine,
)
from minpaku_video.utils.filesystem import atomic_write_json, read_json


class StateManager:
    def __init__(self, project_id: str | None = None):
        settings = get_settings()
        self._output_dir = settings.output_dir

        if project_id:
            self._project_dir = self._output_dir / project_id
            self._state_path = self._project_dir / "state.json"
        else:
            self._project_dir = None
            self._state_path = None

    @property
    def project_dir(self) -> Path:
        assert self._project_dir is not None
        return self._project_dir

    @property
    def state_path(self) -> Path:
        assert self._state_path is not None
        return self._state_path

    def pages_dir(self) -> Path:
        d = self.project_dir / "pages"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def scripts_dir(self) -> Path:
        d = self.project_dir / "scripts"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def audio_dir(self) -> Path:
        d = self.project_dir / "audio"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def video_dir(self) -> Path:
        d = self.project_dir / "video"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def create_project(
        self,
        title: str,
        pdf_path: str,
        total_pages: int,
        pages: list[PageInfo],
        *,
        tts_engine: TTSEngine = TTSEngine.ELEVENLABS,
        voice_id: str = "",
        speaker_id: int = 3,
        script_source: str = "generated",
    ) -> ProjectState:
        project_id = uuid.uuid4().hex[:8]
        self._project_dir = self._output_dir / project_id
        self._state_path = self._project_dir / "state.json"
        self._project_dir.mkdir(parents=True, exist_ok=True)

        state = ProjectState(
            project_id=project_id,
            title=title,
            pdf_path=pdf_path,
            total_pages=total_pages,
            tts_engine=tts_engine,
            voice_id=voice_id,
            speaker_id=speaker_id,
            stage=PipelineStage.PAGES_IMPORTED,
            pages=pages,
            script_source=script_source,
        )
        self.save(state)
        return state

    def load(self) -> ProjectState:
        data = read_json(self.state_path)
        return ProjectState.model_validate(data)

    def save(self, state: ProjectState) -> None:
        atomic_write_json(self.state_path, state.model_dump(mode="json"))

    def update_stage(self, state: ProjectState, stage: PipelineStage) -> None:
        state.stage = stage
        self.save(state)

    def add_cost(self, state: ProjectState, entry: CostEntry) -> None:
        state.add_cost(entry)
        self.save(state)

    def exists(self) -> bool:
        return self.state_path.exists()

    @classmethod
    def list_projects(cls) -> list[ProjectState]:
        settings = get_settings()
        output_dir = settings.output_dir
        if not output_dir.exists():
            return []

        projects: list[ProjectState] = []
        for d in sorted(output_dir.iterdir()):
            state_file = d / "state.json"
            if state_file.exists():
                try:
                    data = read_json(state_file)
                    projects.append(ProjectState.model_validate(data))
                except Exception:
                    pass
        return projects
