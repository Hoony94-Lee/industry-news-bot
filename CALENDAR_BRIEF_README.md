# Calendar Brief — 경제지표 + 미국 실적 일정 봇

기존 industry-news-bot 와 독립적으로 동작하는 별도 스크립트입니다.
매일 아침(KST) 당일 경제지표 발표와 미국 실적 발표 예정 기업을 텔레그램으로 전송합니다.

## 준비물

1. Finnhub 무료 API 키
   - https://finnhub.io 가입(신용카드 불필요) → 대시보드에서 키 복사
   - 무료 티어: 분당 60회. 본 스크립트는 하루 2회 호출이라 충분.

2. GitHub Secrets 등록 (Settings → Secrets and variables → Actions)
   - FINNHUB_API_KEY
   - TELEGRAM_BOT_TOKEN   (기존 봇과 같은 값 재사용 가능)
   - TELEGRAM_CHAT_ID     (기존 봇과 같은 값 재사용 가능)

## 파일 배치

- src/calendar_brief.py                  (스크립트)
- .github/workflows/calendar_brief.yml   (스케줄)

## 수동 테스트

    # 로컬 (키를 환경변수로)
    export FINNHUB_API_KEY=xxxx
    python -m src.calendar_brief --dry-run     # 텔레그램 미발송, 화면 출력만

GitHub에서는 Actions 탭 → Calendar Brief → Run workflow 로 수동 실행 가능.

## 커스터마이징 (calendar_brief.py 상단)

- KEY_INDICATORS : 노출할 주요 지표 키워드. 비우면 미국 전체 지표 노출.
- WATCH_TICKERS  : ⭐ 강조할 관심 종목. 비우면 전체 실적이 동일 취급.
- --days N        : 오늘부터 N일치 (기본 1 = 당일만).

## 주의

- 경제지표 캘린더(/calendar/economic)는 Finnhub 무료 티어에서 막혀 있을 수
  있습니다. 그 경우 스크립트가 자동으로 '경제지표 없음/미지원' 처리하고
  실적 캘린더만 발송합니다(에러로 중단되지 않음).
  지표가 계속 안 나오면 유료 전환 또는 다른 소스(FMP 등) 검토 필요.
- cron의 0-4 는 UTC 요일(일~목)이며 KST 월~금 아침에 대응합니다.
