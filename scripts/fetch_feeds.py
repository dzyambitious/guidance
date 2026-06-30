#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetch up to 20 recent news items for each foreign-media outlet and write feeds.json.

Runs server-side (e.g. in GitHub Actions), so there is NO browser CORS problem:
it can read native RSS feeds and Google News directly.

Strategy per outlet (by domain):
  1) official native RSS feed if we know one (best quality)
  2) Google News site search, Chinese edition
  3) Google News site search, English edition
First candidate that yields items wins.

Usage:
  python fetch_feeds.py --media scripts/media.json --out feeds.json
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import json
import re
import sys
import time
from urllib.parse import quote

import requests
import feedparser

UA = "Mozilla/5.0 (compatible; FeedFetcher/1.0; +https://github.com)"
TIMEOUT = 20
WORKERS = 8
PER_FEED = 20

# Official native feeds (higher quality than Google News). Extend freely.
NATIVE = {
    "bbc.com": "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml",
    "dw.com": "https://rss.dw.com/rdf/rss-chi-all",
    "rfi.fr": "https://www.rfi.fr/cn/rss",
    "theguardian.com": "https://www.theguardian.com/world/rss",
    "thediplomat.com": "https://thediplomat.com/feed/",
    "nationalinterest.org": "https://nationalinterest.org/feed",
    "foxnews.com": "https://moxie.foxnews.com/google-publisher/latest.xml",
    "thehill.com": "https://thehill.com/news/feed/",
    "axios.com": "https://api.axios.com/feed/",
    "vox.com": "https://www.vox.com/rss/index.xml",
    "project-syndicate.org": "https://www.project-syndicate.org/rss",
    "moderndiplomacy.eu": "https://moderndiplomacy.eu/feed/",
    "asiatimes.com": "https://asiatimes.com/feed/",
    "warontherocks.com": "https://warontherocks.com/feed/",
    "time.com": "https://time.com/feed/",
    "wsws.org": "https://www.wsws.org/en/rss.xml",
    "thejakartapost.com": "https://www.thejakartapost.com/feed",
    "geopoliticalmonitor.com": "https://www.geopoliticalmonitor.com/feed/",
    "foreignbrief.com": "https://foreignbrief.com/feed/",
    "chinafile.com": "https://www.chinafile.com/rss.xml",
    "indianexpress.com": "https://indianexpress.com/feed/",
    "thehindu.com": "https://www.thehindu.com/feeder/default.rss",
    "timesofindia.indiatimes.com": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    "hindustantimes.com": "https://www.hindustantimes.com/feeds/rss/world-news/rssfeed.xml",
    "indiatoday.in": "https://www.indiatoday.in/rss/home",
    "zeenews.india.com": "https://zeenews.india.com/rss/world-news.xml",
    "scmp.com": "https://www.scmp.com/rss/91/feed",
    "straitstimes.com": "https://www.straitstimes.com/news/world/rss.xml",
    "asia.nikkei.com": "https://asia.nikkei.com/rss/feed/nar",
    "ftchinese.com": "https://www.ftchinese.com/rss/feed",
    "rt.com": "https://www.rt.com/rss/",
    "russian.rt.com": "https://russian.rt.com/rss/",
    "lefigaro.fr": "https://www.lefigaro.fr/rss/figaro_actualites.xml",
    "ansa.it": "https://www.ansa.it/sito/ansait_rss.xml",
    "washingtonpost.com": "https://feeds.washingtonpost.com/rss/world",
    "theglobeandmail.com": "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/world/",
    "devex.com": "https://www.devex.com/news.rss",
    "voachinese.com": "https://www.voachinese.com/api/zmgqie$moi",
    "voanews.com": "https://www.voanews.com/api/zq$omekvi",
    "cn.nytimes.com": "https://cn.nytimes.com/rss/",
}


def gnews(domain: str, en: bool = False) -> str:
    if domain == "news.google.com":
        return ("https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en" if en
                else "https://news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans")
    q = quote("site:" + domain)
    if en:
        return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    return f"https://news.google.com/rss/search?q={q}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"


def candidates(domain: str):
    out = []
    if domain in NATIVE:
        out.append(NATIVE[domain])
    out.append(gnews(domain, en=False))
    out.append(gnews(domain, en=True))
    return out


_SUFFIX = re.compile(r"^(.*) - ([^-]{2,40})$")


def clean_title(t: str):
    t = (t or "").strip()
    src = ""
    m = _SUFFIX.match(t)
    if m:
        t, src = m.group(1).strip(), m.group(2).strip()
    return t, src


def to_iso(entry) -> str:
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            try:
                return dt.datetime(*st[:6], tzinfo=dt.timezone.utc).isoformat()
            except Exception:
                pass
    return ""


def fetch(url: str) -> bytes:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content


def parse_feed(content: bytes):
    d = feedparser.parse(content)
    items = []
    for e in d.entries:
        raw_title = e.get("title", "")
        title, src_suffix = clean_title(raw_title)
        if not title:
            continue
        # Google News provides the real source under entry.source
        src = ""
        s = e.get("source")
        if isinstance(s, dict):
            src = s.get("title", "") or ""
        if not src:
            src = src_suffix
        link = e.get("link", "")
        items.append({"title": title, "link": link, "date": to_iso(e), "src": src})
    return items


def normalize(items):
    seen, out = set(), []
    for it in items:
        key = it["title"]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
        if len(out) >= PER_FEED:
            break
    return out


def get_domain_items(domain: str):
    for url in candidates(domain):
        try:
            items = normalize(parse_feed(fetch(url)))
            if items:
                return domain, items, url
        except Exception:
            continue
    return domain, [], ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--media", default="scripts/media.json",
                    help="JSON array of outlets with a 'd' (domain) field")
    ap.add_argument("--out", default="feeds.json")
    args = ap.parse_args()

    outlets = json.load(open(args.media, encoding="utf-8"))
    domains = []
    seen = set()
    for o in outlets:
        d = (o.get("d") or "").strip()
        if d and d not in seen:
            seen.add(d)
            domains.append(d)

    print(f"Fetching {len(domains)} unique domains...", flush=True)
    feeds, ok, empty = {}, 0, 0
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for domain, items, used in ex.map(get_domain_items, domains):
            feeds[domain] = items
            if items:
                ok += 1
            else:
                empty += 1
            tag = "OK " if items else "-- "
            print(f"  {tag}{domain:<34} {len(items):>2} 条  {used[:60]}", flush=True)

    payload = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
        "count": len(domains),
        "ok": ok,
        "empty": empty,
        "feeds": feeds,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    dt_s = time.time() - t0
    print(f"\nDone in {dt_s:.1f}s  ->  {args.out}  (有内容 {ok} / 空 {empty})")


if __name__ == "__main__":
    main()
