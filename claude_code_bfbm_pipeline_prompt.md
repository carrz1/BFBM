# Task: Build a daily selections → BFBM tips CSV pipeline

## Context

I bet daily on UK and Irish horse racing WIN markets on Betfair, and I'm
automating execution via Bf Bot Manager (BFBM) v3, which accepts a CSV
"tips" file. I need a pipeline that consolidates my day's selections from
multiple sources into a single BFBM-ready import file.

I am NOT using the Betfair API — no market/selection IDs are available or
needed. BFBM matches selections by horse name. (Betfair's live API app key
costs £499, and BFBM doesn't require it for name-based tips import.)

**Do not ask me for, store, or handle any Betfair account credentials.**
This pipeline never touches Betfair directly.

A reference document on the BFBM tips format is attached:
**bfbm_tips_reference.md**. Read it first — it's a distilled version of the
632-page BFBM manual covering exactly this workflow, including the CSV
column spec, hard constraints, and file-handling gotchas. Treat it as
authoritative over your own assumptions about BFBM.

## Data sources

**Source A — HorseRaceBase (horseracebase.com):** I have 5 accounts running
dozens of systems. Each system produces daily qualifiers. Currently I
manually download a CSV of qualifiers per account (5 files/day).

**Source B — The Racing API (theracingapi.com):** currently supplies
trainer/owner-related horses. I have API access.

Note: this project already has related skills at `/mnt/skills/user/`
(`trainerruns-fetch`, `trainerruns-batch`) that fetch from HorseRaceBase.
Read them — they establish the existing patterns for auth, request
structure and output conventions, and the eventual HRB automation should
follow them rather than inventing a new approach.

## Build in two phases

**Phase 1 (build this first): consolidation and conversion.**
Take the 5 manually-downloaded HRB CSVs plus Racing API data as inputs,
and produce the BFBM tips file. This is the whole value of the pipeline
and it works today with manual downloads.

**Phase 2 (design for, don't build yet): automate HRB extraction.**
Replace the manual downloads with automated fetching across all 5
accounts. Structure Phase 1 so the ingest layer is pluggable — reading
from a folder of CSVs and reading from a live fetch should be
interchangeable behind the same interface. Do not build Phase 2 until
Phase 1 is proven on real data.

## Step 0: Establish ground truth before writing the converter

Two things must be verified against reality first, because everything
depends on them and I don't yet know the answers:

1. **The exact `SelectionName` format BFBM expects.** The manual's example
   shows `1. Captain Bart` — with a leading cloth number and period. It's
   unclear whether the prefix is required. I will export a test tip from
   BFBM and give you the actual string. Ask me for it before finalising
   name formatting. Build the name formatter so the prefix is a
   configurable on/off, not hardcoded.

2. **My actual input schemas.** Ask me to provide (or point you at) one
   real HRB qualifier CSV and one sample of Racing API output, with
   headers. Do not guess column names.

Do not write the conversion logic before both are settled.

## Step 1: Ingest and normalise

Read all input sources into a common internal representation. Each record
should carry at minimum:

- Horse name (as given by source)
- Race identifier: date, course/meeting, race time
- Source system name (which HRB system or Racing API angle flagged it)
- Source account (which of the 5 HRB accounts, where applicable)
- Any per-system odds band, if present in the source data

**Name normalisation is the single point of failure for this whole
pipeline** — BFBM matches on name, so a mismatch means a silently missing
bet. Build a normalisation step handling at least: case, leading/trailing
whitespace, apostrophes (present vs absent — e.g. `O'Brien` vs `OBrien`),
country suffixes on foreign runners (e.g. `(IRE)`, `(FR)`, `(USA)`) —
determine whether Betfair/BFBM includes these and normalise consistently,
and any cloth-number prefixes already present in source data.

Do NOT invent corrections to apparent typos. Flag them instead.

## Step 2: Consolidate to one bet per horse

**Rule: one bet per horse per race, regardless of how many systems flag
it.** Group records by (date, course, race time, normalised horse name).

For each group, compute:

**Stake — scales with the number of distinct systems that flagged the
horse.** Make the scaling function explicit and configurable, with these
requirements:
- A base stake for a single-system qualifier
- A defined scaling rule (linear, square-root, or stepped — default to
  square-root and let me override; linear over-weights high counts)
- **A hard maximum stake cap**, non-negotiable, applied last
- Count *distinct systems*, not distinct rows — the same system appearing
  across two accounts is one signal, not two

**Odds band — resolve per-system bands into a single band.** Systems have
different bands, but there's only one bet, so bands must be reconciled.
Default rule: **tightest overlap (intersection)** — the merged band is
`max(all MinPrice)` to `min(all MaxPrice)`. This never places a bet
outside any contributing system's tolerance.
- If the intersection is empty (max of mins exceeds min of maxes), **do
  not guess**. Exclude the selection and add it to a flag report.
- Make the reconciliation rule configurable (intersection / union /
  highest-priority-system) — I may change my mind after seeing how often
  intersections come up empty.

**Bet type conflicts:** if one source says BACK and another says LAY on
the same horse, exclude and flag. Never resolve this silently.

## Step 3: Generate the BFBM tips CSV

Write one row per consolidated selection. Columns (see the reference doc
for the full spec):

- `Provider` — a single configurable system/tipster name (case sensitive).
  Since we're merging to one bet per horse, one provider name suffices.
- `MarketType` — `WIN`
- `SelectionName` — normalised, formatted per Step 0 finding
- `MinPrice` / `MaxPrice` — the reconciled band
- `BetType` — `BACK` or `LAY`
- `Size` — the computed scaled stake
- `StartTime` — race start time, if the format is confirmed compatible

Critical output requirements from the reference doc:

- **Write CSV programmatically as plain text.** Never round-trip through
  Excel — it mangles ID-like fields and truncates trailing zeroes.
- **Filter to today's card only.** BFBM generally won't have future days'
  markets loaded.
- **Detect same-name runners.** If two different horses in the day's
  selections share a normalised name, the three-column minimum is
  ambiguous. Flag these loudly — they need `EventId`/`MarketId` to
  disambiguate, which we don't have without API access, so they may need
  manual handling.
- File extension `.csv`, and warn me if the target file is currently open
  (Excel locks it and BFBM's import silently fails).

## Step 4: Reporting — this matters as much as the CSV

Every run must produce a human-readable report alongside the file:

- Count of input records per source, and count of output selections
- **Every exclusion, with its reason** (empty odds intersection, bet type
  conflict, name ambiguity, unparseable record)
- Any name that was normalised in a non-trivial way, showing before/after,
  so I can eyeball whether the normalisation is doing something dumb
- Stake distribution: how many selections at each system-count level, and
  the total staked
- **A system correlation report**: which systems most frequently flag the
  same horse. I need this to sanity-check the stake scaling — if several
  systems are variations on one underlying angle, high flag counts
  represent one correlated signal rather than independent confirmation,
  and the scaling would be concentrating risk exactly where I'm least
  diversified.

## Step 5: Safety rails

Non-negotiable, built in from the start:

- **Hard maximum stake per selection** (cap applied after scaling)
- **Hard maximum total stake per day** — if the day's file exceeds it,
  refuse to write and report, rather than truncating arbitrarily
- **Hard maximum selection count per day** — a sanity ceiling that catches
  a parsing bug producing thousands of rows
- **Dry-run mode as the default.** Generate the file to a staging path and
  print the report; require an explicit flag to write to the location
  BFBM imports from
- Never overwrite a previous day's output file — timestamp or date-stamp
  filenames

## Step 6: Validation before I trust it

1. Run against one real day's data. Show me the report and the CSV, and
   walk me through any exclusions.
2. I will manually check a sample of horse names against Betfair to
   confirm the name format matches. Wait for my confirmation before I
   import anything with real stakes.
3. First live run goes at minimum stakes only.

## Preferences

- Python, consistent with the existing project tooling
- Config (stakes, caps, provider name, odds reconciliation rule, cloth
  prefix on/off) in a separate file, not buried in code — I will tune
  these
- API credentials for The Racing API via environment variables or a local
  secrets file that is gitignored. Never hardcoded, never logged
- Idempotent: re-running for the same day should produce the same output,
  not append or duplicate
