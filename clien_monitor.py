# -*- coding: utf-8 -*-
"""클리앙(clien.net) 커뮤니티 게시글 모니터링 — 네이버 웹문서검색 API 경유.

왜 직접 스크래핑이 아닌가:
  클리앙은 RSS/공식 API가 없고, requests/헤드리스 브라우저로 clien.net에 직접
  접속하면 봇 차단(WAF)에 걸려 메인 페이지·robots.txt조차 403이 뜬다(수동 확인:
  User-Agent를 바꿔도 동일). GitHub Actions 등 클라우드 IP 대역도 같은 이유로
  막힐 가능성이 높아, 직접 스크래핑은 실행 환경에 안정적으로 이식하기 어렵다.

  대신 네이버가 이미 클리앙 게시글을 색인하고 있고, 클리앙 페이지의
  <title>은 항상 "게시글 제목 : 클리앙" 형식이라 네이버 검색 오픈API의
  웹문서검색(webkr)에 "{키워드} 클리앙"으로 질의하면 clien.net 결과가
  상위에 잡힌다. 클리앙 서버에 전혀 접속하지 않고 제목/링크/스니펫을 얻는다.

한계:
  - webkr 응답에는 pubDate가 없다 → 게시글 URL 끝 숫자(사이트 전역에서
    오름차순으로 부여되는 게시글 ID)를 최신순 정렬·dedup 키로 쓴다.
  - 네이버 색인 지연(수 분~수십 분)이 있어 실시간성은 RSS보다 떨어진다.
  - "{키워드} 클리앙" 질의는 <title> 접미사 "클리앙"에 기대는 방식이라
    키워드 단독 질의보다 clien.net 비중이 훨씬 높다(직접 확인함).

환경변수:
  NAVER_CLIENT_ID, NAVER_CLIENT_SECRET (필수 — monitor.py와 동일 키 재사용 가능)

이 파일은 axonetool-web(Render) 등 다른 서비스로 포팅하기 쉽도록
fetch_clien()/find_new_posts() 두 함수만으로 동작이 완결되게 짰다.
텔레그램 발송 등은 포함하지 않는다(포팅 대상 쪽에서 처리).
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
import html as html_mod

NAVER_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")

# 모니터링 키워드 — 클리앙 커뮤니티 여론 감지용 (뉴스 모니터의 KEYWORDS와 별개)
CLIEN_KEYWORDS = ["SKT", "KT", "유플러스"]

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clien_state.json")


def _strip_tags(s):
    return html_mod.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _http_get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _post_id(url):
    """클리앙 게시글 URL 끝 숫자(게시글 ID) 추출. 매칭 안 되면 None."""
    m = re.search(r"/(\d+)/?$", urllib.parse.urlsplit(url).path)
    return int(m.group(1)) if m else None


def fetch_clien(keyword, display=30):
    """네이버 웹문서검색으로 "{keyword} 클리앙" 질의 후 clien.net 결과만 필터링.

    반환: [(post_id, title, url, desc), ...] post_id 내림차순(최신 우선).
    """
    url = (
        "https://openapi.naver.com/v1/search/webkr.json?query="
        + urllib.parse.quote(keyword + " 클리앙")
        + "&display=%d&sort=date" % display
    )
    raw = _http_get(url, {
        "X-Naver-Client-Id": NAVER_ID,
        "X-Naver-Client-Secret": NAVER_SECRET,
    })
    items = json.loads(raw).get("items", [])
    results = []
    for it in items:
        link = it.get("link", "")
        host = urllib.parse.urlsplit(link).netloc.lower()
        if host != "www.clien.net":
            continue
        pid = _post_id(link)
        if pid is None:
            continue
        title = _strip_tags(it.get("title", ""))
        desc = _strip_tags(it.get("description", ""))
        results.append((pid, title, link, desc))
    results.sort(key=lambda r: r[0], reverse=True)
    return results


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"seen_ids": [], "initialized": False}


def save_state(state):
    state["seen_ids"] = state["seen_ids"][-2000:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def find_new_posts():
    """CLIEN_KEYWORDS 전체 조회 후 이전에 못 본 게시글만 반환 (최초 실행은 baseline만).

    반환: [(post_id, {"keyword", "title", "url", "desc"}), ...] 최신순.
    """
    if not NAVER_ID or not NAVER_SECRET:
        print("ERROR: NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 미설정", file=sys.stderr)
        return []

    state = load_state()
    seen = set(state["seen_ids"])
    first_run = not state.get("initialized", False)

    new_posts = {}
    for kw in CLIEN_KEYWORDS:
        try:
            for pid, title, link, desc in fetch_clien(kw):
                if pid not in seen and pid not in new_posts:
                    new_posts[pid] = {"keyword": kw, "title": title, "url": link, "desc": desc}
        except Exception as e:
            print("fetch error (%s): %s" % (kw, e), file=sys.stderr)

    seen |= set(new_posts.keys())
    state["seen_ids"] = list(seen)
    state["initialized"] = True
    save_state(state)

    if first_run:
        return []
    return sorted(new_posts.items(), key=lambda kv: kv[0], reverse=True)


def main():
    posts = find_new_posts()
    print(json.dumps(
        [{"id": pid, **data} for pid, data in posts],
        ensure_ascii=False, indent=2,
    ))


if __name__ == "__main__":
    main()
