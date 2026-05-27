# 📊 Industry News Bot

ECM(Equity Capital Markets) 담당자를 위한 산업 뉴스 자동화 파이프라인.

## 🎯 기능

- **매일 2회 발송**: 07:40 (아침), 16:10 (장 마감 후)
- **4개 카테고리**: AI/데이터센터, 반도체, 2차전지, 로봇
- **17개 핵심 키워드** 자동 추적
- **Notion DB 자동 저장** (News Archive + Industry Tracker)
- **상장사 마스터 자동 연결** (탐방노트와 연동)
- **텔레그램 발송** (카테고리별 그룹핑)

## 🏗️ 아키텍처

```
[GitHub Actions 스케줄러]
    ↓
[뉴스 수집] (네이버 API + 7개 RSS)
    ↓
[중복 제거 + 필터링]
    ↓
[Claude API 가공]
    ↓
[Notion 저장] + [텔레그램 발송]
```

## 📂 디렉토리 구조

```
industry-news-bot/
├ .github/workflows/        # GitHub Actions 워크플로우
├ src/                       # 핵심 로직
│   ├ main.py                # 진입점
│   ├ news_collector.py      # 뉴스 수집
│   ├ claude_processor.py    # Claude API 가공
│   ├ notion_writer.py       # Notion 저장
│   ├ telegram_sender.py     # 텔레그램 발송
│   └ utils.py               # 공통 유틸
├ config/                    # 설정 파일
│   ├ keywords.yml           # 17개 핵심 키워드
│   └ rss_sources.yml        # RSS 소스 목록
├ prompts/                   # Claude 프롬프트
│   └ news_analysis.md       # 뉴스 분석 프롬프트
└ tests/                     # 테스트
```

## 🚀 셋업

### 1. 필요한 API 키 (GitHub Secrets에 등록)

| Secret 이름 | 발급처 |
|------------|--------|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `NOTION_TOKEN` | notion.so/my-integrations |
| `TELEGRAM_BOT_TOKEN` | @BotFather (텔레그램) |
| `TELEGRAM_CHAT_ID` | getUpdates API로 확인 |
| `NAVER_CLIENT_ID` | developers.naver.com |
| `NAVER_CLIENT_SECRET` | developers.naver.com |

### 2. Notion DB ID (config/notion_ids.yml에 등록)

| DB | ID |
|----|----|
| News Archive | `07098c1a-e0b8-4208-97ca-116a872b1d0c` |
| Industry Tracker | `7127f2c0-23f9-41cc-9ec3-2bb90be3843e` |
| 상장사 마스터 | `cabbbb13-34d8-44b6-a710-c3f7ac41ed7c` |
| 기업 탐방노트 | `b38b3f96-dd8d-48e1-9e6b-d60037fb6b7c` |

### 3. 로컬 테스트

```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate    # Windows

# 의존성 설치
pip install -r requirements.txt

# .env 파일 생성 (.env.example 참고)
cp .env.example .env
# .env 파일 편집 후 API 키 입력

# 수동 실행
python -m src.main --mode morning  # 아침 모드
python -m src.main --mode evening  # 장 마감 모드
```

### 4. 배포 (GitHub Actions)

```bash
git add .
git commit -m "Initial commit"
git push origin main
```

GitHub Actions가 자동으로 매일 정해진 시간에 실행됩니다.

## 📝 라이선스

Private repository - 개인 사용 전용
