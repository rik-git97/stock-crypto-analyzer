"""Map NSE tickers to a set of aliases used for news tagging.

The Nifty 500 CSV has Symbol + Company Name. We strip 'Limited' / 'Ltd' /
'Industries' to produce shorter aliases that headline-writers actually use.
"""
from __future__ import annotations
import io
import re
import requests
import pandas as pd

NIFTY500_CSV = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 sca/0.1",
    "Accept": "text/csv,application/csv,*/*",
}

_STOP_TOKENS = {
    "limited", "ltd", "ltd.", "industries", "industries.", "company",
    "corporation", "corp", "of", "the", "and", "&", "india", "(india)",
    "private", "pvt",
}


def _short_aliases(company_name: str) -> list[str]:
    if not company_name:
        return []
    name = company_name.strip()
    aliases = {name}
    cleaned = re.sub(r"[(),.]", " ", name)
    tokens = [t for t in cleaned.split() if t.lower() not in _STOP_TOKENS]
    if tokens:
        aliases.add(" ".join(tokens))
    if len(tokens) >= 2:
        aliases.add(tokens[0])  # first word as a coarse alias e.g. "Bharti", "Bajaj"
    aliases = {a for a in aliases if len(a) >= 3}
    return list(aliases)


def fetch_aliases(timeout: int = 30) -> dict[str, list[str]]:
    r = requests.get(NIFTY500_CSV, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    out: dict[str, list[str]] = {}
    for _, row in df.iterrows():
        sym = str(row.get("Symbol", "")).strip()
        name = str(row.get("Company Name", "")).strip()
        if not sym:
            continue
        ns_ticker = f"{sym}.NS"
        out[ns_ticker] = _short_aliases(name)
    return out
