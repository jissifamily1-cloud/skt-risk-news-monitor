# -*- coding: utf-8 -*-
"""특이뉴스 모니터링 — 통신업계 키워드 기사 탐지 → 텔레그램 발송.

소스: 네이버 뉴스 검색 Open API (NAVER_CLIENT_ID/SECRET 없으면 Google News RSS fallback)
매칭: 제목에 KEYWORDS 중 하나라도 있으면 발송 (BLOCK_KEYWORDS 있으면 제외)
중복: state.json seen_urls
실행: GitHub Actions (cron-job.org 트리거, 06~22시 KST)
야간: 22시~06시 발행분은 06시 첫 실행에서 모아보기로 일괄 발송

환경변수:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (필수)
  NAVER_CLIENT_ID, NAVER_CLIENT_SECRET (권장 — 네이버 뉴스 검색 API)
  DRY_RUN=1 이면 텔레그램 발송 생략 (테스트용)
"""

import json
import os
import re
import sys
import html as html_mod
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from config import (
    KEYWORDS,
    BLOCK_KEYWORDS,
    BLOCK_DOMAINS,
    BLOCK_URL_KEYWORDS,
    EXCLUDED_WORDS,
    WORD_BOUNDARY_KEYWORDS,
    RECENCY_MINUTES,
    PRESS_FETCH_MAX,
    PRESS_FETCH_TIMEOUT,
    FETCH_COUNT,
    FETCH_COUNT_NIGHT,
    MAX_SEEN_URLS,
    PRESS_MAP,
)

KST = timezone(timedelta(hours=9))
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
NAVER_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")
DRY_RUN = os.environ.get("DRY_RUN", "") == "1"


# ---------- 매칭 ----------

def _clean_text(text):
    """EXCLUDED_WORDS 제거 후 반환."""
    for w in EXCLUDED_WORDS:
        text = text.replace(w, "")
    return text


def _contains_keyword(text, keyword):
    """키워드 매칭. 짧은 영문 키워드는 영문자 경계 적용.

    (?<![A-Za-z])KT(?![A-Za-z]) — "SKT" 안의 KT는 제외, "KT가"처럼
    한글이 붙은 경우는 매칭 (기존 \\b 방식은 한글 인접 시 매칭 실패).
    """
    if keyword in WORD_BOUNDARY_KEYWORDS:
        pattern = r"(?<![A-Za-z])" + re.escape(keyword) + r"(?![A-Za-z])"
        return re.search(pattern, text, re.IGNORECASE) is not None
    return keyword in text


def blocked_url(url):
    """스포츠 전문 매체 도메인 또는 스포츠 섹션 URL이면 True."""
    host = _host_of(url)
    for d in BLOCK_DOMAINS:
        if host == d or host.endswith("." + d):
            return True
    return any(k in url.lower() for k in BLOCK_URL_KEYWORDS)


def match_keyword(title):
    """제목에 KEYWORDS 중 하나라도 있으면 해당 키워드 반환.

    BLOCK_KEYWORDS(야구 등 제외 토픽)가 제목에 있으면 무조건 제외.
    """
    text = _clean_text(title)
    if any(b in text for b in BLOCK_KEYWORDS):
        return None
    return next((k for k in KEYWORDS if _contains_keyword(text, k)), None)


# ---------- 수집 ----------

def _http_get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _strip_tags(s):
    return html_mod.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def fetch_naver_api(query, count):
    """네이버 뉴스 검색 Open API. [(title, url, published_dt, source), ...]"""
    url = (
        "https://openapi.naver.com/v1/search/news.json?query="
        + urllib.parse.quote(query)
        + "&display=%d&sort=date" % count
    )
    raw = _http_get(url, {
        "X-Naver-Client-Id": NAVER_ID,
        "X-Naver-Client-Secret": NAVER_SECRET,
    })
    items = json.loads(raw).get("items", [])
    results = []
    for it in items:
        title = _strip_tags(it.get("title", ""))
        link = it.get("originallink") or it.get("link", "")
        try:
            pub = parsedate_to_datetime(it.get("pubDate", "")).astimezone(KST)
        except Exception:
            pub = None
        results.append((title, link, pub, ""))
    return results


