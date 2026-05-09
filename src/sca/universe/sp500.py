"""Current S&P 500 constituents + GICS sector from Wikipedia."""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def _parse_table(timeout: int = 30):
    resp = requests.get(WIKI_URL, headers={"User-Agent": "sca/0.1"}, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.find("table", {"id": "constituents"})
    if table is None:
        raise RuntimeError("S&P 500 constituents table not found on Wikipedia page")
    rows = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        ticker = cells[0].get_text(strip=True).replace(".", "-")
        sector = cells[2].get_text(strip=True)
        if ticker:
            rows.append((ticker, sector))
    return rows


def fetch_sp500_tickers(timeout: int = 30) -> list[str]:
    return [t for t, _ in _parse_table(timeout)]


def fetch_sp500_sectors(timeout: int = 30) -> dict[str, str]:
    return {t: s for t, s in _parse_table(timeout)}
