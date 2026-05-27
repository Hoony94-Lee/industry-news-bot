# 🚀 셋업 가이드

이 가이드를 따라 1시간 안에 자동화를 가동할 수 있습니다.

## 📋 사전 준비물

이미 완료하셨거나, 아직이면 먼저 진행:

- ✅ GitHub Private 레포 (`industry-news-bot`)
- ✅ Notion Integration 토큰 (ntn_으로 시작)
- ✅ Notion DB 3곳 권한 부여 (산업DB, 기업 탐방노트, 상장사 마스터)
- ✅ Telegram Bot 토큰 + Chat ID
- ✅ 네이버 검색 API (Client ID + Client Secret)
- ✅ Anthropic API Key

---

## 1단계: 코드 업로드

### 옵션 A: 로컬에서 git push (권장)

```bash
# 1. 레포 클론
git clone https://github.com/<your-username>/industry-news-bot.git
cd industry-news-bot

# 2. 받은 코드 파일 전체를 이 디렉토리에 복사

# 3. 커밋 & 푸시
git add .
git commit -m "Initial commit: 자동화 파이프라인 구축"
git push origin main
```

### 옵션 B: GitHub 웹에서 직접 업로드

1. 레포 페이지 → `Add file` → `Upload files`
2. 받은 파일 전부 드래그 앤 드롭
3. Commit changes

⚠️ **주의**: `.env` 파일은 절대 업로드하지 마세요. (`.gitignore`에 등록되어 있음)

---

## 2단계: GitHub Secrets 등록

GitHub 레포 페이지 → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

다음 6개 secret 등록:

| Name | Value |
|------|-------|
| `ANTHROPIC_API_KEY` | `sk-ant-xxxxx...` |
| `NOTION_TOKEN` | `ntn_xxxxx...` |
| `TELEGRAM_BOT_TOKEN` | `1234567890:ABCxxxxx...` |
| `TELEGRAM_CHAT_ID` | `123456789` (숫자) |
| `NAVER_CLIENT_ID` | 네이버에서 발급받은 ID |
| `NAVER_CLIENT_SECRET` | 네이버에서 발급받은 Secret |

⚠️ **Secret 값에 공백이나 따옴표 없이** 정확히 입력하세요.

---

## 3단계: 로컬 테스트 (선택, 권장)

본격 배포 전에 로컬에서 한 번 돌려보면 좋습니다.

### 3-1. Python 가상환경 셋업

```bash
cd industry-news-bot

# Python 3.11 권장
python3.11 -m venv venv

# 활성화 (macOS/Linux)
source venv/bin/activate

# 활성화 (Windows)
# venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 3-2. .env 파일 생성

```bash
# 템플릿 복사
cp .env.example .env

# 에디터로 .env 열어서 API 키 채우기
# (.env는 .gitignore에 등록되어 있어 git에 안 올라감)
```

### 3-3. 단계별 테스트

```bash
# 1) 뉴스 수집만 테스트
python -m tests.test_modules collector

# 2) Claude 분석까지 테스트 (시간 좀 걸림)
python -m tests.test_modules processor

# 3) Notion 저장 테스트 (실제 Notion에 데이터 입력됨)
python -m tests.test_modules notion

# 4) 텔레그램 발송 테스트 (가상 데이터로 메시지 1건)
python -m tests.test_modules telegram

# 5) 전체 파이프라인 (테스트 모드, 텔레그램 미발송)
python -m src.main --mode test

