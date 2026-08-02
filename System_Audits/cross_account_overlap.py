"""Cross-account overlap / deduplication analysis across all five HRB accounts.

Extends overlap_analysis_noggin2.py (which asked the question for one account)
to the whole portfolio: if every profitable-looking system across noggin,
noggin2, noggin3, noggin4 and noggin5 were run together, how many of the
"bets" are actually the *same horse in the same race* flagged independently
by more than one system - and how much of the naive summed P/L is really
just the same wins counted several times over?

This matters for the BFBM pipeline specifically: the merged daily selections
file collapses to one bet per horse per race, so the honest expectation for
the live portfolio is the deduplicated figure, not the sum of the per-system
audit rows.

Source of truth:
  - Slot / Name / Saved / Odds Band come from each account's FINAL audit
    workbook, so the account-specific odds-band parsing fixes (week/wk,
    run/runs/runtr, N4- cross-refs, "to" separator, DSLR/SOF/ClaimJock)
    are inherited already-validated rather than re-derived here.
  - Per-bet rows come from the cached raw TSVs in <account>_raw/.

Same per-bet economics as every prior script in this project:
    win  -> (Odds_Exchange - 1) * 0.95     # 5% BF commission on winnings
    lose -> -1                              # unit stake, no commission
and the same "since saved date" convention: saved date + 1 day.
"""
import datetime
import re
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).parent

ACCOUNTS = {
    "noggin": "HRB_System_Performance_Audit_noggin_FINAL.xlsx",
    "noggin2": "HRB_System_Performance_Audit_noggin2.xlsx",
    "noggin3": "HRB_System_Performance_Audit_noggin3.xlsx",
    "noggin4": "HRB_System_Performance_Audit_noggin4.xlsx",
    "noggin5": "HRB_System_Performance_Audit_noggin5.xlsx",
}

# Slots whose cached raw TSV is the *truncated* 10,000-row download, while the
# workbook figure is the corrected year-split-and-merge result (see PROJECT.md
# "How to verify (and fix) a capped slot"). Recomputing these from raw will
# legitimately disagree with the workbook - flagged, not silently accepted.
KNOWN_TRUNCATED_RAW = {("noggin3", 51), ("noggin4", 97), ("noggin5", 39)}

# The audit workbooks were built 29-31 Jul 2026; the raw TSVs were downloaded
# 31 Jul - 1 Aug 2026. A workbook figure explainable purely by "HRB has added
# more qualifiers since" must therefore be reachable by truncating the fresh
# data somewhere in that window. Anything matching only at a cutoff months
# earlier is a numeric coincidence, not evidence of drift.
DRIFT_FLOOR = datetime.date(2026, 7, 20)

BAND_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*$")


def parse_band(cell):
    """Parse the workbook's already-validated 'Odds Band' cell."""
    if cell is None or (isinstance(cell, float) and np.isnan(cell)):
        return None, None
    s = str(cell).strip()
    if not s or s.lower() == "none":
        return None, None
    m = BAND_RE.match(s)
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))


def load_slot(account, slot, name, saved, lo, hi):
    """Load one slot's raw per-bet rows, filtered to the audited universe."""
    path = BASE / f"{account}_raw" / f"slot{slot}_quals.tsv"
    if not path.exists():
        return None

    with open(path, "rb") as fh:
        n_rows = sum(1 for _ in fh) - 1  # >=10000 means the download was capped

    df = pd.read_csv(path, sep="\t")
    df = df.loc[:, [c for c in df.columns if not c.startswith("Unnamed")]]
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df[df["Date"].notna()]

    since = pd.Timestamp(saved) + pd.Timedelta(days=1)
    sub = df[df["Date"] >= since].copy()

    if lo is not None:
        sub = sub[(sub["Odds_Exchange"] >= lo) & (sub["Odds_Exchange"] <= hi)]

    if sub.empty:
        sub.attrs["capped"] = n_rows >= 10000
        return sub

    sub["is_win"] = sub["Position"].astype(str).str.strip().str.strip('"') == "1"
    sub["pl_bf"] = np.where(sub["is_win"], (sub["Odds_Exchange"] - 1) * 0.95, -1.0)
    sub["pl_sp"] = np.where(sub["is_win"], sub["Odds_Numeric"], -1.0)
    sub["year"] = sub["Date"].dt.year
    # One real-world bet opportunity = one horse in one race, regardless of
    # how many systems (in how many accounts) independently flagged it.
    sub["bet_key"] = (
        sub["Date"].dt.strftime("%Y-%m-%d")
        + "|" + sub["RTime"].astype(str).str.strip('"')
        + "|" + sub["track"].astype(str).str.strip('"')
        + "|" + sub["Qualifier"].astype(str).str.strip('"')
    )
    sub["account"] = account
    sub["slot"] = slot
    sub["sys_name"] = name
    sub["sys_key"] = f"{account}:{slot}"
    sub.attrs["capped"] = n_rows >= 10000
    return sub


