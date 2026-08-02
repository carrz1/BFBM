"""Race-level dilution: does backing more DIFFERENT horses in the same race
(as opposed to more systems piling onto the SAME horse) drag down returns?

Distinct from every other report in this project: those all deduplicate to
one stake per (Date, RTime, track, Qualifier) - one horse, one bet,
regardless of how many systems flagged it, which is correct for measuring
whether agreement on a single horse is informative. This report groups by
race instead - (Date, RTime, track) - and asks how many *different* horses
end up backed in that same race as the system population has grown, since
only one of them can win and every extra one staked is (usually) an extra
simultaneous loser.

Every number here still uses one stake per distinct horse (a horse flagged
by 5 systems is still 1 stake) - this is purely about how many *different*
horses per race, not re-litigating the same-horse overlap question.
"""
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent
MULTI_THRESHOLD = 4   # "4+ selections backed" per the CEO's specific request

RUNNER_BINS = [1, 5, 8, 11, 14, 17, 20, 999]
RUNNER_LABELS = ["2-5", "6-8", "9-11", "12-14", "15-17", "18-20", "21+"]

ODDS_BINS = [0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 100000]
ODDS_LABELS = ["1.01-2.00", "2.01-4.00", "4.01-8.00", "8.01-16.00",
               "16.01-32.00", "32.01-64.00", "64.01-128.00", "128.01+"]


def load_per_horse():
    d = pd.read_csv(BASE / "cross_account_all_system_bets.csv", low_memory=False)
    d["Date"] = pd.to_datetime(d["Date"])
    d["race_id"] = (d["Date"].dt.strftime("%Y-%m-%d") + "|" +
                     d["RTime"].astype(str) + "|" + d["track"].astype(str))
    # one row per distinct horse per race - pl_bf/is_win/Runners/Odds_Exchange
    # are identical across every system that flagged the same horse
    per_horse = d.drop_duplicates(subset=["race_id", "Qualifier"])[
        ["race_id", "year", "Qualifier", "pl_bf", "is_win", "Runners", "Odds_Exchange"]]
    return per_horse


def roi_row(sub, label, key_col=None):
    n = len(sub)
    return {
        (key_col or "Group"): label, "Bets": n,
        "Wins": int(sub["is_win"].sum()),
        "Win%": round(100 * sub["is_win"].mean(), 2) if n else 0,
        "BF_P/L": round(sub["pl_bf"].sum(), 2),
        "ROI%": round(100 * sub["pl_bf"].sum() / n, 2) if n else 0,
    }


def report_headline(per_horse):
    print("=" * 95)
    print("HOW MANY DIFFERENT HORSES GET BACKED IN THE SAME RACE, BY YEAR")
    print("=" * 95)
    per_race = per_horse.groupby(["race_id", "year"]).size().reset_index(name="distinct_horses")
    print(per_race.groupby("year")["distinct_horses"].mean().round(3)
          .rename("avg_distinct_horses_per_race").to_string())

    print()
    print("=" * 95)
    print("RACE-LEVEL ROI (1-unit stake per distinct horse backed), 2022 vs 2026, "
          "bucketed by how many different horses were backed in that race")
    print("=" * 95)
    race_pl = per_horse.groupby(["race_id", "year"]).agg(
        distinct_horses=("pl_bf", "size"), race_pl=("pl_bf", "sum")).reset_index()
    for y in [2022, 2026]:
        sub = race_pl[race_pl["year"] == y].copy()
        sub["bucket"] = sub["distinct_horses"].clip(upper=6)
        g = sub.groupby("bucket").agg(races=("race_pl", "size"),
                                       total_pl=("race_pl", "sum"),
                                       total_stake=("distinct_horses", "sum"))
        g["roi_pct"] = (100 * g["total_pl"] / g["total_stake"]).round(2)
        overall_roi = 100 * sub["race_pl"].sum() / sub["distinct_horses"].sum()
        print(f"\n--- {y} (overall race-level ROI: {overall_roi:.2f}%) ---")
        print(g)
    return race_pl


def report_multi_selection_breakdown(per_horse, race_pl):
    print()
    print("=" * 95)
    print(f"P/L BREAKDOWN FOR RACES WITH {MULTI_THRESHOLD}+ SELECTIONS BACKED")
    print("=" * 95)
    multi_race_ids = set(race_pl[race_pl["distinct_horses"] >= MULTI_THRESHOLD]["race_id"])
    multi = per_horse[per_horse["race_id"].isin(multi_race_ids)].copy()
    print(f"Races with {MULTI_THRESHOLD}+ distinct selections: {len(multi_race_ids):,}")
    print(f"Individual horse-bets within those races: {len(multi):,}\n")

    print(f"--- Overall ({MULTI_THRESHOLD}+ selection races) ---")
    overall = roi_row(multi, "ALL")
    print(pd.DataFrame([overall]).to_string(index=False))

    print(f"\n--- By NUMBER OF RUNNERS in the race ---")
    multi["runners_band"] = pd.cut(multi["Runners"], bins=RUNNER_BINS, labels=RUNNER_LABELS)
    rows = [roi_row(multi[multi["runners_band"] == b], b, "Runners")
            for b in RUNNER_LABELS if (multi["runners_band"] == b).any()]
    runners_df = pd.DataFrame(rows)
    print(runners_df.to_string(index=False))

    print(f"\n--- By BF ODDS BAND (Odds_Exchange, the real archived Betfair SP) ---")
    multi["odds_band"] = pd.cut(multi["Odds_Exchange"], bins=ODDS_BINS, labels=ODDS_LABELS)
    rows = [roi_row(multi[multi["odds_band"] == b], b, "Odds Band")
            for b in ODDS_LABELS if (multi["odds_band"] == b).any()]
    odds_df = pd.DataFrame(rows)
    print(odds_df.to_string(index=False))

    return runners_df, odds_df, multi


def main():
    per_horse = load_per_horse()
    race_pl = report_headline(per_horse)
    runners_df, odds_df, multi = report_multi_selection_breakdown(per_horse, race_pl)

    print()
    print("=" * 95)
    print("NOTES")
    print("=" * 95)
    print(f"""
- This report groups by RACE (Date+RTime+track), not by horse - it measures
  how many *different* horses get backed in the same race, which is a
  separate effect from the same-horse-multiple-systems overlap covered by
  every other report in this project.
- Every figure still uses one stake per distinct horse - a horse flagged by
  5 systems is one bet here too, exactly as elsewhere.
- "{MULTI_THRESHOLD}+ selections backed" means {MULTI_THRESHOLD} or more different
  horses in the same race, not {MULTI_THRESHOLD}+ systems agreeing on one horse.
- Runners bands are field-size at the time of the race; BF odds bands use
  the real archived Betfair SP (Odds_Exchange), same as every P/L figure
  elsewhere in this project.
- Small buckets (few hundred bets or fewer) are noisy - check the Bets
  column before treating any single row as reliable, same caveat as every
  other combination/agreement report here.
""")

    race_pl.to_csv(BASE / "race_dilution_by_year.csv", index=False)
    runners_df.to_csv(BASE / f"race_dilution_{MULTI_THRESHOLD}plus_by_runners.csv", index=False)
    odds_df.to_csv(BASE / f"race_dilution_{MULTI_THRESHOLD}plus_by_odds_band.csv", index=False)
    print(f"Wrote race_dilution_by_year.csv, "
          f"race_dilution_{MULTI_THRESHOLD}plus_by_runners.csv, "
          f"race_dilution_{MULTI_THRESHOLD}plus_by_odds_band.csv")


if __name__ == "__main__":
    main()
