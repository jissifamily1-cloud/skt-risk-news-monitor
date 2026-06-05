# -*- coding: utf-8 -*-
"""특이뉴스 모니터링 설정.

키워드 추가/삭제는 이 파일만 수정하면 된다.
GitHub UI에서 직접 한 줄씩 편집 권장 (paste 자동화로 큰 변경 금지).
"""

# 뉴스 검색 쿼리 (회사·인물 키워드) — 쿼리당 1회 검색
COMPANY_KEYWORDS = [
    "SKT",
    "SK텔레콤",
    "SK브로드밴드",
    "정재헌",
]

# 리스크 키워드 — 제목에 회사 키워드와 함께 있어야 발송
RISK_KEYWORDS = [
    # 서비스 장애
    "장애", "먹통", "끊김", "오류", "지연", "중단", "차질",
    # 보안
    "해킹", "유출", "침해", "랜섬웨어", "악성코드",
    # 법적 분쟁
    "소송", "고소", "고발", "수사", "압수수색", "기소", "구속", "검찰", "경찰",
    # 규제·제재
    "과징금", "제재", "시정명령", "공정위", "방통위", "개인정보위", "조사",
    # 사건·사고
    "사고", "화재", "사망", "부상", "추락", "폭발",
    # 평판
    "논란", "갑질", "불법", "위반", "담합", "항의", "반발", "비판", "규탄", "의혹",
    # 고객 피해
    "피해", "보상", "배상", "환불", "결함", "리콜", "차별", "누락",
    # 노사
    "파업", "노조", "쟁의",
    # 인물 리스크
    "사퇴", "사임", "퇴진", "경질", "해임", "소환", "출국금지",
    "횡령", "배임", "뇌물", "비리", "비위", "성추행", "성희롱", "막말",
    # 정부·국회
    "국정감사", "국감", "청문회", "특검", "공수처", "감사원", "세무조사",
    # 보안·프라이버시
    "도청", "감청", "사찰", "디도스", "개인정보",
    # 법무 (추가)
    "패소", "영장", "손해배상",
    # 평판 (추가)
    "불매", "물의", "뭇매",
    # 통신 정책·재무 (오탐 다소 가능 — 운영하며 조정)
    "요금 인상", "요금인상", "단통법", "적자", "급락", "어닝쇼크", "최하위",
]

# 오탐 방지 — 텍스트에서 제거 후 매칭 (좁은 표현만 추가할 것)
EXCLUDED_WORDS = [
    # 예: "보상판매" → "보상" 오탐 방지
    "보상판매",
    "오류동",  # 지명
    # 동명이인 오탐 방지 (성우 정재헌) — 제거되면 인물 매칭 자체가 안 됨
    "성우 정재헌",
    "정재헌 성우",
    # "조사" 키워드 오탐 방지
    "설문조사",
    "여론조사",
]

# 짧은 영문 키워드는 단어 경계(\b) 매칭 적용 대상
# 주의: "SK"는 substring 유지 필요 시 whitelist에 (현재 미사용)
WORD_BOUNDARY_KEYWORDS = {"SKT"}

# 발행 후 이 시간(분) 이내 기사만 대상 (오래된 기사 재발송 방지 2중 장치)
RECENCY_MINUTES = 120

# 쿼리당 가져올 기사 수
FETCH_COUNT = 30

# 야간 모아보기(06시 첫 실행) 때 쿼리당 가져올 기사 수
FETCH_COUNT_NIGHT = 100

# state.json에 보관할 최대 URL 수
MAX_SEEN_URLS = 3000

# 기사 URL 도메인 → 매체명 (네이버 API는 매체명을 안 주므로 도메인으로 추정)
PRESS_MAP = {
    "it.chosun.com": "IT조선",
    "yna.co.kr": "연합뉴스",
    "news1.kr": "뉴스1",
    "newsis.com": "뉴시스",
    "biz.chosun.com": "조선비즈",
    "chosun.com": "조선일보",
    "donga.com": "동아일보",
    "joongang.co.kr": "중앙일보",
    "hani.co.kr": "한겨레",
    "khan.co.kr": "경향신문",
    "hankookilbo.com": "한국일보",
    "kmib.co.kr": "국민일보",
    "segye.com": "세계일보",
    "munhwa.com": "문화일보",
    "seoul.co.kr": "서울신문",
    "mk.co.kr": "매일경제",
    "hankyung.com": "한국경제",
    "sedaily.com": "서울경제",
    "fnnews.com": "파이낸셜뉴스",
    "mt.co.kr": "머니투데이",
    "edaily.co.kr": "이데일리",
    "asiae.co.kr": "아시아경제",
    "heraldcorp.com": "헤럴드경제",
    "etnews.com": "전자신문",
    "zdnet.co.kr": "지디넷코리아",
    "ddaily.co.kr": "디지털데일리",
    "dt.co.kr": "디지털타임스",
    "inews24.com": "아이뉴스24",
    "bloter.net": "블로터",
    "kbs.co.kr": "KBS",
    "imbc.com": "MBC",
    "sbs.co.kr": "SBS",
    "jtbc.co.kr": "JTBC",
    "tvchosun.com": "TV조선",
    "ichannela.com": "채널A",
    "mbn.co.kr": "MBN",
    "ytn.co.kr": "YTN",
    "yonhapnewstv.co.kr": "연합뉴스TV",
    "nocutnews.co.kr": "노컷뉴스",
    "ohmynews.com": "오마이뉴스",
    "mediatoday.co.kr": "미디어오늘",
    "dailian.co.kr": "데일리안",
    "kukinews.com": "쿠키뉴스",
    "ajunews.com": "아주경제",
    "businesspost.co.kr": "비즈니스포스트",
    "newdaily.co.kr": "뉴데일리",
    "pressian.com": "프레시안",
    "mtn.co.kr": "MTN",
    "epnc.co.kr": "테크월드뉴스",
    "digitaltoday.co.kr": "디지털투데이",
    "ebn.co.kr": "EBN",
    "techm.kr": "테크M",
    "asiatoday.co.kr": "아시아투데이",
    "newspim.com": "뉴스핌",
    "etoday.co.kr": "이투데이",
    "newstomato.com": "뉴스토마토",
    "newsway.co.kr": "뉴스웨이",
    "econovill.com": "이코노믹리뷰",
    "g-enews.com": "글로벌이코노믹",
    "shinailbo.co.kr": "신아일보",
    "polinews.co.kr": "폴리뉴스",
    "popcornnews.net": "팝콘뉴스",
    "dailypop.kr": "데일리팝",
    "metroseoul.co.kr": "메트로신문",
    "viva100.com": "브릿지경제",
    "ceoscoredaily.com": "CEO스코어데일리",
    "theguru.co.kr": "더구루",
    "enewstoday.co.kr": "이뉴스투데이",
    "dnews.co.kr": "대한경제",
    "datanet.co.kr": "데이터넷",
    "byline.network": "바이라인네트워크",
    "thelec.kr": "디일렉",
    "wowtv.co.kr": "한국경제TV",
    "sisajournal.com": "시사저널",
    "sisajournal-e.com": "시사저널e",
    "ilyo.co.kr": "일요신문",
    "joseilbo.com": "조세일보",
    "ekn.kr": "에너지경제",
    "businesskorea.co.kr": "비즈니스코리아",
    "koreaherald.com": "코리아헤럴드",
    "koreatimes.co.kr": "코리아타임스",
    "seoulfn.com": "서울파이낸스",
    "paxetv.com": "팍스경제TV",
    "m-economynews.com": "M이코노미뉴스",
    "dealsitetv.com": "딜사이트TV",
}
