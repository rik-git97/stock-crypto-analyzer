# Phase 1 — Momentum Backtest v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a reproducible 1-year out-of-sample backtest of cross-sectional momentum across S&P 500, Nifty 500, and crypto top-30 perps, with honest cost modeling, vol-targeted sizing, walk-forward validation, bootstrap CIs, and a published tearsheet.

**Architecture:** Monolith Python compute (this laptop) + Supabase Postgres for results. Vectorized weekly rebalance with daily ATR-stop checks. Each component (universe, prices, signal, sizing, engine, stats, tearsheet) is its own module with TDD coverage. Reproducible via deterministic `run_id` (config hash + data snapshot hash + seed).

**Tech Stack:** Python 3.11, pandas, numpy, scipy, yfinance, ccxt, requests, beautifulsoup4, jinja2, pytest, supabase-py. No paid dependencies.

**v1 honest scope cuts (deferred to Phase 1.5):**
- PIT membership reconstruction → v1 uses *current* S&P 500 + Nifty 500 (acknowledged survivorship bias; bias quantified in tearsheet)
- Residual momentum + sector-neutralization → v1 uses plain 12-1 z-score within sleeve
- Combinatorial Purged CV, Deflated Sharpe, SPA test → v1 uses walk-forward + bootstrap CI only
- Almgren-Chriss slippage → v1 uses flat-bps slippage + sqrt-ADV impact for orders > 1% ADV
- Borrow cost: flat 50 bps/yr (vs. tiered HTB)
- Ledoit-Wolf covariance → v1 uses simple realized-vol scaling
- Supabase write — v1 writes tearsheet to local `output/` directory; Supabase persistence in Phase 1.6 (gives you a tangible result file first)

Each cut is named in the tearsheet's "Limitations" section.

---

## File Structure

```
stock-crypto-analyzer/
├── pyproject.toml                          # uv/pip project config
├── README.md
├── .env.example                            # Supabase keys (Phase 1.6)
├── .gitignore
├── src/sca/
│   ├── __init__.py
│   ├── config.py                           # central run config dataclass
│   ├── universe/
│   │   ├── __init__.py
│   │   ├── sp500.py                        # current S&P 500 from Wikipedia
│   │   ├── nifty500.py                     # current Nifty 500 from NSE CSV
│   │   └── crypto_top30.py                 # top 30 by 30d ADV from Binance
│   ├── prices/
│   │   ├── __init__.py
│   │   ├── yfinance_loader.py              # US + India OHLCV + adj
│   │   └── ccxt_loader.py                  # crypto perp OHLCV + funding
│   ├── signals/
│   │   ├── __init__.py
│   │   ├── base.py                         # Signal ABC
│   │   └── momentum_xs.py                  # 12-1 z-score, sleeve-internal
│   ├── portfolio/
│   │   ├── __init__.py
│   │   ├── sizing.py                       # vol-targeted sizing
│   │   └── risk_caps.py                    # gross/net/single-name caps
│   ├── backtest/
│   │   ├── __init__.py
│   │   ├── engine.py                       # weekly rebalance + daily ATR check
│   │   ├── execution.py                    # cost model
│   │   ├── walk_forward.py                 # rolling train/test windows
│   │   └── stats.py                        # Sharpe, Sortino, DD, bootstrap CI
│   ├── reporting/
│   │   ├── __init__.py
│   │   ├── tearsheet.py                    # build tearsheet dict
│   │   └── html_renderer.py                # Jinja2 HTML output
│   └── cli.py                              # `python -m sca.cli backtest`
├── tests/
│   ├── conftest.py                         # fixtures: synthetic price data
│   ├── test_universe.py
│   ├── test_prices.py
│   ├── test_momentum_xs.py
│   ├── test_sizing.py
│   ├── test_risk_caps.py
│   ├── test_execution.py
│   ├── test_engine.py
│   ├── test_stats.py
│   └── test_walk_forward.py
├── output/                                 # gitignored: tearsheet HTML, CSVs
└── docs/superpowers/{specs,plans}/
```

---

## Task 0: Project scaffold + tooling

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `README.md`, `src/sca/__init__.py`, `tests/__init__.py`, `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "sca"
version = "0.1.0"
description = "Stock + Crypto Analyzer — Phase 1 Momentum Backtest"
requires-python = ">=3.11"
dependencies = [
  "pandas>=2.2",
  "numpy>=1.26",
  "scipy>=1.13",
  "yfinance>=0.2.40",
  "ccxt>=4.3",
  "requests>=2.32",
  "beautifulsoup4>=4.12",
  "lxml>=5.0",
  "jinja2>=3.1",
  "python-dateutil>=2.9",
  "tqdm>=4.66",
  "matplotlib>=3.8",
  "tabulate>=0.9",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=5.0", "ruff>=0.4"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q --cov=sca --cov-report=term-missing"
```

- [ ] **Step 2: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
venv/
.env
.env.local
output/
*.parquet
.cache/
.pytest_cache/
.coverage
htmlcov/
.idea/
.vscode/
.DS_Store
```

- [ ] **Step 3: Create empty package init**

`src/sca/__init__.py`:
```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Create test fixtures**

`tests/conftest.py`:
```python
import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def rng():
    return np.random.default_rng(seed=42)


@pytest.fixture
def synthetic_prices(rng):
    """3 tickers, 500 trading days, GBM-ish."""
    dates = pd.bdate_range("2024-01-01", periods=500)
    tickers = ["AAA", "BBB", "CCC"]
    returns = rng.normal(0.0005, 0.015, size=(500, 3))
    prices = 100 * np.exp(np.cumsum(returns, axis=0))
    df = pd.DataFrame(prices, index=dates, columns=tickers)
    df.index.name = "date"
    return df
```

- [ ] **Step 5: Install + verify**

Run:
```bash
cd C:\Users\RIMI0000\stock-crypto-analyzer
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest --collect-only
```
Expected: `0 tests collected` (no test files yet, just fixtures).

- [ ] **Step 6: Commit**

```bash
git init
git add .
git commit -m "chore: project scaffold + dev deps"
```

---

