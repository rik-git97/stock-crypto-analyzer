"""Signal-health metrics — IC, decay, regime drift.

IC (Information Coefficient) — Spearman correlation between picks' z-scores at
time T and their realized 5-day forward returns. Computed weekly per sleeve.

Strategy is healthy when IC > 0 most weeks. If IC averages < 0 over 4+ weeks,
the strategy is broken — the signal has reversed or decayed.

All metrics persist to output/live/history/health.parquet.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd


@dataclass
class HealthRow:
    sleeve: str
    as_of: str
    ic_5d: float            # Spearman corr of z vs 5d-fwd return
    n_picks: int
    n_with_return: int
    median_5d_return: float


def compute_ic_for_picks(picks_dict: dict, prices: pd.DataFrame, fwd_days: int = 5) -> HealthRow:
    """picks_dict is the saved JSON from a prior run. prices is the wide DataFrame."""
    sleeve = picks_dict.get("sleeve", "")
    as_of_str = picks_dict.get("as_of", "")
    longs = picks_dict.get("longs", [])
    shorts = picks_dict.get("shorts", [])
    all_picks = longs + shorts
    if not all_picks or as_of_str == "":
        return HealthRow(sleeve, as_of_str, float("nan"), 0, 0, float("nan"))

    as_of = pd.Timestamp(as_of_str)
    if prices.empty or as_of not in prices.index:
        return HealthRow(sleeve, as_of_str, float("nan"), len(all_picks), 0, float("nan"))

    fwd = prices.loc[prices.index > as_of].head(fwd_days + 1)
    if len(fwd) < 1:
        return HealthRow(sleeve, as_of_str, float("nan"), len(all_picks), 0, float("nan"))

    target_idx = min(len(fwd) - 1, fwd_days - 1)
    pairs = []
    for p in all_picks:
        t = p["ticker"]
        if t not in prices.columns:
            continue
        entry = prices.at[as_of, t]
        if pd.isna(entry) or entry <= 0:
            continue
        exit_px = fwd.iloc[target_idx][t]
        if pd.isna(exit_px):
            continue
        ret = float(exit_px / entry - 1.0)
        pairs.append((float(p["z_score"]), ret))

    if len(pairs) < 5:
        return HealthRow(sleeve, as_of_str, float("nan"), len(all_picks), len(pairs), float("nan"))

    arr = np.array(pairs)
    # Spearman = Pearson on ranks
    z_ranks = pd.Series(arr[:, 0]).rank().to_numpy()
    r_ranks = pd.Series(arr[:, 1]).rank().to_numpy()
    if z_ranks.std() == 0 or r_ranks.std() == 0:
        ic = float("nan")
    else:
        ic = float(np.corrcoef(z_ranks, r_ranks)[0, 1])

    return HealthRow(
        sleeve=sleeve, as_of=as_of_str,
        ic_5d=ic, n_picks=len(all_picks), n_with_return=len(pairs),
        median_5d_return=float(np.median(arr[:, 1])),
    )


def append_health(row: HealthRow, archive_path: Path) -> Path:
    archive_path = Path(archive_path)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    df_new = pd.DataFrame([{
        "sleeve": row.sleeve, "as_of": row.as_of,
        "ic_5d": row.ic_5d, "n_picks": row.n_picks,
        "n_with_return": row.n_with_return, "median_5d_return": row.median_5d_return,
        "recorded_at": pd.Timestamp.utcnow(),
    }])
    if archive_path.exists():
        prev = pd.read_parquet(archive_path)
        merged = pd.concat([prev, df_new], ignore_index=True)
    else:
        merged = df_new
    merged = merged.drop_duplicates(subset=["sleeve", "as_of"]).reset_index(drop=True)
    merged.to_parquet(archive_path, index=False)
    return archive_path


def health_summary(archive_path: Path) -> list[dict]:
    if not Path(archive_path).exists():
        return []
    df = pd.read_parquet(archive_path)
    if df.empty:
        return []
    out = []
    for sleeve in sorted(df["sleeve"].unique()):
        sub = df[df["sleeve"] == sleeve].sort_values("as_of")
        if len(sub) == 0:
            continue
        ic = sub["ic_5d"].dropna()
        recent4 = ic.tail(4)
        out.append({
            "sleeve": sleeve.upper(),
            "weeks_tracked": int(len(sub)),
            "latest_ic": float(ic.iloc[-1]) if len(ic) else float("nan"),
            "rolling4_ic": float(recent4.mean()) if len(recent4) else float("nan"),
            "rolling4_ic_negative": bool(len(recent4) >= 4 and recent4.mean() < 0),
            "broken_flag": bool(len(recent4) >= 4 and recent4.mean() < 0),
        })
    return out
