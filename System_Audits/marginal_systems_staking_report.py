"""Does value-ratio staking (stake = min(cap, Odds_Exchange/Runners)) rescue
the systems that most need help?

Two groups, per the CEO's request:
  A. "no odds filter" - systems whose completewheresteps has no
     odds_workout condition at all, so their bets can land at any price
     the other criteria happen to produce. Confirmed by grepping every
     system's filter string: only 16 of 423 systems (13 in noggin4, 3 in
     noggin5) constrain odds_workout directly in the query - everything
     else (410 systems, all of noggin/noggin2/noggin3 and most of
     noggin4/noggin5) has no query-time odds restriction at all.
  B. "breakeven to losing 5%" - systems with >=100 standalone bets whose
     all-time standalone ROI is between -5% and 0%: the weakest performers
     that still clear filtered_agreement_report.py's MAX_LOSS_PCT bar, not
     ones already excluded below it.

For each group (and A-and-B, A-or-B), this compares FLAT 1-point staking
(their real historical standalone performance) against value-ratio
staking on their own bets, one stake per distinct bet_key within the
group.
"""
import glob
import json
from pathlib import Path

import pandas as pd

from filtered_agreement_report import load_all_bets, standalone_performance

BASE = Path(__file__).parent
STAKE_CAPS = [1.0, 3.0, 5.0, 8.0]


def load_odds_filter_map():
    has_odds = {}
    for path in glob.glob(str(BASE / "filters" / "*_filters.jsonl")):
        account = Path(path).stem.replace("_filters", "")
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                rec = json.loads(line)
                sys_key = f"{account}:{rec['slot']}"
                has_odds[sys_key] = "odds_workout" in rec["filter"].lower()
    return has_odds


def evaluate_group(all_bets, keys, label):
    subset = all_bets[all_bets["sys_key"].isin(keys)]
    if subset.empty:
        print(f"\n{label}: no bets")
        return None
    grouped = subset.groupby("bet_key").agg(
        pl_bf=("pl_bf", "first"), is_win=("is_win", "first"),
        Runners=("Runners", "first"), Odds_Exchange=("Odds_Exchange", "first"),
    ).dropna(subset=["Runners", "Odds_Exchange"])
    grouped = grouped[grouped["Runners"] > 0]
    grouped["value_ratio"] = grouped["Odds_Exchange"] / grouped["Runners"]

    n = len(grouped)
    flat_roi = 100 * grouped["pl_bf"].sum() / n
    row = {"Group": label, "Systems": len(set(keys) & set(subset["sys_key"].unique())),
           "Bets": n, "Win%": round(100 * grouped["is_win"].mean(), 2),
           "ROI%_flat": round(flat_roi, 2)}
    for cap in STAKE_CAPS:
        stake = grouped["value_ratio"].clip(upper=cap)
        pl = (grouped["pl_bf"] * stake).sum()
        row[f"ROI%_cap{cap}"] = round(100 * pl / stake.sum(), 2)
    return row


def main():
    all_bets = load_all_bets()
    standalone = standalone_performance(all_bets)
    odds_map = load_odds_filter_map()
    standalone["has_odds_filter"] = [odds_map.get(k, False) for k in standalone.index]

    group_a = set(standalone[~standalone["has_odds_filter"]].index)
    group_b = set(standalone[(standalone["bets"] >= 100) &
                              (standalone["roi_pct"] >= -5.0) &
                              (standalone["roi_pct"] <= 0.0)].index)

    print("=" * 100)
    print("GROUP DEFINITIONS")
    print("=" * 100)
    print(f"A. No odds_workout filter in the query at all: {len(group_a)} of "
          f"{len(standalone)} systems")
    print(f"B. >=100 standalone bets AND standalone ROI between -5% and 0%: "
          f"{len(group_b)} of {len(standalone)} systems")
    print(f"A and B (weak AND unfiltered by odds):  {len(group_a & group_b)} systems")
    print(f"A or B  (either condition):              {len(group_a | group_b)} systems")

    print()
    print("=" * 100)
    print("FLAT vs VALUE-RATIO-STAKED PERFORMANCE, BY GROUP "
          "(1 stake per distinct bet within the group)")
    print("=" * 100)
    rows = []
    for label, keys in [
        ("A: no odds filter (410 systems)", group_a),
        ("B: breakeven to -5% ROI, >=100 bets", group_b),
        ("A and B", group_a & group_b),
        ("A or B", group_a | group_b),
    ]:
        r = evaluate_group(all_bets, keys, label)
        if r:
            rows.append(r)
    report = pd.DataFrame(rows)
    print(report.to_string(index=False))

    print()
    print("=" * 100)
    print("GROUP B DETAIL - every individual system, standalone flat ROI vs "
          "its own value-ratio-staked ROI at cap 5")
    print("=" * 100)
    detail_rows = []
    for k in sorted(group_b, key=lambda k: standalone.loc[k, "roi_pct"]):
        sb = all_bets[all_bets["sys_key"] == k].dropna(subset=["Runners", "Odds_Exchange"])
        sb = sb[sb["Runners"] > 0]
        if sb.empty:
            continue
        ratio = sb["Odds_Exchange"] / sb["Runners"]
        stake = ratio.clip(upper=5.0)
        scaled_roi = 100 * (sb["pl_bf"] * stake).sum() / stake.sum()
        detail_rows.append({
            "sys_key": k, "name": standalone.loc[k, "name"],
            "bets": standalone.loc[k, "bets"],
            "ROI%_flat": standalone.loc[k, "roi_pct"],
            "ROI%_cap5": round(scaled_roi, 2),
            "has_odds_filter": odds_map.get(k, False),
        })
    detail = pd.DataFrame(detail_rows)
    print(detail.to_string(index=False))
    rescued = (detail["ROI%_flat"] < 0) & (detail["ROI%_cap5"] > 0)
    print(f"\n{rescued.sum()} of {len(detail)} Group B systems flip from a standalone "
          f"loss to a standalone profit under cap-5 value-ratio staking.")

    print()
    print("=" * 100)
    print("NOTES")
    print("=" * 100)
    print("""
- Group A is ~97% of the whole system universe (410 of 423) - almost no
  system restricts odds_workout directly in its HRB query. This group's
  aggregate numbers are close to (not identical to, because of the
  MIN_BETS/ROI quality filter used elsewhere) the full-universe numbers
  already seen in value_ratio_staking_report.py - it is not a
  distinguishing group on its own, included here for completeness since
  it was explicitly asked for.
- Group B is the more informative test: these are systems that already
  cleared the >=-5% bar (they are NOT among the excluded losers), but sit
  at the weak end - the ones a cautious operator might be tempted to drop
  first. The per-system detail table shows whether value-ratio staking
  gives any of them a genuine reason to be kept instead of dropped.
- ROI% = 100 * BF_P/L / total staked. Flat staking = ROI% under this
  project's normal 1-unit-per-bet convention.
- These figures are in-sample historical results, not a forward test - see
  value_ratio_staking_report.py's notes for the same caveat about riding a
  known odds-ROI relationship rather than proving new information.
""")

    report.to_csv(BASE / "marginal_systems_staking_summary.csv", index=False)
    detail.to_csv(BASE / "marginal_systems_staking_detail.csv", index=False)
    print("Wrote marginal_systems_staking_summary.csv and "
          "marginal_systems_staking_detail.csv")


if __name__ == "__main__":
    main()
