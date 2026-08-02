"""P/L by agreement count, restricted to a quality-filtered system universe.

Extends the overlap analysis's "does agreement predict winners" question
(which used all 418 bet-producing systems) to a more realistic universe:
only systems with a proven track record are allowed to vote at all.

Filter (CEO-specified):
  - >= MIN_BETS standalone bets (enough history to trust the number)
  - standalone ROI >= MAX_LOSS_PCT (not a system that's simply a loser)

Within that filtered universe, every bet is re-scored by how many
*qualifying* systems fired on it (a bet where 5 systems agreed but only 2
of them pass the filter counts as "2" here, not "5") - then bucketed by
that count, one stake per distinct bet as always.

ROI% = 100 * P/L(BF) / bets - i.e. profit as a percentage of total staked,
assuming a 1-unit stake per bet. ROI 50% means every 1 unit staked returned
1.50 back on average; ROI -100% means every bet in the bucket lost.
"""
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent
MIN_BETS = 100
MAX_LOSS_PCT = -5.0   # standalone ROI must be >= this

# Exact-duplicate systems found by filter_similarity_analysis.py - identical
# criteria AND identical odds band, so they always produce the exact same
# set of bets. Left in, each pair would double-vote in every agreement
# count (two "systems" agreeing that are really one system saved twice).
# One of each pair is dropped here; which one is arbitrary (kept the
# alphabetically-first sys_key of each pair) since they are bet-for-bet
# identical - dropping either produces the same filtered universe.
EXACT_DUPLICATES_TO_DROP = [
    "noggin5:98",   # == noggin5:30  ("Ascot HUNT CUP AW WIN LTO" / "...Hdgr")
    "noggin5:23",   # == noggin3:23  ("SS 4YO 5F 5.5F 9.01 - 1000.00")
    "noggin5:31",   # == noggin2:75  ("2021 MeehanB(J) ... 2021")
    "noggin2:88",   # == noggin2:39  ("...Elliott Gordon Hurdles NH Flat ALL BSPs")
]


def load_all_bets():
    df = pd.read_csv(BASE / "cross_account_all_system_bets.csv", low_memory=False)
    before = df["sys_key"].nunique()
    df = df[~df["sys_key"].isin(EXACT_DUPLICATES_TO_DROP)].copy()
    print(f"Dropped {len(EXACT_DUPLICATES_TO_DROP)} exact-duplicate systems "
          f"({before} -> {df['sys_key'].nunique()} distinct systems in the universe)\n")
    return df


def standalone_performance(all_bets):
    g = all_bets.groupby("sys_key").agg(
        name=("sys_name", "first"),
        account=("account", "first"),
        bets=("pl_bf", "size"),
        pl_bf=("pl_bf", "sum"),
    )
    g["roi_pct"] = round(100 * g["pl_bf"] / g["bets"], 2)
    return g


