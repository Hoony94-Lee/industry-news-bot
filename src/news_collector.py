"""뉴스 수집 모듈.

네이버 검색 API와 RSS 피드에서 뉴스를 수집합니다.
"""

from __future__ import annotations

import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import requests
import pytz

from .utils import (
    KST,
    RawNews,
    clean_html,
    deduplicate_news,
    get_env,
    is_recent,
    load_yaml_config,
    logger,
    now_kst,
)


# ============================================================
# 네이버 뉴스 API
# ============================================================

class NaverNewsCollector:
    """네이버 검색 API를 통한 뉴스 수집."""

    API_URL = "https://openapi.naver.com/v1/search/news.json"

    def __init__(self) -> None:
        self.client_id = get_env("NAVER_CLIENT_ID")
        self.client_secret = get_env("NAVER_CLIENT_SECRET")
        self.headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }

    def search(
        self,
        query: str,
        display: int = 10,
        sort: str = "date",
    ) -> list[dict[str, Any]]:
        """단일 키워드 검색."""
        params = {
            "query": query,
            "display": min(display, 100),
            "sort": sort,
        }

        try:
            response = requests.get(
                self.API_URL,
                headers=self.headers,
                params=params,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("items", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"네이버 API 검색 실패 ({query}): {e}")
            return []

    def parse_pub_date(self, date_str: str) -> datetime:
        """네이버 RFC 822 형식 → datetime (KST)."""
        try:
            dt = parsedate_to_datetime(date_str)
            if dt.tzinfo is None:
                dt = pytz.utc.localize(dt)
            return dt.astimezone(KST)
        except Exception as e:
            logger.warning(f"네이버 발행일 파싱 실패: {date_str} - {e}")
            return now_kst()

    def to_raw_news(self, item: dict[str, Any], keyword: str) -> RawNews:
        """네이버 API item → RawNews."""
        return RawNews(
            title=clean_html(item.get("title", "")),
            url=item.get("originallink") or item.get("link", ""),
            source=self._extract_source(item.get("originallink", "")),
            pub_date=self.parse_pub_date(item.get("pubDate", "")),
            summary=clean_html(item.get("description", "")),
            language="ko",
            matched_keywords=[keyword],
        )

    @staticmethod
    def _extract_source(url: str) -> str:
        """URL에서 매체명 추정."""
        if not url:
            return "Unknown"
        domain_map = {
            "etnews.com": "전자신문",
            "thelec.kr": "디일렉",
            "hankyung.com": "한국경제",
            "mk.co.kr": "매일경제",
            "sedaily.com": "서울경제",
            "edaily.co.kr": "이데일리",
            "fnnews.com": "파이낸셜뉴스",
            "mt.co.kr": "머니투데이",
            "heraldcorp.com": "헤럴드경제",
            "asiae.co.kr": "아시아경제",
            "zdnet.co.kr": "ZDNet Korea",
            "dt.co.kr": "디지털타임즈",
            "semianalysis.com": "SemiAnalysis",
            "reuters.com": "Reuters",
            "bloomberg.com": "Bloomberg",
            "wsj.com": "WSJ",
            "ft.com": "Financial Times",
            "nikkei.com": "Nikkei",
            "asia.nikkei.com": "Nikkei Asia",
        }
        for domain, name in domain_map.items():
            if domain in url:
                return name
        return "Other"

    def collect_by_keywords(
        self,
        keywords_config: dict[str, Any],
        max_age_hours: int = 24,
    ) -> list[RawNews]:
        """모든 키워드에 대해 네이버 뉴스 수집."""
        collected: list[RawNews] = []
        display = load_yaml_config("rss_sources.yml")["naver_settings"]["display"]

        for category_name, category_data in keywords_config["categories"].items():
            for keyword_name, keyword_data in category_data["keywords"].items():
                queries = keyword_data.get("search_queries", [])
                for query in queries:
                    items = self.search(query, display=display)
                    for item in items:
                        news = self.to_raw_news(item, keyword_name)
                        if is_recent(news.pub_date, hours=max_age_hours):
                            collected.append(news)
                    time.sleep(0.1)

        logger.info(f"네이버 뉴스 수집 완료: {len(collected)}건")
        return collected


# ============================================================
# RSS 수집
# ============================================================

class RSSCollector:
    """RSS 피드 수집."""

    def __init__(self) -> None:
        self.config = load_yaml_config("rss_sources.yml")
        self.user_agent = self.config["rss_settings"]["user_agent"]
        self.timeout = self.config["rss_settings"]["timeout"]
        self.max_items = self.config["rss_settings"]["max_items_per_feed"]

    def parse_feed(self, url: str, source_name: str, language: str) -> list[RawNews]:
        """단일 RSS 피드 파싱."""
        try:
            headers = {"User-Agent": self.user_agent}
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            feed = feedparser.parse(response.content)
            news_list: list[RawNews] = []

            for entry in feed.entries[: self.max_items]:
                try:
                    pub_date = self._parse_entry_date(entry)
                    news = RawNews(
                        title=clean_html(entry.get("title", "")),
                        url=entry.get("link", ""),
                        source=source_name,
                        pub_date=pub_date,
                        summary=clean_html(
                            entry.get("summary", "") or entry.get("description", "")
                        ),
                        language=language,
                        matched_keywords=[],
                    )
                    if news.title and news.url:
                        news_list.append(news)
                except Exception as e:
                    logger.warning(f"RSS entry 파싱 실패 ({source_name}): {e}")
                    continue

            return news_list
        except requests.exceptions.RequestException as e:
            logger.error(f"RSS 가져오기 실패 ({source_name}, {url}): {e}")
            return []

    def _parse_entry_date(self, entry: Any) -> datetime:
        """RSS entry의 발행일 파싱."""
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            dt = datetime(*entry.published_parsed[:6])
            return pytz.utc.localize(dt).astimezone(KST)
        if hasattr(entry, "updated_parsed") and entry.updated_parsed:
            dt = datetime(*entry.updated_parsed[:6])
            return pytz.utc.localize(dt).astimezone(KST)
        if hasattr(entry, "published"):
            try:
                return parsedate_to_datetime(entry.published).astimezone(KST)
            except Exception:
                pass
        return now_kst()

    def collect_all(self, max_age_hours: int = 24) -> list[RawNews]:
        """활성화된 모든 RSS 수집."""
        collected: list[RawNews] = []

        for source_key, source_data in self.config["sources"].items():
            if not source_data.get("enabled", True):
                continue

            url = source_data["url"]
            name = source_data["name"]
            language = source_data["language"]

            logger.info(f"RSS 수집 중: {name} ({url})")
            news_list = self.parse_feed(url, name, language)

            recent_news = [n for n in news_list if is_recent(n.pub_date, hours=max_age_hours)]
            collected.extend(recent_news)
            logger.info(f"  → {len(recent_news)}건 수집 (전체 {len(news_list)}건 중)")

        logger.info(f"RSS 수집 완료: 총 {len(collected)}건")
        return collected


# ============================================================
# 키워드 매칭 (RSS용)
# ============================================================

def match_keywords_to_news(
    news_list: list[RawNews],
    keywords_config: dict[str, Any],
) -> list[RawNews]:
    """RSS로 수집된 뉴스에 키워드 매칭."""
    matched: list[RawNews] = []

    all_search_terms: dict[str, list[str]] = {}
    for category_data in keywords_config["categories"].values():
        for keyword_name, keyword_data in category_data["keywords"].items():
            terms = []
            terms.extend(keyword_data.get("search_queries", []))
            terms.extend(keyword_data.get("english_queries", []))
            all_search_terms[keyword_name] = terms

    for news in news_list:
        haystack = (news.title + " " + news.summary).lower()
        matched_kws = []

        for keyword_name, terms in all_search_terms.items():
            for term in terms:
                if term.lower() in haystack:
                    matched_kws.append(keyword_name)
                    break

        if matched_kws:
            news.matched_keywords = list(set(news.matched_keywords + matched_kws))
            matched.append(news)

    logger.info(f"키워드 매칭: {len(news_list)}건 → {len(matched)}건 (키워드 매칭됨)")
    return matched


# ============================================================
# 화이트리스트 + 블랙리스트 필터링
# ============================================================

def filter_by_whitelist_and_blacklist(news_list: list[RawNews]) -> list[RawNews]:
    """화이트리스트(허용 도메인) + 블랙리스트(제외 키워드) 필터링."""
    rss_config = load_yaml_config("rss_sources.yml")
    
    # 화이트리스트
    whitelist_cfg = rss_config.get("source_whitelist", {})
    whitelist_enabled = whitelist_cfg.get("enabled", False)
    allowed_domains = whitelist_cfg.get("domains", [])
    
    # 블랙리스트 키워드
    blacklist_cfg = rss_config.get("source_blacklist", {})
    blocked_keywords = blacklist_cfg.get("keywords_in_title", [])
    
    filtered: list[RawNews] = []
    removed_by_whitelist = 0
    removed_by_keyword = 0
    
    for news in news_list:
        url_lower = news.url.lower()
        
        # 1) 화이트리스트 체크
        if whitelist_enabled and allowed_domains:
            if not any(domain in url_lower for domain in allowed_domains):
                removed_by_whitelist += 1
                continue
        
        # 2) 제목 키워드 블랙리스트 체크
        title_lower = news.title.lower()
        if any(kw.lower() in title_lower for kw in blocked_keywords):
            removed_by_keyword += 1
            continue
        
        filtered.append(news)
    
    if removed_by_whitelist or removed_by_keyword:
        logger.info(
            f"필터링: 화이트리스트 외 {removed_by_whitelist}건, "
            f"키워드 제외 {removed_by_keyword}건 → {len(filtered)}건 남음"
        )
    
    return filtered


# ============================================================
# 통합 수집기
# ============================================================

def collect_all_news() -> list[RawNews]:
    """전체 뉴스 수집 + 중복 제거 + 필터링."""
    keywords_config = load_yaml_config("keywords.yml")
    max_age = keywords_config["filter"]["max_age_hours"]
    similarity = keywords_config["filter"]["similarity_threshold"]

    # 1. 네이버 뉴스 수집
    logger.info("=" * 60)
    logger.info("📡 네이버 뉴스 수집 시작")
    logger.info("=" * 60)
    naver = NaverNewsCollector()
    naver_news = naver.collect_by_keywords(keywords_config, max_age_hours=max_age)

    # 2. RSS 수집
    logger.info("=" * 60)
    logger.info("📡 RSS 수집 시작")
    logger.info("=" * 60)
    rss = RSSCollector()
    rss_news_raw = rss.collect_all(max_age_hours=max_age)
    rss_news = match_keywords_to_news(rss_news_raw, keywords_config)

    # 3. 통합 + 중복 제거
    all_news = naver_news + rss_news
    logger.info(f"통합 전: {len(all_news)}건 (네이버 {len(naver_news)}, RSS {len(rss_news)})")

    deduplicated = deduplicate_news(all_news, similarity_threshold=similarity)
    
    # 4. 화이트리스트 + 블랙리스트 필터 적용
    final = filter_by_whitelist_and_blacklist(deduplicated)
    
    return final
