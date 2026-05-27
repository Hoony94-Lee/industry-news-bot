# 4개 카테고리 × 17개 핵심 키워드 정의
# 각 키워드는 네이버 뉴스 검색에 사용되는 search_queries를 포함

categories:
  반도체:
    color: blue
    keywords:
      엔비디아:
        search_queries:
          - "엔비디아"
          - "NVIDIA"
          - "엔비디아 GPU"
        english_queries:
          - "NVIDIA"
          - "Nvidia GPU"

      베라 루빈:
        search_queries:
          - "베라 루빈"
          - "Vera Rubin"
          - "엔비디아 루빈"
        english_queries:
          - "Vera Rubin"
          - "NVIDIA Rubin"

      SO-CAMM:
        search_queries:
          - "SOCAMM"
          - "SO-CAMM"
          - "소캠"
          - "LPCAMM"
        english_queries:
          - "SOCAMM"
          - "SO-CAMM"

      CPO:
        search_queries:
          - "CPO 광반도체"
          - "광반도체"
          - "Co-Packaged Optics"
          - "실리콘 포토닉스"
        english_queries:
          - "Co-Packaged Optics"
          - "silicon photonics"

      DRAM:
        search_queries:
          - "DRAM"
          - "디램"
          - "HBM"
          - "HBM4"
        english_queries:
          - "DRAM"
          - "HBM"
          - "HBM4"

      NAND:
        search_queries:
          - "NAND"
          - "낸드"
          - "낸드 플래시"
        english_queries:
          - "NAND flash"
          - "NAND memory"

      프로브카드:
        search_queries:
          - "프로브카드"
          - "probe card"
        english_queries:
          - "probe card"

  AI/데이터센터:
    color: orange
    keywords:
      AI 인프라 CapEx:
        search_queries:
          - "AI 인프라 투자"
          - "빅테크 CapEx"
          - "데이터센터 투자"
          - "하이퍼스케일러"
        english_queries:
          - "AI infrastructure CapEx"
          - "hyperscaler"

      데이터센터 냉각:
        search_queries:
          - "데이터센터 냉각"
          - "액체냉각"
          - "DLC 냉각"
          - "침지냉각"
        english_queries:
          - "data center cooling"
          - "liquid cooling"
          - "immersion cooling"

      전력/송배전:
        search_queries:
          - "데이터센터 전력"
          - "AI 전력"
          - "송배전"
          - "전력기기"
        english_queries:
          - "data center power"
          - "grid infrastructure"

  2차전지:
    color: green
    keywords:
      전고체:
        search_queries:
          - "전고체"
          - "전고체 배터리"
        english_queries:
          - "solid-state battery"

      LFP:
        search_queries:
          - "LFP"
          - "LFP 배터리"
          - "리튬인산철"
        english_queries:
          - "LFP battery"

      건식전극:
        search_queries:
          - "건식전극"
          - "드라이 전극"
        english_queries:
          - "dry electrode"

      실리콘 음극재:
        search_queries:
          - "실리콘 음극재"
          - "Si 음극재"
        english_queries:
          - "silicon anode"

  로봇:
    color: purple
    keywords:
      휴머노이드:
        search_queries:
          - "휴머노이드"
          - "휴머노이드 로봇"
          - "옵티머스"
          - "피규어 AI"
        english_queries:
          - "humanoid robot"
          - "Optimus"
          - "Figure AI"

      협동로봇:
        search_queries:
          - "협동로봇"
          - "코봇"
          - "cobot"
        english_queries:
          - "collaborative robot"
          - "cobot"

      로봇 부품:
        search_queries:
          - "로봇 감속기"
          - "로봇 액추에이터"
          - "하모닉 드라이브"
        english_queries:
          - "robot reducer"
          - "robot actuator"
          - "harmonic drive"

# 필터링 설정
filter:
  # 24시간 이내 뉴스만 (시간 단위)
  max_age_hours: 24

  # 중복 제거 임계값 (제목 유사도, 0~100)
  similarity_threshold: 80

  # 발송할 최소 중요도 (1~5)
  min_importance: 3

  # 카테고리당 최대 발송 건수
  max_per_category: 5