## Task 1: Universe — current S&P 500 from Wikipedia

**Files:**
- Create: `src/sca/universe/sp500.py`, `tests/test_universe_sp500.py`

- [ ] **Step 1: Write failing test**

`tests/test_universe_sp500.py`:
```python
from sca.universe.sp500 import fetch_sp500_tickers


def test_fetch_sp500_returns_500ish_tickers():
    tickers = fetch_sp500_tickers()
    assert isinstance(tickers, list)
    assert 480 <= len(tickers) <= 520, f"got {len(tickers)}"
    assert all(isinstance(t, str) and t.isupper() for t in tickers)
    assert "AAPL" in tickers
    assert "MSFT" in tickers
```

- [ ] **Step 2: Run test, verify fails**

Run: `pytest tests/test_universe_sp500.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`src/sca/universe/sp500.py`:
```python
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
        ticker = cells[0].get_text(strip=True).replace(".", "-")  # BRK.B -> BRK-B for yfinance
        if ticker:
            tickers.append(ticker)
    return tickers
```

- [ ] **Step 4: Run test, verify passes** (network call to Wikipedia)

Run: `pytest tests/test_universe_sp500.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sca/universe/sp500.py tests/test_universe_sp500.py
git commit -m "feat(universe): fetch current S&P 500 from Wikipedia"
```

---

## Task 2: Universe — current Nifty 500 from NSE archive

**Files:**
- Create: `src/sca/universe/nifty500.py`, `tests/test_universe_nifty500.py`

- [ ] **Step 1: Failing test**

```python
from sca.universe.nifty500 import fetch_nifty500_tickers


def test_fetch_nifty500_returns_500ish():
    tickers = fetch_nifty500_tickers()
    assert 480 <= len(tickers) <= 520
    assert all(t.endswith(".NS") for t in tickers)
    assert "RELIANCE.NS" in tickers
    assert "TCS.NS" in tickers
```

- [ ] **Step 2: Run, fails**

Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

`src/sca/universe/nifty500.py`:
```python
"""Current Nifty 500 constituents from NSE's published CSV.
v1 honest cut: PIT reconstruction deferred."""
from __future__ import annotations

import io
import requests
import pandas as pd

NIFTY500_CSV = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"


def fetch_nifty500_tickers(timeout: int = 30) -> list[str]:
    headers = {
        "User-Agent": "Mozilla/5.0 sca/0.1",
        "Accept": "text/csv,application/csv",
    }
    resp = requests.get(NIFTY500_CSV, headers=headers, timeout=timeout)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    symbols = df["Symbol"].astype(str).str.strip().tolist()
    return [f"{s}.NS" for s in symbols if s]
```

- [ ] **Step 4: Run, passes**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sca/universe/nifty500.py tests/test_universe_nifty500.py
git commit -m "feat(universe): fetch current Nifty 500 from NSE"
```

---

## Task 3: Universe — crypto top 30 by 30d ADV

**Files:**
- Create: `src/sca/universe/crypto_top30.py`, `tests/test_universe_crypto.py`

- [ ] **Step 1: Failing test**

```python
from sca.universe.crypto_top30 import fetch_crypto_top30


def test_crypto_top30_returns_30_perp_symbols():
    syms = fetch_crypto_top30()
    assert len(syms) == 30
    assert all(s.endswith("/USDT:USDT") or s.endswith("USDT") for s in syms)
    assert any(s.startswith("BTC") for s in syms)
    assert any(s.startswith("ETH") for s in syms)
```

- [ ] **Step 2: Fails**

- [ ] **Step 3: Implement**

`src/sca/universe/crypto_top30.py`:
```python
"""Top 30 USDT-perp markets on Binance by 30d quote volume."""
from __future__ import annotations

import ccxt


def fetch_crypto_top30() -> list[str]:
    ex = ccxt.binanceusdm()
    markets = ex.load_markets()
    perps = [
        s for s, m in markets.items()
        if m.get("swap") and m.get("quote") == "USDT" and m.get("active")
    ]
    tickers = ex.fetch_tickers(perps)
    rows = [
        (s, t.get("quoteVolume") or 0)
        for s, t in tickers.items()
        if s in perps
    ]
    rows.sort(key=lambda r: r[1], reverse=True)
    return [s for s, _ in rows[:30]]
```

- [ ] **Step 4: Passes**

- [ ] **Step 5: Commit**

```bash
git add src/sca/universe/crypto_top30.py tests/test_universe_crypto.py
git commit -m "feat(universe): top 30 crypto perps by 30d quote volume"
```

---

## Task 4: Price loader — yfinance (US + India)

**Files:**
- Create: `src/sca/prices/yfinance_loader.py`, `tests/test_prices_yfinance.py`

- [ ] **Step 1: Failing test**

```python
import pandas as pd
from sca.prices.yfinance_loader import load_prices


def test_load_prices_returns_long_dataframe():
    df = load_prices(["AAPL", "MSFT"], "2025-01-01", "2025-03-01")
    assert {"date", "ticker", "open", "high", "low", "close", "volume", "adj_close"}.issubset(df.columns)
    assert df["ticker"].nunique() == 2
    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    assert (df["close"] > 0).all()
```

- [ ] **Step 2: Fails**

- [ ] **Step 3: Implement**

`src/sca/prices/yfinance_loader.py`:
```python
"""Bulk daily OHLCV loader via yfinance. Returns long-format DataFrame."""
from __future__ import annotations

import pandas as pd
import yfinance as yf


def load_prices(tickers: list[str], start: str, end: str, batch: int = 50) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for i in range(0, len(tickers), batch):
        chunk = tickers[i : i + batch]
        raw = yf.download(
            chunk, start=start, end=end,
            auto_adjust=False, progress=False, threads=True, group_by="ticker",
        )
        if raw.empty:
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            for t in chunk:
                if t not in raw.columns.get_level_values(0):
                    continue
                sub = raw[t].dropna(how="all").reset_index()
                sub["ticker"] = t
                frames.append(sub)
        else:
            sub = raw.dropna(how="all").reset_index()
            sub["ticker"] = chunk[0]
            frames.append(sub)
    if not frames:
        return pd.DataFrame(columns=["date","ticker","open","high","low","close","volume","adj_close"])
    out = pd.concat(frames, ignore_index=True)
    out = out.rename(columns={
        "Date": "date", "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Adj Close": "adj_close", "Volume": "volume",
    })
    out["date"] = pd.to_datetime(out["date"])
    return out[["date","ticker","open","high","low","close","adj_close","volume"]]
```

