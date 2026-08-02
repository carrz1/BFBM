"""Are newer systems 'stealing' the good picks out of the single-selection
bucket, or is the decline in single-selection ROI just dilution?

The CEO's hypothesis after seeing single-selection ROI fall from 20% (2022)
to roughly break-even (2026) while multi-selection held up: the process of
building new systems around "what's working" has meant a growing share of
what used to be lone, unconfirmed picks are now getting joined by newly
saved systems - i.e. the single-selection bucket isn't just shrinking, its
best members are being promoted out of it.

This is directly testable. Freeze an "early" system universe (everything
saved on/before EARLY_CUTOFF) and compare, for every bet in the analysis
window:
  - how many EARLY qualifying systems fired on it
  - how many TOTAL qualifying systems fired on it (early + everything
    saved after the cutoff)

A bet that was single under the early-only view (exactly 1 early system
fired) but ends up multi in the full view (2+ total systems fired) was
"promoted" - a newer system joined an already-existing pick. If promoted
bets systematically outperform the ones that stayed single, the erosion
is concentration, not just noise: newer systems are disproportionately
confirming already-good horses rather than firing independently.

Same quality filter and exact-duplicate handling as filtered_agreement_
report.py.
"""
from pathlib import Path

import pandas as pd

from filtered_agreement_report import (
    MIN_BETS, MAX_LOSS_PCT, load_all_bets, standalone_performance,
)

BASE = Path(__file__).parent
START_DATE = "2022-01-01"
EARLY_CUTOFF = "2021-12-31"   # systems saved on/before this = the "early" universe

ACCOUNTS = {
    "noggin": "HRB_System_Performance_Audit_noggin_FINAL.xlsx",
    "noggin2": "HRB_System_Performance_Audit_noggin2.xlsx",
    "noggin3": "HRB_System_Performance_Audit_noggin3.xlsx",
    "noggin4": "HRB_System_Performance_Audit_noggin4.xlsx",
    "noggin5": "HRB_System_Performance_Audit_noggin5.xlsx",
}


def load_saved_dates():
    saved = {}
    for account, wb in ACCOUNTS.items():
        df = pd.read_excel(BASE / wb)
        for _, r in df.iterrows():
            try:
                saved[f"{account}:{int(r['Slot'])}"] = pd.Timestamp(r["Saved"])
            except Exception:
                continue
    return saved


def main():
    all_bets = load_all_bets()
    standalone = standalone_performance(all_bets)
    qualifying = set(standalone[(standalone["bets"] >= MIN_BETS) &
                                 (standalone["roi_pct"] >= MAX_LOSS_PCT)].index)
    saved = load_saved_dates()

    early_systems = {k for k in qualifying if k in saved and saved[k] <= pd.Timestamp(EARLY_CUTOFF)}
    new_systems = qualifying - early_systems
    print(f"Qualifying systems total: {len(qualifying)}")
    print(f"  saved on/before {EARLY_CUTOFF} ('early'): {len(early_systems)}")
    print(f"  saved after {EARLY_CUTOFF} ('new')       : {len(new_systems)}\n")

    filtered = all_bets[all_bets["sys_key"].isin(qualifying)].copy()
    filtered["Date"] = pd.to_datetime(filtered["Date"])
    windowed = filtered[filtered["Date"] >= START_DATE]

    g = windowed.groupby("bet_key").agg(
        pl_bf=("pl_bf", "first"), is_win=("is_win", "first"),
        year=("year", "first"),
        total_count=("sys_key", "nunique"),
        early_count=("sys_key", lambda s: sum(1 for k in s if k in early_systems)),
    )

    def categorize(row):
        if row["early_count"] == 1 and row["total_count"] == 1:
            return "stayed_single"
        if row["early_count"] == 1 and row["total_count"] >= 2:
            return "promoted_out_of_single"
        if row["early_count"] == 0 and row["total_count"] == 1:
            return "single_new_system_only"
        if row["early_count"] == 0 and row["total_count"] >= 2:
            return "multi_new_systems_only"
        return "was_already_multi"  # early_count >= 2

    g["category"] = g.apply(categorize, axis=1)

    print("=" * 95)
    print("CATEGORY PERFORMANCE - was this bet 'stolen' from the single-selection bucket?")
    print("=" * 95)
    rows = []
    for cat, sub in g.groupby("category"):
        rows.append({
            "Category": cat, "Bets": len(sub),
            "Win%": round(100 * sub["is_win"].mean(), 2),
            "BF_P/L": round(sub["pl_bf"].sum(), 2),
            "ROI%": round(100 * sub["pl_bf"].sum() / len(sub), 2),
        })
    cat_df = pd.DataFrame(rows).sort_values("Bets", ascending=False)
    print(cat_df.to_string(index=False))

    print("""
Key comparison:
  stayed_single           - single under the early-only view AND still
                             single today (no new system ever joined)
  promoted_out_of_single  - single under the early-only view, but a system
                             saved after the cutoff has since joined it
""")

    stayed = g[g["category"] == "stayed_single"]
    promoted = g[g["category"] == "promoted_out_of_single"]
    print(f"stayed_single    : {len(stayed):>7,} bets, ROI {100*stayed['pl_bf'].sum()/len(stayed):>7.2f}%")
    print(f"promoted_out     : {len(promoted):>7,} bets, ROI {100*promoted['pl_bf'].sum()/len(promoted):>7.2f}%  "
          f"(this is the performance of what got taken OUT of the single bucket)")

    print()
    print("=" * 95)
    print("PROMOTION RATE OVER TIME - is more of the early-single pool being "
          "absorbed each year?")
    print("=" * 95)
    early_single_pool = g[g["early_count"] == 1]
    yr_rows = []
    for year in sorted(early_single_pool["year"].unique()):
        sub = early_single_pool[early_single_pool["year"] == year]
        stayed_y = sub[sub["category"] == "stayed_single"]
        promoted_y = sub[sub["category"] == "promoted_out_of_single"]
        total = len(sub)
        yr_rows.append({
            "Year": int(year),
            "Early-single pool": total,
            "Promoted": len(promoted_y),
            "Promotion rate %": round(100 * len(promoted_y) / total, 2) if total else 0,
            "Stayed-single ROI%": round(100 * stayed_y["pl_bf"].sum() / len(stayed_y), 2) if len(stayed_y) else float("nan"),
            "Promoted ROI%": round(100 * promoted_y["pl_bf"].sum() / len(promoted_y), 2) if len(promoted_y) else float("nan"),
        })
    print(pd.DataFrame(yr_rows).to_string(index=False))

    print()
    print("=" * 95)
    print("NOTES")
    print("=" * 95)
    print(f"""
- "Early" = qualifying systems saved on/before {EARLY_CUTOFF}; "new" =
  saved after. This is a fixed split, not a moving one - a system saved in
  2022 counts as "new" for every year in this report, including 2026.
- Every bet already respects each system's own odds band and saved-date
  window (see verify_odds_band_applied.py and the audit pipeline) - this
  report only adds the early/new system split on top of that.
- ROI% = 100 * BF_P/L / Bets throughout.
""")

    cat_df.to_csv(BASE / "single_selection_erosion_categories.csv", index=False)
    pd.DataFrame(yr_rows).to_csv(BASE / "single_selection_erosion_by_year.csv", index=False)
    print("Wrote single_selection_erosion_categories.csv and single_selection_erosion_by_year.csv")


if __name__ == "__main__":
    main()
