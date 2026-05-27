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
            title = f"🌅 *{date_str} 아침 산업 인텔리전스*"
        else:
            title = f"🌆 *{date_str} 장 마감 산업 인텔리전스*"

        return f"{title}\n━━━━━━━━━━━━━━━━━━━━"

    def build_news_block(self, news: ProcessedNews) -> str:
        """단일 뉴스 블록.
        
        포맷:
        🔥 *제목* (볼드)
        - 요약: 요약 내용
        - 수혜주: 종목명(티커)
        🔗 https://www.example.com/...
        """
        if news.importance >= 5:
            star = "🔥 "
        elif news.importance >= 4:
            star = "⭐ "
        else:
            star = ""

        lines = []
        
        # 1. 제목 (볼드)
        headline = truncate(news.headline, 80)
        lines.append(f"{star}*{self._escape_md(headline)}*")

        # 2. 요약
        summary = news.meaning or news.core
        summary_short = truncate(summary, 100)
        lines.append(f"\\- 요약: {self._escape_md(summary_short)}")

        # 3. 수혜주
        if news.matched_company_pages:
            company_strs = []
            for c in news.matched_company_pages[:3]:
                name = self._escape_md(c["name"])
                ticker = c.get("ticker", "")
                ir_badge = "💼" if c.get("has_ir_note") else ""
                if ticker:
                    company_strs.append(f"{name}\\({ticker}\\){ir_badge}")
                else:
                    company_strs.append(f"{name}{ir_badge}")
            companies_str = ", ".join(company_strs)
            lines.append(f"\\- 수혜주: {companies_str}")
        else:
            lines.append(f"\\- 수혜주: \\-")

        # 4. 링크 (🔗 이모티콘 + URL 바로)
        url = news.raw.url
        lines.append(f"🔗 {self._escape_url(url)}")

        return "\n".join(lines)

    def build_category_section(
        self,
        category: str,
        news_list: list[ProcessedNews],
    ) -> str:
        """카테고리 섹션."""
        emoji = CATEGORY_EMOJI.get(category, "📌")
        header = f"\n{emoji} *{category}*"

        blocks = [self.build_news_block(news) for news in news_list]
        return header + "\n\n" + "\n\n".join(blocks)

    @staticmethod
    def _escape_md(text: str) -> str:
        """Telegram MarkdownV2 이스케이프 (일반 텍스트용)."""
        if not text:
            return ""
        special_chars = r"_*[]()~`>#+-=|{}.!"
        result = []
        for char in text:
            if char in special_chars:
                result.append(f"\\{char}")
            else:
                result.append(char)
        return "".join(result)

    @staticmethod
    def _escape_url(url: str) -> str:
        """URL용 이스케이프."""
        if not url:
            return ""
        result = []
        special_chars = r"_*[]()~`>#+-=|{}.!"
        for char in url:
            if char in special_chars:
                result.append(f"\\{char}")
            else:
                result.append(char)
        return "".join(result)

    async def _send_async(self, text: str) -> bool:
        """비동기 메시지 발송."""
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
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True,
            )
            return True
        except TelegramError as e:
            logger.error(f"텔레그램 발송 실패: {e}")
            try:
                plain_text = self._strip_markdown(text)
                await self.bot.send_message(
                    chat_id=self.chat_id,
