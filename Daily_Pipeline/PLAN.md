# Daily selections -> BFBM tips CSV pipeline (Phase 1: HRB only)

## Context

The BFBM project has spent this project's life so far on two separate
tracks that have never been connected: (1) auditing which of the ~420
HRB systems are actually profitable, culminating today in a
quality-filtered system list, several refinement analyses (agreement
count, combinations, erosion, race dilution, a value-ratio staking
formula), and (2) verifying, also today, that BFBM's tips-CSV import
actually works end-to-end - plain selection names with no cloth-number
prefix are enough to match a live market, once it's loaded and a rescan
cycle has run. Both tracks are now proven. This plan is the first thing
that actually joins them: a real pipeline that turns HRB's daily
qualifiers into a CSV BFBM can import, gated by everything learned about
which systems and stake sizes are actually trustworthy.

This is Phase 1 of the two-phase build already specified by the CEO in
`claude_code_bfbm_pipeline_prompt.md` - consolidation/conversion only,
taking manually-exported HRB CSVs as input. Phase 2 (automating the HRB
export itself) is explicitly deferred in that spec and stays deferred
here. Racing API / trainer-owner matches (Source B) are also deferred to
a later pass per the CEO's explicit choice today - this build is HRB
only.

**Intended outcome**: a `python run_pipeline.py` command that, given the
5 HRB accounts' daily bulk-qualifier exports sitting in an input folder,
produces (a) a BFBM-ready tips CSV in the verified format, gated to only
quality-proven systems, one flat-staked bet per horse, and (b) a
human-readable report the CEO can review before ever letting the file
near BFBM - defaulting to a dry-run/staging write, never touching the
live BFBM import location without an explicit flag.

## Decisions already settled (this session)

- **Stake sizing (v1): flat unit stake, gated by system quality only.**
  No agreement-count scaling, no value-ratio formula in v1 - both are
  real but nuanced enough (diluted by new-system growth; only helps in
  the 16-128 odds range and can hurt weak systems) that they're v2
  work, layered in only after this baseline is proven on real results.
- **Quality gate: reuse, don't recompute.**
  `System_Audits/filtered_agreement_qualifying_systems.csv` already has
  the 220 systems that pass `>=100 standalone bets` and
  `standalone ROI >= -5%` (exact-duplicate systems already excluded) -
  this is the existing source of truth for "which systems are allowed to
  vote," built and validated by `filtered_agreement_report.py`. No new
  filtering logic needed, just a lookup.
- **Odds bands: also reuse.**
  `System_Audits/filter_similarity_systems.csv` already has every
  system's validated odds band (min/max) alongside its account/slot -
  the per-selection band reconciliation (intersection of every firing
  system's band, CEO's specified default) reads from this file rather
  than re-parsing anything.
- **BFBM CSV format: fully verified today, no open questions left.**
  `Provider,MarketType,SelectionName` is sufficient; `SelectionName`
  needs no cloth-number prefix (plain racecard name); `MarketType=WIN`;
  quoted fields aren't required for matching but will be used anyway for
  consistency with BFBM's own file convention; `Size` carries the flat
  stake. Full detail lives in the `bfbm-tips-reference` skill.
- **Source scope: HRB only for this build.** The Racing API
  trainer/owner-match pipeline already exists and works
  (`TO_Project/API_pipeline.py` -> `output/YYYY-MM-DD_matches.csv`) but
  is a structurally different signal (no backtested track record, no
  odds band) - wiring it in is future work, not this build.
- **HRB input shape: one bulk report per account (5 files/day),
  manually exported** - matches the CEO's confirmation and the original
  spec's Phase 1 assumption. Exact column names are still unconfirmed
  (every existing HRB automation in this repo pulls a system's full
  historical audit data, never this daily bulk-qualifier view) - **the
  first real implementation step is to get one real sample file and
  nail the ingest column mapping against it**, per the original spec's
  own "Step 0" instruction not to guess column names. If a sample isn't
  available yet when implementation starts, build the ingest module
  against a clearly-documented placeholder schema and treat finalizing
  it as the explicit first validation task before anything downstream is
  trusted.

## New pipeline location

`E:\racing\AI\GitHub\BFBM\Daily_Pipeline\` - a new top-level folder,
parallel to `System_Audits/` (which stays as the backtesting/audit
codebase, untouched). Keeps the live-execution pipeline cleanly separate
from the historical analysis scripts.

```
Daily_Pipeline/
  config.py              # every tunable in one place, per CEO's explicit request
  ingest_hrb.py           # reads the 5 bulk-qualifier CSVs -> common records
  normalize.py            # name normalization (case, whitespace, apostrophes,
                           #   country suffixes, cloth-number stripping)
  quality_filter.py       # drops rows from non-qualifying systems (reads
                           #   filtered_agreement_qualifying_systems.csv)
  consolidate.py          # one bet per (date, course, race time, horse);
                           #   odds-band intersection; ambiguity/conflict flags
  write_bfbm_csv.py       # emits the tips CSV in the verified format
  report.py               # human-readable run report
  run_pipeline.py         # orchestrates the above; dry-run by default
  staging/                # dry-run output lands here (gitignored)
  input/                  # where the CEO drops the day's 5 HRB exports (gitignored)
