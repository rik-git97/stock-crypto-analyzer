"""Current S&P 500 constituents from Wikipedia.
v1 honest cut: PIT membership reconstruction deferred. Survivorship bias documented in tearsheet."""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def fetch_sp500_tickers(timeout: int = 30) -> list[str]:
    resp = requests.get(WIKI_URL, headers={"User-Agent": "sca/0.1"}, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.find("table", {"id": "constituents"})
    if table is None:
        raise RuntimeError("S&P 500 constituents table not found on Wikipedia page")
    tickers: list[str] = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if not cells:
            continue
        ticker = cells[0].get_text(strip=True).replace(".", "-")
        if ticker:
            tickers.append(ticker)
    return tickers
