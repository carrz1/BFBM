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

# --- name formatting ---
STRIP_CLOTH_NUMBER_PREFIX = False      # confirmed not needed (2026-08-03 live BFBM test)
STRIP_COUNTRY_SUFFIX = True            # CEO reports no country suffixes visible
                                          # anywhere in BF/BFBM - overrides this
                                          # pipeline's earlier (wrong) assumption
                                          # that HRB's "(IRE)" etc. was genuine.
                                          # Get one concrete same-day example
                                          # confirmed before fully trusting this
                                          # for a live run - see bfbm-tips-reference.

# --- odds-band reconciliation across systems that agree on the same horse ---
ODDS_RECONCILIATION_RULE = "intersection"   # "intersection" | "union"

# Betfair's actual tradable decimal-odds range - used as the MinPrice/
# MaxPrice for a genuinely unrestricted selection instead of leaving the
# field blank. CONFIRMED 2026-08-03: a blank MinPrice/MaxPrice value
# causes BFBM's importer to reject the ENTIRE file (0 tips imported),
# not just that row - isolated via a bisection of diagnostic files after
# the CEO's real 86-row pipeline output imported as 0. Never write "".
UNRESTRICTED_MIN_PRICE = 1.01
UNRESTRICTED_MAX_PRICE = 1000.0

# --- BFBM tips CSV output ---
PROVIDER_NAME = "BFBM_HRB_v1"
MARKET_TYPE = "WIN"
BET_TYPE = "BACK"

# --- scope (v1) ---
ALLOWED_STORAGE_TYPES = ["My Systems"]  # "My Multicuts" is a different HRB
                                          # mechanism, never part of this
                                          # project's audit - out of scope
