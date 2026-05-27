"""공통 유틸 함수 모음."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytz
import yaml
from rapidfuzz import fuzz

# 한국 시간대
KST = pytz.timezone("Asia/Seoul")

# 로거 설정
def setup_logger(name: str = "industry_news_bot", level: int = logging.INFO) -> logging.Logger:
    """로거 셋업."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


logger = setup_logger()


# ============================================================
# 데이터 클래스
# ============================================================

@dataclass
class RawNews:
    """수집된 원본 뉴스."""

    title: str
    url: str
    source: str  # 매체명 (예: "전자신문")
    pub_date: datetime
    summary: str = ""  # 요약/본문 (있으면)
    language: str = "ko"  # ko / en
    matched_keywords: list[str] = field(default_factory=list)  # 어느 키워드로 수집됐는지

    def __hash__(self) -> int:
        return hash(self.url)


@dataclass
class ProcessedNews:
    """Claude로 가공된 뉴스."""

    # 원본 정보
    raw: RawNews

    # 가공 결과
    category: str  # "AI/데이터센터" / "반도체" / "2차전지" / "로봇"
    keywords: list[str]  # 17개 핵심 키워드 중 매칭된 것
    headline: str
    core: str
    meaning: str
    korea_impact: str
    related_companies: list[str]  # 한국 상장사 종목명
    importance: int  # 1~5
    evaluation: str  # "⭐ 핵심" / "👍 좋음" / "미평가"

    # 후처리 정보 (Notion 저장 시 채워짐)
    notion_page_id: str = ""
    matched_company_pages: list[dict[str, str]] = field(default_factory=list)
    # [{"name": "SK하이닉스", "page_id": "...", "has_ir_note": True}, ...]


# ============================================================
# 설정 파일 로딩
# ============================================================

def get_project_root() -> Path:
    """프로젝트 루트 디렉토리 반환."""
    return Path(__file__).parent.parent


def load_yaml_config(filename: str) -> dict[str, Any]:
    """config/ 디렉토리의 YAML 설정 파일 로드."""
    config_path = get_project_root() / "config" / filename
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_prompt(filename: str) -> str:
    """prompts/ 디렉토리의 프롬프트 파일 로드."""
    prompt_path = get_project_root() / "prompts" / filename
    return prompt_path.read_text(encoding="utf-8")


# ============================================================
# 환경변수
# ============================================================

def get_env(key: str, required: bool = True, default: str = "") -> str:
    """환경변수 가져오기 (필수 누락 시 에러)."""
    value = os.environ.get(key, default)
    if required and not value:
        raise ValueError(f"Environment variable {key} is required but not set.")
    return value


def is_debug_mode() -> bool:
    """디버그 모드 여부 (텔레그램 미발송)."""
    return os.environ.get("DEBUG_MODE", "false").lower() == "true"


# ============================================================
# 시간 유틸
# ============================================================

def now_kst() -> datetime:
    """현재 한국 시간."""
    return datetime.now(KST)


def to_kst(dt: datetime) -> datetime:
    """datetime을 KST로 변환 (naive면 UTC로 간주)."""
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(KST)


def is_recent(dt: datetime, hours: int = 24) -> bool:
    """N시간 이내 뉴스인지."""
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return (now_kst() - to_kst(dt)) < timedelta(hours=hours)


# ============================================================
# 텍스트 처리
# ============================================================

def clean_html(text: str) -> str:
    """HTML 태그 제거 및 정리."""
    if not text:
        return ""
    # HTML 태그 제거
    text = re.sub(r"<[^>]+>", "", text)
    # HTML 엔티티 디코딩
    text = (
        text.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )
    # 다중 공백 정리
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_url(url: str) -> str:
    """URL 정규화 (쿼리 파라미터 일부 제거)."""
    # 트래킹 파라미터 제거
    url = re.sub(r"[?&](utm_[^=]+|fbclid|gclid)=[^&]*", "", url)
    url = re.sub(r"[?&]$", "", url)
    return url


# ============================================================
# 중복 제거
# ============================================================

def deduplicate_news(
    news_list: list[RawNews],
    similarity_threshold: int = 80,
) -> list[RawNews]:
    """뉴스 중복 제거 (URL 완전 일치 + 제목 유사도).

    Args:
        news_list: 중복 제거할 뉴스 목록
        similarity_threshold: 제목 유사도 임계값 (0~100)

    Returns:
        중복 제거된 뉴스 목록 (발행일 최신순 정렬)
    """
    if not news_list:
        return []

    # 1단계: URL 정규화 후 완전 일치 중복 제거
    seen_urls: set[str] = set()
    unique_by_url: list[RawNews] = []

    for news in news_list:
        normalized = normalize_url(news.url)
        if normalized not in seen_urls:
            seen_urls.add(normalized)
            news.url = normalized
            unique_by_url.append(news)

    # 2단계: 제목 유사도 기반 중복 제거
    # 발행일 최신순 정렬 (최신 뉴스를 살리고 오래된 중복 제거)
    unique_by_url.sort(key=lambda x: x.pub_date, reverse=True)

    final: list[RawNews] = []
    for news in unique_by_url:
        is_duplicate = False
        for existing in final:
            # 같은 소스 내에서만 비교 (다른 매체가 같은 사건 다루는 건 OK)
            if news.source == existing.source:
                similarity = fuzz.ratio(news.title, existing.title)
                if similarity >= similarity_threshold:
                    is_duplicate = True
                    # 기존 항목에 키워드 매칭 추가
                    existing.matched_keywords = list(
                        set(existing.matched_keywords + news.matched_keywords)
                    )
                    break

        if not is_duplicate:
            final.append(news)

    logger.info(
        f"중복 제거: {len(news_list)}건 → {len(unique_by_url)}건 (URL 기준) → "
        f"{len(final)}건 (제목 유사도 기준)"
    )
    return final


def truncate(text: str, max_len: int = 100) -> str:
    """텍스트 길이 제한."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
