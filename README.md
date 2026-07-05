# skt-risk-news-monitor — 특이뉴스 모니터링

통신업계 키워드(SKT·SK텔레콤·SK브로드밴드·정재헌·유플러스·KT·이통사·통신사) 기사를 06~22시 KST 주기 실행으로 탐지해 텔레그램으로 발송하는 자동화 시스템.

## 구조

| 항목 | 값 |
|---|---|
| 소스 | 네이버 뉴스 검색 Open API (키 없으면 Google News RSS 자동 fallback) |
| 매칭 | 제목에 **키워드**(SKT·SK텔레콤·SK브로드밴드·정재헌·유플러스·KT·이통사·통신사) 중 하나라도 있으면 발송. 단 BLOCK_KEYWORDS(야구 등)가 제목에 있으면 제외 |
| 매체명 | Google RSS source → PRESS_MAP 도메인 → 기사 페이지 og:site_name 동적 조회(state.json `press_names` 캐시) |
| 중복 방지 | `state.json` seen_urls + 최근 120분 발행 기사만 |
| 실행 | GitHub Actions (`workflow_dispatch`) ← cron-job.org 트리거 |
| 주기 | `*/2 6-21 * * *` KST (06:00~21:58, 하루 480회) |
| 발송 | 텔레그램 @skt_personnel_bot → 특이뉴스 채널 |

## 파일

- `monitor.py` — 수집·매칭·발송·상태관리 전부
- `config.py` — 키워드 설정 (유지보수 시 이 파일만 수정)
- `state.json` — 발송 이력·매체명 캐시 (자동 갱신)
- `.github/workflows/cron.yml` — Actions 워크플로우 (`cron.yml`을 이 경로로 업로드)

## 셋업 순서

### 1. 텔레그램 채널 생성
1. 새 채널 생성 (예: "SKT 특이뉴스")
2. `@skt_personnel_bot`을 관리자로 추가 ("메시지 게시" 권한 필수)
3. chat_id 확인: web.telegram.org/k/ 에서 채널 클릭 → URL의 음수 숫자 (예: `-100xxxxxxxxxx`)

### 2. 네이버 API 키 발급 (권장, 5분)
1. https://developers.naver.com/apps/#/register → 애플리케이션 등록
2. 사용 API: "검색" 선택 → Client ID / Client Secret 확보
3. 무료 일 25,000회 (2분 주기 기준 일 3,840회 사용)
4. ※ 생략 시 Google News RSS로 자동 동작 (네이버 검색 대비 커버리지 다를 수 있음)

### 3. GitHub repo 생성
1. jissifamily1-cloud 계정에 **public** repo `skt-risk-news-monitor` 생성 (public이어야 Actions 무료 무제한)
2. 파일 업로드: `monitor.py`, `config.py`, `state.json`, 그리고 `cron.yml`은 `.github/workflows/cron.yml` 경로로
3. Settings → Secrets and variables → Actions → 등록:
   - `TELEGRAM_BOT_TOKEN` (기존 봇 토큰)
   - `TELEGRAM_CHAT_ID` (1에서 확인한 음수 ID)
   - `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` (2에서 발급, 선택)
4. Settings → Actions → General → Workflow permissions → **Read and write permissions** 체크 (state.json commit용)

### 4. 동작 확인
1. Actions 탭 → risk-news-monitor → Run workflow (수동 실행)
2. 최초 실행은 기존 기사를 baseline 처리만 하고 발송하지 않음 (과거 기사 폭주 방지)
3. 한 번 더 실행해 신규 기사 매칭 여부 확인

### 5. cron-job.org 등록
1. https://console.cron-job.org/jobs → Create cronjob
2. URL: `https://api.github.com/repos/jissifamily1-cloud/skt-risk-news-monitor/actions/workflows/cron.yml/dispatches`
3. Method: POST, Body: `{"ref":"main"}`
4. Headers:
   - `Authorization: Bearer {GitHub PAT}` (기존 시스템과 동일 PAT 사용 가능, repo+workflow 권한)
   - `Accept: application/vnd.github+json`
   - `Content-Type: application/json`
5. Schedule: `*/2 6-21 * * *` (KST 타임존 확인)

## 유지보수

- **키워드 추가/삭제**: `config.py`의 `KEYWORDS` — GitHub UI에서 직접 한 줄씩 편집 (paste 자동화로 큰 변경 금지)
- **발송 폭주 시**: `이통사`·`통신사` 같은 광범위 키워드부터 제거
- **야구 등 토픽 제외**: `config.py`의 `BLOCK_KEYWORDS` — 제목에 있으면 무조건 발송 제외
- **매체명 오표기 시**: `config.py`의 `PRESS_MAP`에 도메인 추가(우선 적용) 또는 `state.json`의 `press_names` 캐시 수정
- **오탐 제거**: `EXCLUDED_WORDS`에 좁은 표현만 추가
- **키워드 변경 후 기존 기사 재평가**: `state.json`을 `{"seen_urls": [], "last_run": "", "initialized": true}`로 reset
- **알림 폭주 시**: `RECENCY_MINUTES` 축소 또는 키워드 정리
- **"chat not found"**: 봇이 채널 관리자인지, chat_id가 `-100`으로 시작하는지 확인

## 비용

전부 무료: public repo Actions 무제한 + cron-job.org 무료 + 네이버 API 무료 한도 내 + 텔레그램 무료.

## 클리앙(clien.net) 커뮤니티 모니터링

`clien_monitor.py` — 뉴스 모니터와 별개로, 클리앙 게시글에서 SKT/KT/유플러스 언급을 탐지하는 참고 구현.

**방식**: 클리앙은 RSS·공식 API가 없고, 직접 스크래핑은 clien.net 자체 봇 차단(WAF)에
막혀 메인 페이지·robots.txt까지 403이 뜬다(User-Agent를 바꿔도 동일 — 확인됨).
GitHub Actions 같은 클라우드 IP도 같은 이유로 막힐 가능성이 높다.

대신 네이버가 이미 클리앙 게시글을 색인해 두고, 클리앙 페이지 `<title>`이 항상
"게시글 제목 : 클리앙" 형식이라는 점을 이용한다. 네이버 검색 오픈API의
웹문서검색(`openapi.naver.com/v1/search/webkr.json`)에 **"{키워드} 클리앙"**으로
질의하면 clien.net 결과가 상위에 잡히고, 클리앙 서버에 전혀 접속하지 않고
제목·링크·스니펫을 얻을 수 있다(실제 질의로 확인: "SKT 클리앙", "KT 클리앙",
"유플러스 클리앙" 모두 최근 클리앙 게시글이 정상 반환됨).

**한계**:
- webkr 응답에는 pubDate가 없음 → 게시글 URL 끝 숫자(사이트 전역 오름차순
  게시글 ID)로 최신순 정렬·dedup.
- 네이버 색인 지연(수 분~수십 분)이 있어 실시간성은 RSS보다 떨어짐.
- 필요 환경변수는 뉴스 모니터와 동일: `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`.

**axonetool-web으로 포팅 시**: `fetch_clien(keyword)` / `find_new_posts()` 두 함수로
동작이 완결되므로, 텔레그램 발송이나 `clien_state.json` 로컬 파일 저장 대신
포팅 대상 쪽의 저장소(DB 등)에 맞춰 dedup 로직만 옮기면 된다.
