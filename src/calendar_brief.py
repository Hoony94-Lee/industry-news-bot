"""경제지표 + 미국 실적 발표 일정 브리핑 스크립트.

Finnhub 무료 API를 사용해 '오늘(KST)' 기준 경제지표 발표와
미국 실적 발표 예정 기업을 텔레그램으로 전송한다.

기존 industry-news-bot 와 독립적으로 동작하는 별도 스크립트.

환경변수:
    FINNHUB_API_KEY     : Finnhub API 키 (https://finnhub.io 무료 발급)
    TELEGRAM_BOT_TOKEN  : 텔레그램 봇 토큰 (기존 봇과 공유 가능)
    TELEGRAM_CHAT_ID    : 전송 대상 채팅 ID

사용법:
    python -m src.calendar_brief
    python -m src.calendar_brief --days 1     # 오늘만 (기본)
    python -m src.calendar_brief --days 3     # 오늘부터 3일
    python -m src.calendar_brief --dry-run    # 텔레그램 미발송, 출력만
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta

import pytz
import requests

KST = pytz.timezone("Asia/Seoul")
ET = pytz.timezone("America/New_York")
FINNHUB_BASE = "https://finnhub.io/api/v1"

# 주요 경제지표만 노출 (노이즈 컷). Finnhub event 문자열 부분일치로 필터.
KEY_INDICATORS = [
    "Rate Decision", "Interest Rate", "FOMC", "Fed",
    "CPI", "PPI", "PCE", "Core",
    "Nonfarm", "Payrolls", "Unemployment", "Jobless",
    "GDP", "Retail Sales", "ISM", "PMI",
    "Crude Oil Inventories", "Consumer Confidence", "Michigan",
]

# 관심 실적 종목 (있으면 ⭐ 강조). 비우면 전체 노출.
WATCH_TICKERS = {
    "NVDA", "AMD", "AVGO", "MU", "TSM", "ASML", "AAPL", "MSFT",
    "GOOGL", "AMZN", "META", "TSLA", "INTC", "QCOM", "ARM", "SMCI",
}


def _get(endpoint: str, params: dict) -> dict:
    params["token"] = os.environ["FINNHUB_API_KEY"]
    r = requests.get(f"{FINNHUB_BASE}{endpoint}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_economic_calendar(date_from: str, date_to: str) -> list[dict]:
    """경제지표 캘린더. 무료티어에서 막히면 빈 리스트 반환."""
    try:
        data = _get("/calendar/economic", {"from": date_from, "to": date_to})
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        print(f"[경고] 경제지표 캘린더 호출 실패(HTTP {code}). "
              f"무료 티어 미지원일 수 있음. 실적만 진행합니다.", file=sys.stderr)
        return []
    events = data.get("economicCalendar", []) or data.get("data", [])
    # 미국 + 주요 지표만
    out = []
    for ev in events:
        if ev.get("country") not in ("US", "USA", None):
            continue
        name = ev.get("event", "")
        if KEY_INDICATORS and not any(k.lower() in name.lower() for k in KEY_INDICATORS):
            continue
        out.append(ev)
    return out


def fetch_earnings_calendar(date_from: str, date_to: str) -> list[dict]:
    """미국 실적 발표 캘린더."""
    try:
        data = _get("/calendar/earnings", {"from": date_from, "to": date_to})
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        print(f"[경고] 실적 캘린더 호출 실패(HTTP {code}).", file=sys.stderr)
        return []
    return data.get("earningsCalendar", [])


def _econ_time_kst(time_str: str) -> str:
    """Finnhub 경제지표 time(UTC) → KST 'MM/DD HH:MM'.

    Finnhub time 형식은 보통 'YYYY-MM-DD HH:MM:SS' (UTC).
    파싱 실패하거나 시각이 없으면 빈 문자열 반환(날짜만 표기).
    """
    if not time_str:
        return ""
    s = str(time_str).replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            naive = datetime.strptime(s[:19] if len(s) >= 19 else s, fmt)
            utc_dt = pytz.utc.localize(naive)
            return utc_dt.astimezone(KST).strftime("%m/%d %H:%M")
        except Exception:
            continue
    return ""


def build_message(econ: list[dict], earn: list[dict], date_label: str) -> str:
    lines = ["⚡️ 주요 일정 브리핑", f"📅 {date_label} (KST 기준)", ""]

    # --- 경제지표 ---
    lines.append("━━━━━━━━━━━━━━")
    lines.append("📊 경제지표")
    if econ:
        for ev in econ:
            name = ev.get("event", "?")
            t_kst = _econ_time_kst(ev.get("time", ""))
            est = ev.get("estimate")
            prev = ev.get("prev")
            detail = []
            if est is not None:
                detail.append(f"예상 {est}")
            if prev is not None:
                detail.append(f"이전 {prev}")
            tail = f" ({', '.join(detail)})" if detail else ""
            prefix = f"{t_kst} – " if t_kst else "· "
            lines.append(f"{prefix}{name}{tail}")
    else:
        lines.append("· (해당 일자 주요 지표 없음 또는 미지원)")

    # --- 실적 ---
    lines.append("")
    lines.append("━━━━━━━━━━━━━━")
    lines.append("📈 미국 실적 발표")
    if earn:
        # 관심종목 우선 정렬
        def sort_key(e):
            sym = e.get("symbol", "")
            return (0 if sym in WATCH_TICKERS else 1, sym)
        for e in sorted(earn, key=sort_key):
            sym = e.get("symbol", "?")
            star = "⭐ " if sym in WATCH_TICKERS else ""
            hour = e.get("hour", "")  # bmo(장전)/amc(장후)
            hour_map = {"bmo": "장전", "amc": "장후", "dmh": "장중"}
            hour_kr = hour_map.get(hour, "")
            eps = e.get("epsEstimate")
            eps_txt = f" EPS예상 {eps}" if eps is not None else ""
            lines.append(f"· {star}{sym} ({hour_kr}){eps_txt}")
    else:
        lines.append("· (해당 일자 발표 예정 없음)")

    return "\n".join(lines)


def send_telegram(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
    r.raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser(description="경제지표+실적 일정 브리핑")
    parser.add_argument("--days", type=int, default=1, help="오늘부터 N일 (기본 1)")
    parser.add_argument("--dry-run", action="store_true", help="텔레그램 미발송")
    args = parser.parse_args()

    today = datetime.now(KST)
    date_from = today.strftime("%Y-%m-%d")
    date_to = (today + timedelta(days=args.days - 1)).strftime("%Y-%m-%d")
    date_label = date_from if args.days == 1 else f"{date_from} ~ {date_to}"

    econ = fetch_economic_calendar(date_from, date_to)
    earn = fetch_earnings_calendar(date_from, date_to)

    msg = build_message(econ, earn, date_label)

    if args.dry_run:
        print(msg)
    else:
        send_telegram(msg)
        print(f"전송 완료: 지표 {len(econ)}건, 실적 {len(earn)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
