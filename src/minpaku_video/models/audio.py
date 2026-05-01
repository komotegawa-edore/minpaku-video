from __future__ import annotations

from pydantic import BaseModel, Field


class AudioSegment(BaseModel):
    page_number: int
    file_name: str
    duration_seconds: float = 0.0
    file_size_bytes: int = 0


class AudioManifest(BaseModel):
    total_duration_seconds: float = 0.0
    segments: list[AudioSegment] = Field(default_factory=list)

    def add_segment(self, segment: AudioSegment) -> None:
        self.segments.append(segment)
        self.total_duration_seconds = sum(s.duration_seconds for s in self.segments)