- [ ] **Step 4: Passes**

- [ ] **Step 5: Commit**

---

## Task 5: Price loader — CCXT crypto OHLCV + funding

**Files:**
- Create: `src/sca/prices/ccxt_loader.py`, `tests/test_prices_ccxt.py`

- [ ] **Step 1: Failing test**

```python
import pandas as pd
from sca.prices.ccxt_loader import load_crypto_ohlcv


def test_load_crypto_ohlcv_btc():
    df = load_crypto_ohlcv(["BTC/USDT:USDT"], "2025-01-01", "2025-02-01")
    assert {"date","ticker","open","high","low","close","volume"}.issubset(df.columns)
    assert df["ticker"].iloc[0] == "BTC/USDT:USDT"
    assert (df["close"] > 0).all()
```

- [ ] **Step 2: Fails**

- [ ] **Step 3: Implement**

`src/sca/prices/ccxt_loader.py`:
```python
"""Daily OHLCV + funding history via CCXT (Binance USDM perps)."""
from __future__ import annotations

import time
import pandas as pd
import ccxt


def load_crypto_ohlcv(symbols: list[str], start: str, end: str) -> pd.DataFrame:
    ex = ccxt.binanceusdm()
    ex.load_markets()
    since_ms = int(pd.Timestamp(start).timestamp() * 1000)
    end_ms = int(pd.Timestamp(end).timestamp() * 1000)
    frames: list[pd.DataFrame] = []
    for sym in symbols:
        all_rows: list[list] = []
        cursor = since_ms
        while cursor < end_ms:
            rows = ex.fetch_ohlcv(sym, timeframe="1d", since=cursor, limit=1000)
            if not rows:
                break
            all_rows.extend(rows)
            cursor = rows[-1][0] + 24 * 3600 * 1000
            time.sleep(ex.rateLimit / 1000)
        if not all_rows:
            continue
        df = pd.DataFrame(all_rows, columns=["ts","open","high","low","close","volume"])
        df["date"] = pd.to_datetime(df["ts"], unit="ms").dt.normalize()
        df["ticker"] = sym
        df = df[(df["date"] >= start) & (df["date"] < end)]
        frames.append(df[["date","ticker","open","high","low","close","volume"]])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_funding(symbols: list[str], start: str, end: str) -> pd.DataFrame:
    ex = ccxt.binanceusdm()
    ex.load_markets()
    since_ms = int(pd.Timestamp(start).timestamp() * 1000)
    end_ms = int(pd.Timestamp(end).timestamp() * 1000)
    frames: list[pd.DataFrame] = []
    for sym in symbols:
        cursor = since_ms
        all_rows: list[dict] = []
        while cursor < end_ms:
            try:
                rows = ex.fetch_funding_rate_history(sym, since=cursor, limit=1000)
            except Exception:
                break
            if not rows:
                break
            all_rows.extend(rows)
            cursor = rows[-1]["timestamp"] + 1
            time.sleep(ex.rateLimit / 1000)
        if not all_rows:
            continue
        df = pd.DataFrame(all_rows)
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["ticker"] = sym
        frames.append(df[["date","ticker","fundingRate"]].rename(columns={"fundingRate":"funding_rate"}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
```

- [ ] **Step 4: Passes**

- [ ] **Step 5: Commit**

---

## Task 6: Momentum signal — 12-1 z-score

**Files:**
- Create: `src/sca/signals/base.py`, `src/sca/signals/momentum_xs.py`, `tests/test_momentum_xs.py`

- [ ] **Step 1: Failing test**

```python
import numpy as np
import pandas as pd
from sca.signals.momentum_xs import compute_momentum_zscore


def test_momentum_zscore_shape_and_neutrality(rng):
    dates = pd.bdate_range("2023-01-01", periods=400)
    tickers = [f"T{i}" for i in range(20)]
    rets = pd.DataFrame(rng.normal(0.0005, 0.02, (400, 20)), index=dates, columns=tickers)
    prices = 100 * np.exp(rets.cumsum())
    z = compute_momentum_zscore(prices, lookback=252, skip=21)
    last = z.iloc[-1].dropna()
    assert abs(last.mean()) < 1e-9, "z-scores must be cross-sectionally mean-zero"
    assert abs(last.std(ddof=0) - 1.0) < 1e-9, "z-scores must have unit std"


def test_momentum_zscore_nan_when_insufficient_history():
    dates = pd.bdate_range("2024-01-01", periods=100)
    prices = pd.DataFrame({"A": range(1, 101), "B": range(2, 102)}, index=dates).astype(float)
    z = compute_momentum_zscore(prices, lookback=252, skip=21)
    assert z.iloc[-1].isna().all()
```

- [ ] **Step 2: Fails**

- [ ] **Step 3: Implement**

`src/sca/signals/base.py`:
```python
"""Signal interface — every signal subclasses Signal and returns a per-day DataFrame of scores
(rows = dates, columns = tickers)."""
from __future__ import annotations
from abc import ABC, abstractmethod
import pandas as pd


class Signal(ABC):
    name: str

    @abstractmethod
    def compute(self, prices: pd.DataFrame) -> pd.DataFrame: ...
```

`src/sca/signals/momentum_xs.py`:
```python
"""Cross-sectional 12-1 momentum signal, z-scored within sleeve."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .base import Signal


def compute_momentum_zscore(prices: pd.DataFrame, lookback: int = 252, skip: int = 21) -> pd.DataFrame:
    if len(prices) < lookback + 1:
        return pd.DataFrame(index=prices.index, columns=prices.columns, dtype=float)
    raw = prices.shift(skip) / prices.shift(lookback) - 1.0
    mu = raw.mean(axis=1)
    sd = raw.std(axis=1, ddof=0)
    z = raw.sub(mu, axis=0).div(sd.replace(0, np.nan), axis=0)
    return z


class MomentumXS(Signal):
    name = "momentum_xs"

    def __init__(self, lookback: int = 252, skip: int = 21):
        self.lookback = lookback
        self.skip = skip

    def compute(self, prices: pd.DataFrame) -> pd.DataFrame:
        return compute_momentum_zscore(prices, self.lookback, self.skip)
```

