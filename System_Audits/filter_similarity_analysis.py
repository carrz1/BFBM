"""Cross-account system similarity / duplicate analysis.

With ~423 systems spread across 5 HRB accounts that have become unwieldy to
manage by hand, the CEO asked: how many of them are actually similar or
identical to each other, not just by name?

This joins each system's literal compiled HRB filter (`completewheresteps`,
extracted via System_Audits/filters/*.jsonl) with its already-validated odds
band (from the audit workbooks) and compares every system against every
other system - because two systems can share identical selection criteria
but bet completely different price ranges, and the reverse: same odds band,
different criteria. Both parts have to match for two systems to actually be
redundant.

Comparison is done on the *set of individual conditions* in each filter
(split on " AND "), not the raw string, so condition order or the exact
IN-list formatting differences (extra spaces, "(1,2)" vs "( 1, 2 )") don't
cause a false near-miss. `dateyears >=2003` is present in literally every
system (it's a fixed floor HRB applies to all archive queries) and carries
no discriminating information, so it's dropped before comparing - keeping
it would understate every pair's distance from being an exact match by one
constant, shared condition.
"""
import json
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

BOILERPLATE = {"dateyears >=2003"}


def normalize_conditions(filter_str):
    """Split a completewheresteps string into a comparable set of conditions."""
    parts = re.split(r"\s+AND\s+", filter_str.strip())
    norm = set()
    for p in parts:
        p = re.sub(r"\s+", " ", p.strip())
        p = re.sub(r"\(\s*", "(", p)
        p = re.sub(r"\s*\)", ")", p)
        p = re.sub(r",\s+", ",", p)
        if p and p not in BOILERPLATE:
            norm.add(p)
    return frozenset(norm)


def load_filters():
    rows = []
    for account in ACCOUNTS:
        path = BASE / "filters" / f"{account}_filters.jsonl"
        with open(path, encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line)
                rows.append({
                    "account": account,
                    "slot": obj["slot"],
                    "name": obj["name"],
                    "filter": obj.get("filter"),
                    "error": obj.get("error"),
                })
    return pd.DataFrame(rows)


def load_odds_bands():
    rows = []
    for account, wb in ACCOUNTS.items():
        df = pd.read_excel(BASE / wb)
        for _, r in df.iterrows():
            rows.append({
                "account": account,
                "slot": int(r["Slot"]),
                "odds_band": str(r["Odds Band"]).strip(),
                "plbf": r["P/L(BF)"],
                "bets": r["Bets"],
            })
    return pd.DataFrame(rows)


def build():
    filt = load_filters()
    bands = load_odds_bands()
    df = filt.merge(bands, on=["account", "slot"], how="left")
    no_filter = df[df["filter"].isna()]
    df = df[df["filter"].notna()].copy()
    df["odds_band"] = df["odds_band"].fillna("none")
    df["conditions"] = df["filter"].apply(normalize_conditions)
    df["sys_key"] = df["account"] + ":" + df["slot"].astype(str)
    return df, no_filter


def report_exact_duplicates(df):
    print("=" * 78)
    print("STEP 1 - EXACT DUPLICATES (identical criteria AND identical odds band)")
    print("=" * 78)
    df["fingerprint"] = df.apply(
        lambda r: (r["conditions"], r["odds_band"]), axis=1)
    groups = df.groupby("fingerprint")["sys_key"].apply(list)
    dupes = groups[groups.apply(len) > 1]
    print(f"{len(dupes)} groups of exact duplicates, "
          f"covering {sum(len(v) for v in dupes)} systems.\n")
    for fp, keys in dupes.items():
        names = df[df["sys_key"].isin(keys)][["sys_key", "name"]]
        print(f"  {' == '.join(keys)}")
        for _, row in names.iterrows():
            print(f"      {row['sys_key']:<14} {row['name']}")
    return dupes


def report_near_duplicates(df, threshold=0.75):
    print()
    print("=" * 78)
    print(f"STEP 2 - NEAR-DUPLICATES (Jaccard similarity >= {threshold}, "
          f"same odds band, not already an exact duplicate)")
    print("=" * 78)

    exact_pairs = set()
    for keys in df.groupby(df.apply(
            lambda r: (r["conditions"], r["odds_band"]), axis=1))["sys_key"].apply(list):
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                exact_pairs.add((keys[i], keys[j]))

    records = df[["sys_key", "name", "conditions", "odds_band", "account"]].to_dict("records")
    near = []
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            a, b = records[i], records[j]
            if a["odds_band"] != b["odds_band"]:
                continue
            ca, cb = a["conditions"], b["conditions"]
            if not ca and not cb:
                continue
            union = ca | cb
            if not union:
                continue
            jac = len(ca & cb) / len(union)
            if jac >= threshold:
                pair = tuple(sorted([a["sys_key"], b["sys_key"]]))
                if pair in exact_pairs:
                    continue
                near.append((jac, a, b))

    near.sort(key=lambda t: -t[0])
    print(f"{len(near)} near-duplicate pairs found.\n")
    for jac, a, b in near:
        cross = " [CROSS-ACCOUNT]" if a["account"] != b["account"] else ""
        print(f"  {jac:.3f}  {a['sys_key']:<14} {a['name'][:38]:<38} "
              f"<-> {b['sys_key']:<14} {b['name'][:38]:<38}{cross}")
        only_a = a["conditions"] - b["conditions"]
        only_b = b["conditions"] - a["conditions"]
        if only_a:
            print(f"         only in A: {'; '.join(sorted(only_a))}")
        if only_b:
            print(f"         only in B: {'; '.join(sorted(only_b))}")
    return near


def report_summary(df, dupes, near):
    print()
    print("=" * 78)
    print("STEP 3 - SUMMARY")
    print("=" * 78)
    n_exact = sum(len(v) for v in dupes)
    n_near_systems = len({k for _, a, b in near for k in (a["sys_key"], b["sys_key"])})
    print(f"Systems analysed              : {len(df)}")
    print(f"Exact duplicates              : {n_exact} systems in {len(dupes)} groups")
    print(f"Near-duplicates (>=0.75 Jaccard, not exact): "
          f"{n_near_systems} systems in {len(near)} pairs")
    cross_account_near = sum(1 for _, a, b in near if a["account"] != b["account"])
    print(f"  of which cross-account       : {cross_account_near} pairs")
    print(f"\nSystems seemingly unique to their own criteria+band: "
          f"{len(df) - n_exact - n_near_systems}")


def main():
    df, no_filter = build()
    if len(no_filter):
        print(f"WARNING: {len(no_filter)} slots had no filter extracted "
              f"(errors): {no_filter[['account', 'slot', 'error']].to_dict('records')}\n")

    dupes = report_exact_duplicates(df)
    near = report_near_duplicates(df)
    report_summary(df, dupes, near)

    df.drop(columns=["conditions"]).to_csv(
        BASE / "filter_similarity_systems.csv", index=False)
    print(f"\nWrote filter_similarity_systems.csv ({len(df)} systems).")


if __name__ == "__main__":
    main()