def fetch_google_rss(query, count):
    """Google News RSS fallback. [(title, url, published_dt, source), ...]"""
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query + " when:1d")
        + "&hl=ko&gl=KR&ceid=KR:ko"
    )
    raw = _http_get(url)
    results = []
    for m in re.finditer(r"<item>(.*?)</item>", raw, re.S):
        block = m.group(1)
        t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, re.S)
        l = re.search(r"<link/?>(.*?)(?:</link>|<)", block, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        s = re.search(r"<source[^>]*>(.*?)</source>", block, re.S)
        if not t or not l:
            continue
        title = _strip_tags(t.group(1))
        source = _strip_tags(s.group(1)) if s else ""
        # Google RSS 제목 끝의 " - 매체명" 제거
        if source and title.endswith(" - " + source):
            title = title[: -(len(source) + 3)]
        try:
            pub = parsedate_to_datetime(d.group(1)).astimezone(KST) if d else None
        except Exception:
            pub = None
        results.append((title, l.group(1).strip(), pub, source))
    return results[:count]


def fetch_all(count):
    use_naver = bool(NAVER_ID and NAVER_SECRET)
    print("source: %s, count: %d" % ("naver-api" if use_naver else "google-rss", count))
    articles = []
    for q in KEYWORDS:
        try:
            articles += fetch_naver_api(q, count) if use_naver else fetch_google_rss(q, count)
        except Exception as e:
            print("fetch error (%s): %s" % (q, e))
    return articles


# ---------- 상태 ----------

def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"seen_urls": [], "last_run": "", "initialized": False}


def save_state(state):
    state["seen_urls"] = state["seen_urls"][-MAX_SEEN_URLS:]
    state["last_run"] = datetime.now(KST).isoformat()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def _norm_url(u):
    """dedup 키: fragment·추적 파라미터만 제거 (기사 ID 쿼리스트링은 유지)."""
    parts = urllib.parse.urlsplit(u)
    query = ""
    if parts.query:
        kept = [
            (k, v) for k, v in urllib.parse.parse_qsl(parts.query)
            if not k.lower().startswith("utm") and k.lower() not in ("fbclid", "gclid", "ref")
        ]
        query = urllib.parse.urlencode(kept)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


# ---------- 발송 ----------

TELEGRAM_MAX = 3500  # 4096 한도 대비 여유