```

## config.py - tunables (CEO's explicit request: separate from code)

- `PROVIDER_NAME` - single provider string for the merged tips (default
  something like `"BFBM_HRB_v1"`)
- `FLAT_STAKE` - the v1 unit stake
- `MAX_STAKE_PER_SELECTION` - hard cap (non-negotiable, applied last)
- `MAX_TOTAL_STAKE_PER_DAY` - hard cap; exceeding it refuses to write
  rather than truncating
- `MAX_SELECTION_COUNT` - sanity ceiling catching a parsing bug
- `ODDS_RECONCILIATION_RULE` - default `"intersection"`, configurable to
  `"union"` / `"highest_priority_system"` later
- `CLOTH_NUMBER_PREFIX` - default `False` (verified today: not needed)
- `QUALIFYING_SYSTEMS_CSV` - path to
  `System_Audits/filtered_agreement_qualifying_systems.csv`
- `ODDS_BANDS_CSV` - path to `System_Audits/filter_similarity_systems.csv`
- `INPUT_DIR` / `STAGING_DIR` / `LIVE_OUTPUT_DIR`

## Step-by-step

1. **`ingest_hrb.py`**: read all CSVs in `input/`, one per account. Each
   record normalized to: horse name (raw), date, course, race time,
   sys_key (account:slot, to join against the quality/odds-band CSVs),
   raw odds band if present inline. **Do not guess column names** - this
   is the step that gets finalized against a real sample first.
2. **`normalize.py`**: produce a canonical horse-name string per CEO's
   spec requirements (case, whitespace, apostrophe variants, country
   suffix and cloth-number stripping - configurable, off by default per
   today's finding). Log every non-trivial normalization (before/after)
   for the report - never silently "fix" an apparent typo, flag it
   instead.
3. **`quality_filter.py`**: join each record's `sys_key` against
   `filtered_agreement_qualifying_systems.csv`; drop rows for
   non-qualifying systems; count and report how many were dropped and
   why (not qualifying vs. not found in the lookup at all - the latter
   is a data-integrity flag, not an expected exclusion).
4. **`consolidate.py`**: group surviving records by (date, course, race
   time, normalized name) - one bet per horse regardless of how many
   qualifying systems flagged it (system count is deliberately NOT used
   for stake sizing in v1, per the decision above - it's only used to
   decide odds-band reconciliation across whichever systems fired).
   Reconcile each group's odds band via intersection using
   `filter_similarity_systems.csv`; empty intersection -> exclude +
   flag, don't guess. Detect and flag same-normalized-name collisions
   within the same day (ambiguous without `MarketId`, per the reference
   skill's hard constraint).
5. **`write_bfbm_csv.py`**: one row per surviving consolidated
   selection - `Provider` (from config), `MarketType=WIN`,
   `SelectionName` (normalized name, no cloth prefix per config
   default), `MinPrice`/`MaxPrice` (reconciled band), `BetType=BACK`,
   `Size=FLAT_STAKE` (capped by `MAX_STAKE_PER_SELECTION`). Write with
   Python's `csv` module, `QUOTE_ALL`, explicit `\r\n` line terminator
   matching BFBM's own convention (confirmed today this isn't strictly
   required for matching, but keeps the file consistent with what BFBM
   itself produces). Never touch Excel. Refuse to write if
   `MAX_TOTAL_STAKE_PER_DAY` or `MAX_SELECTION_COUNT` would be exceeded -
   report why instead.
6. **`report.py`**: per-source input counts, output selection count,
   every exclusion with its reason, the normalization log, stake/total
   summary, and a system-correlation section reusing the pairwise logic
   already built in `System_Audits/system_combination_performance.py`
   (which systems most often co-fire on the same horse - so correlated
   variations-on-one-angle don't get mistaken for independent
   confirmation later, when agreement-scaling becomes relevant in v2).
7. **`run_pipeline.py`**: wires steps 1-6 together. **Dry-run is the
   default** - writes to `staging/YYYY-MM-DD_tips.csv` and prints the
   report; a `--live` flag is required to write to
   `LIVE_OUTPUT_DIR` instead. Filenames are always date-stamped; never
   overwrite an existing day's file (refuse and error instead).

## Explicitly out of scope for this build

- Racing API / Source B ingestion (deferred, per CEO's choice today)
- HRB live-fetch automation (Phase 2 of the original spec, still
  deferred)
- Agreement-count stake scaling and the value-ratio staking formula
  (v2 work, only after this flat-stake baseline is validated against
  real results)
- Any Betfair API usage or credential handling (this pipeline only ever
  produces a CSV; BFBM handles everything past that)

## Verification plan

1. Get one real sample HRB bulk-qualifier CSV (one account) and finalize
   `ingest_hrb.py`'s column mapping against it before writing anything
   downstream that depends on guessed column names.
2. Run `run_pipeline.py` (dry-run) against a real day's 5 account
   exports once available. Review the staging CSV and report together
   with the CEO - walk through every exclusion.
3. CEO manually spot-checks a handful of output `SelectionName` values
   against Betfair's actual displayed names for that day, per the
   original spec's own validation step.
4. Deliberately test the safety rails once (e.g. temporarily lower
   `MAX_TOTAL_STAKE_PER_DAY` below what a real day would produce) to
   confirm the pipeline actually refuses to write rather than silently
   truncating.
5. First real `--live` run only after the above, and only imported into
   BFBM at minimum/flat stakes, consistent with the original spec's own
   plan.

---

*Note: this plan reflects the state of thinking at the start of the
build (2026-08-03). Several things evolved during and after
implementation - see CHANGELOG.md and PROJECT.md's "Daily_Pipeline"
section for what actually happened, including three real bugs found
and fixed, the first real BFBM import, and the first bet placed and
settled (in Simulation Mode). This file is kept as a historical record
of the original plan, not updated to match current state.*
