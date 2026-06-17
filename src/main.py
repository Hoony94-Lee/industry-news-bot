"""main.py 에 반영할 코드.

1) import 에 NotionWriter, is_duplicate_of_archive 추가
2) filter_already_sent() 함수 신규 추가
3) run_pipeline() Step 1 과 Step 2 사이에 중복 필터 단계 삽입
"""

# ─────────────────────────────────────────────────────────────
# 1) import 부 (기존 import에 추가/확인)
# ─────────────────────────────────────────────────────────────
#
#   from .utils import is_duplicate_of_archive   # 신규
#   (NotionWriter 는 이미 import 되어 있음)


# ─────────────────────────────────────────────────────────────
# 2) 신규 함수 (run_pipeline 위에 정의)
# ─────────────────────────────────────────────────────────────

def filter_already_sent(raw_news: list, writer) -> list:
    """과거(최근 N일) 발송분과 중복되는 뉴스를 제거.

    Claude 분석 '전'에 호출 → Haiku 호출 비용 절감.

    Args:
        raw_news: 수집된 RawNews 목록
        writer: load_recent_archive() 가 호출된 NotionWriter 인스턴스
    """
    from .utils import is_duplicate_of_archive

    if not writer._archive_urls and not writer._archive_titles:
        return raw_news

    kept: list = []
    removed = 0
    for news in raw_news:
        if is_duplicate_of_archive(
            news.title,
            news.url,
            writer._archive_urls,
            writer._archive_titles,
        ):
            removed += 1
            continue
        kept.append(news)

    logger.info(
        f"과거 발송분 중복 제거: {len(raw_news)}건 → {len(kept)}건 "
        f"(제거 {removed}건)"
    )
    return kept


# ─────────────────────────────────────────────────────────────
# 3) run_pipeline() Step 1 직후에 삽입할 블록
#    (raw_news = collect_all_news() 다음, processor 생성 전)
# ─────────────────────────────────────────────────────────────
#
#         # ============================================================
#         # Step 1.5: 과거 발송분 중복 제거 (분석 전 → Haiku 비용 절감)
#         # ============================================================
#         logger.info("\n[Step 1.5/4] 🔁 과거 발송분 중복 제거")
#         writer = NotionWriter()
#         writer.warm_up()
#         writer.load_recent_archive(days=3)
#         raw_news = filter_already_sent(raw_news, writer)
#         if not raw_news:
#             logger.warning("신규 뉴스가 없습니다(전부 기발송). 종료.")
#             return 0
#
#  ※ 이렇게 하면 Step 3의 NotionWriter()/warm_up() 은 중복이므로,
#    Step 3에서 writer 를 재생성하지 말고 위에서 만든 writer 를 그대로
#    재사용하세요. (warm_up 캐시도 이미 채워져 있어 효율적)
