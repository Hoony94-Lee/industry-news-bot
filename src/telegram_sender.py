"""텔레그램 발송 모듈."""

from __future__ import annotations

import asyncio
import time
from typing import Literal

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from .utils import (
    ProcessedNews,
    get_env,
    is_debug_mode,
    logger,
    now_kst,
    truncate,
)


CATEGORY_EMOJI = {
    "AI/데이터센터": "🤖",
    "반도체": "💾",
    "2차전지": "🔋",
    "로봇": "🦾",
}

MAX_MESSAGE_LENGTH = 3500


class TelegramSender:
    """텔레그램 발송기."""

    def __init__(self) -> None:
        self.bot_token = get_env("TELEGRAM_BOT_TOKEN")
        self.chat_id = get_env("TELEGRAM_CHAT_ID")
        self.bot = Bot(token=self.bot_token)

    def build_header(self, mode: Literal["morning", "evening"]) -> str:
        """헤더 메시지."""
        now = now_kst()
        date_str = now.strftime("%Y-%m-%d (%a)")
        weekday_kr = {
            "Mon": "월", "Tue": "화", "Wed": "수", "Thu": "목",
            "Fri": "금", "Sat": "토", "Sun": "일",
        }
        for en, kr in weekday_kr.items():
            date_str = date_str.replace(en, kr)

        if mode == "morning":
            title = f"🌅 <b>{date_str} 아침 산업 인텔리전스</b>"
        else:
            title = f"🌆 <b>{date_str} 장 마감 산업 인텔리전스</b>"

        return f"{title}\n━━━━━━━━━━━━━━━━━━━━"

    def build_news_block(self, news: ProcessedNews) -> str:
        """단일 뉴스 블록.
        
        포맷 (HTML 모드):
        🔥 <b>제목 볼드</b>
        - 요약: 요약 내용
        🔗 https://...
        """
        if news.importance >= 5:
            star = "🔥 "
        elif news.importance >= 4:
            star = "⭐ "
        else:
            star = ""

        lines = []

        # 1. 제목 (HTML 볼드 태그)
        headline = truncate(news.headline, 80)
        lines.append(f"{star}<b>{self._escape_html(headline)}</b>")

        # 2. 요약
        summary = news.meaning or news.core
        summary_short = truncate(summary, 100)
        lines.append(f"- 요약: {self._escape_html(summary_short)}")

        # 3. 링크 (수혜주 제거)
        url = news.raw.url
        lines.append(f"🔗 {url}")

        return "\n".join(lines)

    def build_category_section(
        self,
        category: str,
        news_list: list[ProcessedNews],
    ) -> str:
        """카테고리 섹션."""
        emoji = CATEGORY_EMOJI.get(category, "📌")
        header = f"\n{emoji} <b>{category}</b>"

        blocks = [self.build_news_block(news) for news in news_list]
        return header + "\n\n" + "\n\n".join(blocks)

    @staticmethod
    def _escape_html(text: str) -> str:
        """Telegram HTML 모드 이스케이프.
        
        HTML 파싱 모드에서는 <, >, & 만 이스케이프하면 됨.
        MarkdownV2보다 훨씬 단순하고 안정적.
        """
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    async def _send_async(self, text: str) -> bool:
        """비동기 메시지 발송 (HTML 모드)."""
        if is_debug_mode():
            logger.info("=" * 60)
            logger.info("🔍 DEBUG MODE - 텔레그램 미발송, 내용 출력:")
            logger.info("=" * 60)
            print(text)
            print("=" * 60)
            return True

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return True
        except TelegramError as e:
            logger.error(f"텔레그램 발송 실패: {e}")
            try:
                plain_text = self._strip_html(text)
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=plain_text,
                    disable_web_page_preview=True,
                )
                logger.info("Plain text로 재발송 성공")
                return True
            except Exception as e2:
                logger.error(f"Plain text 재발송도 실패: {e2}")
                return False

    @staticmethod
    def _strip_html(text: str) -> str:
        """HTML 태그 제거 (폴백용)."""
        import re
        text = re.sub(r"<[^>]+>", "", text)
        text = (
            text.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
        )
        return text

    def _split_long_message(self, text: str) -> list[str]:
        """긴 메시지를 여러 개로 분할."""
        if len(text) <= MAX_MESSAGE_LENGTH:
            return [text]

        chunks: list[str] = []
        current = ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > MAX_MESSAGE_LENGTH:
                chunks.append(current)
                current = line
            else:
                current = current + "\n" + line if current else line
        if current:
            chunks.append(current)
        return chunks

    async def send_news_digest(
        self,
        processed_list: list[ProcessedNews],
        mode: Literal["morning", "evening"] = "morning",
    ) -> bool:
        """전체 뉴스 다이제스트 발송."""
        if not processed_list:
            logger.warning("발송할 뉴스가 없습니다.")
            return False

        by_category: dict[str, list[ProcessedNews]] = {}
        for news in processed_list:
            by_category.setdefault(news.category, []).append(news)

        category_order = ["AI/데이터센터", "반도체", "2차전지", "로봇"]

        sections = [self.build_header(mode)]
        for cat in category_order:
            if cat in by_category:
                items = by_category[cat]
                items.sort(key=lambda x: x.importance, reverse=True)
                sections.append(self.build_category_section(cat, items))

        for cat, items in by_category.items():
            if cat not in category_order:
                items.sort(key=lambda x: x.importance, reverse=True)
                sections.append(self.build_category_section(cat, items))

        full_message = "\n".join(sections)

        chunks = self._split_long_message(full_message)
        logger.info(f"텔레그램 발송: {len(chunks)}개 메시지")

        success = True
        for i, chunk in enumerate(chunks, 1):
            result = await self._send_async(chunk)
            if not result:
                success = False
            if i < len(chunks):
                time.sleep(1)

        if success:
            logger.info("✅ 텔레그램 발송 완료")
        return success

    def send_digest(
        self,
        processed_list: list[ProcessedNews],
        mode: Literal["morning", "evening"] = "morning",
    ) -> bool:
        """동기 wrapper."""
        return asyncio.run(self.send_news_digest(processed_list, mode))
