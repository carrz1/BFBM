"""One bet per (date, track, race time, normalized horse name), regardless
of how many quality-filtered systems flagged it. Reconciles each group's
odds band (default: intersection - the merged band never places a bet
outside any contributing system's own tolerance) and flags anything that
can't be safely resolved rather than guessing.
"""
import pandas as pd

import config


def load_odds_bands() -> dict:
    """sys_key -> (min_price, max_price) or (None, None) for 'none' (no band)."""
    df = pd.read_csv(config.ODDS_BANDS_CSV)
    bands = {}
    for _, row in df.iterrows():
        band = row["odds_band"]
        if not isinstance(band, str) or band.strip().lower() == "none":
            bands[row["sys_key"]] = (None, None)
            continue
        try:
            lo_s, hi_s = band.split(" - ")
            bands[row["sys_key"]] = (float(lo_s), float(hi_s))
        except ValueError:
            bands[row["sys_key"]] = (None, None)
    return bands


def _reconcile_band(sys_keys, bands: dict):
    """Returns (min_price, max_price, conflict_note_or_None).
    None/None means genuinely unrestricted (every contributing system has
    no odds band at all) - left blank in the output, not guessed at.
    """
    los, his = [], []
    for sk in sys_keys:
        lo, hi = bands.get(sk, (None, None))
        if lo is not None:
            los.append(lo)
        if hi is not None:
            his.append(hi)

    if not los and not his:
        return None, None, None

    if config.ODDS_RECONCILIATION_RULE == "intersection":
        merged_lo = max(los) if los else None
        merged_hi = min(his) if his else None
    else:  # "union"
        merged_lo = min(los) if los else None
        merged_hi = max(his) if his else None

    if merged_lo is not None and merged_hi is not None and merged_lo > merged_hi:
        return None, None, (
            f"empty odds-band intersection across {sorted(sys_keys)}: "
            f"max(mins)={merged_lo} > min(maxes)={merged_hi}"
        )
    return merged_lo, merged_hi, None


def consolidate(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    bands = load_odds_bands()
    exclusions = {"empty_odds_intersection": [], "ambiguous_same_name": []}

    grouped = df.groupby(["Date", "track", "time", "normalized_name"])
    rows = []
    for (date, track, race_time, name), g in grouped:
        sys_keys = sorted(g["sys_key"].unique())
        lo, hi, conflict = _reconcile_band(sys_keys, bands)
        if conflict:
            exclusions["empty_odds_intersection"].append(
                {"date": date, "track": track, "time": race_time,
                 "name": name, "reason": conflict}
            )
            continue
        rows.append({
            "date": date, "track": track, "time": race_time,
            "normalized_name": name, "sys_keys": sys_keys,
            "min_price": lo, "max_price": hi,
        })

    consolidated = pd.DataFrame(rows)
    if consolidated.empty:
        return consolidated, exclusions

    # same normalized name appearing in more than one race the same day
    # is ambiguous without MarketId/EventId (hard constraint, see the
    # bfbm-tips-reference skill) - flag and drop both/all occurrences
    dupe_names = (
        consolidated.groupby(["date", "normalized_name"])
        .filter(lambda g: g["track"].nunique() > 1 or g["time"].nunique() > 1)
    )
    if not dupe_names.empty:
        for _, row in dupe_names.iterrows():
            exclusions["ambiguous_same_name"].append(
                {"date": row["date"], "name": row["normalized_name"],
                 "track": row["track"], "time": row["time"]}
            )
        consolidated = consolidated.drop(dupe_names.index)

    return consolidated.reset_index(drop=True), exclusions
