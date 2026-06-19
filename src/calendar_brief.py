"""경제지표 + 미국 실적 발표 일정 브리핑 스크립트.

- 경제지표 일정: FRED API (무료) + FOMC 내장 일정. ET 고정 발표시각을 KST로 변환.
- 미국 실적: Finnhub earnings calendar (무료). 회사명 풀네임 + (티커).

경제지표는 '예상치/이전치'는 제공하지 않음(FRED는 일정만). 발표 시각은
지표별 ET 고정시각을 KST로 자동 변환(서머타임 자동 반영).

환경변수:
    FRED_API_KEY        : https://fredaccount.stlouisfed.org 무료 발급
    FINNHUB_API_KEY     : https://finnhub.io 무료 발급 (실적용)
    TELEGRAM_BOT_TOKEN  : 텔레그램 봇 토큰
    TELEGRAM_CHAT_ID    : 전송 대상 채팅 ID

사용법:
    python -m src.calendar_brief                # 오늘
    python -m src.calendar_brief --days 3       # 오늘부터 3일
    python -m src.calendar_brief --dry-run      # 미발송, 출력만
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
FRED_BASE = "https://api.stlouisfed.org/fred"
FINNHUB_BASE = "https://finnhub.io/api/v1"

MAX_PROFILE_LOOKUPS = 25  # 실적 회사명 조회 상한

# ─────────────────────────────────────────────────────────
# FRED 주요 경제지표 매핑 (release_name 부분일치 → 한국어명, ET 발표시각).
# 발표시각은 BLS/Census/BEA/연준 공식 고정 스케줄 기준(ET).
# 순서 = 우선순위. 위에 둘수록 핵심 지표.
# 지표를 빼고 싶으면 해당 줄을 삭제, 시각이 다르면 끝 값을 수정.
# ─────────────────────────────────────────────────────────
FRED_NAME_MAP = [
    # === 1군: 최상위 ===
    ("Employment Situation",                  "고용상황(비농업)",          "08:30"),
    ("Consumer Price Index",                  "CPI(소비자물가)",           "08:30"),
    ("Personal Income and Outlays",           "PCE(개인소비지출물가)",     "08:30"),
    # === 2군: 상위 ===
    ("Producer Price Index",                  "PPI(생산자물가)",           "08:30"),
    ("Advance Monthly Sales for Retail",      "소매판매",                  "08:30"),
    ("Unemployment Insurance Weekly Claims",  "신규 실업수당 청구",        "08:30"),
    ("Gross Domestic Product",                "GDP",                       "08:30"),
    ("Job Openings and Labor Turnover",       "JOLTS(구인이직)",           "10:00"),
    # === 3군: 보조 ===
    ("Industrial Production",                 "산업생산",                  "09:15"),
    ("New Residential Construction",          "신규주택착공",              "08:30"),
    ("New Residential Sales",                 "신규주택판매",              "10:00"),
    ("Existing Home Sales",                   "기존주택판매",              "10:00"),
    ("Surveys of Consumers",                  "미시간대 소비자심리",       "10:00"),
    ("Empire State Manufacturing Survey",     "엠파이어스테이트 제조업",   "08:30"),
    ("Manufacturing Business Outlook Survey", "필라델피아 연준 제조업",    "08:30"),
    ("U.S. International Trade",               "무역수지",                  "08:30"),
    ("Employment Cost Index",                 "고용비용지수(ECI)",         "08:30"),
    ("Productivity and Costs",                "생산성·단위노동비용",       "08:30"),
    ("Construction Spending",                 "건설지출",                  "10:00"),
    ("New Orders",                            "내구재·공장주문",           "10:00"),
    ("House Price Index",                     "주택가격지수(FHFA)",        "09:00"),
    ("S&P Cotality Case-Shiller",             "케이스실러 주택가격",       "09:00"),
    ("G.19 Consumer Credit",                  "소비자신용",                "15:00"),
]
# (구버전 호환용 — 더 이상 사용 안 함)
FRED_RELEASES: dict[int, tuple[str, str]] = {}

# ─────────────────────────────────────────────────────────
# FOMC 결정일(둘째 날). ET 14:00 결정 / 14:30 기자회견.
# 출처: federalreserve.gov FOMC calendars. 정기회의 8회.
# ─────────────────────────────────────────────────────────
FOMC_DECISION_DATES = {
    # 2026
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
    # 2027
    "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09",
    "2027-07-28", "2027-09-15", "2027-10-27", "2027-12-08",
}

# 관심 실적 종목 (⭐ 강조)
WATCH_TICKERS = {
    "NVDA", "AMD", "AVGO", "MU", "TSM", "ASML", "AAPL", "MSFT",
    "GOOGL", "AMZN", "META", "TSLA", "INTC", "QCOM", "ARM", "SMCI",
}


def _et_to_kst(date_str: str, hhmm: str) -> str:
    """ET date+time → KST 'MM/DD HH:MM' (서머타임 자동)."""
    naive = datetime.strptime(f"{date_str} {hhmm}", "%Y-%m-%d %H:%M")
    return ET.localize(naive).astimezone(KST).strftime("%m/%d %H:%M")


# ============================================================
# 경제지표 (FRED + FOMC)
# ============================================================

def fetch_economic_events(date_from: str, date_to: str) -> list[dict]:
    """FRED 일정 + FOMC 내장 일정 → [{kst, name}] (kst 정렬)."""
    events: list[dict] = []

    # 1) FRED release dates
    key = os.environ.get("FRED_API_KEY")
    if key:
        try:
            r = requests.get(
                f"{FRED_BASE}/releases/dates",
                params={
                    "api_key": key,
                    "file_type": "json",
                    "realtime_start": date_from,
                    "realtime_end": date_to,
                    "include_release_dates_with_no_data": "true",
                    "sort_order": "asc",
                    "limit": 1000,
                },
                timeout=15,
            )
            r.raise_for_status()
            for rd in r.json().get("release_dates", []):
                d = rd.get("date", "")
                if not (date_from <= d <= date_to):
                    continue
                rname = rd.get("release_name", "")
                kr, hhmm = None, None
                for kw, k_kr, k_t in FRED_NAME_MAP:
                    if kw.lower() in rname.lower():
                        kr, hhmm = k_kr, k_t
                        break
                if kr:
                    events.append({"kst": _et_to_kst(d, hhmm), "name": kr, "_d": d})
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            print(f"[경고] FRED 호출 실패(HTTP {code}).", file=sys.stderr)
        except Exception as e:
            print(f"[경고] FRED 예외: {e}", file=sys.stderr)
    else:
        print("[경고] FRED_API_KEY 미설정. FOMC만 표기.", file=sys.stderr)

    # 2) FOMC (내장)
    cur = datetime.strptime(date_from, "%Y-%m-%d")
    end = datetime.strptime(date_to, "%Y-%m-%d")
    while cur <= end:
        ds = cur.strftime("%Y-%m-%d")
        if ds in FOMC_DECISION_DATES:
            events.append({"kst": _et_to_kst(ds, "14:00"),
                           "name": "FOMC 금리결정·성명", "_d": ds})
            events.append({"kst": _et_to_kst(ds, "14:30"),
                           "name": "FOMC 기자회견", "_d": ds})
        cur += timedelta(days=1)

    # 중복 제거 + KST 시각순 정렬
    seen = set()
    uniq = []
    for ev in events:
        k = (ev["name"], ev["kst"])
        if k not in seen:
            seen.add(k)
            uniq.append(ev)
    uniq.sort(key=lambda e: e["kst"])
    return uniq


# ============================================================
# 실적 (Finnhub)
# ============================================================

_NAME_CACHE: dict[str, str] = {}


def fetch_company_name(symbol: str) -> str:
    if symbol in _NAME_CACHE:
        return _NAME_CACHE[symbol]
    name = ""
    try:
        r = requests.get(
            f"{FINNHUB_BASE}/stock/profile2",
            params={"symbol": symbol, "token": os.environ["FINNHUB_API_KEY"]},
            timeout=15,
        )
        r.raise_for_status()
        name = (r.json() or {}).get("name", "") or ""
    except Exception:
        name = ""
    _NAME_CACHE[symbol] = name
    return name


def fetch_earnings(date_from: str, date_to: str) -> list[dict]:
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        print("[경고] FINNHUB_API_KEY 미설정. 실적 생략.", file=sys.stderr)
        return []
    try:
        r = requests.get(
            f"{FINNHUB_BASE}/calendar/earnings",
            params={"from": date_from, "to": date_to, "token": key},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("earningsCalendar", [])
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        print(f"[경고] 실적 캘린더 실패(HTTP {code}).", file=sys.stderr)
        return []


# ============================================================
# 메시지
# ============================================================

def build_message(econ: list[dict], earn: list[dict], date_label: str) -> str:
    lines = ["⚡️ 주요 일정 브리핑", f"📅 {date_label} (KST 기준)", ""]

    lines.append("━━━━━━━━━━━━━━")
    lines.append("📊 경제지표")
    if econ:
        for ev in econ:
            lines.append(f"{ev['kst']} – {ev['name']}")
    else:
        lines.append("· (해당 일자 주요 지표 없음)")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━")
    lines.append("📈 미국 실적 발표")
    lines.append("※ 발표 시각은 장전(BMO)/장후(AMC)까지만 제공")
    if earn:
        def sort_key(e):
            sym = e.get("symbol", "")
            return (0 if sym in WATCH_TICKERS else 1, sym)
        lookups = 0
        for e in sorted(earn, key=sort_key):
            sym = e.get("symbol", "?")
            star = "⭐ " if sym in WATCH_TICKERS else ""
            name = ""
            if lookups < MAX_PROFILE_LOOKUPS:
                name = fetch_company_name(sym)
                lookups += 1
            label = f"{name} ({sym})" if name else sym
            hour = e.get("hour", "")
            hour_kr = {"bmo": "장전", "amc": "장후", "dmh": "장중"}.get(hour, "미정")
            eps = e.get("epsEstimate")
            eps_txt = f", EPS예상 {eps}" if eps is not None else ""
            lines.append(f"· {star}{label} [{hour_kr}{eps_txt}]")
    else:
        lines.append("· (해당 일자 발표 예정 없음)")

    return "\n".join(lines)


def send_telegram(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=15,
    )
    r.raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser(description="경제지표(FRED)+실적(Finnhub) 일정 브리핑")
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    today = datetime.now(KST)
    date_from = today.strftime("%Y-%m-%d")
    date_to = (today + timedelta(days=args.days - 1)).strftime("%Y-%m-%d")
    date_label = date_from if args.days == 1 else f"{date_from} ~ {date_to}"

    econ = fetch_economic_events(date_from, date_to)
    earn = fetch_earnings(date_from, date_to)
    msg = build_message(econ, earn, date_label)

    if args.dry_run:
        print(msg)
    else:
        send_telegram(msg)
        print(f"전송 완료: 지표 {len(econ)}건, 실적 {len(earn)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
