"""notion_writer.py 에 추가할 코드.

NotionWriter 클래스 안에 아래 두 가지를 반영하세요.
1) __init__ 끝에 캐시 필드 2개 추가
2) load_recent_archive() 메서드 신규 추가
"""

# ─────────────────────────────────────────────────────────────
# 1) __init__ 의 캐시 선언부에 아래 2줄 추가
# ─────────────────────────────────────────────────────────────
#
#   self._archive_urls: set[str] = set()          # 최근 발송분 정규화 URL
#   self._archive_titles: list[str] = []          # 최근 발송분 정규화 제목
#
# (기존 self._ir_note_cache 선언 아래에 넣으면 됩니다)


# ─────────────────────────────────────────────────────────────
# 2) 메서드 신규 추가 (warm_up 근처에 배치)
# ─────────────────────────────────────────────────────────────

def load_recent_archive(self, days: int = 3) -> None:
    """News Archive에서 최근 N일치 발송분의 URL/제목을 캐시.

    main.py 의 수집 직후 중복 필터에서 사용.
    """
    from datetime import timedelta
    from .utils import normalize_url, normalize_title, now_kst

    since = (now_kst() - timedelta(days=days)).strftime("%Y-%m-%d")
    db_id = self.db_ids["news_archive"]

    results: list = []
    cursor = None
    while True:
        kwargs: dict = {
            "database_id": db_id,
            "page_size": 100,
            "filter": {
                "property": "발행일",
                "date": {"on_or_after": since},
            },
        }
        if cursor:
            kwargs["start_cursor"] = cursor
        try:
            resp = self.client.databases.query(**kwargs)
        except Exception as e:
            logger.warning(f"아카이브 캐시 로드 실패: {e}")
            break
        results.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")

    for page in results:
        props = page.get("properties", {})
        # 원문 URL
        url_val = props.get("원문 URL", {}).get("url") or ""
        if url_val:
            self._archive_urls.add(normalize_url(url_val))
        # 제목
        title_items = props.get("제목", {}).get("title", [])
        title_txt = "".join(i.get("plain_text", "") for i in title_items)
        n = normalize_title(title_txt)
        if n:
            self._archive_titles.append(n)

    logger.info(
        f"아카이브 캐시 로드(최근 {days}일): "
        f"URL {len(self._archive_urls)}건, 제목 {len(self._archive_titles)}건"
    )
