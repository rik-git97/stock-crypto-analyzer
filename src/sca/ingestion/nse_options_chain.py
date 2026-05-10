"""NSE F&O bhav-copy fetcher — official EOD archive (much more reliable than live chain).

Live option chain (`/api/option-chain-indices`) is heavily anti-bot-protected and returns
empty body for headless requests. The F&O bhav-copy is published daily by NSE and
covers every NSE derivative (options + futures) — strikes, expiries, EOD close, OI,
volume, lot size. For positional 3-6 month strategies, EOD Friday close is sufficient.

Backed by nselib's `fno_bhav_copy`. Falls back across the last 5 trading days if today's
file isn't published yet (Sundays, holidays).
"""
from __future__ import annotations
from datetime import date, timedelta
import pandas as pd  # noqa: F401

try:
    from nselib import derivatives as _nse_derivs
except ImportError:
    _nse_derivs = None


def _latest_bhav_copy(max_lookback_days: int = 7) -> tuple[pd.DataFrame, str]:
    """Try the last few trading days until we get a populated bhav-copy."""
    if _nse_derivs is None:
        return pd.DataFrame(), ""
    today = date.today()
    for offset in range(max_lookback_days):
        d = today - timedelta(days=offset)
        if d.weekday() >= 5:        # Sat/Sun — NSE doesn't publish
            continue
        s = d.strftime("%d-%m-%Y")
        try:
            df = _nse_derivs.fno_bhav_copy(trade_date=s)
            if df is not None and len(df) > 0:
                return df, s
        except Exception:
            continue
    return pd.DataFrame(), ""


def fetch_option_chain(symbol: str = "NIFTY", timeout: int = 25, retries: int = 3) -> dict:
    """Compat-shim returning a dict that chain_to_dataframe knows how to flatten.

    Internally pulls the most recent F&O bhav-copy and filters to options for `symbol`.
    """
    df, trade_date = _latest_bhav_copy()
    if df.empty:
        return {}
    # Filter to options for the symbol. NSE uses IDO (index option), STO (stock option);
    # filter by OptnTp ∈ {CE, PE} which works for both.
    options = df[
        (df.get("TckrSymb", "").astype(str) == symbol)
        & (df.get("OptnTp", "").astype(str).isin(["CE", "PE"]))
    ].copy()
    if options.empty:
        return {}
    # Repackage into the structure chain_to_dataframe expects
    records_data = []
    for (strike, expiry), grp in options.groupby(["StrkPric", "XpryDt"]):
        row = {"strikePrice": float(strike), "expiryDate": _format_expiry(expiry)}
        for _, opt in grp.iterrows():
            side_letter = str(opt.get("OptnTp", "")).strip().upper()
            side = "CE" if side_letter == "CE" else ("PE" if side_letter == "PE" else None)
            if side is None:
                continue
            row[side] = {
                "lastPrice": float(opt.get("ClsPric") or 0),
                "bidprice": 0,
                "askPrice": 0,
                "openInterest": int(opt.get("OpnIntrst") or 0),
                "changeinOpenInterest": int(opt.get("ChngInOpnIntrst") or 0),
                "impliedVolatility": 0,    # bhav copy doesn't carry IV
                "totalTradedVolume": int(opt.get("TtlTradgVol") or 0),
                "underlyingValue": float(opt.get("UndrlygPric") or 0),
            }
        records_data.append(row)
    return {
        "records": {"data": records_data, "underlyingValue": float(options["UndrlygPric"].dropna().iloc[0]) if not options["UndrlygPric"].dropna().empty else 0},
        "_source": f"fno_bhav_copy {trade_date}",
    }


def _format_expiry(x) -> str:
    """Normalize to dd-MMM-yyyy as the live chain returns."""
    ts = pd.to_datetime(x, errors="coerce")
    if pd.isna(ts):
        return ""
    return ts.strftime("%d-%b-%Y")


def chain_to_dataframe(chain_json: dict) -> pd.DataFrame:
    """Flatten our compat-shape JSON to a long DataFrame."""
    records = chain_json.get("records", {})
    data = records.get("data", [])
    rows = []
    for item in data:
        strike = item.get("strikePrice")
        expiry = item.get("expiryDate")
        for side in ("CE", "PE"):
            leg = item.get(side)
            if not leg:
                continue
            rows.append({
                "expiry": expiry,
                "strike": strike,
                "side": side,
                "ltp": leg.get("lastPrice", 0),
                "bid": leg.get("bidprice", 0),
                "ask": leg.get("askPrice", 0),
                "oi": leg.get("openInterest", 0),
                "oi_change": leg.get("changeinOpenInterest", 0),
                "iv": leg.get("impliedVolatility", 0),
                "volume": leg.get("totalTradedVolume", 0),
                "underlying": leg.get("underlyingValue", 0),
            })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["expiry"] = pd.to_datetime(df["expiry"], errors="coerce", format="%d-%b-%Y")
    return df


def list_expiries(chain_df: pd.DataFrame) -> list[pd.Timestamp]:
    if chain_df.empty:
        return []
    return sorted(chain_df["expiry"].dropna().unique())
