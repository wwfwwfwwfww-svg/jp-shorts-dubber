"""Pydantic schemas shared across the API and pipeline."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

SegmentType = Literal["narration", "dialogue"]


class Segment(BaseModel):
    index: int
    start: float                  # source (original video) start, seconds
    end: float
    duration: float
    text_kr: str = ""             # SOURCE subtitle text (any language, as on screen)
    text_ko: str = ""             # Korean gloss of the source (so the user understands)
    type: SegmentType = "narration"
    color: str = "white"
    # --- Stage 2+ ---
    text_ja: str = ""             # Japanese narration
    text_ja_back: str = ""        # natural Korean back-translation of text_ja
    audio_file: Optional[str] = None   # relative filename under the job's audio/ dir
    audio_duration: Optional[float] = None
    seq_start: float = 0.0        # start on the sequential (concatenated) timeline
    speed: float = 1.0

    def recompute_duration(self) -> None:
        self.duration = round(max(0.0, self.end - self.start), 3)


class VideoMeta(BaseModel):
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    source: str = ""              # "upload" | "url"
    title: str = ""


class Job(BaseModel):
    id: str
    # uploaded -> extracting -> stage1_ready -> translating -> stage2_ready
    #  -> dubbing -> qa -> stage3_ready -> generating_meta -> done | error
    status: str = "created"
    message: str = ""
    engine: str = ""
    meta: VideoMeta = Field(default_factory=VideoMeta)
    segments: List[Segment] = Field(default_factory=list)

    # Stage-1 params.
    crop_top_ratio: float = 0.68
    crop_bottom_ratio: float = 1.0
    frame_interval: float = 0.5
    source_lang: str = ""
    # Stage 1 human-readable output: a coherent Korean plot summary + guessed title.
    summary_ko: str = ""
    title_ja: str = ""
    title_ko: str = ""

    # Stage 2 (Japanese) state.
    speed: float = 1.0                 # single uniform TTS speed for the whole video
    active_seconds: float = 0.0        # narration active seconds used for the budget
    char_target_min: int = 0
    char_target_max: int = 0
    char_actual: int = 0

    # Stage 3 (TTS/QA) state.
    voice_id: str = ""
    qa: Optional[dict] = None
    audio_seconds: float = 0.0         # actual length of the concatenated dub
    target_seconds: float = 0.0        # narration span we aimed for (= active_seconds)

    # Stage 4.
    metadata: Optional[dict] = None


class CreateJobUrl(BaseModel):
    url: str


class SegmentPatch(BaseModel):
    index: int
    text_kr: Optional[str] = None
    text_ja: Optional[str] = None
    type: Optional[SegmentType] = None


class SegmentsUpdate(BaseModel):
    segments: List[SegmentPatch]
