"""Orchestrates the daily HRB -> BFBM tips pipeline.

Dry-run by default: writes to config.STAGING_DIR and prints the report,
never touching config.LIVE_OUTPUT_DIR without an explicit --live flag.

Usage:
    python run_pipeline.py                  # dry-run, today
    python run_pipeline.py --date 2026-08-04
    python run_pipeline.py --live            # writes to LIVE_OUTPUT_DIR
"""
import argparse
from datetime import date

import config
import ingest_hrb
import normalize
import quality_filter
import consolidate
import write_bfbm_csv
import report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--live", action="store_true",
                         help="write to LIVE_OUTPUT_DIR instead of STAGING_DIR")
    args = parser.parse_args()

    per_account_counts = {}
    for prefix, account in config.FILENAME_PREFIX_TO_ACCOUNT.items():
        path = config.INPUT_DIR / f"{prefix}_qualifiers_{args.date}.csv"
        per_account_counts[account] = "not provided" if not path.exists() else None

    rows_df, ingest_exclusions = ingest_hrb.load_today(args.date)

    for account in config.ACCOUNTS:
        if per_account_counts[account] is None:
            per_account_counts[account] = int((rows_df["account"] == account).sum())

    rows_df, normalize_log = normalize.normalize_dataframe(rows_df)
    rows_df, quality_exclusions = quality_filter.apply(rows_df)
    consolidated, consolidate_exclusions = consolidate.consolidate(rows_df)

    bfbm_rows = write_bfbm_csv.build_rows(consolidated)

    report_text = report.build_report(
        target_date=args.date,
        ingest_exclusions=ingest_exclusions,
        quality_exclusions=quality_exclusions,
        normalize_log=normalize_log,
        consolidate_exclusions=consolidate_exclusions,
        consolidated=consolidated,
        rows=bfbm_rows,
        per_account_counts=per_account_counts,
    )
    print(report_text)

    out_dir = config.LIVE_OUTPUT_DIR if args.live else config.STAGING_DIR
    csv_path = out_dir / f"{args.date}_tips.csv"
    report_path = out_dir / f"{args.date}_report.txt"

    try:
        write_bfbm_csv.check_caps(bfbm_rows)
    except write_bfbm_csv.SafetyCapExceeded as exc:
        print(f"\nREFUSING TO WRITE: {exc}")
        return 1

    try:
        write_bfbm_csv.write(bfbm_rows, csv_path)
    except FileExistsError as exc:
        print(f"\nREFUSING TO WRITE: {exc}")
        return 1

    report_path.parent.mkdir(parents=True, exist_ok=True)
    if not report_path.exists():
        report_path.write_text(report_text, encoding="utf-8")

    mode = "LIVE" if args.live else "DRY-RUN (staging)"
    print(f"\n[{mode}] Wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