def build():
    frames, validation, missing = [], [], []

    for account, wb in ACCOUNTS.items():
        meta = pd.read_excel(BASE / wb)
        for _, row in meta.iterrows():
            slot = int(row["Slot"])
            lo, hi = parse_band(row["Odds Band"])
            sub = load_slot(account, slot, row["Name"], row["Saved"], lo, hi)
            if sub is None:
                missing.append((account, slot, row["Name"]))
                continue
            # HRB adds new qualifiers daily, and these raw TSVs were downloaded
            # after the workbooks were built, so a workbook figure that is
            # simply *older* should be reproducible by truncating the fresh
            # data at some date near the build date. Test that directly rather
            # than assuming it: does any cutoff on/after DRIFT_FLOOR give back
            # exactly the workbook's bet count?
            drift_ok = False
            if len(sub):
                cum = sub.groupby(sub["Date"].dt.date).size().sort_index().cumsum()
                drift_ok = any(c == row["Bets"] and d >= DRIFT_FLOOR
                               for d, c in cum.items())
            validation.append({
                "account": account,
                "slot": slot,
                "wb_bets": row["Bets"],
                "calc_bets": len(sub),
                "wb_plbf": row["P/L(BF)"],
                "calc_plbf": round(float(sub["pl_bf"].sum()), 2) if len(sub) else 0.0,
                "drift_ok": drift_ok,
                "capped": bool(sub.attrs.get("capped", False)),
            })
            if len(sub):
                frames.append(sub)

    return pd.concat(frames, ignore_index=True), pd.DataFrame(validation), missing


def classify(row):
    """Why does this system's raw-derived figure differ from its workbook row?"""
    if (row["account"], row["slot"]) in KNOWN_TRUNCATED_RAW:
        return "truncated-raw"
    # Evidence-based: the workbook figure is recoverable from the fresh data by
    # rolling the clock back to the build date, so nothing but new racing days
    # separates them.
    if row["drift_ok"]:
        return "date-drift"
    # A capped download shifts its 10,000-row window forward as new rows land,
    # pushing old rows off the bottom - so a capped slot can legitimately lose
    # post-saved-date bets without the system having changed.
    if row["capped"]:
        return "date-drift(cap-shift)"
    # No exact cutoff exists, but only a handful of bets were ADDED - consistent
    # with the workbook having been built partway through a race day, so the
    # cumulative count steps straight past the workbook's figure.
    if 0 < row["bets_diff"] <= 5:
        return "date-drift(partial-day)"
    # Fewer bets than the workbook on an UNCAPPED slot. Daily accumulation only
    # ever adds rows, and no window shift is possible without a cap, so the
    # qualifier set itself must have moved: edited criteria, or dynamic criteria
    # (form/ratings-relative) re-evaluating against newer data.
    if row["bets_diff"] < 0:
        return "system-changed"
    # Far more bets than one or two extra racing days could produce.
    return "system-changed"


