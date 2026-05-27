"""Notion DB 저장 모듈.

News Archive에 뉴스를 저장하고 상장사 마스터/Industry Tracker와 Relation 연결.
"""

from __future__ import annotations

from typing import Any

from notion_client import Client

from .utils import (
    ProcessedNews,
    get_env,
    load_yaml_config,
    logger,
    now_kst,
    truncate,
)


class NotionWriter:
    """Notion DB 작성기."""

    def __init__(self) -> None:
        self.client = Client(auth=get_env("NOTION_TOKEN"))
        self.config = load_yaml_config("notion_ids.yml")
        self.db_ids = {k: v["id"] for k, v in self.config["databases"].items()}

        # 캐시
        self._company_cache: dict[str, dict[str, Any]] = {}  # 종목명 → page info
        self._theme_cache: dict[str, str] = {}  # 키워드 → Industry Tracker page_id
        self._ir_note_cache: set[str] = set()  # 탐방노트 있는 종목코드

    # ============================================================
    # 캐시 로딩 (시작 시 1회)
    # ============================================================

    def warm_up(self) -> None:
        """시작 시 상장사 마스터 / Industry Tracker / 탐방노트 캐시."""
        logger.info("Notion 캐시 워밍업...")
        self._load_company_cache()
        self._load_theme_cache()
        self._load_ir_note_cache()
        logger.info(
            f"캐시 완료: 상장사 {len(self._company_cache)}개, "
            f"테마 {len(self._theme_cache)}개, "
            f"탐방노트 보유 종목 {len(self._ir_note_cache)}개"
        )

    def _load_company_cache(self) -> None:
        """상장사 마스터 전체 로드."""
        results = self._query_database_all(self.db_ids["company_master"])
        for page in results:
            props = page.get("properties", {})
            name = self._get_title(props.get("기업명", {}))
            code = self._get_rich_text(props.get("종목코드", {}))
            if name:
                self._company_cache[name] = {
                    "page_id": page["id"],
                    "ticker": code,
                    "url": page.get("url", ""),
                }

    def _load_theme_cache(self) -> None:
        """Industry Tracker 전체 로드 (테마명 → page_id 매핑)."""
        results = self._query_database_all(self.db_ids["industry_tracker"])
        for page in results:
            props = page.get("properties", {})
            theme_name = self._get_title(props.get("테마명", {}))
            if theme_name:
                self._theme_cache[theme_name] = page["id"]

    def _load_ir_note_cache(self) -> None:
        """탐방노트 있는 종목코드 집합."""
        results = self._query_database_all(self.db_ids["ir_meeting_notes"])
        for page in results:
            props = page.get("properties", {})
            code = self._get_rich_text(props.get("종목코드", {}))
            if code:
                self._ir_note_cache.add(code)

    def _query_database_all(self, database_id: str) -> list[dict[str, Any]]:
        """DB의 모든 페이지 조회 (pagination 처리)."""
        results: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            kwargs: dict[str, Any] = {"database_id": database_id, "page_size": 100}
            if cursor:
                kwargs["start_cursor"] = cursor

            response = self.client.databases.query(**kwargs)
            results.extend(response.get("results", []))

            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")

        return results

    # ============================================================
    # 헬퍼: property 값 추출
    # ============================================================

    @staticmethod
    def _get_title(prop: dict[str, Any]) -> str:
        title_items = prop.get("title", [])
        return "".join(item.get("plain_text", "") for item in title_items)

    @staticmethod
    def _get_rich_text(prop: dict[str, Any]) -> str:
        rt_items = prop.get("rich_text", [])
        return "".join(item.get("plain_text", "") for item in rt_items)

    # ============================================================
    # 종목명 매칭
    # ============================================================

    def match_companies(self, company_names: list[str]) -> list[dict[str, Any]]:
        """ProcessedNews의 related_companies → 상장사 마스터 페이지 매칭.

        Returns:
            매칭된 종목 정보 [{"name", "page_id", "ticker", "has_ir_note"}, ...]
        """
        matched: list[dict[str, Any]] = []
        for name in company_names:
            # 정확 일치 우선
            if name in self._company_cache:
                info = self._company_cache[name]
                matched.append({
                    "name": name,
                    "page_id": info["page_id"],
                    "ticker": info["ticker"],
                    "has_ir_note": info["ticker"] in self._ir_note_cache,
                })
                continue

            # "(추측)" 같은 접미사 제거 후 재시도
            cleaned = name.replace("(추측)", "").strip()
            if cleaned in self._company_cache:
                info = self._company_cache[cleaned]
                matched.append({
                    "name": cleaned,
                    "page_id": info["page_id"],
                    "ticker": info["ticker"],
                    "has_ir_note": info["ticker"] in self._ir_note_cache,
                })
                continue

            # 부분 일치 (포함관계)
            for master_name in self._company_cache:
                if master_name in cleaned or cleaned in master_name:
                    info = self._company_cache[master_name]
                    matched.append({
                        "name": master_name,
                        "page_id": info["page_id"],
                        "ticker": info["ticker"],
                        "has_ir_note": info["ticker"] in self._ir_note_cache,
                    })
                    break

        return matched

    def match_themes(self, keywords: list[str]) -> list[str]:
        """ProcessedNews의 keywords → Industry Tracker page_id 매칭."""
        page_ids: list[str] = []
        for kw in keywords:
            if kw in self._theme_cache:
                page_ids.append(self._theme_cache[kw])
        return page_ids

    # ============================================================
    # News Archive 저장
    # ============================================================

    def save_news(self, processed: ProcessedNews) -> str:
        """News Archive에 뉴스 저장.

        Returns:
            생성된 페이지 ID
        """
        # Relation 매칭
        matched_companies = self.match_companies(processed.related_companies)
        processed.matched_company_pages = matched_companies
        company_page_ids = [c["page_id"] for c in matched_companies]
        theme_page_ids = self.match_themes(processed.keywords)

        # Properties 구성
        properties = self._build_news_properties(
            processed, company_page_ids, theme_page_ids
        )

        try:
            response = self.client.pages.create(
                parent={"database_id": self.db_ids["news_archive"]},
                icon={"emoji": self._get_emoji(processed.importance)},
                properties=properties,
            )
            page_id = response["id"]
            processed.notion_page_id = page_id
            logger.info(
                f"  ✅ Notion 저장: {truncate(processed.headline, 40)} "
                f"(종목 {len(matched_companies)}, 테마 {len(theme_page_ids)})"
            )
            return page_id
        except Exception as e:
            logger.error(f"Notion 저장 실패: {e}")
            logger.debug(f"문제 뉴스: {processed.headline}")
            return ""

    def _build_news_properties(
        self,
        processed: ProcessedNews,
        company_page_ids: list[str],
        theme_page_ids: list[str],
    ) -> dict[str, Any]:
        """News Archive properties 구성."""
        # 발행일 (KST)
        pub_date_str = processed.raw.pub_date.strftime("%Y-%m-%d")

        properties: dict[str, Any] = {
            "제목": {
                "title": [{"text": {"content": truncate(processed.headline, 200)}}]
            },
            "카테고리": {"select": {"name": processed.category}},
            "세부 키워드": {
                "multi_select": [{"name": kw} for kw in processed.keywords]
            },
            "헤드라인": {
                "rich_text": [{"text": {"content": truncate(processed.headline, 1900)}}]
            },
            "핵심": {
                "rich_text": [{"text": {"content": truncate(processed.core, 1900)}}]
            },
            "의미": {
                "rich_text": [{"text": {"content": truncate(processed.meaning, 1900)}}]
            },
            "한국 시사점": {
                "rich_text": [
                    {"text": {"content": truncate(processed.korea_impact, 1900)}}
                ]
            },
            "중요도": {"select": {"name": str(processed.importance)}},
            "평가": {"select": {"name": processed.evaluation}},
            "출처 매체": {
                "rich_text": [{"text": {"content": processed.raw.source[:100]}}]
            },
            "원문 URL": {"url": processed.raw.url[:500]},
            "발행일": {"date": {"start": pub_date_str}},
        }

        # Relation 추가
        if company_page_ids:
            properties["관련 종목"] = {
                "relation": [{"id": pid} for pid in company_page_ids]
            }
        if theme_page_ids:
            properties["관련 테마"] = {
                "relation": [{"id": pid} for pid in theme_page_ids]
            }

        return properties

    @staticmethod
    def _get_emoji(importance: int) -> str:
        """중요도에 따른 이모지."""
        return {
            5: "🔥",
            4: "⭐",
            3: "📰",
            2: "📄",
            1: "📋",
        }.get(importance, "📰")

    # ============================================================
    # Industry Tracker 업데이트
    # ============================================================

    def update_theme_last_seen(self, processed_list: list[ProcessedNews]) -> None:
        """관련 테마들의 '최근 업데이트' 날짜 갱신."""
        today = now_kst().strftime("%Y-%m-%d")
        updated_themes: set[str] = set()

        for news in processed_list:
            for kw in news.keywords:
                if kw in self._theme_cache and kw not in updated_themes:
                    page_id = self._theme_cache[kw]
                    try:
                        self.client.pages.update(
                            page_id=page_id,
                            properties={
                                "최근 업데이트": {"date": {"start": today}},
                            },
                        )
                        updated_themes.add(kw)
                    except Exception as e:
                        logger.warning(f"테마 업데이트 실패 ({kw}): {e}")

        logger.info(f"Industry Tracker 갱신: {len(updated_themes)}개 테마")

    # ============================================================
    # 일괄 저장
    # ============================================================

    def save_batch(self, processed_list: list[ProcessedNews]) -> list[ProcessedNews]:
        """여러 뉴스 일괄 저장.

        Returns:
            성공적으로 저장된 뉴스 목록 (notion_page_id, matched_company_pages 채워짐)
        """
        if not processed_list:
            return []

        logger.info("=" * 60)
        logger.info(f"📝 Notion 저장 시작: {len(processed_list)}건")
        logger.info("=" * 60)

        saved: list[ProcessedNews] = []
        for news in processed_list:
            page_id = self.save_news(news)
            if page_id:
                saved.append(news)

        # Industry Tracker 갱신
        if saved:
            self.update_theme_last_seen(saved)

        logger.info(f"Notion 저장 완료: {len(saved)}/{len(processed_list)}건")
        return saved
