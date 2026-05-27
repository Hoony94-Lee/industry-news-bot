# RSS 소스 목록
# enabled: false로 설정하면 해당 소스 비활성화

sources:
  # === 한글 소스 ===
  
  electronic_times:
    name: 전자신문
    url: https://rss.etnews.com/Section902.xml
    language: ko
    enabled: true
    weight: 1.0
    description: 반도체/IT 전문

  thelec:
    name: 디일렉
    url: https://www.thelec.kr/rss/allArticle.xml
    language: ko
    enabled: true
    weight: 1.2
    description: 반도체/디스플레이 전문 (가중치 높음)

  hankyung_it:
    name: 한국경제 IT
    url: https://www.hankyung.com/feed/it
    language: ko
    enabled: true
    weight: 1.0
    description: 한국경제 IT 섹션

  hankyung_industry:
    name: 한국경제 산업
    url: https://www.hankyung.com/feed/industry
    language: ko
    enabled: true
    weight: 1.0
    description: 한국경제 산업 섹션

  mk_it:
    name: 매일경제 IT/과학
    url: https://www.mk.co.kr/rss/30000023/
    language: ko
    enabled: true
    weight: 1.0
    description: 매경 IT/과학

  mk_economy:
    name: 매일경제 경제
    url: https://www.mk.co.kr/rss/30100041/
    language: ko
    enabled: true
    weight: 1.0
    description: 매경 경제

  # === 영문 소스 ===

  reuters_tech:
    name: Reuters Technology
    url: https://www.reuters.com/arc/outboundfeeds/v3/category/technology/?outputType=xml
    language: en
    enabled: true
    weight: 1.1
    description: 로이터 기술 섹션

  semianalysis:
    name: SemiAnalysis
    url: https://semianalysis.com/feed/
    language: en
    enabled: true
    weight: 1.3
    description: 반도체 심층 분석 (가중치 높음, 일부 유료)

# RSS 수집 설정
rss_settings:
  # 각 RSS에서 최대 가져올 항목 수
  max_items_per_feed: 30
  
  # User-Agent (일부 사이트는 봇 차단)
  user_agent: "Mozilla/5.0 (compatible; IndustryNewsBot/1.0)"
  
  # 타임아웃 (초)
  timeout: 15

# 네이버 API 설정
naver_settings:
  # 키워드당 가져올 결과 수 (최대 100)
  display: 30
  
  # 정렬 (sim=정확도, date=최신순)
  sort: date
