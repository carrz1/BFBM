"""Writes the BFBM tips CSV in the format verified live on 2026-08-03
(see the bfbm-tips-reference skill) - plain SelectionName, no cloth-
number prefix, no IDs needed. Quoted fields + CRLF match BFBM's own
export convention (not required for matching, kept for consistency).

Refuses to write - rather than truncating - if either hard cap would be
exceeded. Never round-trips through Excel; written directly as text.
"""
import csv

import pandas as pd

import config

BFBM_COLUMNS = ["Provider", "MarketType", "SelectionName", "MinPrice", "MaxPrice", "BetType", "Size"]


class SafetyCapExceeded(Exception):
    pass


def build_rows(consolidated) -> list[dict]:
    rows = []
    for _, r in consolidated.iterrows():
        stake = min(config.FLAT_STAKE, config.MAX_STAKE_PER_SELECTION)
        rows.append({
            "Provider": config.PROVIDER_NAME,
            "MarketType": config.MARKET_TYPE,
            "SelectionName": r["normalized_name"],
            "MinPrice": "" if pd.isna(r["min_price"]) else r["min_price"],
            "MaxPrice": "" if pd.isna(r["max_price"]) else r["max_price"],
            "BetType": config.BET_TYPE,
            "Size": stake,
        })
    return rows


def check_caps(rows: list[dict]):
    if len(rows) > config.MAX_SELECTION_COUNT:
        raise SafetyCapExceeded(
            f"{len(rows)} selections exceeds MAX_SELECTION_COUNT="
            f"{config.MAX_SELECTION_COUNT} - refusing to write. Likely a "
            f"parsing bug upstream, not a genuinely huge day."
        )
    total_stake = sum(r["Size"] for r in rows)
    if total_stake > config.MAX_TOTAL_STAKE_PER_DAY:
        raise SafetyCapExceeded(
            f"Total stake {total_stake} exceeds MAX_TOTAL_STAKE_PER_DAY="
            f"{config.MAX_TOTAL_STAKE_PER_DAY} - refusing to write."
        )


def write(rows: list[dict], out_path):
    if out_path.exists():
        raise FileExistsError(
            f"{out_path} already exists - refusing to overwrite a previous run's output."
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BFBM_COLUMNS, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