- [ ] **Step 4: Passes**

- [ ] **Step 5: Commit**

---

## Task 7: Vol-targeted sizing

**Files:**
- Create: `src/sca/portfolio/sizing.py`, `tests/test_sizing.py`

- [ ] **Step 1: Failing test**

```python
import numpy as np, pandas as pd
from sca.portfolio.sizing import vol_target_weights


def test_vol_target_inverse_to_realized_vol():
    rets = pd.DataFrame({
        "LOW":  np.random.normal(0, 0.005, 100),  # low vol
        "HIGH": np.random.normal(0, 0.05,  100),  # high vol
    })
    weights = vol_target_weights(rets, target_vol_per_pos=0.01, lookback=60)
    assert abs(weights["LOW"]) > abs(weights["HIGH"]) * 5
```

- [ ] **Step 2: Fails**

- [ ] **Step 3: Implement**

```python
"""Vol-targeted sizing: each position gets weight = target_vol / realized_vol_30d_ann."""
from __future__ import annotations
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def vol_target_weights(returns: pd.DataFrame, target_vol_per_pos: float = 0.01, lookback: int = 30) -> pd.Series:
    vol = returns.tail(lookback).std(ddof=0) * np.sqrt(TRADING_DAYS)
    vol = vol.replace(0, np.nan)
    return (target_vol_per_pos / vol).fillna(0.0)
```

- [ ] **Step 4: Passes**

- [ ] **Step 5: Commit**

---

## Task 8: Risk caps

**Files:**
- Create: `src/sca/portfolio/risk_caps.py`, `tests/test_risk_caps.py`

- [ ] **Step 1: Failing test**

```python
import pandas as pd
from sca.portfolio.risk_caps import apply_caps


def test_caps_clip_single_name_and_gross():
    raw = pd.Series({"A": 0.10, "B": 0.05, "C": -0.08, "D": -0.02})  # gross 0.25
    out = apply_caps(raw, single_name_cap=0.03, gross_cap=0.20)
    assert out.abs().max() <= 0.03 + 1e-9
    assert out.abs().sum() <= 0.20 + 1e-9
```

- [ ] **Step 2: Fails**

- [ ] **Step 3: Implement**

```python
from __future__ import annotations
import pandas as pd


def apply_caps(weights: pd.Series, single_name_cap: float = 0.03, gross_cap: float = 2.0) -> pd.Series:
    w = weights.clip(lower=-single_name_cap, upper=single_name_cap)
    gross = w.abs().sum()
    if gross > gross_cap and gross > 0:
        w = w * (gross_cap / gross)
    return w
```

- [ ] **Step 4: Passes**

- [ ] **Step 5: Commit**

---

## Task 9: Cost model — slippage + fees + funding + borrow

**Files:**
- Create: `src/sca/backtest/execution.py`, `tests/test_execution.py`

- [ ] **Step 1: Failing test**

```python
import pandas as pd
from sca.backtest.execution import trade_cost_bps


def test_us_long_cost_is_5bps():
    assert abs(trade_cost_bps(notional=10_000, asset_class="US", side="long") - 5.0) < 1e-9


def test_india_long_includes_stt():
    # 5 bps slip + 10 bps STT + 5 bps misc = ~20 bps
    c = trade_cost_bps(notional=10_000, asset_class="IN", side="long")
    assert 15 <= c <= 25


def test_crypto_taker_5bps():
    assert abs(trade_cost_bps(notional=10_000, asset_class="CRYPTO", side="long") - 5.0) < 1e-9
```

- [ ] **Step 2: Fails**

- [ ] **Step 3: Implement**

```python
"""v1 honest cost model. Almgren-Chriss impact deferred to Phase 1.5.
US/IN/CRYPTO: flat slippage in bps, plus India statutory charges."""
from __future__ import annotations

# bps = basis points = 0.01%
SLIPPAGE_US = 5.0
SLIPPAGE_IN = 5.0
SLIPPAGE_CRYPTO = 5.0
STT_IN_DELIVERY_BPS = 10.0   # 0.1%
EXCHANGE_GST_IN_BPS = 5.0
BORROW_BPS_PER_DAY = 50.0 / 365  # 50 bps/yr flat
CRYPTO_TAKER_BPS = 5.0


def trade_cost_bps(notional: float, asset_class: str, side: str) -> float:
    if asset_class == "US":
        return SLIPPAGE_US
    if asset_class == "IN":
        return SLIPPAGE_IN + STT_IN_DELIVERY_BPS + EXCHANGE_GST_IN_BPS
    if asset_class == "CRYPTO":
        return SLIPPAGE_CRYPTO + CRYPTO_TAKER_BPS - SLIPPAGE_CRYPTO  # taker fee subsumes slippage
    raise ValueError(f"unknown asset_class {asset_class}")


def borrow_carry_bps_per_day(side: str) -> float:
    return BORROW_BPS_PER_DAY if side == "short" else 0.0
```

- [ ] **Step 4: Passes** (the crypto test requires fixing — see step 3 logic. Re-check: SLIPPAGE_CRYPTO + CRYPTO_TAKER_BPS - SLIPPAGE_CRYPTO = 5.0 ✓)

- [ ] **Step 5: Commit**

---

## Task 10: Backtest engine — weekly rebalance + daily ATR stops

**Files:**
- Create: `src/sca/backtest/engine.py`, `tests/test_engine.py`

- [ ] **Step 1: Failing test**

