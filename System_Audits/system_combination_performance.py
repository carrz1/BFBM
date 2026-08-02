"""Which specific systems perform best (and worst) together?

Extends the overlap analysis's Step 7 ("does agreement predict winners?",
which only asked *how many* systems agree) to ask *which* systems: for every
pair of systems that have independently fired on the same horse+race at
least MIN_SAMPLE times, what was the resulting deduplicated P/L and ROI?

Same ground rules as every other script in this project: one stake per
distinct bet (Date|RTime|track|Qualifier), not one per system - firing
together on a bet doesn't mean betting on it twice.

This is retrospective pattern-matching over historical co-occurrences, not
a claim that any specific pair is a "strategy" - see the caveats printed
at the end before acting on any single pair.
"""
import itertools
from collections import defaultdict
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent
MIN_SAMPLE = 20        # minimum co-fired bets before a pair/triple is reported
LARGE_SAMPLE = 300     # threshold for the "trustworthy" (low-noise) pair tier
TOP_N = 20


def load_bets_by_key():
    d = pd.read_csv(BASE / "cross_account_all_system_bets.csv", low_memory=False)
    grouped = d.groupby("bet_key").agg(
        sys_keys=("sys_key", lambda s: tuple(sorted(set(s)))),
        pl_bf=("pl_bf", "first"),
        is_win=("is_win", "first"),
        date=("Date", "first"),
    )
    return grouped, d


def pairwise_performance(grouped):
    stats = defaultdict(lambda: {"n": 0, "wins": 0, "pl_bf": 0.0})
    for row in grouped.itertuples():
        keys = row.sys_keys
        if len(keys) < 2:
            continue
        for a, b in itertools.combinations(keys, 2):
            s = stats[(a, b)]
            s["n"] += 1
            s["wins"] += int(row.is_win)
            s["pl_bf"] += row.pl_bf

    rows = []
    for (a, b), s in stats.items():
        rows.append({
            "system_a": a, "system_b": b, "bets": s["n"],
            "wins": s["wins"], "win_pct": round(100 * s["wins"] / s["n"], 2),
            "pl_bf": round(s["pl_bf"], 2),
            "roi_pct": round(100 * s["pl_bf"] / s["n"], 2),
        })
    return pd.DataFrame(rows)


def standalone_performance(all_bets):
    """Each system's own performance, for comparison against its pairs."""
    g = all_bets.groupby("sys_key").agg(
        name=("sys_name", "first"),
        bets=("pl_bf", "size"),
        pl_bf=("pl_bf", "sum"),
    )
    g["roi_pct"] = round(100 * g["pl_bf"] / g["bets"], 2)
    return g


def name_lookup(all_bets):
    return (all_bets.drop_duplicates("sys_key")
            .set_index("sys_key")["sys_name"].to_dict())


def report_pairs(pairs, names, standalone):
    qualified = pairs[pairs["bets"] >= MIN_SAMPLE].copy()
    print("=" * 100)
    print(f"PAIRWISE PERFORMANCE - pairs with >= {MIN_SAMPLE} co-fired bets "
          f"({len(qualified)} of {len(pairs)} pairs qualify)")
    print("=" * 100)

    def fmt(df, label):
        print(f"\n--- {label} ---")
        cols = ["system_a", "name_a", "system_b", "name_b", "bets", "win_pct",
                "pl_bf", "roi_pct"]
        out = df.copy()
        out["name_a"] = out["system_a"].map(names).str.slice(0, 30)
        out["name_b"] = out["system_b"].map(names).str.slice(0, 30)
        print(out[cols].to_string(index=False))

    fmt(qualified.sort_values("roi_pct", ascending=False).head(TOP_N),
        f"TOP {TOP_N} pairs by ROI")
    fmt(qualified.sort_values("roi_pct").head(TOP_N),
        f"BOTTOM {TOP_N} pairs by ROI")
    fmt(qualified.sort_values("bets", ascending=False).head(TOP_N),
        f"TOP {TOP_N} pairs by sample size (most frequent co-firers)")
    return qualified


def report_large_sample_pairs(qualified, names):
    """The tier that actually matters for decisions: enough co-fired bets
    that the ROI isn't just one or two lucky-priced winners."""
    print()
    print("=" * 100)
    print(f"LARGE-SAMPLE PAIRS (>= {LARGE_SAMPLE} co-fired bets) - "
          f"the low-noise, decision-worthy tier")
    print("=" * 100)
    big = qualified[qualified["bets"] >= LARGE_SAMPLE].copy()
    print(f"{len(big)} pairs qualify.\n")

    def fmt(df, label):
        print(f"\n--- {label} ---")
        out = df.copy()
        out["name_a"] = out["system_a"].map(names).str.slice(0, 32)
        out["name_b"] = out["system_b"].map(names).str.slice(0, 32)
        cols = ["system_a", "name_a", "system_b", "name_b", "bets", "win_pct", "roi_pct"]
        print(out[cols].to_string(index=False))

    fmt(big.sort_values("roi_pct", ascending=False).head(15),
        f"BEST large-sample pairs (>={LARGE_SAMPLE} bets) by ROI")
    fmt(big.sort_values("roi_pct").head(15),
        f"WORST large-sample pairs (>={LARGE_SAMPLE} bets) by ROI")
    return big