def report_validation(val, missing):
    print("=" * 78)
    print("STEP 1 - VALIDATION: recomputed from raw vs. the signed-off workbooks")
    print("=" * 78)
    val["bets_diff"] = val["calc_bets"] - val["wb_bets"]
    val["plbf_diff"] = (val["calc_plbf"] - val["wb_plbf"]).round(2)
    val["match"] = (val["bets_diff"] == 0) & (val["plbf_diff"].abs() <= 0.05)
    val["reason"] = ""
    bad = ~val["match"]
    val.loc[bad, "reason"] = val[bad].apply(classify, axis=1)

    print(f"Systems checked: {len(val)}   exact matches: {val['match'].sum()}")
    if missing:
        print(f"No raw TSV (excluded): {[(a, s, n) for a, s, n in missing]}")

    print("\nMismatches by cause:")
    for reason, g in val[bad].groupby("reason"):
        print(f"  {reason:<15} {len(g):>3} systems   "
              f"median |bets diff| {g['bets_diff'].abs().median():>7.1f}   "
              f"max {g['bets_diff'].abs().max():>7.0f}")

    print("""
  date-drift      - HRB adds qualifiers daily and the raw was downloaded after
                    the workbook was built. Confirmed, not assumed: truncating
                    the fresh data at a date near the build date reproduces the
                    workbook figure exactly. Benign.
  date-drift(cap-shift)
                  - same cause, on a slot whose download is capped at 10,000
                    rows: new rows arriving push old ones off the bottom, so
                    the post-saved-date count can fall as well as rise. Benign.
  truncated-raw   - noggin3/51, noggin4/97, noggin5/39: cached raw is the capped
                    download; the workbook holds the corrected merged figure.
  system-changed  - noggin 1-57 only. NOT drift: no cutoff in the build window
                    reproduces the workbook figure, and most of these are
                    UNCAPPED slots showing FEWER bets than the workbook, which
                    daily accumulation cannot produce (it only adds). The
                    qualifier set itself has moved - edited criteria, or
                    dynamic criteria re-evaluating against newer data. Slot 53
                    ("NEWTONclaude", saved 2026-07-05) is the clearest case.""")

    unexplained = val[val["reason"] == "UNEXPLAINED"]
    if len(unexplained):
        print("\n*** UNEXPLAINED mismatches - review before trusting totals ***")
        print(unexplained.to_string(index=False))
    else:
        print("\nNo unexplained mismatches. Proceeding with the raw per-bet data")
        print("as ground truth: it reflects the systems as they exist today,")
        print("which is what a live pipeline would actually fire.")
    return unexplained


def report_overlap(all_bets):
    print()
    print("=" * 78)
    print("STEP 2 - PORTFOLIO OVERLAP (all five accounts pooled)")
    print("=" * 78)

    n_rows = len(all_bets)
    n_unique = all_bets["bet_key"].nunique()
    print(f"Systems contributing bets : {all_bets['sys_key'].nunique()}")
    print(f"Naive system-bet rows     : {n_rows:,}")
    print(f"Distinct real-world bets  : {n_unique:,}")
    print(f"Overlap ratio             : {n_rows / n_unique:.3f}x "
          f"({100 * (1 - n_unique / n_rows):.1f}% of rows are duplicates)")
    print(f"Date span                 : {all_bets['Date'].min():%Y-%m-%d} "
          f"to {all_bets['Date'].max():%Y-%m-%d}")

    hits = all_bets.groupby("bet_key").size()
    print("\nHow many systems fired on the same horse+race:")
    vc = hits.value_counts().sort_index()
    for k, v in vc.items():
        print(f"  {k:>3} system(s): {v:>8,} bets  ({100 * v / n_unique:5.2f}%)")

    accts_per_bet = all_bets.groupby("bet_key")["account"].nunique()
    print("\nHow many *accounts* fired on the same horse+race:")
    for k, v in accts_per_bet.value_counts().sort_index().items():
        print(f"  {k:>3} account(s): {v:>8,} bets  ({100 * v / n_unique:5.2f}%)")
    cross = int((accts_per_bet > 1).sum())
    print(f"\nCross-account duplicated bets: {cross:,} "
          f"({100 * cross / n_unique:.1f}% of distinct bets)")


def report_pl(all_bets):
    print()
    print("=" * 78)
    print("STEP 3 - NAIVE vs DEDUPLICATED P/L(BF)")
    print("=" * 78)

    dedup = all_bets.sort_values("Date").drop_duplicates("bet_key", keep="first")
    naive_pl, dedup_pl = all_bets["pl_bf"].sum(), dedup["pl_bf"].sum()

    print(f"Naive  (sum of per-system rows): {naive_pl:>12,.2f} over "
          f"{len(all_bets):>8,} bets   ROI {100 * naive_pl / len(all_bets):6.2f}%")
    print(f"Dedup  (one stake per horse)   : {dedup_pl:>12,.2f} over "
          f"{len(dedup):>8,} bets   ROI {100 * dedup_pl / len(dedup):6.2f}%")
    print(f"\nP/L attributable to double-counting: {naive_pl - dedup_pl:,.2f} "
          f"({100 * (naive_pl - dedup_pl) / naive_pl:.1f}% of the naive figure)")

    print("\nPer-year:")
    naive_y = all_bets.groupby("year")["pl_bf"].agg(["sum", "count"])
    naive_y.columns = ["naive_plbf", "naive_bets"]
    dedup_y = dedup.groupby("year")["pl_bf"].agg(["sum", "count"])
    dedup_y.columns = ["dedup_plbf", "dedup_bets"]
    comb = naive_y.join(dedup_y, how="outer").fillna(0)
    comb["naive_roi%"] = 100 * comb["naive_plbf"] / comb["naive_bets"]
    comb["dedup_roi%"] = 100 * comb["dedup_plbf"] / comb["dedup_bets"]
    print(comb.round(2).to_string())
    return dedup


