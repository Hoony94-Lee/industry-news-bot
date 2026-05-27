"""Claude API를 사용한 뉴스 분석 모듈."""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from anthropic import Anthropic
from anthropic import RateLimitError, APIError

from .utils import (
    ProcessedNews,
    RawNews,
    get_env,
    load_prompt,
    load_yaml_config,
    logger,
)


# Haiku 4.5
CLAUDE_MODEL = "claude-haiku-4-5-20251001"


class ClaudeNewsProcessor:
    """Claude API로 뉴스를 가공."""

    def __init__(self) -> None:
        api_key = get_env("ANTHROPIC_API_KEY")
        self.client = Anthropic(api_key=api_key)
        self.prompt_template = load_prompt("news_analysis.md")
        
        config = load_yaml_config("keywords.yml")["filter"]
        self.min_importance = config["min_importance"]
        self.max_news_for_analysis = config.get("max_news_for_analysis", 40)
        self.max_workers = config.get("claude_max_workers", 2)
        self.request_delay = config.get("claude_request_delay", 1.5)

    def _build_user_prompt(self, news: RawNews) -> str:
        return self.prompt_template.format(
            title=news.title,
            summary=news.summary[:800],
            source=news.source,
            pub_date=news.pub_date.strftime("%Y-%m-%d %H:%M"),
            url=news.url,
        )

    def _extract_system_prompt(self) -> str:
        match = re.search(
            r"## System Prompt\s*\n(.*?)(?=## User Prompt Template)",
            self.prompt_template,
            re.DOTALL,
        )
        if match:
            return match.group(1).strip()
        return "당신은 한국 ECM 담당자의 산업 리서치 어시스턴트입니다."

    def _extract_json(self, content: str) -> dict | None:
        """응답 텍스트에서 JSON 객체를 강건하게 추출.
        
        Haiku 모델이 JSON 뒤에 부연 설명을 붙이거나, 
        마크다운 fence를 추가하는 경우에 대응.
        """
        if not content:
            return None
        
        # 1) 마크다운 코드 fence 제거
        content = re.sub(r"^```(?:json)?\s*", "", content.strip())
        content = re.sub(r"\s*```$", "", content)
        content = content.strip()
        
        # 2) 일반적인 JSON 파싱 시도
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # 3) 첫 번째 완전한 JSON 객체만 추출 (중괄호 매칭)
        start = content.find('{')
        if start == -1:
            return None
        
        depth = 0
        end = -1
        in_string = False
        escape_next = False
        
        for i in range(start, len(content)):
            char = content[i]
            
            if escape_next:
                escape_next = False
                continue
            
            if char == '\\':
                escape_next = True
                continue
            
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            
            if in_string:
                continue
            
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        
        if end == -1:
            return None
        
        json_str = content[start:end]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.debug(f"JSON 추출 실패: {e}, 내용: {json_str[:200]}")
            return None

    def analyze_one(self, news: RawNews) -> ProcessedNews | None:
        """단일 뉴스 분석."""
        system_prompt = self._extract_system_prompt()
        user_prompt = self._build_user_prompt(news)

        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = self.client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=800,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                content = response.content[0].text

                data = self._extract_json(content)
                if data is None:
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"JSON 추출 실패 (attempt {attempt + 1}/{max_retries}), 재시도..."
                        )
                        time.sleep(1)
                        continue
                    logger.warning(f"JSON 추출 최종 실패: {news.title[:40]}")
                    return None

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

            except RateLimitError as e:
                wait_time = 30
                logger.warning(
                    f"Rate limit 발생 (attempt {attempt + 1}/{max_retries}), "
                    f"{wait_time}초 대기..."
                )
                time.sleep(wait_time)
                continue

            except Exception as e:
                logger.error(f"Claude API 에러: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                continue

        logger.error(f"뉴스 분석 실패: {news.title[:50]}")
        return None

    def _prefilter_news(self, news_list: list[RawNews]) -> list[RawNews]:
        """Claude 호출 전 사전 필터링."""
        sorted_news = sorted(
            news_list,
            key=lambda x: (len(x.matched_keywords), x.pub_date),
            reverse=True,
        )
        
        limited = sorted_news[:self.max_news_for_analysis]
        
        if len(news_list) > self.max_news_for_analysis:
            logger.info(
                f"사전 필터링: {len(news_list)}건 → {self.max_news_for_analysis}건"
            )
        
        return limited

    def analyze_batch(
        self,
        news_list: list[RawNews],
        max_workers: int | None = None,
    ) -> list[ProcessedNews]:
        """여러 뉴스 분석."""
        if not news_list:
            return []

        news_list = self._prefilter_news(news_list)
        workers = max_workers if max_workers else self.max_workers

        logger.info(
            f"Claude 분석 시작: {len(news_list)}건 "
            f"(병렬 {workers}, 요청 간격 {self.request_delay}초, 모델 Haiku)"
        )
        processed_list: list[ProcessedNews] = []

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_news = {}
            for news in news_list:
                future = executor.submit(self.analyze_one, news)
                future_to_news[future] = news
                time.sleep(self.request_delay)
            
            for i, future in enumerate(as_completed(future_to_news), 1):
                result = future.result()
                if result and result.importance >= self.min_importance:
                    processed_list.append(result)

                if i % 10 == 0:
                    logger.info(f"  진행: {i}/{len(news_list)} (분석 성공 {len(processed_list)})")

        processed_list.sort(key=lambda x: x.importance, reverse=True)

        logger.info(
            f"Claude 분석 완료: {len(news_list)}건 → {len(processed_list)}건 "
            f"(중요도 {self.min_importance} 이상)"
        )
        return processed_list


def filter_by_category_limit(
    processed_list: list[ProcessedNews],
    max_per_category: int = 2,
) -> list[ProcessedNews]:
    """카테고리당 최대 N건으로 제한."""
    by_category: dict[str, list[ProcessedNews]] = {}
    for news in processed_list:
        by_category.setdefault(news.category, []).append(news)

    final: list[ProcessedNews] = []
    for category, items in by_category.items():
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