def report_vs_standalone(qualified, standalone, names):
    """Do these pairs outperform what each system does on its own?"""
    print()
    print("=" * 100)
    print("DO THE TOP PAIRS OUTPERFORM EITHER SYSTEM ALONE?")
    print("=" * 100)
    top = qualified.sort_values("roi_pct", ascending=False).head(10)
    for _, r in top.iterrows():
        a_solo = standalone.loc[r["system_a"], "roi_pct"] if r["system_a"] in standalone.index else float("nan")
        b_solo = standalone.loc[r["system_b"], "roi_pct"] if r["system_b"] in standalone.index else float("nan")
        print(f"  {r['system_a']} ({names.get(r['system_a'],'')[:28]:<28}) solo ROI {a_solo:>7.2f}%  "
              f"+  {r['system_b']} ({names.get(r['system_b'],'')[:28]:<28}) solo ROI {b_solo:>7.2f}%  "
              f"-> together ({int(r['bets'])} bets): {r['roi_pct']:>7.2f}%")


def triple_performance(grouped):
    stats = defaultdict(lambda: {"n": 0, "wins": 0, "pl_bf": 0.0})
    for row in grouped.itertuples():
        keys = row.sys_keys
        if len(keys) < 3:
            continue
        for combo in itertools.combinations(keys, 3):
            s = stats[combo]
            s["n"] += 1
            s["wins"] += int(row.is_win)
            s["pl_bf"] += row.pl_bf

    rows = []
    for combo, s in stats.items():
        rows.append({
            "sys_a": combo[0], "sys_b": combo[1], "sys_c": combo[2],
            "bets": s["n"], "win_pct": round(100 * s["wins"] / s["n"], 2),
            "pl_bf": round(s["pl_bf"], 2),
            "roi_pct": round(100 * s["pl_bf"] / s["n"], 2),
        })
    return pd.DataFrame(rows)


def _fmt_triples(df, names, label, top_n=15):
    print(f"\n--- {label} ---")
    out = df.copy()
    for col in ["a", "b", "c"]:
        out[f"name_{col}"] = out[f"sys_{col}"].map(names).str.slice(0, 26)
    cols = ["sys_a", "name_a", "sys_b", "name_b", "sys_c", "name_c",
            "bets", "win_pct", "roi_pct"]
    print(out[cols].head(top_n).to_string(index=False))


def report_triples(triples, names, min_sample=15, top_n=15):
    print()
    print("=" * 100)
    print(f"THREE-WAY COMBINATIONS (>= {min_sample} co-fired bets)")
    print("=" * 100)
    qualified = triples[triples["bets"] >= min_sample].copy()
    if qualified.empty:
        print("No triples meet the sample threshold.")
        return qualified
    print(f"{len(qualified)} triples qualify.")
    _fmt_triples(qualified.sort_values("roi_pct", ascending=False), names,
                 f"TOP {top_n} triples by ROI", top_n)
    _fmt_triples(qualified.sort_values("roi_pct"), names,
                 f"BOTTOM {top_n} triples by ROI", top_n)
    return qualified


def report_large_sample_triples(triples, names, top_n=15):
    """Same low-noise standard as the pairs: enough co-fired bets that the
    ROI isn't just one or two lucky-priced winners."""
    print()
    print("=" * 100)
    print(f"LARGE-SAMPLE TRIPLES (>= {LARGE_SAMPLE} co-fired bets) - "
          f"the low-noise, decision-worthy tier")
    print("=" * 100)
    big = triples[triples["bets"] >= LARGE_SAMPLE].copy()
    print(f"{len(big)} triples qualify.")
    if big.empty:
        return big
    _fmt_triples(big.sort_values("roi_pct", ascending=False), names,
                 f"BEST large-sample triples (>={LARGE_SAMPLE} bets) by ROI", top_n)
    _fmt_triples(big.sort_values("roi_pct"), names,
                 f"WORST large-sample triples (>={LARGE_SAMPLE} bets) by ROI", top_n)
    return big


def main():
    grouped, all_bets = load_bets_by_key()
    names = name_lookup(all_bets)
    standalone = standalone_performance(all_bets)

    pairs = pairwise_performance(grouped)
    qualified = report_pairs(pairs, names, standalone)
    report_large_sample_pairs(qualified, names)
    report_vs_standalone(qualified, standalone, names)

    triples = triple_performance(grouped)
    report_triples(triples, names)
    report_large_sample_triples(triples, names)

    print()
    print("=" * 100)
    print("CAVEATS - read before acting on any single pair/triple")
    print("=" * 100)
    print(f"""
- These are the same historical bets the systems were built from - not an
  out-of-sample test. A pair standing out here may partly reflect that both
  systems were independently tuned on the same market inefficiencies, not a
  new discovery.
- The top-by-ROI tables at the {MIN_SAMPLE}-bet floor (both pairs and
  triples) are mostly noise: those combinations mostly show a 0-10% win
  rate carried to a four-figure ROI% by one or two long-priced winners. Do
  not act on anything from those tables alone. The LARGE-SAMPLE sections
  (>={LARGE_SAMPLE} bets) are the ones worth reading - ROI numbers there
  are still built on genuine volume. Triples are rarer than pairs by
  construction (all three systems must fire on the same horse), so the
  large-sample triple list is shorter - treat that as a real constraint,
  not a bug.
- A pair's bets are a *subset* of each system's own bets (only the ones
  where both fired), so "pair beats both systems solo" is somewhat expected
  by construction - agreement selects for the more standout runners in each
  system's coverage, which is the same effect already documented in the
  "does agreement predict winners" finding. This table is mainly useful for
  finding *which* systems drive that effect hardest.
""")


if __name__ == "__main__":
    main()