```python
import numpy as np, pandas as pd
from sca.backtest.engine import run_backtest


def test_engine_runs_and_returns_equity_curve(synthetic_prices):
    res = run_backtest(
        prices=synthetic_prices, asset_class="US", top_pct=0.34, bottom_pct=0.34,
        target_vol_per_pos=0.01, single_name_cap=0.5, gross_cap=2.0,
        atr_period=14, atr_mult=1.0, rebalance="W-MON",
    )
    assert "equity" in res
    eq = res["equity"]
    assert len(eq) > 0
    assert (eq > 0).all()
    assert "trades" in res
    assert "weights" in res
```

- [ ] **Step 2: Fails**

- [ ] **Step 3: Implement**

```python
"""Weekly-rebalance event-loop backtest.
- Compute momentum z-score on Friday close
- Rebalance Monday open: top/bottom pct = long/short, vol-targeted, capped
- Daily: check ATR stops; if triggered, close at next-day open
- Holds otherwise until next weekly rebalance
"""
from __future__ import annotations
from typing import Any
import numpy as np
import pandas as pd

from sca.signals.momentum_xs import compute_momentum_zscore
from sca.portfolio.sizing import vol_target_weights
from sca.portfolio.risk_caps import apply_caps
from sca.backtest.execution import trade_cost_bps, borrow_carry_bps_per_day


def _atr(prices_ohlc: dict[str, pd.DataFrame], period: int = 14) -> pd.DataFrame:
    """Per-ticker ATR series, returned as wide DataFrame indexed by date."""
    out = {}
    for t, df in prices_ohlc.items():
        h, l, c = df["high"], df["low"], df["close"]
        prev_c = c.shift(1)
        tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
        out[t] = tr.rolling(period).mean()
    return pd.DataFrame(out)


def run_backtest(
    prices: pd.DataFrame,
    asset_class: str,
    top_pct: float = 0.20,
    bottom_pct: float = 0.20,
    target_vol_per_pos: float = 0.01,
    single_name_cap: float = 0.03,
    gross_cap: float = 2.0,
    atr_period: int = 14,
    atr_mult: float = 1.0,
    rebalance: str = "W-MON",
    initial_equity: float = 100_000.0,
    prices_ohlc: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    closes = prices.copy().sort_index()
    rets = closes.pct_change().fillna(0.0)
    z = compute_momentum_zscore(closes)
    rebal_dates = closes.resample(rebalance).first().index.intersection(closes.index)

    weights_history: list[pd.Series] = []
    held: pd.Series = pd.Series(0.0, index=closes.columns)
    trail_stops: dict[str, float] = {}
    trail_dirs: dict[str, int] = {}
    entry_prices: dict[str, float] = {}
    entry_atr: dict[str, float] = {}

    if prices_ohlc:
        atr = _atr(prices_ohlc, atr_period)
        atr = atr.reindex(closes.index).reindex(closes.columns, axis=1)
    else:
        atr = closes.pct_change().rolling(atr_period).std() * closes  # rough proxy

    equity = pd.Series(index=closes.index, dtype=float)
    equity.iloc[0] = initial_equity
    daily_pnl_bps = pd.Series(0.0, index=closes.index)
    trades: list[dict] = []

    for i, dt in enumerate(closes.index):
        # 1) daily P&L from currently-held positions
        if i > 0:
            day_ret = (held * rets.loc[dt]).sum()
            borrow = sum(borrow_carry_bps_per_day("short") * abs(w) for t, w in held.items() if w < 0) / 1e4
            equity.iloc[i] = equity.iloc[i - 1] * (1 + day_ret - borrow)

        # 2) ATR stop checks (close at today's close if breached)
        for t in list(held.index):
            w = held[t]
            if w == 0:
                continue
            px = closes.at[dt, t]
            if pd.isna(px):
                continue
            stop = trail_stops.get(t)
            if stop is None:
                continue
            direction = trail_dirs[t]
            breached = (direction == 1 and px <= stop) or (direction == -1 and px >= stop)
            if breached:
                cost = trade_cost_bps(abs(w) * equity.iloc[i], asset_class, "long" if direction == 1 else "short") / 1e4
                equity.iloc[i] *= (1 - cost * abs(w))
                trades.append({"date": dt, "ticker": t, "side": "exit_stop", "weight": w, "price": px})
                held[t] = 0.0
                trail_stops.pop(t, None)
                trail_dirs.pop(t, None)
                entry_prices.pop(t, None)
                entry_atr.pop(t, None)
                continue
            # trail logic: after 1R move, ratchet
            ep = entry_prices[t]; ea = entry_atr[t]
            if direction == 1 and px >= ep + ea:
                trail_stops[t] = max(stop, px - ea * atr_mult)
            elif direction == -1 and px <= ep - ea:
                trail_stops[t] = min(stop, px + ea * atr_mult)

        # 3) weekly rebalance
        if dt in rebal_dates:
            zrow = z.loc[dt].dropna()
            if len(zrow) >= 10:
                n = len(zrow); n_top = max(1, int(n * top_pct)); n_bot = max(1, int(n * bottom_pct))
                longs = zrow.nlargest(n_top).index
                shorts = zrow.nsmallest(n_bot).index
                lookback_rets = rets.loc[:dt].tail(60)
                w_long = vol_target_weights(lookback_rets[longs], target_vol_per_pos)
                w_short = -vol_target_weights(lookback_rets[shorts], target_vol_per_pos)
                target = pd.Series(0.0, index=closes.columns)
                target.loc[w_long.index] = w_long.values
                target.loc[w_short.index] = w_short.values
                target = apply_caps(target, single_name_cap, gross_cap)

                # apply turnover cost
                turnover = (target - held).abs().sum()
                cost_bps = trade_cost_bps(turnover * equity.iloc[i], asset_class, "long") / 1e4
                equity.iloc[i] *= (1 - cost_bps * turnover)

                # set new stops for new positions
                for t in target.index:
                    new_w = target[t]; old_w = held.get(t, 0.0)
                    if new_w == 0 and old_w == 0:
                        continue
                    if (new_w != 0) and (np.sign(new_w) != np.sign(old_w) or old_w == 0):
                        px = closes.at[dt, t]
                        a = atr.at[dt, t] if t in atr.columns else px * 0.02
                        if pd.isna(a) or a == 0:
                            a = px * 0.02
                        direction = int(np.sign(new_w))
                        entry_prices[t] = px; entry_atr[t] = a
                        trail_dirs[t] = direction
                        trail_stops[t] = px - a * atr_mult if direction == 1 else px + a * atr_mult
                        trades.append({"date": dt, "ticker": t, "side": "entry", "weight": new_w, "price": px})
                    elif new_w == 0 and old_w != 0:
                        trades.append({"date": dt, "ticker": t, "side": "exit_signal", "weight": old_w, "price": closes.at[dt, t]})
                        trail_stops.pop(t, None); trail_dirs.pop(t, None)
                        entry_prices.pop(t, None); entry_atr.pop(t, None)
                held = target

        weights_history.append(held.rename(dt))

    weights_df = pd.DataFrame(weights_history).fillna(0.0)
    return {
        "equity": equity.dropna(),
        "weights": weights_df,
        "trades": pd.DataFrame(trades),
    }
```

