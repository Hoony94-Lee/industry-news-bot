"""utils.py 교체/추가 코드 모음.

아래 내용으로 기존 utils.py의 해당 부분을 교체하거나 추가하세요.
- normalize_title()        : 신규 추가
- deduplicate_news()       : 기존 함수 교체
- is_duplicate_of_archive(): 신규 추가 (과거 발송분 비교용 헬퍼)
"""

from __future__ import annotations

import re
from rapidfuzz import fuzz


# ============================================================
# [신규] 제목 정규화
# ============================================================

# 머리말/꼬리말 패턴: [속보] [단독] [종합] (종합2보) 등
_BRACKET_RE = re.compile(r"[\[\(<【［][^\]\)>】］]{0,12}[\]\)>】］]")
# 매체명 꼬리: " - 전자신문", " | 한국경제" 등
_TAIL_SOURCE_RE = re.compile(r"\s*[-|·ㅣ]\s*[^-|·ㅣ]{1,15}$")
# 한글/영문/숫자/공백 외 제거 (공백은 유지 → 토큰 비교 정확도 ↑)
_NON_ALNUM_RE = re.compile(r"[^0-9a-z가-힣\s]")
_MULTISPACE_RE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """제목 정규화: 머리말/매체명/특수문자 제거 후 소문자화(공백은 유지).

    교차 매체 비교 정확도를 높이기 위함.
    예: "[속보] SK하이닉스, HBM4 양산 돌입 - 전자신문"
        → "sk하이닉스 hbm4 양산 돌입"
    """
    if not title:
        return ""
    t = title.strip()
    # 대괄호/소괄호 머리말 반복 제거
    prev = None
    while prev != t:
        prev = t
        t = _BRACKET_RE.sub("", t).strip()
    # 끝부분 매체명 꼬리 제거
    t = _TAIL_SOURCE_RE.sub("", t).strip()
    # 소문자화 후 영숫자/한글/공백만 남김
    t = t.lower()
    t = _NON_ALNUM_RE.sub(" ", t)
    t = _MULTISPACE_RE.sub(" ", t).strip()
    return t


# ============================================================
# [교체] 중복 제거
# ============================================================

def deduplicate_news(
    news_list: list,
    similarity_threshold: int = 80,
    cross_source_threshold: int | None = None,
) -> list:
    """뉴스 중복 제거 (URL 완전 일치 + 제목 유사도, 교차 매체 포함).

    Args:
        news_list: 중복 제거할 뉴스 목록 (RawNews)
        similarity_threshold: 동일 매체 내 제목 유사도 임계값 (0~100)
        cross_source_threshold: 서로 다른 매체 간 제목 유사도 임계값.
            None이면 similarity_threshold + 7 로 자동 설정(약간 더 엄격).

    Returns:
        중복 제거된 뉴스 목록 (발행일 최신순 정렬)
    """
    if not news_list:
        return []

    if cross_source_threshold is None:
        cross_source_threshold = min(similarity_threshold + 7, 100)

    # 1단계: URL 정규화 후 완전 일치 중복 제거
    seen_urls: set[str] = set()
    unique_by_url: list = []
    for news in news_list:
        normalized = normalize_url(news.url)
        if normalized and normalized not in seen_urls:
            seen_urls.add(normalized)
            news.url = normalized
            unique_by_url.append(news)

    # 2단계: 제목 유사도 기반 중복 제거 (동일 매체 + 교차 매체 모두)
    unique_by_url.sort(key=lambda x: x.pub_date, reverse=True)

    final: list = []
    norm_cache: list[str] = []  # final과 같은 인덱스의 정규화 제목

    for news in unique_by_url:
        n_title = normalize_title(news.title)
        is_duplicate = False

        for idx, existing in enumerate(final):
            e_title = norm_cache[idx]
            # token_set_ratio: 어순/일부 단어 차이에 강함 (교차매체 대응)
            sim = fuzz.token_set_ratio(n_title, e_title)
            same_source = (news.source == existing.source)
            threshold = similarity_threshold if same_source else cross_source_threshold

            if sim >= threshold:
                is_duplicate = True
                existing.matched_keywords = list(
                    set(existing.matched_keywords + news.matched_keywords)
                )
                break

        if not is_duplicate:
            final.append(news)
            norm_cache.append(n_title)

    logger.info(
        f"중복 제거: {len(news_list)}건 → {len(unique_by_url)}건 (URL) → "
        f"{len(final)}건 (제목 유사도, 동일매체 {similarity_threshold}/"
        f"교차매체 {cross_source_threshold})"
    )
    return final


# ============================================================
# [신규] 과거 발송분(아카이브) 대비 중복 판정
# ============================================================

def is_duplicate_of_archive(
    title: str,
    url: str,
    archive_urls: set[str],
    archive_titles: list[str],
    similarity_threshold: int = 82,
) -> bool:
    """기수집/발송된 아카이브와 중복인지 판정.

    Args:
        title: 검사할 뉴스 제목
        url: 검사할 뉴스 URL (정규화된 값 권장)
        archive_urls: 과거 발송분 정규화 URL 집합
        archive_titles: 과거 발송분 정규화 제목 리스트
        similarity_threshold: 제목 유사도 임계값

    Returns:
        중복이면 True
    """
    norm_u = normalize_url(url)
    if norm_u and norm_u in archive_urls:
        return True

    n_title = normalize_title(title)
    if not n_title:
        return False
    for a_title in archive_titles:
        if fuzz.token_set_ratio(n_title, a_title) >= similarity_threshold:
            return True
    return False
