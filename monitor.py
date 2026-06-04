# -*- coding: utf-8 -*-
"""특이뉴스 모니터링 — SKT 부정·리스크 기사 탐지 → 텔레그램 발송.

소스: 네이버 뉴스 검색 Open API (NAVER_CLIENT_ID/SECRET 없으면 Google News RSS fallback)
매칭: 제목에 회사 키워드 AND 리스크 키워드 둘 다 있어야 발송
중복: state.json seen_urls
실행: GitHub Actions (cron-job.org 트리거, 06~22시 KST 10분 단위)
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
    COMPANY_KEYWORDS,
    RISK_KEYWORDS,
    EXCLUDED_WORDS,
    WORD_BOUNDARY_KEYWORDS,
    RECENCY_MINUTES,
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
    """키워드 매칭. 짧은 영문 키워드는 단어 경계(\\b) 적용."""
    if keyword in WORD_BOUNDARY_KEYWORDS:
        return re.search(r"\b" + re.escape(keyword) + r"\b", text) is not None
    return keyword in text


def match_risk(title):
    """제목에 회사 키워드 AND 리스크 키워드 둘 다 있으면 (회사kw, 리스크kw) 반환."""
    text = _clean_text(title)
    company_hit = next((k for k in COMPANY_KEYWORDS if _contains_keyword(text, k)), None)
    if not company_hit:
        return None
    risk_hit = next((k for k in RISK_KEYWORDS if _contains_keyword(text, k)), None)
    if not risk_hit:
        return None
    return (company_hit, risk_hit)


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
    for q in COMPANY_KEYWORDS:
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


def press_name(url, source=""):
    """매체명 결정: Google RSS source 우선, 없으면 URL 도메인 → PRESS_MAP."""
    if source:
        return source
    host = urllib.parse.urlparse(url).netloc.lower()
    for domain, name in PRESS_MAP.items():
        if host == domain or host.endswith("." + domain):
            return name
    return host.removeprefix("www.") or "기타"


def build_message(hits, night_range=None):
    header = "*특이기사 모니터링"
    if night_range:
        header += " (야간 모아보기 %s)" % night_range
    lines = [header, ""]
    for title, url, pub, source, ckw, rkw in hits:
        lines.append("[%s] %s" % (press_name(url, source), title))
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
        m = match_risk(title)
        if not m:
            continue
        tkey = re.sub(r"\s+", "", title)[:40]
        if tkey in dedup_titles:
            continue
        dedup_titles.add(tkey)
        hits.append((title, url, pub, source, m[0], m[1]))

    print("hits: %d" % len(hits))

    if first_run:
        # 최초 실행은 기존 기사를 seen 처리만 하고 발송 생략 (과거 기사 폭주 방지)
        print("first run — baseline only, no send")
    elif hits:
        send_telegram(build_message(hits, night_range))

    state["initialized"] = True
    save_state(state)


if __name__ == "__main__":
    main()
