"""Pydantic request/response schemas for the 소재 찾기 tab."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

# Period presets → days. "all" means no publishedAfter bound.
PERIOD_DAYS = {"1d": 1, "3d": 3, "1w": 7, "2w": 14, "1m": 30, "3m": 90, "all": None}


class SearchRequest(BaseModel):
    keywords: List[str] = Field(default_factory=list)   # 직접 입력 키워드
    categories: List[str] = Field(default_factory=list)  # 저장된 키워드 묶음(카테고리명)
    period: str = "2w"                                    # 1d/3d/1w/2w/1m/3m/all
    order: str = "viewCount"                              # viewCount(인기) | date(최신)
    regions: Optional[List[str]] = None                  # None이면 설정 기본값
    per_keyword: Optional[int] = None                    # 키워드당 수집량(최대 100)
    view_floor: Optional[int] = None                     # 조회수 하한
    translate_titles: bool = True                        # 제목 한국어 번역(AI, 선택)


class EstimateRequest(SearchRequest):
    pass


class SettingsUpdate(BaseModel):
    youtube_api_key: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    view_floor: Optional[int] = None
    per_keyword: Optional[int] = None
    regions: Optional[List[str]] = None
    scan_hours: Optional[int] = None
    morning_hour: Optional[int] = None
    morning_enabled: Optional[bool] = None
    japan_check_top_n: Optional[int] = None


class ValidateKeysRequest(BaseModel):
    youtube_api_key: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None


class VideoPatch(BaseModel):
    status: Optional[str] = None          # bookmark|working|done|excluded|new
    watched: Optional[bool] = None
    category: Optional[str] = None        # 수동 카테고리 변경


class RegisterChannelRequest(BaseModel):
    category: Optional[str] = ""


class JapanCheckRequest(BaseModel):
    video_ids: Optional[List[str]] = None   # 지정 없으면 배수 상위 N개
    top_n: Optional[int] = None


class CategorizeRequest(BaseModel):
    video_ids: Optional[List[str]] = None   # 지정 없으면 미분류 전체
    limit: int = 40


class KeywordCreate(BaseModel):
    category: str
    text: str


class CategoryCreate(BaseModel):
    name: str
    warn_tag: Optional[str] = None
