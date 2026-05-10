"""Indian financial-news RSS aggregator with per-ticker tagging.

Sources (all free):
- Moneycontrol: https://www.moneycontrol.com/rss/buzzingstocks.xml, marketreports.xml, etc.
- Economic Times Markets: https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms
- Business Standard Markets: https://www.business-standard.com/rss/markets-106.rss
- Livemint Markets: https://www.livemint.com/rss/markets

Per-ticker tagging is rule-based: substring match of company name (or aliases) in
headline. NO synthesized sentiment; we only count headlines and apply transparent
keyword flags for risk categories.
"""
from __future__ import annotations
import re
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
import requests
from xml.etree import ElementTree as ET

FEEDS = {
    "moneycontrol_buzzing": "https://www.moneycontrol.com/rss/buzzingstocks.xml",
    "moneycontrol_market": "https://www.moneycontrol.com/rss/marketreports.xml",
    "moneycontrol_business": "https://www.moneycontrol.com/rss/business.xml",
    "et_markets": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "et_news": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "business_standard_markets": "https://www.business-standard.com/rss/markets-106.rss",
    "livemint_markets": "https://www.livemint.com/rss/markets",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

RISK_FLAGS = {
    "regulatory": [r"\bSEBI\b", r"raid", r"probe", r"investigat", r"penalty", r"banned",
                   r"suspended", r"non[- ]compliance", r"show cause"],
    "fraud": [r"fraud", r"scam", r"misappropriat", r"forgery", r"cheating"],
    "downgrade": [r"downgrad", r"cut rating", r"sell rating", r"underperform", r"reduce"],
    "upgrade": [r"upgrad", r"buy rating", r"outperform", r"target raised", r"target hiked"],
    "results": [r"q[1-4] result", r"earnings beat", r"earnings miss", r"profit jumps",
                r"profit fall", r"net loss", r"revenue ros", r"revenue fell"],
    "corporate_action": [r"bonus", r"split", r"dividend", r"buyback", r"rights issue",
                         r"merger", r"acquisition", r"demerger"],
    "litigation": [r"lawsuit", r"court", r"tribunal", r"NCLT", r"insolvency", r"IBC"],
}


@dataclass
class NewsItem:
    headline: str
    link: str
    source: str
    published: str
    flags: list[str] = field(default_factory=list)


def _parse_feed(url: str, source_label: str, timeout: int = 15) -> list[NewsItem]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
    except Exception as e:
        print(f"[news] {source_label} fetch failed: {e}")
        return []
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        return []
    items = []
    for ch in root.iter("item"):
        title_el = ch.find("title"); link_el = ch.find("link"); pub_el = ch.find("pubDate")
        title = (title_el.text or "").strip() if title_el is not None else ""
        link = (link_el.text or "").strip() if link_el is not None else ""
        pub = (pub_el.text or "").strip() if pub_el is not None else ""
        if not title:
            continue
        items.append(NewsItem(headline=title, link=link, source=source_label, published=pub))
    return items


def fetch_all_news() -> list[NewsItem]:
    out: list[NewsItem] = []
    for label, url in FEEDS.items():
        out.extend(_parse_feed(url, label))
        time.sleep(0.3)
    seen = set()
    deduped = []
    for n in out:
        key = n.headline.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(n)
    return deduped


def apply_flags(items: list[NewsItem]) -> list[NewsItem]:
    for n in items:
        text = n.headline.lower()
        for flag, patterns in RISK_FLAGS.items():
            if any(re.search(p, text, flags=re.I) for p in patterns):
                if flag not in n.flags:
                    n.flags.append(flag)
    return items


def tag_per_ticker(
    items: list[NewsItem],
    ticker_to_aliases: dict[str, list[str]],
    max_per_ticker: int = 3,
) -> dict[str, list[NewsItem]]:
    """Match headlines to tickers using alias substring matching (case-insensitive, word-boundary).
    Returns ticker -> list of news items, sorted most-recent first, capped at max_per_ticker.
    """
    out: dict[str, list[NewsItem]] = {t: [] for t in ticker_to_aliases.keys()}
    compiled = {
        t: [re.compile(rf"\b{re.escape(a)}\b", re.IGNORECASE) for a in aliases if a]
        for t, aliases in ticker_to_aliases.items()
    }
    for n in items:
        for ticker, regs in compiled.items():
            if any(rg.search(n.headline) for rg in regs):
                if len(out[ticker]) < max_per_ticker:
                    out[ticker].append(n)
    return out


def newsitems_to_dict(items: list[NewsItem]) -> list[dict]:
    return [asdict(n) for n in items]
