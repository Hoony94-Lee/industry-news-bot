"""텔레그램 발송 모듈.

카테고리별로 그룹핑하여 보기 좋게 발송.
"""

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


# 카테고리별 이모지
CATEGORY_EMOJI = {
    "AI/데이터센터": "🤖",
    "반도체": "💾",
    "2차전지": "🔋",
    "로봇": "🦾",
}

# 텔레그램 메시지 길이 제한 (4096 자, 안전 마진 두고 3500)
MAX_MESSAGE_LENGTH = 3500


class TelegramSender:
    """텔레그램 발송기."""

    def __init__(self) -> None:
        self.bot_token = get_env("TELEGRAM_BOT_TOKEN")
        self.chat_id = get_env("TELEGRAM_CHAT_ID")
        self.bot = Bot(token=self.bot_token)

    # ============================================================
    # 메시지 빌더
    # ============================================================

    def build_header(self, mode: Literal["morning", "evening"]) -> str:
        """헤더 메시지."""
        now = now_kst()
        date_str = now.strftime("%Y-%m-%d (%a)")
        weekday_kr = {
            "Mon": "월",
            "Tue": "화",
            "Wed": "수",
            "Thu": "목",
            "Fri": "금",
            "Sat": "토",
            "Sun": "일",
        }
        for en, kr in weekday_kr.items():
            date_str = date_str.replace(en, kr)

        if mode == "morning":
            title = f"🌅 *{date_str} 아침 산업 인텔리전스*"
        else:
            title = f"🌆 *{date_str} 장 마감 산업 인텔리전스*"

        return f"{title}\n━━━━━━━━━━━━━━━━━━━━"

    def build_news_block(self, news: ProcessedNews, idx: int) -> str:
        """단일 뉴스 블록."""
        # 중요도별 강조
        if news.importance >= 5:
            star = "🔥"
        elif news.importance >= 4:
            star = "⭐"
        else:
            star = "📰"

        lines = []
        # 제목 라인
        lines.append(f"{star} *{self._escape_md(news.headline)}*")
        
        # 핵심 (간결하게)
        if news.core:
            core_short = truncate(news.core, 200)
            lines.append(f"`핵심` {self._escape_md(core_short)}")

        # 의미
        if news.meaning:
            meaning_short = truncate(news.meaning, 200)
            lines.append(f"`의미` {self._escape_md(meaning_short)}")

        # 한국 시사점 (중요도 4 이상만 상세)
        if news.korea_impact and news.importance >= 4:
            impact_short = truncate(news.korea_impact, 250)
            lines.append(f"`시사점` {self._escape_md(impact_short)}")

        # 관련 종목 (매칭된 것만)
        if news.matched_company_pages:
            company_strs = []
            for c in news.matched_company_pages[:5]:  # 최대 5개
                name = self._escape_md(c["name"])
                ticker = c.get("ticker", "")
                ir_badge = " 💼" if c.get("has_ir_note") else ""
                if ticker:
                    company_strs.append(f"{name}({ticker}){ir_badge}")
                else:
                    company_strs.append(f"{name}{ir_badge}")
            lines.append(f"`종목` {', '.join(company_strs)}")

        # 출처 + Notion 링크
        source = self._escape_md(news.raw.source)
        url = news.raw.url
        notion_link = ""
        if news.notion_page_id:
            page_url = f"https://www.notion.so/{news.notion_page_id.replace('-', '')}"
            notion_link = f" \\| [📊 Notion]({page_url})"
        lines.append(f"[{source}]({url}){notion_link}")

        return "\n".join(lines)

    def build_category_section(
        self,
        category: str,
        news_list: list[ProcessedNews],
    ) -> str:
        """카테고리 섹션."""
        emoji = CATEGORY_EMOJI.get(category, "📌")
        header = f"\n{emoji} *{category}* ({len(news_list)}건)\n"
        header += "─" * 20

        blocks = []
        for i, news in enumerate(news_list, 1):
            blocks.append(self.build_news_block(news, i))

        return header + "\n\n" + "\n\n".join(blocks)

    def build_summary_footer(self, processed_list: list[ProcessedNews]) -> str:
        """요약 푸터."""
        total = len(processed_list)
        critical = sum(1 for n in processed_list if n.importance >= 5)
        with_ir = sum(
            1
            for n in processed_list
            if any(c.get("has_ir_note") for c in n.matched_company_pages)
        )

        lines = [
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            f"📊 *총 {total}건* \\| 🔥 핵심 {critical}건 \\| 💼 탐방 매칭 {with_ir}건",
            "💼 = 기업 탐방노트 보유 종목",
        ]
        return "\n".join(lines)

    @staticmethod
    def _escape_md(text: str) -> str:
        """Telegram MarkdownV2 이스케이프."""
        if not text:
            return ""
        # MarkdownV2에서 이스케이프 필요한 문자
        special_chars = r"_*[]()~`>#+-=|{}.!"
        result = []
        for char in text:
            if char in special_chars:
                result.append(f"\\{char}")
            else:
                result.append(char)
        return "".join(result)

    # ============================================================
    # 메시지 발송
    # ============================================================

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
            # MarkdownV2 파싱 실패 시 plain text로 재시도
            try:
                plain_text = self._strip_markdown(text)
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
    def _strip_markdown(text: str) -> str:
        """마크다운 이스케이프 제거."""
        import re
        text = re.sub(r"\\([_*\[\]()~`>#+\-=|{}.!])", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)  # bold 제거
        text = re.sub(r"`([^`]+)`", r"\1", text)  # code 제거
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
        """전체 뉴스 다이제스트 발송.

        Args:
            processed_list: 발송할 뉴스 목록
            mode: morning / evening

        Returns:
            전체 발송 성공 여부
        """
        if not processed_list:
            logger.warning("발송할 뉴스가 없습니다.")
            return False

        # 카테고리별 그룹핑
        by_category: dict[str, list[ProcessedNews]] = {}
        for news in processed_list:
            by_category.setdefault(news.category, []).append(news)

        # 카테고리 순서 고정
        category_order = ["AI/데이터센터", "반도체", "2차전지", "로봇"]

        # 메시지 빌드
        sections = [self.build_header(mode)]
        for cat in category_order:
            if cat in by_category:
                items = by_category[cat]
                # 중요도 내림차순
                items.sort(key=lambda x: x.importance, reverse=True)
                sections.append(self.build_category_section(cat, items))

        # 그 외 카테고리
        for cat, items in by_category.items():
            if cat not in category_order:
                items.sort(key=lambda x: x.importance, reverse=True)
                sections.append(self.build_category_section(cat, items))

        sections.append(self.build_summary_footer(processed_list))
        full_message = "\n".join(sections)

        # 길이 분할
        chunks = self._split_long_message(full_message)
        logger.info(f"텔레그램 발송: {len(chunks)}개 메시지")

        success = True
        for i, chunk in enumerate(chunks, 1):
            result = await self._send_async(chunk)
            if not result:
                success = False
            if i < len(chunks):
                time.sleep(1)  # rate limit 방지

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