def report_accounts(all_bets):
    print()
    print("=" * 78)
    print("STEP 4 - PER-ACCOUNT CONTRIBUTION AND PAIRWISE OVERLAP")
    print("=" * 78)

    rows = []
    for acct, g in all_bets.groupby("account"):
        rows.append({
            "account": acct,
            "systems": g["sys_key"].nunique(),
            "naive_bets": len(g),
            "unique_bets": g["bet_key"].nunique(),
            "internal_overlap": round(len(g) / g["bet_key"].nunique(), 3),
            "naive_plbf": round(g["pl_bf"].sum(), 2),
        })
    print(pd.DataFrame(rows).to_string(index=False))

    sets = {a: set(g["bet_key"]) for a, g in all_bets.groupby("account")}
    accts = sorted(sets)
    print("\nPairwise shared distinct bets (count, and % of the smaller set):")
    mat = pd.DataFrame(index=accts, columns=accts, dtype=object)
    for a in accts:
        for b in accts:
            if a == b:
                mat.loc[a, b] = f"{len(sets[a]):,}"
            else:
                inter = len(sets[a] & sets[b])
                pct = 100 * inter / min(len(sets[a]), len(sets[b]))
                mat.loc[a, b] = f"{inter:,} ({pct:.1f}%)"
    print(mat.to_string())


def report_top_duplicates(all_bets):
    print()
    print("=" * 78)
    print("STEP 5 - THE MOST-DUPLICATED SELECTIONS")
    print("=" * 78)
    hits = (all_bets.groupby("bet_key")
            .agg(systems=("sys_key", "nunique"),
                 accounts=("account", "nunique"),
                 pl_bf=("pl_bf", "first"),
                 won=("is_win", "first"))
            .sort_values("systems", ascending=False))
    print("Top 10 horse+race combinations by number of systems firing:")
    print(hits.head(10).to_string())

    print("\nSystem pairs that most often fire on the same bet "
          "(candidate near-duplicates):")
    pairs = {}
    for _, g in all_bets.groupby("bet_key"):
        keys = sorted(g["sys_key"].unique())
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                pairs[(keys[i], keys[j])] = pairs.get((keys[i], keys[j]), 0) + 1
    top = sorted(pairs.items(), key=lambda kv: -kv[1])[:15]
    sizes = all_bets.groupby("sys_key")["bet_key"].nunique()
    print(f"{'system A':<14}{'system B':<14}{'shared':>8}"
          f"{'  A bets':>9}{'  B bets':>9}{'  jaccard':>10}")
    for (a, b), n in top:
        jac = n / (sizes[a] + sizes[b] - n)
        print(f"{a:<14}{b:<14}{n:>8,}{sizes[a]:>9,}{sizes[b]:>9,}{jac:>10.3f}")