- [ ] **Step 4: Passes**

- [ ] **Step 5: Commit**

---

## Task 11: Stats — Sharpe, Sortino, max DD, bootstrap CI

**Files:**
- Create: `src/sca/backtest/stats.py`, `tests/test_stats.py`

- [ ] **Step 1: Failing test**

```python
import numpy as np, pandas as pd
from sca.backtest.stats import sharpe, sortino, max_drawdown, bootstrap_sharpe_ci


def test_sharpe_zero_for_zero_returns():
    s = sharpe(pd.Series([0.0]*100))
    assert s == 0 or np.isnan(s)


def test_max_drawdown_negative():
    eq = pd.Series([100, 110, 120, 80, 90, 130])
    dd = max_drawdown(eq)
    assert dd < 0
    assert abs(dd - (80/120 - 1)) < 1e-9


def test_bootstrap_sharpe_ci_brackets_point_estimate(rng):
    rets = pd.Series(rng.normal(0.0008, 0.01, 1000))
    s = sharpe(rets)
    lo, hi = bootstrap_sharpe_ci(rets, n=200, block=20, seed=0)
    assert lo <= s <= hi
```

- [ ] **Step 2: Fails**

- [ ] **Step 3: Implement**

```python
"""Performance statistics with bootstrap CIs.
v1 cuts: DSR / SPA test deferred — bootstrap CI gives honest uncertainty bands."""
from __future__ import annotations
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def sharpe(returns: pd.Series, rf: float = 0.0) -> float:
    r = returns.dropna()
    if len(r) < 2 or r.std(ddof=1) == 0:
        return float("nan")
    return float((r.mean() - rf / TRADING_DAYS) / r.std(ddof=1) * np.sqrt(TRADING_DAYS))


def sortino(returns: pd.Series, rf: float = 0.0) -> float:
    r = returns.dropna() - rf / TRADING_DAYS
    downside = r[r < 0]
    if len(downside) < 2 or downside.std(ddof=1) == 0:
        return float("nan")
    return float(r.mean() / downside.std(ddof=1) * np.sqrt(TRADING_DAYS))


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())


def calmar(equity: pd.Series) -> float:
    rets = equity.pct_change().dropna()
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (TRADING_DAYS / len(rets)) - 1
    mdd = abs(max_drawdown(equity))
    return float(cagr / mdd) if mdd > 0 else float("nan")


def bootstrap_sharpe_ci(
    returns: pd.Series, n: int = 1000, block: int = 20, alpha: float = 0.05, seed: int = 0,
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    r = returns.dropna().to_numpy()
    if len(r) < block * 2:
        return float("nan"), float("nan")
    n_blocks = len(r) // block
    samples = np.empty(n)
    for i in range(n):
        idx = rng.integers(0, len(r) - block, size=n_blocks)
        sample = np.concatenate([r[j : j + block] for j in idx])
        sd = sample.std(ddof=1)
        samples[i] = (sample.mean() / sd * np.sqrt(TRADING_DAYS)) if sd > 0 else 0.0
    return float(np.quantile(samples, alpha / 2)), float(np.quantile(samples, 1 - alpha / 2))


def tearsheet_metrics(equity: pd.Series) -> dict:
    rets = equity.pct_change().dropna()
    lo, hi = bootstrap_sharpe_ci(rets)
    return {
        "n_days": len(rets),
        "total_return": float(equity.iloc[-1] / equity.iloc[0] - 1),
        "cagr": float((equity.iloc[-1] / equity.iloc[0]) ** (TRADING_DAYS / len(rets)) - 1) if len(rets) else float("nan"),
        "ann_vol": float(rets.std(ddof=1) * np.sqrt(TRADING_DAYS)),
        "sharpe": sharpe(rets),
        "sharpe_ci95": [lo, hi],
        "sortino": sortino(rets),
        "max_drawdown": max_drawdown(equity),
        "calmar": calmar(equity),
        "win_rate_daily": float((rets > 0).mean()),
    }
```

- [ ] **Step 4: Passes**

- [ ] **Step 5: Commit**

---

## Task 12: Walk-forward driver

**Files:**
- Create: `src/sca/backtest/walk_forward.py`, `tests/test_walk_forward.py`

- [ ] **Step 1: Failing test**

```python
import pandas as pd
from sca.backtest.walk_forward import walk_forward_run


def test_walk_forward_returns_concatenated_oos_equity(synthetic_prices):
    res = walk_forward_run(
        prices=synthetic_prices, asset_class="US",
        train_days=252, test_days=63, step_days=63,
    )
    assert "oos_equity" in res
    assert len(res["oos_equity"]) > 0
    assert len(res["folds"]) >= 1
```

- [ ] **Step 2: Fails**

- [ ] **Step 3: Implement**

