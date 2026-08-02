"""Odds-to-field-size ratio as a proxy for 'distance from the crowd', and a
variable-stake formula built on it (Phil Bull-style: bet more when the
value signal is stronger).

CEO's theory: in an N-runner race, if every horse had an equal chance the
'fair' BF price would be N (a 10-runner race -> 10.00 each). A selection's
own price relative to that baseline tells you how far the crowd has moved
it from equal-chance:
  - odds < runners  -> shorter than the equal-chance baseline ("towards the
    crowd" - the market already fancies it, harder to find an edge here)
  - odds > runners  -> longer than the baseline ("away from the crowd" -
    less likely to win any one bet, but if the system is right, more
    likely to be a genuine inefficiency)

value_ratio = Odds_Exchange / Runners

Staking idea (Phil Bull logic, "half the expected odds half the stake,
double the expected odds double the stake"): stake = value_ratio, capped
at a chosen ceiling to bound drawdown, base unit = 1 point.

IMPORTANT CAVEAT this report is built to surface, not hide: we already know
from race_dilution_report.py that ROI rises with raw odds. Since
value_ratio is odds divided by a (comparatively low-variance) runners
count, betting more when value_ratio is high will mechanically shift stake
toward the bets that were already the best-performing bucket. A better
blended ROI in a backtest is therefore NOT by itself proof the ratio found
something odds-alone didn't - it may just be leverage on a known effect.
Section 2 checks whether the ratio explains anything BEYOND raw odds and
runners individually; Section 4 is the year-by-year stability check.
"""
from pathlib import Path

import pandas as pd

from filtered_agreement_report import (
    MIN_BETS, MAX_LOSS_PCT, load_all_bets, standalone_performance,
)

BASE = Path(__file__).parent

RATIO_BINS = [0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0, 100000]
RATIO_LABELS = ["<0.5", "0.5-1.0", "1.0-1.5", "1.5-2.0", "2.0-3.0",
                "3.0-5.0", "5.0-8.0", "8.0+"]

ODDS_BINS = [0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 100000]
ODDS_LABELS = ["1.01-2.00", "2.01-4.00", "4.01-8.00", "8.01-16.00",
               "16.01-32.00", "32.01-64.00", "64.01-128.00", "128.01+"]

STAKE_CAPS = [1.0, 2.0, 3.0, 5.0, 8.0, 10.0, None]  # None = uncapped


def load_filtered_bets():
    all_bets = load_all_bets()
    standalone = standalone_performance(all_bets)
    qualifying = standalone[(standalone["bets"] >= MIN_BETS) &
                             (standalone["roi_pct"] >= MAX_LOSS_PCT)]
    filtered = all_bets[all_bets["sys_key"].isin(qualifying.index)].copy()

    grouped = filtered.groupby("bet_key").agg(
        pl_bf=("pl_bf", "first"), is_win=("is_win", "first"),
        year=("year", "first"), Date=("Date", "first"),
        Runners=("Runners", "first"), Odds_Exchange=("Odds_Exchange", "first"),
    ).reset_index()
    grouped["Date"] = pd.to_datetime(grouped["Date"])
    grouped = grouped.dropna(subset=["Runners", "Odds_Exchange"])
    grouped = grouped[grouped["Runners"] > 0]
    grouped["value_ratio"] = grouped["Odds_Exchange"] / grouped["Runners"]
    return grouped.sort_values("Date").reset_index(drop=True)


def roi_row(sub, label, key_col="Group"):
    n = len(sub)
    return {
        key_col: label, "Bets": n,
        "Wins": int(sub["is_win"].sum()),
        "Win%": round(100 * sub["is_win"].mean(), 2) if n else 0,
        "AvgOdds": round(sub["Odds_Exchange"].mean(), 2) if n else 0,
        "AvgRunners": round(sub["Runners"].mean(), 2) if n else 0,
        "BF_P/L": round(sub["pl_bf"].sum(), 2),
        "ROI%": round(100 * sub["pl_bf"].sum() / n, 2) if n else 0,
    }


def section1_ratio_bands(bets):
    print("=" * 100)
    print("SECTION 1 - P/L BY value_ratio BAND (Odds_Exchange / Runners), "
          "quality-filtered universe, 1 stake per distinct bet")
    print("=" * 100)
    bets = bets.copy()
    bets["ratio_band"] = pd.cut(bets["value_ratio"], bins=RATIO_BINS, labels=RATIO_LABELS)
    rows = [roi_row(bets[bets["ratio_band"] == b], b, "Ratio Band")
            for b in RATIO_LABELS if (bets["ratio_band"] == b).any()]
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    return df


