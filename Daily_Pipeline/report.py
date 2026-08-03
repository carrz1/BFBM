"""Human-readable run report - per the original spec, this matters as
much as the CSV itself. Printed to stdout and saved alongside the CSV.
"""
from collections import Counter
from itertools import combinations
from io import StringIO

import config


def _system_correlation_lines(consolidated) -> list[str]:
    pair_counts = Counter()
    for sys_keys in consolidated["sys_keys"]:
        for a, b in combinations(sorted(sys_keys), 2):
            pair_counts[(a, b)] += 1
    if not pair_counts:
        return ["  No pairs co-fired today."]
    lines = ["  Top co-firing system pairs today:"]
    for (a, b), n in pair_counts.most_common(10):
        lines.append(f"    {a} + {b}: {n} shared selection(s)")
    return lines


def build_report(target_date, ingest_exclusions, quality_exclusions,
                  normalize_log, consolidate_exclusions, consolidated, rows,
                  per_account_counts) -> str:
    buf = StringIO()
    w = lambda s="": print(s, file=buf)

    w("=" * 80)
    w(f"DAILY PIPELINE REPORT - {target_date}")
    w("=" * 80)

    w("\n--- INPUT ---")
    for account, count in per_account_counts.items():
        w(f"  {account}: {count} qualifier rows read")
    if ingest_exclusions.get("missing_account_files"):
        w(f"  MISSING files (no export provided today): {ingest_exclusions['missing_account_files']}")

    w("\n--- EXCLUSIONS ---")
    w(f"  Out-of-scope (My Multicuts, not an audited system): {ingest_exclusions['out_of_scope_multicuts']}")
    w(f"  Already run / unparseable race time: {ingest_exclusions['already_run_or_no_time']}")
    w(f"  Not in quality-filtered system list: {quality_exclusions['not_quality_filtered_count']}")
    if quality_exclusions["not_quality_filtered_sys_keys"]:
        w(f"    sys_keys dropped: {quality_exclusions['not_quality_filtered_sys_keys']}")
    w(f"  Empty odds-band intersection: {len(consolidate_exclusions['empty_odds_intersection'])}")
    for item in consolidate_exclusions["empty_odds_intersection"]:
        w(f"    {item['name']} ({item['track']} {item['time']}): {item['reason']}")
    w(f"  Ambiguous same-name-same-day (need MarketId/EventId to disambiguate): "
      f"{len(consolidate_exclusions['ambiguous_same_name'])}")
    for item in consolidate_exclusions["ambiguous_same_name"]:
        w(f"    {item['name']} appears at both/multiple: {item['track']} {item['time']}")

    w("\n--- NAME NORMALIZATION LOG ---")
    if normalize_log:
        for note in normalize_log:
            w(f"  {note}")
    else:
        w("  (no non-trivial changes)")

    w("\n--- FINAL SELECTIONS ---")
    w(f"  {len(rows)} selections, total stake {sum(r['Size'] for r in rows):.2f}")
    for r in rows:
        is_unrestricted = (r["MinPrice"] == config.UNRESTRICTED_MIN_PRICE
                            and r["MaxPrice"] == config.UNRESTRICTED_MAX_PRICE)
        band = "unrestricted" if is_unrestricted else f"{r['MinPrice']}-{r['MaxPrice']}"
        w(f"  {r['SelectionName']:<30} Size={r['Size']:<6} Band={band}")

    w("\n--- SYSTEM CORRELATION (today only) ---")
    w("  Which quality-filtered systems most often co-fired on the same")
    w("  horse today - a high count here is ONE correlated signal, not")
    w("  independent confirmation (see single_selection_erosion_report.py).")
    if not consolidated.empty:
        for line in _system_correlation_lines(consolidated):
            w(line)
    else:
        w("  No consolidated selections today.")

    return buf.getvalue()