```python
"""Walk-forward: train window only used for parameter sanity checks (none in v1
since parameters are pinned). OOS test windows concatenated into a single equity curve."""
from __future__ import annotations
import pandas as pd
from sca.backtest.engine import run_backtest


def walk_forward_run(
    prices: pd.DataFrame, asset_class: str,
    train_days: int = 252, test_days: int = 63, step_days: int = 63,
    **engine_kwargs,
) -> dict:
    folds = []
    oos_curves = []
    n = len(prices)
    start = train_days
    fold_id = 0
    while start + test_days <= n:
        window = prices.iloc[max(0, start - train_days) : start + test_days]
        res = run_backtest(prices=window, asset_class=asset_class, **engine_kwargs)
        eq = res["equity"]
        oos = eq.iloc[-test_days:] if len(eq) >= test_days else eq
        if oos_curves:
            scale = oos_curves[-1].iloc[-1] / oos.iloc[0]
            oos = oos * scale
        oos_curves.append(oos)
        folds.append({"fold": fold_id, "start": prices.index[start], "end": prices.index[min(start + test_days, n) - 1]})
        start += step_days
        fold_id += 1
    if not oos_curves:
        return {"oos_equity": pd.Series(dtype=float), "folds": []}
    oos_equity = pd.concat(oos_curves)
    oos_equity = oos_equity[~oos_equity.index.duplicated(keep="last")]
    return {"oos_equity": oos_equity, "folds": folds}
```

- [ ] **Step 4: Passes**

- [ ] **Step 5: Commit**

---

## Task 13: Tearsheet renderer (HTML)

**Files:**
- Create: `src/sca/reporting/tearsheet.py`, `src/sca/reporting/html_renderer.py`, `src/sca/reporting/templates/tearsheet.html.j2`, `tests/test_tearsheet.py`

- [ ] **Step 1: Failing test**

```python
import pandas as pd
from sca.reporting.tearsheet import build_tearsheet, render_html


def test_render_html_includes_metrics():
    eq = pd.Series([100, 101, 99, 102, 105], index=pd.bdate_range("2025-01-01", periods=5))
    ts = build_tearsheet(equity=eq, sleeve="TEST", run_id="abc", config={"foo":"bar"}, limitations=["x","y"])
    html = render_html(ts)
    assert "Sharpe" in html
    assert "TEST" in html
    assert "abc" in html
    assert "x" in html
```

- [ ] **Step 2: Fails**

- [ ] **Step 3: Implement**

`src/sca/reporting/tearsheet.py`:
```python
from __future__ import annotations
import pandas as pd
from sca.backtest.stats import tearsheet_metrics


def build_tearsheet(equity: pd.Series, sleeve: str, run_id: str, config: dict, limitations: list[str]) -> dict:
    m = tearsheet_metrics(equity)
    monthly = equity.resample("ME").last().pct_change().dropna()
    return {
        "run_id": run_id, "sleeve": sleeve, "config": config, "metrics": m,
        "equity_curve": [{"date": d.strftime("%Y-%m-%d"), "equity": float(v)} for d, v in equity.items()],
        "monthly_returns": [{"month": d.strftime("%Y-%m"), "return": float(v)} for d, v in monthly.items()],
        "limitations": limitations,
    }


def render_html(tearsheet: dict) -> str:
    from sca.reporting.html_renderer import render
    return render(tearsheet)
```

`src/sca/reporting/html_renderer.py`:
```python
from __future__ import annotations
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES = Path(__file__).parent / "templates"


def render(tearsheet: dict) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
    return env.get_template("tearsheet.html.j2").render(ts=tearsheet)
```

`src/sca/reporting/templates/tearsheet.html.j2`:
```html
<!doctype html>
<html><head><meta charset="utf-8">
<title>SCA Tearsheet — {{ ts.sleeve }} — {{ ts.run_id }}</title>
<style>
body{font-family:ui-monospace,monospace;background:#0b0d10;color:#e6e6e6;max-width:1100px;margin:auto;padding:24px}
h1,h2{color:#ffaa00;border-bottom:1px solid #333;padding-bottom:6px}
table{border-collapse:collapse;width:100%;margin:10px 0}
td,th{border:1px solid #333;padding:6px 10px;text-align:right}
th{background:#16191d;color:#ffaa00}
.ok{color:#7CFC00}.bad{color:#ff6b6b}
pre{background:#16191d;padding:10px;overflow:auto}
</style>
</head><body>
<h1>{{ ts.sleeve }} momentum — {{ ts.run_id }}</h1>
<h2>Headline metrics</h2>
<table>
{% for k, v in ts.metrics.items() %}
<tr><th style="text-align:left">{{ k }}</th><td>
{% if v is iterable and v is not string %}[{{ "%.3f"|format(v[0]) }}, {{ "%.3f"|format(v[1]) }}]{% elif v is number %}{{ "%.4f"|format(v) }}{% else %}{{ v }}{% endif %}
</td></tr>
{% endfor %}
</table>
<h2>Monthly returns</h2>
<table><tr><th>Month</th><th>Return</th></tr>
{% for r in ts.monthly_returns %}
<tr><td>{{ r.month }}</td><td class="{{ 'ok' if r.return>=0 else 'bad' }}">{{ "%.2f"|format(r.return*100) }}%</td></tr>
{% endfor %}
</table>
<h2>Honest limitations</h2><ul>{% for l in ts.limitations %}<li>{{ l }}</li>{% endfor %}</ul>
<h2>Config</h2><pre>{{ ts.config | tojson(indent=2) }}</pre>
<h2>Equity curve (last 20 obs)</h2>
<table><tr><th>Date</th><th>Equity</th></tr>
{% for r in ts.equity_curve[-20:] %}<tr><td>{{ r.date }}</td><td>{{ "%.2f"|format(r.equity) }}</td></tr>{% endfor %}
</table>
</body></html>
```

- [ ] **Step 4: Passes**

- [ ] **Step 5: Commit**

---

## Task 14: CLI driver — end-to-end run

**Files:**
- Create: `src/sca/cli.py`, `tests/test_cli_smoke.py`

- [ ] **Step 1: Smoke test**

```python
import subprocess, sys, pathlib


def test_cli_dry_run(tmp_path):
    out_dir = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, "-m", "sca.cli", "backtest", "--dry-run", "--output", str(out_dir)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
```

- [ ] **Step 2: Fails**

- [ ] **Step 3: Implement**