def main():
    all_bets = load_all_bets()
    standalone = standalone_performance(all_bets)

    qualifying = standalone[(standalone["bets"] >= MIN_BETS) &
                             (standalone["roi_pct"] >= MAX_LOSS_PCT)]
    excluded = standalone[~standalone.index.isin(qualifying.index)]

    print("=" * 90)
    print(f"FILTER: systems with >={MIN_BETS} standalone bets AND "
          f"standalone ROI >= {MAX_LOSS_PCT}%")
    print("=" * 90)
    print(f"Qualifying systems : {len(qualifying)} of {len(standalone)}")
    print(f"Excluded systems   : {len(excluded)} "
          f"({(excluded['bets'] < MIN_BETS).sum()} for insufficient sample, "
          f"{((excluded['bets'] >= MIN_BETS) & (excluded['roi_pct'] < MAX_LOSS_PCT)).sum()} "
          f"for a standalone loss > {abs(MAX_LOSS_PCT)}%)")

    filtered_bets = all_bets[all_bets["sys_key"].isin(qualifying.index)].copy()
    print(f"Naive bet-rows in the filtered universe: {len(filtered_bets):,} "
          f"of {len(all_bets):,} ({100*len(filtered_bets)/len(all_bets):.1f}%)")

    grouped = filtered_bets.groupby("bet_key").agg(
        systems=("sys_key", "nunique"),
        pl_bf=("pl_bf", "first"),
        is_win=("is_win", "first"),
    )
    print(f"Distinct bets in the filtered universe : {len(grouped):,}\n")

    print("=" * 90)
    print("P/L BY NUMBER OF QUALIFYING SYSTEMS AGREEING ON THE SAME SELECTION")
    print("=" * 90)
    grouped["bucket"] = grouped["systems"].clip(upper=10)
    rows = []
    for bucket in range(1, 11):
        sub = grouped[grouped["bucket"] == bucket]
        if sub.empty:
            continue
        label = "10+" if bucket == 10 else str(bucket)
        rows.append({
            "Number of Systems": label,
            "Bets": len(sub),
            "Wins": int(sub["is_win"].sum()),
            "Win%": round(100 * sub["is_win"].mean(), 2),
            "BF_P/L": round(sub["pl_bf"].sum(), 2),
            "ROI%": round(100 * sub["pl_bf"].sum() / len(sub), 2),
        })
    report = pd.DataFrame(rows)
    print(report.to_string(index=False))

    total_bets = len(grouped)
    total_pl = grouped["pl_bf"].sum()
    print(f"\n{'TOTAL':<19}{total_bets:>6,}{'':>4}{int(grouped['is_win'].sum()):>6}"
          f"{100*grouped['is_win'].mean():>8.2f}{total_pl:>12,.2f}"
          f"{100*total_pl/total_bets:>9.2f}")

    print()
    print("=" * 90)
    print("FOR COMPARISON - the same breakdown with NO system-quality filter "
          "(all 418 systems)")
    print("=" * 90)
    grouped_all = all_bets.groupby("bet_key").agg(
        systems=("sys_key", "nunique"), pl_bf=("pl_bf", "first"),
        is_win=("is_win", "first"))
    grouped_all["bucket"] = grouped_all["systems"].clip(upper=10)
    rows2 = []
    for bucket in range(1, 11):
        sub = grouped_all[grouped_all["bucket"] == bucket]
        if sub.empty:
            continue
        label = "10+" if bucket == 10 else str(bucket)
        rows2.append({
            "Number of Systems": label,
            "Bets": len(sub),
            "Win%": round(100 * sub["is_win"].mean(), 2),
            "BF_P/L": round(sub["pl_bf"].sum(), 2),
            "ROI%": round(100 * sub["pl_bf"].sum() / len(sub), 2),
        })
    print(pd.DataFrame(rows2).to_string(index=False))

    print()
    print("=" * 90)
    print("NOTES")
    print("=" * 90)
    print("""
- ROI% = 100 * BF_P/L / Bets: profit as a percentage of total staked,
  assuming a 1-unit stake per bet. ROI 50% -> every 1 unit staked returned
  1.50 on average; ROI -100% -> every bet in that row lost.
- "Number of Systems" counts only systems that passed the quality filter -
  a bet flagged by 6 systems where only 3 pass the filter is bucketed under
  "3", not "6". This is deliberate: the question is what agreement among
  systems you'd actually trust looks like, not raw agreement.
- Sample size still matters at the high end: fewer bets ever reach 8-10+
  system agreement even before filtering, and the filter removes some of
  those too. Check the Bets column before treating any one row's ROI as
  reliable - the same caveat as every other combination report in this
  project.
- This is the historical data the systems were tuned on, not a forward
  test.
""")

    qualifying.sort_values("roi_pct", ascending=False).to_csv(
        BASE / "filtered_agreement_qualifying_systems.csv")
    report.to_csv(BASE / "filtered_agreement_by_count.csv", index=False)
    print(f"Wrote filtered_agreement_qualifying_systems.csv ({len(qualifying)} systems) "
          f"and filtered_agreement_by_count.csv")


if __name__ == "__main__":
    main()
