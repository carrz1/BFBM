"""Verification: does every row in cross_account_all_system_bets.csv actually
respect its own system's odds band?

Prompted by the CEO asking, after the combination and agreement-count
reports, whether those numbers had any odds filtering applied at all. They
do - cross_account_overlap.py's load_slot() filters each slot's raw TSV to
`Odds_Exchange` within [lo, hi] from that system's validated Odds Band
*before* any row reaches the merged CSV every downstream report is built
from (system_combination_performance.py, filtered_agreement_report.py).

This script proves it independently rather than re-reading that code: it
rebuilds the odds-band lookup straight from the audit workbooks and checks
every row in the merged CSV against its own system's stated band directly.
"""
import re
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent

ACCOUNTS = {
    "noggin": "HRB_System_Performance_Audit_noggin_FINAL.xlsx",
    "noggin2": "HRB_System_Performance_Audit_noggin2.xlsx",
    "noggin3": "HRB_System_Performance_Audit_noggin3.xlsx",
    "noggin4": "HRB_System_Performance_Audit_noggin4.xlsx",
    "noggin5": "HRB_System_Performance_Audit_noggin5.xlsx",
}
BAND_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*$")


def load_bands():
    bands = {}
    for account, wb in ACCOUNTS.items():
        df = pd.read_excel(BASE / wb)
        for _, r in df.iterrows():
            cell = str(r["Odds Band"]).strip()
            m = BAND_RE.match(cell)
            bands[(account, int(r["Slot"]))] = (
                (float(m.group(1)), float(m.group(2))) if m else None)
    return bands


def main():
    d = pd.read_csv(BASE / "cross_account_all_system_bets.csv", low_memory=False)
    bands = load_bands()

    violations = []
    checked_with_band = 0
    checked_no_band = 0
    for (account, slot), sub in d.groupby(["account", "slot"]):
        band = bands.get((account, slot))
        if band is None:
            checked_no_band += len(sub)
            continue
        lo, hi = band
        checked_with_band += len(sub)
        bad = sub[(sub["Odds_Exchange"] < lo) | (sub["Odds_Exchange"] > hi)]
        if len(bad):
            violations.append((account, slot, lo, hi, len(bad)))

    print(f"Rows belonging to a system WITH an odds band    : {checked_with_band:,}")
    print(f"Rows belonging to a system with NO odds band ('none'): {checked_no_band:,}")
    print(f"Total rows checked                               : {len(d):,}")
    print(f"Rows found OUTSIDE their system's stated band    : "
          f"{sum(v[4] for v in violations)}")

    if violations:
        print("\n*** VIOLATIONS FOUND - odds filtering is NOT being applied "
              "correctly for: ***")
        for account, slot, lo, hi, n in violations:
            print(f"  {account}:{slot}  band=[{lo},{hi}]  {n} rows outside it")
    else:
        print("\nPASS: every row respects its own system's odds band. "
              "'No band' systems are unrestricted by design (the system's "
              "name genuinely has no price restriction), not a gap.")


if __name__ == "__main__":
    main()