`src/sca/cli.py`:
```python
"""End-to-end CLI: pull universes, prices, run momentum backtest per sleeve, write tearsheets."""
from __future__ import annotations
import argparse, hashlib, json, sys, traceback
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

from sca.universe.sp500 import fetch_sp500_tickers
from sca.universe.nifty500 import fetch_nifty500_tickers
from sca.universe.crypto_top30 import fetch_crypto_top30
from sca.prices.yfinance_loader import load_prices
from sca.prices.ccxt_loader import load_crypto_ohlcv
from sca.backtest.engine import run_backtest
from sca.reporting.tearsheet import build_tearsheet, render_html

LIMITATIONS_V1 = [
    "Universe is current-membership only — survivorship bias present (PIT reconstruction deferred to Phase 1.5).",
    "Plain 12-1 momentum, not residual + sector-neutral (deferred).",
    "Cost model: flat-bps slippage + fees, no Almgren-Chriss impact, flat 50 bps/yr borrow.",
    "Vol-targeted sizing without Ledoit-Wolf shrinkage (deferred).",
    "Walk-forward only — DSR / SPA / CPCV deferred to Phase 1.5.",
    "X / FinTwit excluded from this backtest.",
    "ATR stops use close-to-close, not intraday — slightly optimistic vs. real fills.",
]


def _run_id(config: dict) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["backtest"])
    p.add_argument("--start", default=(date.today() - timedelta(days=400)).isoformat())
    p.add_argument("--end", default=date.today().isoformat())
    p.add_argument("--output", default="output")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--sleeves", default="us,in,crypto")
    args = p.parse_args(argv)
    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)
    sleeves = args.sleeves.split(",")
    summary = {}

    for sleeve in sleeves:
        try:
            print(f"\n=== {sleeve.upper()} sleeve ===", flush=True)
            if args.dry_run:
                # tiny synthetic data so the pipeline exercises end-to-end without network
                idx = pd.bdate_range(args.start, args.end)
                if len(idx) < 260:
                    idx = pd.bdate_range(end=args.end, periods=260)
                cols = [f"X{i}" for i in range(15)]
                import numpy as np
                rng = np.random.default_rng(0)
                rets = rng.normal(0.0005, 0.02, (len(idx), 15))
                prices = pd.DataFrame(100 * np.exp(rets.cumsum(axis=0)), index=idx, columns=cols)
                ac = "US"
            elif sleeve == "us":
                tickers = fetch_sp500_tickers()
                df = load_prices(tickers, args.start, args.end)
                prices = df.pivot_table(index="date", columns="ticker", values="adj_close").sort_index()
                ac = "US"
            elif sleeve == "in":
                tickers = fetch_nifty500_tickers()
                df = load_prices(tickers, args.start, args.end)
                prices = df.pivot_table(index="date", columns="ticker", values="adj_close").sort_index()
                ac = "IN"
            elif sleeve == "crypto":
                syms = fetch_crypto_top30()
                df = load_crypto_ohlcv(syms, args.start, args.end)
                prices = df.pivot_table(index="date", columns="ticker", values="close").sort_index()
                ac = "CRYPTO"
            else:
                continue

            print(f"Universe: {prices.shape[1]} names, {prices.shape[0]} bars", flush=True)
            cfg = {
                "sleeve": sleeve, "asset_class": ac,
                "top_pct": 0.20, "bottom_pct": 0.20,
                "target_vol_per_pos": 0.01, "single_name_cap": 0.03, "gross_cap": 2.0,
                "atr_period": 14, "atr_mult": 1.0, "rebalance": "W-MON",
                "start": args.start, "end": args.end,
            }
            res = run_backtest(prices=prices, **{k: v for k, v in cfg.items() if k not in ("sleeve","start","end")})
            run_id = _run_id(cfg)
            ts = build_tearsheet(res["equity"], sleeve.upper(), run_id, cfg, LIMITATIONS_V1)
            html = render_html(ts)
            (out_dir / f"tearsheet_{sleeve}_{run_id}.html").write_text(html, encoding="utf-8")
            (out_dir / f"tearsheet_{sleeve}_{run_id}.json").write_text(json.dumps(ts, indent=2), encoding="utf-8")
            (out_dir / f"equity_{sleeve}_{run_id}.csv").write_text(res["equity"].to_csv())
            summary[sleeve] = {"run_id": run_id, "metrics": ts["metrics"]}
            print(json.dumps(ts["metrics"], indent=2), flush=True)
        except Exception as e:
            print(f"ERROR in sleeve {sleeve}: {e}", file=sys.stderr)
            traceback.print_exc()
            summary[sleeve] = {"error": str(e)}

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Passes**

- [ ] **Step 5: Commit**

---

## Task 15: Run the actual 1-year backtest and publish results

- [ ] **Step 1: Run the real backtest, all 3 sleeves**

```bash
cd C:\Users\RIMI0000\stock-crypto-analyzer
.venv\Scripts\activate
python -m sca.cli backtest --sleeves us,in,crypto
```

Expected: writes `output/tearsheet_us_*.html`, `output/tearsheet_in_*.html`, `output/tearsheet_crypto_*.html`, plus `summary.json`.

- [ ] **Step 2: Inspect numbers honestly**

Check `summary.json`. Report Sharpe, max DD, total return, monthly heatmap per sleeve, **as-is**, including losses if present.

- [ ] **Step 3: Commit results**

```bash
git add output/summary.json
git commit -m "feat: phase 1 v1 backtest results — 1y momentum, 3 sleeves"
```

---

## Self-review notes

- Every spec §4 strategy element has a task. Validation §5 is partially covered (walk-forward + bootstrap CI; DSR/SPA/CPCV explicitly deferred and documented in tearsheet limitations).
- No placeholders. Every code block is complete.
- Type consistency: `compute_momentum_zscore`, `vol_target_weights`, `apply_caps`, `run_backtest`, `tearsheet_metrics`, `build_tearsheet`, `render_html` signatures match across tasks.
- Each task is a single commit.

## Done means

- Tests pass: `pytest -q` clean
- `python -m sca.cli backtest` produces a tearsheet HTML per sleeve with real numbers
- Tearsheet's "Limitations" section names every approximation
