"""Single-selection vs multi-selection P/L, 2022-2026, quality-filtered.

Same universe and rules as filtered_agreement_report.py (systems with
>=100 standalone bets and standalone ROI >= -5%, exact-duplicate systems
dropped first so a system saved twice doesn't double-vote), restricted to
bets dated 2022-01-01 onward, with every multi-selection (2+ qualifying
systems agreeing) collapsed into a single row instead of split by exact
count - i.e. "did more than one system confirm this horse, yes or no".

ROI% = 100 * BF_P/L / Bets, as in every other report in this project.
"""
from pathlib import Path

import pandas as pd

from filtered_agreement_report import (
    EXACT_DUPLICATES_TO_DROP, MIN_BETS, MAX_LOSS_PCT,
    load_all_bets, standalone_performance,
)

BASE = Path(__file__).parent
START_DATE = "2022-01-01"


def main():
    all_bets = load_all_bets()
    standalone = standalone_performance(all_bets)
    qualifying = standalone[(standalone["bets"] >= MIN_BETS) &
                             (standalone["roi_pct"] >= MAX_LOSS_PCT)]

    print("=" * 90)
    print(f"FILTER: systems with >={MIN_BETS} standalone bets AND "
          f"standalone ROI >= {MAX_LOSS_PCT}% (all-time, {len(EXACT_DUPLICATES_TO_DROP)} "
          f"exact duplicates already dropped)")
    print(f"Date window: {START_DATE} onward")
    print("=" * 90)
    print(f"Qualifying systems: {len(qualifying)} of {len(standalone)}\n")

    filtered_bets = all_bets[all_bets["sys_key"].isin(qualifying.index)].copy()
    filtered_bets["Date"] = pd.to_datetime(filtered_bets["Date"])
    windowed = filtered_bets[filtered_bets["Date"] >= START_DATE]

    print(f"Naive bet-rows in window: {len(windowed):,} of "
          f"{len(filtered_bets):,} in the full filtered universe")

    grouped = windowed.groupby("bet_key").agg(
        systems=("sys_key", "nunique"),
        pl_bf=("pl_bf", "first"),
        is_win=("is_win", "first"),
    )
    print(f"Distinct bets in window: {len(grouped):,}\n")

    grouped["bucket"] = grouped["systems"].apply(
        lambda n: "1 (single selection)" if n == 1 else "2+ (multi-selection, collapsed)")

    rows = []
    for label in ["1 (single selection)", "2+ (multi-selection, collapsed)"]:
        sub = grouped[grouped["bucket"] == label]
        if sub.empty:
            continue
        rows.append({
            "Number of Systems": label,
            "Bets": len(sub),
            "Wins": int(sub["is_win"].sum()),
            "Win%": round(100 * sub["is_win"].mean(), 2),
            "BF_P/L": round(sub["pl_bf"].sum(), 2),
            "ROI%": round(100 * sub["pl_bf"].sum() / len(sub), 2),
        })
    report = pd.DataFrame(rows)

    print("=" * 90)
    print(f"SINGLE- VS MULTI-SELECTION P/L, {START_DATE} to present "
          f"(quality-filtered universe)")
    print("=" * 90)
    print(report.to_string(index=False))

    total_bets = len(grouped)
    total_pl = grouped["pl_bf"].sum()
    print(f"\n{'TOTAL':<27}{total_bets:>6,}{'':>4}{int(grouped['is_win'].sum()):>6}"
          f"{100*grouped['is_win'].mean():>8.2f}{total_pl:>12,.2f}"
          f"{100*total_pl/total_bets:>9.2f}")

    print()
    print("=" * 90)
    print("SAME BREAKDOWN, YEAR BY YEAR (for context - not requested as the "
          "primary table, but shows whether the collapsed view is stable)")
    print("=" * 90)
    grouped2 = windowed.groupby("bet_key").agg(
        systems=("sys_key", "nunique"), pl_bf=("pl_bf", "first"),
        is_win=("is_win", "first"), year=("year", "first"))
    grouped2["bucket"] = grouped2["systems"].apply(lambda n: "1" if n == 1 else "2+")
    yr_rows = []
    for year in sorted(grouped2["year"].unique()):
        for label in ["1", "2+"]:
            sub = grouped2[(grouped2["year"] == year) & (grouped2["bucket"] == label)]
            if sub.empty:
                continue
            yr_rows.append({
                "Year": int(year), "Systems": label, "Bets": len(sub),
                "Win%": round(100 * sub["is_win"].mean(), 2),
                "BF_P/L": round(sub["pl_bf"].sum(), 2),
                "ROI%": round(100 * sub["pl_bf"].sum() / len(sub), 2),
            })
    print(pd.DataFrame(yr_rows).to_string(index=False))

    print()
    print("=" * 90)
    print("NOTES")
    print("=" * 90)
    print(f"""
- "Qualifying systems" is decided from all-time standalone performance
  (same systems as filtered_agreement_report.py) - only the bet *dates*
  are restricted to {START_DATE} onward, not the criteria for which
  systems are allowed to vote.
- ROI% = 100 * BF_P/L / Bets: profit as a percentage of total staked,
  1-unit stake per bet.
- "2+ (multi-selection, collapsed)" merges every agreement level from 2
  up to 10+ into one row - it answers "does more than one system agreeing
  beat a single system firing alone", not "how much does agreement help
  as it climbs", which is what filtered_agreement_report.py's full
  per-count breakdown is for.
""")

    report.to_csv(BASE / "collapsed_agreement_2022_2026.csv", index=False)
    print(f"Wrote collapsed_agreement_2022_2026.csv")


if __name__ == "__main__":
    main()
