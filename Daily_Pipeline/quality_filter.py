"""Gates rows to only quality-proven systems.

Reuses filtered_agreement_report.py's existing output as the source of
truth rather than recomputing anything - see PROJECT.md "Selection-
quality refinement" for how that list (>=100 standalone bets, standalone
ROI >= -5%, exact-duplicate systems already dropped) was built.
"""
import pandas as pd

import config


def load_qualifying_sys_keys() -> set:
    df = pd.read_csv(config.QUALIFYING_SYSTEMS_CSV)
    return set(df["sys_key"])


def apply(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    qualifying = load_qualifying_sys_keys()
    mask = df["sys_key"].isin(qualifying)
    dropped = df[~mask]
    exclusions = {
        "not_quality_filtered_count": int((~mask).sum()),
        "not_quality_filtered_sys_keys": sorted(dropped["sys_key"].unique().tolist()),
    }
    return df[mask].copy(), exclusions
