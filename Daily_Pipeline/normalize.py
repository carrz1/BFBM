"""Horse-name normalization - the single point of failure for this whole
pipeline, per the original spec: BFBM matches on plain text name, so a
mismatch here is a silently missing bet.

Deliberately conservative: only whitespace cleanup by default. Country
suffixes and apostrophes are left exactly as HRB provides them (see
ingest_hrb.py's docstring for why) - this module does not try to guess
or "fix" anything, it only logs what it changed so a human can review.
"""
import re

import config

_WHITESPACE_RE = re.compile(r"\s+")
_CLOTH_NUMBER_RE = re.compile(r"^\s*\d{1,2}\.\s*")
_COUNTRY_SUFFIX_RE = re.compile(r"\s*\([A-Z]{2,4}\)\s*$")


def normalize_name(raw_name: str) -> tuple[str, str | None]:
    """Returns (normalized_name, change_note_or_None)."""
    if not isinstance(raw_name, str):
        return "", f"non-string name: {raw_name!r}"

    name = raw_name.strip()
    name = _WHITESPACE_RE.sub(" ", name)

    note = None

    if config.STRIP_CLOTH_NUMBER_PREFIX:
        stripped = _CLOTH_NUMBER_RE.sub("", name)
        if stripped != name:
            note = f"stripped cloth-number prefix: {name!r} -> {stripped!r}"
            name = stripped

    if config.STRIP_COUNTRY_SUFFIX:
        stripped = _COUNTRY_SUFFIX_RE.sub("", name)
        if stripped != name:
            note = (note + "; " if note else "") + f"stripped country suffix: {name!r} -> {stripped!r}"
            name = stripped

    if name != raw_name:
        note = note or f"whitespace-normalized: {raw_name!r} -> {name!r}"

    return name, note


def normalize_dataframe(df, name_col="horse_name"):
    """Adds a `normalized_name` column and returns (df, change_log list)."""
    change_log = []
    normalized = []
    for raw in df[name_col]:
        name, note = normalize_name(raw)
        normalized.append(name)
        if note:
            change_log.append(note)
    df = df.copy()
    df["normalized_name"] = normalized
    return df, change_log
