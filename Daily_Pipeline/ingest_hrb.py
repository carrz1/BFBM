"""Reads the day's 5 HRB bulk-qualifier exports into one common DataFrame.

Confirmed column schema (2026-08-03, from a real sample -
E:\\racing\\BFBOTManager\\qualifiers_2026-08-03.csv):

    Date,StorageType,slot,description,horse_name,time,track,odds,
    jockey_name,trainer,official_rating,Distance,Age,DaysSinceRun,
    notes,placing,<trailing empty column>

Two things this schema forces on the design, learned from that sample -
do not "fix" either without re-checking against real data first:

1. `horse_name` already carries a breeding-country suffix where relevant
   (e.g. "Arctic Flame (IRE)") - this is very likely genuinely part of
   Betfair's own selection name for non-GB-bred horses, unlike the
   cloth-number prefix (confirmed NOT needed). So this ingest step does
   NOT strip country suffixes - see config.STRIP_COUNTRY_SUFFIX.
2. The file mixes races that have already run today (some rows already
   show a real `placing`) with ones still to come - `placing` is NOT a
   reliable "hasn't run yet" flag on its own (seen rows in the identical
   race with a mix of real placings and "??"), so eligibility is decided
   by comparing each row's Date+time against wall-clock now.
"""
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

import config

EXPECTED_COLUMNS = {
    "Date", "StorageType", "slot", "description", "horse_name", "time",
    "track", "odds", "jockey_name", "trainer", "official_rating",
    "notes", "placing",
}
# Columns seen in real exports but NOT required here because nothing in
# this pipeline reads them, and they vary by account (confirmed
# 2026-08-03: noggin/n4 have Distance+Age, n2 has neither, n3 has
# Distance+RaceClass+LR_Position+LR_NumberRunners instead of Age, n5 has
# none of them at all) - Distance, Age, DaysSinceRun, RaceClass,
# LR_Position, LR_NumberRunners. If a future step needs one of these,
# add it to EXPECTED_COLUMNS deliberately, don't just assume every
# account has it.

FILENAME_RE = re.compile(r"^(?P<prefix>n[2-5]?)_qualifiers_(?P<date>\d{4}-\d{2}-\d{2})\.csv$")


class IngestError(Exception):
    pass


def _account_from_filename(path: Path) -> tuple[str, str]:
    m = FILENAME_RE.match(path.name)
    if not m:
        raise IngestError(
            f"'{path.name}' doesn't match the expected "
            f"'<prefix>_qualifiers_<YYYY-MM-DD>.csv' naming convention "
            f"(prefix is one of {sorted(config.FILENAME_PREFIX_TO_ACCOUNT)}, "
            f"e.g. n3_qualifiers_2026-08-03.csv)."
        )
    prefix = m.group("prefix")
    account = config.FILENAME_PREFIX_TO_ACCOUNT.get(prefix)
    if account is None:
        raise IngestError(f"prefix '{prefix}' in '{path.name}' isn't mapped to any account")
    return account, m.group("date")


def _read_one_file(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    # tolerate the trailing empty/unnamed column seen in the real sample
    df = df.loc[:, [c for c in df.columns if not c.startswith("Unnamed:")]]

    missing = EXPECTED_COLUMNS - set(df.columns)
    if missing:
        raise IngestError(
            f"{path.name}: missing expected column(s) {sorted(missing)} - "
            f"actual columns were {list(df.columns)}. Refusing to guess a "
            f"mapping; the schema may have changed since 2026-08-03."
        )
    return df


def load_today(target_date: str) -> tuple[pd.DataFrame, dict]:
    """Reads every account's file for target_date (YYYY-MM-DD) from
    config.INPUT_DIR. Returns (surviving_rows, exclusion_counts).
    exclusions["raw_counts_per_account"] is the true as-read row count per
    account, BEFORE any filtering - use this for reporting, not
    len(surviving_rows) grouped by account, which is post-filter.
    """
    exclusions = {"missing_account_files": [], "out_of_scope_multicuts": 0,
                  "already_run_or_no_time": 0, "raw_counts_per_account": {}}
    frames = []

    for prefix, account in config.FILENAME_PREFIX_TO_ACCOUNT.items():
        path = config.INPUT_DIR / f"{prefix}_qualifiers_{target_date}.csv"
        if not path.exists():
            exclusions["missing_account_files"].append(account)
            continue
        df = _read_one_file(path)
        file_account, file_date = _account_from_filename(path)
        if file_date != target_date:
            raise IngestError(f"{path.name}: filename date doesn't match requested {target_date}")
        df["account"] = file_account
        exclusions["raw_counts_per_account"][file_account] = len(df)
        frames.append(df)

    if not frames:
        raise IngestError(
            f"No HRB export files found for {target_date} in {config.INPUT_DIR}. "
            f"Expected files named like 'noggin_qualifiers_{target_date}.csv'."
        )

    all_rows = pd.concat(frames, ignore_index=True)

    scope_mask = all_rows["StorageType"].isin(config.ALLOWED_STORAGE_TYPES)
    exclusions["out_of_scope_multicuts"] = int((~scope_mask).sum())
    all_rows = all_rows[scope_mask].copy()

    all_rows["sys_key"] = all_rows["account"] + ":" + all_rows["slot"].astype(str)
    all_rows["race_dt"] = pd.to_datetime(
        all_rows["Date"].astype(str) + " " + all_rows["time"].astype(str),
        errors="coerce",
    )

    bad_time = all_rows["race_dt"].isna()
    now = datetime.now()
    past_or_bad = bad_time | (all_rows["race_dt"] <= now)
    exclusions["already_run_or_no_time"] = int(past_or_bad.sum())
    all_rows = all_rows[~past_or_bad].copy()

    return all_rows, exclusions
