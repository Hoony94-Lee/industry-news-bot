"""Industry News Bot 메인 진입점.

사용법:
    python -m src.main --mode morning
    python -m src.main --mode evening
    python -m src.main --mode test     # 디버깅 모드 (텔레그램 미발송)
"""

from __future__ import annotations

import argparse
import sys
import traceback
from typing import Literal

from dotenv import load_dotenv

from .claude_processor import ClaudeNewsProcessor, filter_by_category_limit
from .news_collector import collect_all_news
from .notion_writer import NotionWriter
from .telegram_sender import TelegramSender
from .utils import is_debug_mode, load_yaml_config, logger, now_kst


def run_pipeline(mode: Literal["morning", "evening", "test"]) -> int:
    """전체 파이프라인 실행.

    Returns:
        Exit code (0 = 성공, 1 = 실패)
    """
    start_time = now_kst()
    logger.info("=" * 70)
    logger.info(f"🚀 Industry News Bot 시작 (모드: {mode})")
    logger.info(f"   시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    if is_debug_mode():
        logger.info("   ⚠️  DEBUG MODE 활성화 (텔레그램 미발송)")
    logger.info("=" * 70)

    try:
        # ============================================================
        # Step 1: 뉴스 수집
        # ============================================================
        logger.info("\n[Step 1/4] 📡 뉴스 수집")
        raw_news = collect_all_news()
        if not raw_news:
            logger.warning("수집된 뉴스가 없습니다. 종료.")
            return 0

        # ============================================================
        # Step 2: Claude 분석
        # ============================================================
        logger.info(f"\n[Step 2/4] 🤖 Claude 분석 (총 {len(raw_news)}건)")
        processor = ClaudeNewsProcessor()
        processed = processor.analyze_batch(raw_news, max_workers=5)
        if not processed:
            logger.warning("분석 결과가 없습니다. 종료.")
            return 0

        # 카테고리당 5건 제한
        keywords_config = load_yaml_config("keywords.yml")
        max_per_cat = keywords_config["filter"]["max_per_category"]
        final_list = filter_by_category_limit(processed, max_per_category=max_per_cat)

        # ============================================================
        # Step 3: Notion 저장
        # ============================================================
        logger.info(f"\n[Step 3/4] 📝 Notion 저장 ({len(final_list)}건)")
        writer = NotionWriter()
        writer.warm_up()
        saved_list = writer.save_batch(final_list)

        # ============================================================
        # Step 4: 텔레그램 발송
        # ============================================================
        logger.info(f"\n[Step 4/4] 📱 텔레그램 발송 ({len(saved_list)}건)")
        if mode == "test" or is_debug_mode():
            # 테스트 모드: 발송 안 함, 결과만 출력
            logger.info("테스트 모드: 텔레그램 발송 스킵")
            for news in saved_list[:5]:
                logger.info(
                    f"  [{news.category}] {news.headline} "
                    f"(중요도 {news.importance})"
                )
        else:
            sender = TelegramSender()
            tg_mode: Literal["morning", "evening"] = (
                "morning" if mode == "morning" else "evening"
            )
            sender.send_digest(saved_list, mode=tg_mode)

        # ============================================================
        # 완료
        # ============================================================
        elapsed = now_kst() - start_time
        logger.info("=" * 70)
        logger.info(f"✅ 완료 (총 소요시간: {elapsed.total_seconds():.1f}초)")
        logger.info(
            f"   수집 {len(raw_news)} → 분석 {len(processed)} → "
            f"필터 {len(final_list)} → 저장 {len(saved_list)}"
        )
        logger.info("=" * 70)
        return 0

    except Exception as e:
        logger.error(f"❌ 파이프라인 실행 실패: {e}")
        logger.error(traceback.format_exc())
        return 1


def main() -> None:
    """CLI 엔트리포인트."""
    # .env 파일 로드 (있으면)
    load_dotenv()

    parser = argparse.ArgumentParser(description="ECM Industry News Bot")
    parser.add_argument(
        "--mode",
        choices=["morning", "evening", "test"],
        default="test",
        help="실행 모드: morning(아침) / evening(저녁) / test(테스트, 텔레그램 미발송)",
    )
    args = parser.parse_args()

    exit_code = run_pipeline(args.mode)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