def send_telegram(text):
    """긴 메시지는 기사 단위로 분할 발송."""
    chunks = []
    cur = ""
    for block in text.split("\n\n"):
        if cur and len(cur) + len(block) + 2 > TELEGRAM_MAX:
            chunks.append(cur)
            cur = block
        else:
            cur = (cur + "\n\n" + block) if cur else block
    if cur:
        chunks.append(cur)

    for chunk in chunks:
        if DRY_RUN:
            print("[DRY_RUN] message:\n%s\n" % chunk)
            continue
        chat_id_val = int(CHAT_ID) if CHAT_ID.lstrip("-").isdigit() else CHAT_ID
        payload = json.dumps({
            "chat_id": chat_id_val,
            "text": chunk,
            "disable_web_page_preview": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.telegram.org/bot%s/sendMessage" % BOT_TOKEN,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            print("telegram: %s" % resp.status)


def _host_of(url):
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def _fetch_site_name(url):
    """기사 페이지에서 og:site_name 매체명 추출. 실패 시 None."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=PRESS_FETCH_TIMEOUT) as resp:
            data = resp.read(65536)
    except Exception:
        return None
    head = data[:2048].decode("ascii", errors="ignore").lower()
    enc = "euc-kr" if ("euc-kr" in head or "ms949" in head or "cp949" in head) else "utf-8"
    text = data.decode(enc, errors="replace")
    m = re.search(
        r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)', text, re.I
    ) or re.search(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:site_name["\']', text, re.I
    )
    if not m:
        # 2차: copyright 메타/문구에서 매체명 추출
        # 예: <meta name="Copyright" content="서울타임즈뉴스">
        #     "Copyright ⓒ 메가경제 All rights reserved"
        m = re.search(
            r'<meta[^>]+name=["\']copyright["\'][^>]+content=["\']([^"\']+)', text, re.I
        ) or re.search(
            r'Copyright\s*[@ⓒ©]?\s*([^\s<>][^<>\n]{0,28}?)\s*(?:Corp\.?)?\s*All\s+rights\s+reserved',
            text, re.I,
        )
    if not m:
        return None
    name = html_mod.unescape(m.group(1)).strip().strip('.@ⓒ© ')
    return name[:30] or None


def press_name(url, source="", cache=None):
    """매체명 결정: Google RSS source → PRESS_MAP → 캐시. 미해결이면 None."""
    if source:
        return source
    host = _host_of(url)
    for domain, name in PRESS_MAP.items():
        if host == domain or host.endswith("." + domain):
            return name
    if cache and host in cache:
        return cache[host]
    return None


def resolve_press_names(hits, cache):
    """hits의 매체명 확정. 미등록 도메인은 기사 페이지에서 동적 조회 후 캐시.

    실행당 최대 PRESS_FETCH_MAX건만 신규 조회. 실패 시 도메인명으로 캐시해
    반복 조회를 방지한다 (수동 교정은 PRESS_MAP 또는 state.json press_names).
    """
    budget = PRESS_FETCH_MAX
    resolved = []
    for title, url, pub, source, kw in hits:
        name = press_name(url, source, cache)
        if name is None:
            host = _host_of(url) or "기타"
            if budget > 0:
                budget -= 1
                name = _fetch_site_name(url) or host
                cache[host] = name
            else:
                name = host
        resolved.append((name, title, url))
    return resolved


def build_message(resolved_hits, night_range=None):
    lines = []
    if night_range:
        lines += ["야간 모아보기 %s" % night_range, ""]
    for name, title, url in resolved_hits:
        lines.append("[%s] %s" % (name, title))
        lines.append(url)
        lines.append("")
    return "\n".join(lines).strip()


# ---------- 메인 ----------

def main():
    if not DRY_RUN and (not BOT_TOKEN or not CHAT_ID):
        print("ERROR: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정")
        sys.exit(1)

    state = load_state()
    seen = set(state["seen_urls"])
    now = datetime.now(KST)

    # 마지막 실행 이후 발행분 커버 (야간 공백 포함). 최소 RECENCY_MINUTES 보장.
    last_run = None
    try:
        last_run = datetime.fromisoformat(state.get("last_run", ""))
    except (ValueError, TypeError):
        pass
    default_cutoff = now - timedelta(minutes=RECENCY_MINUTES)
    cutoff = min(last_run, default_cutoff) if last_run else default_cutoff

    # 마지막 실행과 2시간 이상 공백이면 야간 모아보기 모드
    night_mode = last_run is not None and (now - last_run) > timedelta(hours=2)
    night_range = None
    if night_mode:
        night_range = "%s ~ %s" % (last_run.strftime("%m-%d %H:%M"), now.strftime("%m-%d %H:%M"))

    articles = fetch_all(FETCH_COUNT_NIGHT if night_mode else FETCH_COUNT)
    print("fetched: %d, night_mode: %s" % (len(articles), night_mode))

    first_run = not state.get("initialized", False)
    hits = []
    dedup_titles = set()
    for title, url, pub, source in articles:
        key = _norm_url(url)
        if not key or key in seen:
            continue
        seen.add(key)
        state["seen_urls"].append(key)
        if pub and pub < cutoff:
            continue
        if blocked_url(url):
            continue
        m = match_keyword(title)
        if not m:
            continue
        tkey = re.sub(r"\s+", "", title)[:40]
        if tkey in dedup_titles:
            continue
        dedup_titles.add(tkey)
        hits.append((title, url, pub, source, m))

    print("hits: %d" % len(hits))

    if first_run:
        # 최초 실행은 기존 기사를 seen 처리만 하고 발송 생략 (과거 기사 폭주 방지)
        print("first run — baseline only, no send")
    elif hits:
        cache = state.setdefault("press_names", {})
        send_telegram(build_message(resolve_press_names(hits, cache), night_range))

    state["initialized"] = True
    save_state(state)


if __name__ == "__main__":
    main()
