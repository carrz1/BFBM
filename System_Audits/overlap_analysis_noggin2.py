"""Overlap / deduplication analysis for noggin2, using the still-cached raw
per-bet TSVs (E:/.../noggin2_raw/). Purpose: quantify how much of the
naive per-system-summed P/L is driven by multiple systems independently
firing on the *same* underlying bet (same horse, same race), vs how much
of the portfolio is genuinely distinct bets - to get an honest sense of
the effective independent sample size behind the headline numbers.

Reuses the exact same odds-band parsing / saved+1-date filter / BF
commission formula as build_noggin2_audit.py.
"""
import re
import pandas as pd
import numpy as np
from pathlib import Path

RAW = Path(r"E:/racing/AI/GitHub/BFBM/System_Audits/noggin2_raw")

from build_noggin2_audit import SLOTS, parse_odds_band  # reuse the real logic

def load_filtered(slot, name, saved_date):
    df = pd.read_csv(RAW / f"slot{slot}_quals.tsv", sep="\t")
    df["Date"] = pd.to_datetime(df["Date"])
    saved = pd.Timestamp(saved_date)
    since = saved + pd.Timedelta(days=1)
    sub = df[df["Date"] >= since].copy()

    lo, hi, _ = parse_odds_band(name)
    if lo is not None:
        sub = sub[(sub["Odds_Exchange"] >= lo) & (sub["Odds_Exchange"] <= hi)]

    if sub.empty:
        return sub

    sub["is_win"] = sub["Position"].astype(str) == "1"
    sub["pl_bf"] = np.where(sub["is_win"], (sub["Odds_Exchange"] - 1) * 0.95, -1.0)
    sub["pl_sp"] = np.where(sub["is_win"], sub["Odds_Numeric"], -1.0)
    sub["year"] = sub["Date"].dt.year
    # unique-bet key: same horse, same race (date+time+track) = the same
    # real-world bet opportunity, regardless of which system(s) flagged it
    sub["bet_key"] = (
        sub["Date"].dt.strftime("%Y-%m-%d") + "|" + sub["RTime"].astype(str) + "|"
        + sub["track"].astype(str) + "|" + sub["Qualifier"].astype(str)
    )
    sub["slot"] = slot
    sub["sys_name"] = name
    return sub


def main():
    frames = []
    missing = []
    for slot, (name, saved) in SLOTS.items():
        path = RAW / f"slot{slot}_quals.tsv"
        if not path.exists():
            missing.append(slot)
            continue
        sub = load_filtered(slot, name, saved)
        if not sub.empty:
            frames.append(sub)

    if missing:
        print(f"Skipped {len(missing)} slots with no raw tsv: {missing}")

    all_bets = pd.concat(frames, ignore_index=True)
    print(f"\nTotal system-bet rows (naive, one row per system-selection): {len(all_bets)}")
    print(f"Distinct systems contributing bets: {all_bets['slot'].nunique()}")

    # --- Overlap diagnostics ---
    unique_bets = all_bets["bet_key"].nunique()
    overlap_ratio = len(all_bets) / unique_bets
    print(f"Distinct real-world bets (unique horse+race): {unique_bets}")
    print(f"Overlap ratio (naive rows / unique bets): {overlap_ratio:.3f}")

    hits_per_bet = all_bets.groupby("bet_key").size()
    print("\nDistribution of how many systems fired on the same bet:")
    print(hits_per_bet.value_counts().sort_index().to_string())

    # --- Naive (per-system-summed) vs deduplicated (unique-bet) P/L by year ---
    naive_by_year = all_bets.groupby("year")["pl_bf"].agg(["sum", "count"])
    naive_by_year.columns = ["naive_plbf", "naive_bets"]

    dedup = all_bets.sort_values("Date").drop_duplicates(subset="bet_key", keep="first")
    dedup_by_year = dedup.groupby("year")["pl_bf"].agg(["sum", "count"])
    dedup_by_year.columns = ["dedup_plbf", "dedup_bets"]

    combined = naive_by_year.join(dedup_by_year, how="outer").fillna(0)
    combined["naive_bets"] = combined["naive_bets"].astype(int)
    combined["dedup_bets"] = combined["dedup_bets"].astype(int)
    combined["naive_roi_pct"] = 100 * combined["naive_plbf"] / combined["naive_bets"]
    combined["dedup_roi_pct"] = 100 * combined["dedup_plbf"] / combined["dedup_bets"]

    print("\nPer-year comparison (P/L(BF)):")
    print(combined.round(2).to_string())

    print(f"\nTOTAL naive P/L(BF):  {all_bets['pl_bf'].sum():.2f}  over {len(all_bets)} system-bets")
    print(f"TOTAL dedup P/L(BF):  {dedup['pl_bf'].sum():.2f}  over {len(dedup)} unique bets")

    all_bets.to_csv(Path(__file__).parent / "noggin2_all_system_bets.csv", index=False)
    dedup.to_csv(Path(__file__).parent / "noggin2_dedup_bets.csv", index=False)
    print("\nSaved noggin2_all_system_bets.csv and noggin2_dedup_bets.csv for further analysis.")


if __name__ == "__main__":
    main()
