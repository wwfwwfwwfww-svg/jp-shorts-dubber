"""Pydantic schema for a 제작(자막교체) job. Reuses Segment from the main models."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from ..models import Segment, VideoMeta


class ProduceJob(BaseModel):
    id: str
    # created -> analyzing -> analyzed -> translating -> translated
    #   -> rendering -> done | error
    status: str = "created"
    message: str = ""
    error: str = ""

    source_path: str = ""          # 원본 mp4 (data/produce/<id>/source.mp4 또는 finder 파일)
    title: str = ""
    origin: str = "upload"         # upload | finder
    meta: VideoMeta = Field(default_factory=VideoMeta)
    source_lang: str = ""

    segments: List[Segment] = Field(default_factory=list)

    # --- Stage-1(vision.extract) 파라미터 (기존 Job과 같은 이름이라 재사용 가능) ---
    frame_interval: float = 0.5
    crop_top_ratio: float = 0.45
    crop_bottom_ratio: float = 1.0

    # --- 가릴 자막 띠 + 스타일 ---
    band_top: float = 0.72         # 원본 영어 자막을 가릴 띠 (세로 비율)
    band_bottom: float = 0.93
    cover_mode: str = "box"        # box(어두운 띠) | blur
    cover_opacity: float = 0.85
    font_name: str = "Yu Gothic UI"
    font_scale: float = 1.0        # 자막 크기 배율

    output_file: Optional[str] = None


class SegmentEdit(BaseModel):
    index: int
    text_kr: Optional[str] = None   # 인식된 영어 원문(수정 가능)
    text_ja: Optional[str] = None   # 일본어 자막
    start: Optional[float] = None
    end: Optional[float] = None


class SegmentsUpdate(BaseModel):
    segments: List[SegmentEdit]


class BandUpdate(BaseModel):
    band_top: Optional[float] = None
    band_bottom: Optional[float] = None
    cover_mode: Optional[str] = None
    cover_opacity: Optional[float] = None
    font_name: Optional[str] = None
    font_scale: Optional[float] = None


class FromFinderRequest(BaseModel):
    video_id: str