def section2_ratio_vs_odds_alone(bets):
    print()
    print("=" * 100)
    print("SECTION 2 - DOES value_ratio ADD ANYTHING BEYOND RAW ODDS? Within each "
          "odds band, split bets at the median ratio into 'small field for the "
          "price' vs 'big field for the price'")
    print("=" * 100)
    bets = bets.copy()
    bets["odds_band"] = pd.cut(bets["Odds_Exchange"], bins=ODDS_BINS, labels=ODDS_LABELS)
    rows = []
    for b in ODDS_LABELS:
        sub = bets[bets["odds_band"] == b]
        if len(sub) < 40:
            continue
        med = sub["value_ratio"].median()
        lo, hi = sub[sub["value_ratio"] <= med], sub[sub["value_ratio"] > med]
        r_lo, r_hi = roi_row(lo, "low", "Half"), roi_row(hi, "high", "Half")
        rows.append({
            "OddsBand": b, "MedianRatio": round(med, 2),
            "Bets_smallfield": r_lo["Bets"], "AvgRunners_small": r_lo["AvgRunners"],
            "ROI%_smallfield": r_lo["ROI%"],
            "Bets_bigfield": r_hi["Bets"], "AvgRunners_big": r_hi["AvgRunners"],
            "ROI%_bigfield": r_hi["ROI%"],
        })
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print("""
Reading this table: within EACH odds band, "small field" bets got that
price in a race with fewer runners than typical for the band (so a HIGH
value_ratio - priced long relative to a small field); "big field" bets got
the same price range but in a bigger field (LOW value_ratio - priced long,
but that's less remarkable with more runners to be long against). If
value_ratio is only re-describing raw odds, the two ROI% columns should
look similar in every row. If field size is doing independent work, they
should diverge - specifically, the theory predicts small-field (high
ratio) should outperform big-field (low ratio) within the same odds band.
""")
    return df


def section3_staking_backtest(bets):
    print("=" * 100)
    print("SECTION 3 - VARIABLE-STAKE BACKTEST: stake = min(cap, value_ratio), "
          "vs flat 1-point staking (bets ordered chronologically by Date)")
    print("=" * 100)
    rows = []
    for cap in STAKE_CAPS:
        stake = bets["value_ratio"] if cap is None else bets["value_ratio"].clip(upper=cap)
        scaled_pl = bets["pl_bf"] * stake
        total_staked = stake.sum()
        total_pl = scaled_pl.sum()
        cum = scaled_pl.cumsum()
        running_peak = cum.cummax()
        max_dd = (cum - running_peak).min()
        rows.append({
            "Cap": "uncapped" if cap is None else cap,
            "TotalStaked": round(total_staked, 1),
            "BF_P/L": round(total_pl, 2),
            "ROI%": round(100 * total_pl / total_staked, 2),
            "MaxDrawdown": round(max_dd, 1),
            "MaxSingleStake": round(stake.max(), 2),
        })
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    flat_roi = 100 * bets["pl_bf"].sum() / len(bets)
    print(f"\n(for reference, flat 1-point staking on this exact universe: "
          f"ROI% = {flat_roi:.2f}, BF_P/L = {bets['pl_bf'].sum():.2f}, "
          f"total staked = {len(bets)})")
    return df


def section4_year_by_year(bets, cap=5.0):
    print()
    print("=" * 100)
    print(f"SECTION 4 - YEAR-BY-YEAR STABILITY, cap={cap}, scaled vs flat staking")
    print("=" * 100)
    bets = bets.copy()
    bets["stake"] = bets["value_ratio"].clip(upper=cap)
    rows = []
    for y in sorted(bets["year"].unique()):
        sub = bets[bets["year"] == y]
        staked = sub["stake"].sum()
        pl = (sub["pl_bf"] * sub["stake"]).sum()
        flat_pl = sub["pl_bf"].sum()
        rows.append({
            "Year": int(y), "Bets": len(sub),
            "ROI%_flat": round(100 * flat_pl / len(sub), 2),
            "ROI%_scaled": round(100 * pl / staked, 2) if staked else 0,
        })
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    return df


def main():
    bets = load_filtered_bets()
    print(f"Distinct bets in quality-filtered universe (with Runners/Odds_Exchange "
          f"available): {len(bets):,}\n")

    s1 = section1_ratio_bands(bets)
    s2 = section2_ratio_vs_odds_alone(bets)
    s3 = section3_staking_backtest(bets)
    s4 = section4_year_by_year(bets)

    print()
    print("=" * 100)
    print("NOTES")
    print("=" * 100)
    print("""
- value_ratio = Odds_Exchange / Runners. Under a naive equal-chance
  baseline (every runner priced at exactly 'Runners') a ratio of 1.0 is
  the baseline itself; >1 means the selection is priced longer than that
  naive baseline ("away from the crowd"), <1 means shorter ("towards the
  crowd"). This is a CEO-proposed heuristic, not a validated probability
  model - the equal-chance baseline is almost never how the market
  actually sees a race, so treat value_ratio as a cheap proxy for
  "distance from the pack", not a true value measure.
- Section 3's backtest is run on the SAME historical bets used throughout
  this project - it is not a forward/out-of-sample test, and because we
  already know ROI rises with raw odds (race_dilution_report.py), any
  staking scheme that bets more at long odds will tend to show a better
  blended ROI almost by construction. Section 4's year-by-year split is
  the more honest check on whether the effect is broad and stable or
  driven by one or two years.
- ROI% = 100 * BF_P/L / total staked throughout.
- MaxDrawdown in Section 3 is the worst peak-to-trough dip in cumulative
  P/L with bets ordered chronologically by Date - a rough guide to bank
  requirements, not a rigorous risk figure (same-day bet ordering within a
  date is arbitrary).
""")

    s1.to_csv(BASE / "value_ratio_by_band.csv", index=False)
    s2.to_csv(BASE / "value_ratio_vs_odds_alone.csv", index=False)
    s3.to_csv(BASE / "value_ratio_staking_backtest.csv", index=False)
    s4.to_csv(BASE / "value_ratio_staking_by_year.csv", index=False)
    print("Wrote value_ratio_by_band.csv, value_ratio_vs_odds_alone.csv, "
          "value_ratio_staking_backtest.csv, value_ratio_staking_by_year.csv")


if __name__ == "__main__":
    main()
