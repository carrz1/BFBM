"""All tunables for the daily HRB -> BFBM tips pipeline, in one place.

Nothing in the rest of this package should hardcode a threshold, path,
or stake value - if a script needs a new knob, it goes here first.
"""
from pathlib import Path

BASE = Path(__file__).parent
SYSTEM_AUDITS = BASE.parent / "System_Audits"

ACCOUNTS = ["noggin", "noggin2", "noggin3", "noggin4", "noggin5"]

# Filename prefix -> account, per the CEO's naming convention for the
# daily HRB exports: n_qualifiers_DATE.csv, n2_qualifiers_DATE.csv, etc.
FILENAME_PREFIX_TO_ACCOUNT = {
    "n": "noggin",
    "n2": "noggin2",
    "n3": "noggin3",
    "n4": "noggin4",
    "n5": "noggin5",
}

INPUT_DIR = BASE / "input"
STAGING_DIR = BASE / "staging"
LIVE_OUTPUT_DIR = BASE / "live_output"

QUALIFYING_SYSTEMS_CSV = SYSTEM_AUDITS / "filtered_agreement_qualifying_systems.csv"
ODDS_BANDS_CSV = SYSTEM_AUDITS / "filter_similarity_systems.csv"

# --- staking (v1: flat, gated by system quality only - see PROJECT.md
#     "Selection-quality refinement" for why agreement-count scaling and
#     the value-ratio formula are deliberately NOT used here yet) ---
FLAT_STAKE = 1.0
MAX_STAKE_PER_SELECTION = 1.0          # v1: no scaling, so this just equals FLAT_STAKE
MAX_TOTAL_STAKE_PER_DAY = 150.0        # refuse to write past this, don't truncate
MAX_SELECTION_COUNT = 150              # sanity ceiling catching a parsing bug

# --- name formatting (verified 2026-08-03 via live BFBM testing - see
#     the bfbm-tips-reference skill's Verified Findings) ---
STRIP_CLOTH_NUMBER_PREFIX = False      # confirmed not needed
STRIP_COUNTRY_SUFFIX = False           # deliberately NOT stripped - see ingest_hrb.py

# --- odds-band reconciliation across systems that agree on the same horse ---
ODDS_RECONCILIATION_RULE = "intersection"   # "intersection" | "union"

# --- BFBM tips CSV output ---
PROVIDER_NAME = "BFBM_HRB_v1"
MARKET_TYPE = "WIN"
BET_TYPE = "BACK"

# --- scope (v1) ---
ALLOWED_STORAGE_TYPES = ["My Systems"]  # "My Multicuts" is a different HRB
                                          # mechanism, never part of this
                                          # project's audit - out of scope