# 6) 실제 발송 테스트
python -m src.main --mode morning
```

### 3-4. 문제 해결

**`ModuleNotFoundError`**
```bash
# 의존성 재설치
pip install -r requirements.txt --upgrade
```

**Notion 권한 에러**
- Notion에서 해당 DB → ··· → 연결 → industry-news-bot 추가 확인
- 산업DB / 기업 탐방노트 / 상장사 마스터 3곳 모두 권한 부여 필요

**텔레그램 발송 실패**
- Bot Token 확인 (1234567890:ABC... 형식)
- Chat ID 확인 (양수 또는 음수, 그룹은 음수)
- 봇과 1:1 대화방에서 한 번 메시지 보냈는지 확인 (안 보내면 봇이 메시지 못 보냄)

---

## 4단계: GitHub Actions 실행

### 4-1. 수동 실행 (먼저 테스트)

1. 레포 페이지 → `Actions` 탭
2. `Daily News Pipeline` 클릭
3. 우측 `Run workflow` 클릭
4. `mode: test` 선택 → `Run workflow`
5. 실행 로그 확인 (Actions 탭에서 실시간 확인)

### 4-2. 정상 작동 확인 후 실제 발송

`mode: morning` 또는 `mode: evening`으로 수동 실행.

### 4-3. 자동 스케줄 활성화

코드를 푸시한 시점부터 cron 스케줄이 자동 활성화됩니다:
- **매일 07:40 KST**: morning 모드 자동 실행
- **매일 16:10 KST**: evening 모드 자동 실행

⚠️ **GitHub Actions cron은 약간 지연될 수 있습니다** (최대 10~15분). 정확한 시간이 중요하면 외부 cron 서비스(예: cron-job.org)로 webhook 트리거가 더 정확합니다.

---

## 5단계: 운영 점검

### 매일 확인

```
✅ 07:40 / 16:10 텔레그램 메시지 도착 확인
✅ Notion News Archive 누적 확인
✅ 중복 뉴스 / 품질 문제 발견 시 피드백
```

### 주간 점검

```
✅ GitHub Actions 실행 이력 (실패한 건 없는지)
✅ Anthropic API 사용량 (console.anthropic.com)
✅ Industry Tracker 부상 점수 조정 (수동)
✅ 워치리스트 종목 추가/제거
```

### 비용 모니터링

예상 비용 (월 기준):
- GitHub Actions: **무료** (한 달 50~100분 사용, 무료 한도 2,000분)
- Anthropic API: **3~8만원** (하루 30~50건 분석 × 2회)
- Naver API: **무료** (25,000건/일 한도, 충분)
- Notion: **현재 플랜 그대로** (개인 무료/Plus)

---

## 🔧 커스터마이징

### 키워드 추가/변경

`config/keywords.yml` 수정 후 push. 단, Notion DB의 Multi-select 옵션도 같이 추가해야 합니다.

### RSS 소스 추가

`config/rss_sources.yml`에 새 소스 추가. `enabled: false`로 임시 비활성화 가능.

### 발송 시간 변경

`.github/workflows/daily_news.yml`의 cron 수정:
```yaml
- cron: '40 22 * * *'  # KST 07:40 = UTC 22:40
- cron: '10 7 * * *'   # KST 16:10 = UTC 07:10
```

⚠️ cron은 UTC 기준이므로 한국시간 - 9 = UTC로 환산.

### 발송량 변경

`config/keywords.yml`의 `filter.max_per_category` 수정.

---

## ❓ 자주 묻는 문제

**Q: 매일 같은 뉴스가 반복돼요**
A: 24시간 이내 뉴스만 필터링하고 있으므로 정상. 다만 중요도 5 뉴스가 며칠 지속되면 보일 수 있음. `config/keywords.yml`의 `max_age_hours`를 12로 줄이면 더 새로운 뉴스만.

**Q: 영문 뉴스가 너무 많아요**
A: `config/rss_sources.yml`에서 영문 소스 `enabled: false`로 설정.

**Q: Notion에 종목 매칭이 잘 안 돼요**
A: 상장사 마스터의 기업명과 Claude가 추출한 종목명이 다를 수 있음. NewsArchive 페이지를 직접 열어 수동으로 Relation 추가 가능. 자주 매칭 안 되는 종목은 상장사 마스터에 추가하거나, claude_processor.py의 프롬프트를 조정.

**Q: 텔레그램 메시지가 너무 길어요**
A: 자동으로 여러 메시지로 분할됨. 더 짧게 하려면 `config/keywords.yml`의 `max_per_category` 줄이기 (예: 3건).
