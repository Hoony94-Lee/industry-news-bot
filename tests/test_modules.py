"""로컬 개별 모듈 테스트 스크립트.

사용법:
    python -m tests.test_modules collector   # 뉴스 수집만 테스트
    python -m tests.test_modules processor   # Claude 분석만 테스트 (수집 + 분석)
    python -m tests.test_modules notion      # Notion 저장 테스트 (수집 + 분석 + 저장)
    python -m tests.test_modules telegram    # 텔레그램 발송 테스트 (가상 데이터)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from dotenv import load_dotenv

from src.claude_processor import ClaudeNewsProcessor, filter_by_category_limit
from src.news_collector import collect_all_news
from src.notion_writer import NotionWriter
from src.telegram_sender import TelegramSender
from src.utils import KST, ProcessedNews, RawNews, logger


def test_collector() -> None:
    """뉴스 수집 테스트."""
    logger.info("뉴스 수집 테스트 시작")
    news_list = collect_all_news()
    logger.info(f"수집 결과: {len(news_list)}건")

    # 상위 5건 출력
    for i, news in enumerate(news_list[:5], 1):
        logger.info(f"\n[{i}] {news.title}")
        logger.info(f"    매체: {news.source}")
        logger.info(f"    발행: {news.pub_date.strftime('%Y-%m-%d %H:%M')}")
        logger.info(f"    키워드: {news.matched_keywords}")
        logger.info(f"    URL: {news.url}")


def test_processor() -> list[ProcessedNews]:
    """Claude 분석 테스트 (수집 포함)."""
    logger.info("Claude 분석 테스트 시작")
    news_list = collect_all_news()

    # 너무 많으면 시간 오래 걸리니 상위 10건만
    sample = news_list[:10]
    logger.info(f"분석 대상: {len(sample)}건 (전체 {len(news_list)}건 중 샘플)")

    processor = ClaudeNewsProcessor()
    processed = processor.analyze_batch(sample, max_workers=3)
    
    # 카테고리 제한
    final = filter_by_category_limit(processed, max_per_category=5)

    for i, news in enumerate(final, 1):
        logger.info(f"\n[{i}] {news.category} | 중요도 {news.importance}")
        logger.info(f"    헤드라인: {news.headline}")
        logger.info(f"    키워드: {news.keywords}")
        logger.info(f"    관련 종목: {news.related_companies}")

    return final


def test_notion() -> None:
    """Notion 저장 테스트."""
    processed = test_processor()
    if not processed:
        logger.warning("저장할 뉴스가 없습니다.")
        return

    writer = NotionWriter()
    writer.warm_up()
    saved = writer.save_batch(processed)
    logger.info(f"\n✅ Notion 저장 완료: {len(saved)}건")


def test_telegram() -> None:
    """텔레그램 발송 테스트 (가상 데이터)."""
    # 가상 뉴스 생성
    fake_raw = RawNews(
        title="SK하이닉스 SOCAMM2 양산 임박",
        url="https://example.com/test",
        source="전자신문",
        pub_date=datetime.now(KST),
        summary="SK하이닉스가 차세대 메모리 모듈 SOCAMM2 양산을 1분기 내 시작한다고 발표했다.",
        language="ko",
        matched_keywords=["SO-CAMM"],
    )
    
    fake_processed = ProcessedNews(
        raw=fake_raw,
        category="반도체",
        keywords=["SO-CAMM", "DRAM"],
        headline="SK하이닉스 SOCAMM2 1Q 양산 임박, 엔비디아 베라 루빈 공급망 선점",
        core="SK하이닉스 2026.1Q 내 SOCAMM2 양산 개시. 단일 모듈 256GB 용량 + 153.6GB/s 대역폭으로 기존 DDR5 압도. 엔비디아 베라 루빈 플랫폼 채택 확정.",
        meaning="AI 메모리 수퍼사이클 내 HBM에 이은 제2의 구조적 성장 카테고리 부상. RDIMM 서버 메모리 대체 가시화.",
        korea_impact="SK하이닉스 직접 수혜. 코스닥 PCB/모듈 검사 밸류체인(티엘비 등) 동반 수혜 기대. 메자닌 발행사 발굴 관점 주목.",
        related_companies=["SK하이닉스", "티엘비"],
        importance=5,
        evaluation="⭐ 핵심",
        notion_page_id="36da685f4383814988d3e7ed28cc93c3",
        matched_company_pages=[
            {
                "name": "SK하이닉스",
                "page_id": "abc",
                "ticker": "000660",
                "has_ir_note": False,
            },
            {
                "name": "티엘비",
                "page_id": "def",
                "ticker": "356860",
                "has_ir_note": False,
            },
        ],
    )

    sender = TelegramSender()
    sender.send_digest([fake_processed], mode="morning")
    logger.info("✅ 텔레그램 테스트 발송 완료")


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "module",
        choices=["collector", "processor", "notion", "telegram"],
        help="테스트할 모듈",
    )
    args = parser.parse_args()

    if args.module == "collector":
        test_collector()
    elif args.module == "processor":
        test_processor()
    elif args.module == "notion":
        test_notion()
    elif args.module == "telegram":
        test_telegram()


if __name__ == "__main__":
    main()