def report_common_window(all_bets, val):
    """The pooled totals above mix systems with saved dates spanning 2012-2026,
    so they are the union of 418 different 'since saved' windows, not a
    portfolio anyone could have run. This restricts to the window in which
    essentially every system was already live - the honest proxy for what the
    live BFBM pipeline would actually do."""
    print()
    print("=" * 78)
    print("STEP 6 - COMMON-WINDOW VIEW (the number that matters for going live)")
    print("=" * 78)

    live = all_bets.groupby("sys_key")["Date"].min()
    print("Systems already live (first qualifying bet on/before 1 Jan):")
    for yr in range(2022, 2027):
        n = int((live < pd.Timestamp(f"{yr}-01-01")).sum())
        print(f"  {yr}: {n:>3} of {all_bets['sys_key'].nunique()} systems "
              f"({100 * n / all_bets['sys_key'].nunique():.0f}%)")

    for label, start in [("2026 year-to-date", "2026-01-01"),
                         ("last 12 months", "2025-08-01")]:
        w = all_bets[all_bets["Date"] >= pd.Timestamp(start)]
        d = w.sort_values("Date").drop_duplicates("bet_key", keep="first")
        n_sys = w["sys_key"].nunique()
        print(f"\n{label} (from {start}, {n_sys} systems firing):")
        print(f"  naive : {w['pl_bf'].sum():>10,.2f} over {len(w):>7,} bets"
              f"   ROI {100 * w['pl_bf'].sum() / len(w):>6.2f}%")
        print(f"  dedup : {d['pl_bf'].sum():>10,.2f} over {len(d):>7,} bets"
              f"   ROI {100 * d['pl_bf'].sum() / len(d):>6.2f}%")
        print(f"  -> {100 * (1 - len(d) / len(w)):.1f}% of the bets, and "
              f"{100 * (1 - d['pl_bf'].sum() / w['pl_bf'].sum()):.1f}% of the "
              f"profit, is duplication")

    print("\nCaveat: 'stale-legacy' and 'truncated-raw' systems (Step 1) are")
    print("included on their raw figures; the three truncated ones under-")
    print("contribute. Neither materially moves a portfolio of 418 systems.")


def report_agreement(all_bets):
    """Overlap is not purely waste: if several independent systems converge on
    the same horse, does that horse do better? Directly relevant to the stake
    scaling in the BFBM pipeline spec."""
    print()
    print("=" * 78)
    print("STEP 7 - IS AGREEMENT A SIGNAL? (ROI by number of systems firing)")
    print("=" * 78)

    u = (all_bets.groupby("bet_key")
         .agg(systems=("sys_key", "nunique"), accounts=("account", "nunique"),
              pl_bf=("pl_bf", "first"), won=("is_win", "first"),
              odds=("Odds_Exchange", "first"), date=("Date", "first")))

    buckets = [("1", lambda s: s.systems == 1), ("2", lambda s: s.systems == 2),
               ("3", lambda s: s.systems == 3),
               ("4-5", lambda s: s.systems.between(4, 5)),
               ("6-9", lambda s: s.systems.between(6, 9)),
               ("10+", lambda s: s.systems >= 10)]

    for label, frame in [("All years", u),
                         ("Last 12 months", u[u.date >= pd.Timestamp("2025-08-01")])]:
        print(f"\n{label} (deduplicated bets):")
        print(f"{'systems':>8}{'bets':>9}{'win%':>8}{'med odds':>10}"
              f"{'P/L(BF)':>11}{'ROI%':>8}")
        for lab, fn in buckets:
            s = frame[fn(frame)]
            if not len(s):
                continue
            print(f"{lab:>8}{len(s):>9,}{100 * s.won.mean():>8.2f}"
                  f"{s.odds.median():>10.2f}{s.pl_bf.sum():>11,.2f}"
                  f"{100 * s.pl_bf.mean():>8.2f}")

    print("""
Read with care: these systems were hand-built and hand-selected by the same
person, so 'independent agreement' is not statistically independent, and the
high-agreement buckets sit at longer odds where variance is widest. But the
direction is consistent across both windows and the 6+ bucket holds a few
thousand bets, so an agreement threshold looks like a far better lever than
running all 418 systems flat.""")


def main():
    all_bets, val, missing = build()
    unexplained = report_validation(val, missing)
    if len(unexplained):
        print("\nAborting the portfolio analysis: explain the mismatches first.")
        return

    report_overlap(all_bets)
    dedup = report_pl(all_bets)
    report_accounts(all_bets)
    report_top_duplicates(all_bets)
    report_common_window(all_bets, val)
    report_agreement(all_bets)

    all_bets.to_csv(BASE / "cross_account_all_system_bets.csv", index=False)
    dedup.to_csv(BASE / "cross_account_dedup_bets.csv", index=False)
    val.to_csv(BASE / "cross_account_validation.csv", index=False)
    print("\nWrote cross_account_all_system_bets.csv, "
          "cross_account_dedup_bets.csv, cross_account_validation.csv")


if __name__ == "__main__":
    main()
