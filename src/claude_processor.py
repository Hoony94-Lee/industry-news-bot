"""Claude API를 사용한 뉴스 분석 모듈."""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from anthropic import Anthropic

from .utils import (
    ProcessedNews,
    RawNews,
    get_env,
    load_prompt,
    load_yaml_config,
    logger,
)


# Claude 모델 (Sonnet 4 - 비용/성능 균형)
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"


class ClaudeNewsProcessor:
    """Claude API로 뉴스를 가공."""

    def __init__(self) -> None:
        api_key = get_env("ANTHROPIC_API_KEY")
        self.client = Anthropic(api_key=api_key)
        self.prompt_template = load_prompt("news_analysis.md")
        self.min_importance = load_yaml_config("keywords.yml")["filter"][
            "min_importance"
        ]

    def _build_user_prompt(self, news: RawNews) -> str:
        """뉴스 정보를 프롬프트에 주입."""
        # 프롬프트 템플릿에서 User Prompt 부분만 추출
        # (간단히 변수 치환만 수행)
        return self.prompt_template.format(
            title=news.title,
            summary=news.summary[:1500],  # 너무 길면 자르기
            source=news.source,
            pub_date=news.pub_date.strftime("%Y-%m-%d %H:%M"),
            url=news.url,
        )

    def _extract_system_prompt(self) -> str:
        """프롬프트 파일에서 System Prompt 부분 추출."""
        # ## System Prompt ~ ## User Prompt Template 사이
        match = re.search(
            r"## System Prompt\s*\n(.*?)(?=## User Prompt Template)",
            self.prompt_template,
            re.DOTALL,
        )
        if match:
            return match.group(1).strip()
        # 폴백: 첫 부분
        return "당신은 한국 ECM 담당자의 산업 리서치 어시스턴트입니다."

    def analyze_one(self, news: RawNews) -> ProcessedNews | None:
        """단일 뉴스 분석.

        Returns:
            ProcessedNews 또는 None (분석 실패 시)
        """
        system_prompt = self._extract_system_prompt()
        user_prompt = self._build_user_prompt(news)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=2000,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                content = response.content[0].text

                # JSON 추출 (혹시 마크다운 fence가 있으면 제거)
                content = re.sub(r"^```(?:json)?\s*", "", content.strip())
                content = re.sub(r"\s*```$", "", content)

                data = json.loads(content)

                # ProcessedNews 생성
                processed = ProcessedNews(
                    raw=news,
                    category=data.get("category", "반도체"),
                    keywords=data.get("keywords", []),
                    headline=data.get("headline", news.title)[:200],
                    core=data.get("core", ""),
                    meaning=data.get("meaning", ""),
                    korea_impact=data.get("korea_impact", ""),
                    related_companies=data.get("related_companies", []),
                    importance=int(data.get("importance", 3)),
                    evaluation=data.get("evaluation", "미평가"),
                )
                return processed

            except json.JSONDecodeError as e:
                logger.warning(
                    f"JSON 파싱 실패 (attempt {attempt + 1}/{max_retries}): {e}"
                )
                logger.debug(f"응답 내용: {content[:200]}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                continue
            except Exception as e:
                logger.error(f"Claude API 호출 실패: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # exponential backoff
                continue

        logger.error(f"뉴스 분석 실패 (최대 재시도 초과): {news.title[:50]}")
        return None

    def analyze_batch(
        self,
        news_list: list[RawNews],
        max_workers: int = 5,
    ) -> list[ProcessedNews]:
        """여러 뉴스 병렬 분석.

        Args:
            news_list: 분석할 뉴스 목록
            max_workers: 동시 API 호출 수

        Returns:
            성공적으로 분석된 ProcessedNews 목록 (중요도 필터 적용)
        """
        if not news_list:
            return []

        logger.info(f"Claude 분석 시작: {len(news_list)}건 (병렬 {max_workers})")
        processed_list: list[ProcessedNews] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_news = {
                executor.submit(self.analyze_one, news): news for news in news_list
            }
            for i, future in enumerate(as_completed(future_to_news), 1):
                result = future.result()
                if result and result.importance >= self.min_importance:
                    processed_list.append(result)

                if i % 10 == 0:
                    logger.info(f"  진행: {i}/{len(news_list)}")

        # 중요도 내림차순 정렬
        processed_list.sort(key=lambda x: x.importance, reverse=True)

        logger.info(
            f"Claude 분석 완료: {len(news_list)}건 → {len(processed_list)}건 "
            f"(중요도 {self.min_importance} 이상)"
        )
        return processed_list


def filter_by_category_limit(
    processed_list: list[ProcessedNews],
    max_per_category: int = 5,
) -> list[ProcessedNews]:
    """카테고리당 최대 N건으로 제한 (중요도 높은 순).

    Args:
        processed_list: 분석된 뉴스 목록
        max_per_category: 카테고리당 최대 건수

    Returns:
        카테고리당 max_per_category건으로 제한된 목록
    """
    by_category: dict[str, list[ProcessedNews]] = {}
    for news in processed_list:
        by_category.setdefault(news.category, []).append(news)

    final: list[ProcessedNews] = []
    for category, items in by_category.items():
        # 중요도 + 키워드 매칭 수로 정렬
        items.sort(
            key=lambda x: (x.importance, len(x.keywords)),
            reverse=True,
        )
        final.extend(items[:max_per_category])

    final.sort(key=lambda x: (x.importance, x.category), reverse=True)
    logger.info(
        f"카테고리 제한 적용: {len(processed_list)}건 → {len(final)}건 "
        f"(카테고리당 최대 {max_per_category}건)"
    )
    return final
