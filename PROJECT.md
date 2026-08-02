# BFBM Automated Betting Pipeline

## Goal

Automate daily horse racing betting via Betfair Bot Manager (BFBM) v3:

1. Collate and merge racing selections from six sources into one file.
2. Convert them into a CSV that BFBM accepts and can import (name-based
   matching — no Betfair API, no market/selection IDs).
3. Import into BFBM and click "run" — no manual intervention needed.

The six sources: five HorseRaceBase (HRB) accounts (each running dozens
of independent saved "systems"), plus The Racing API
(theracingapi.com), which supplies trainer/owner-matched selections.

Full technical spec for the merge/CSV pipeline (name normalisation,
stake scaling, odds-band reconciliation, safety rails, reporting) is in
[claude_code_bfbm_pipeline_prompt.md](claude_code_bfbm_pipeline_prompt.md).
The BFBM CSV column format itself is documented in
[bfbm_tips_reference.md](bfbm_tips_reference.md).

**Current stage: audit complete, selection-quality refinement well
underway, live-execution pipeline not yet built (but investigated).**
Before merging any selections, the CEO wanted to know which of the ~500
systems across the five HRB accounts are actually profitable, how they
interact (overlap, agreement, combinations), and how a portfolio-level
staking approach might improve on flat 1-point staking per bet. See
"Selection-quality refinement" and "Live execution pipeline - BFBM
tips-import" below for where that stands.

## Why the audit matters

HRB's own "My Performance Report" (Performance since saved date) is
close but has one critical gap: **it cannot apply a min/max Betfair
odds filter**. Most systems have an odds band baked into their name
(e.g. "10.01 - 400.00") that was never enforced by that report — it
just aggregates every bet regardless of price. So the site's own
number for a system can look profitable (or not) while blending in
bets outside the price range the system was actually designed for.

The audit therefore recomputes P/L per system from the raw per-bet
data, applying:
- the odds band parsed from the system's name (see below)
- "since saved date" as **the day after** the saved date (the CEO's
  explicit instruction — note this differs by one day from HRB's own
  report, which is inclusive of the saved date itself)

## The five HRB accounts

Each account has its own **completely independent** set of saved
systems — same slot numbers (1-100ish) but different names, different
criteria, different performance, across accounts. There is no mirroring
between accounts. Credentials for all five live in `.env`
(`HORSERACEBASE_USERNAME` / `HORSERACEBASE_PASSWORD`, repeated once per
account).

Audit status per account:

| Account | Status | Output file |
|---|---|---|
| noggin (account 1) | **Complete.** All 92 slots on this account (55 already done + 37 finished 2026-07-31 once the CEO re-logged-in past the earlier lockout). | `System_Audits/HRB_System_Performance_Audit_noggin_FINAL.xlsx` |
| noggin2 (account 2) | **Complete.** All 88 slots. | `System_Audits/HRB_System_Performance_Audit_noggin2.xlsx` |
| noggin3 (account 3) | **Complete.** All 81 slots, done entirely in one pass 2026-07-31 (fetch+compute pipeline, no real downloads). | `System_Audits/HRB_System_Performance_Audit_noggin3.xlsx` |
| noggin4 (account 4) | **Complete.** All 93 slots, done entirely in one pass 2026-07-31. | `System_Audits/HRB_System_Performance_Audit_noggin4.xlsx` |
| noggin5 (account 5) | **Complete.** All 68 slots, done 2026-07-31 (interrupted mid-run by a context reset, resumed and finished same day). | `System_Audits/HRB_System_Performance_Audit_noggin5.xlsx` |

**All five accounts are now audited. The system-profitability audit phase of the project is complete.**

**But the per-system audit is not the whole answer — see the overlap
analysis below.** Two caveats now qualify the workbooks above:
1. ~~17 systems' workbook rows no longer matched what their criteria
   return today~~ - **re-audited 2026-08-01** via
   `System_Audits/reaudit_system_changed.py`. All 17 (16 in noggin slots
   1-57, plus noggin3 slot 67) now match their current raw data exactly.
   Biggest correction: noggin slot 53 "NEWTONclaude" (actively worked on),
   Bets 922->234, P/L(BF) 305.75->36.35.
2. Summing per-system P/L massively overstates the portfolio, because
   the same horse is counted once per system that fired on it.

## Cross-account overlap analysis (2026-08-01)

`System_Audits/cross_account_overlap.py`, output in
`System_Audits/cross_account_overlap_report.txt`. Run it after any
re-audit; it self-validates every system against the workbooks first and
refuses to report totals if a mismatch can't be explained.

The question it answers: the per-system audit says "these systems are
profitable", but the BFBM pipeline merges everything into one bet per
horse per race. So what does the *portfolio* actually earn?

- 418 bet-producing systems → 305,468 per-system bet rows → **175,149
  distinct horse+race bets** (1.744x overlap).
- Naive summed P/L(BF) **+30,191** → deduplicated **+11,893**. **60.6%
  of the apparent profit is double-counting.**
- 2026 YTD, the closest thing to a live portfolio (400 systems firing):
  naive +5,383 (7.89% ROI) vs **dedup +206 (0.69% ROI)**.
- 21.3% of distinct bets fire in more than one *account*, so this is not
  an artefact of one account's systems being variations on a theme.
- **Agreement is a signal**: dedup ROI by number of systems firing is
  5.65% (1), 12.05% (3), 28.60% (6-9), 36.03% (10+), while strike rate
  falls — agreement concentrates at longer prices. Soft evidence (one
  author, so not truly independent systems) but consistent across
  windows, and it points at an agreement threshold as the main selection
  lever for the live pipeline.

Key implementation detail: a bet is identified by
`Date|RTime|track|Qualifier`. Verified that this is a clean key — across
all 175,149 distinct bets there is never a conflicting `Odds_Exchange`
or P/L between the systems that fired it, so deduplication is unambiguous.

## System filter extraction — for duplicate/overlap detection (started 2026-08-01)

Follow-up question from the CEO: with ~420 systems spread across 5 accounts
that have become unwieldy to manage by hand, how many are actually similar
or identical to each other under the hood, not just by name? This extracts
the literal compiled HRB filter (`completewheresteps` — a SQL-like criteria
string HRB generates per system, e.g. `horse_age BETWEEN 4 and 13 AND
nh_flat_aw_id IN (1) AND dateyears >=2003`) for every slot in every account,
so a real similarity/duplicate comparison can be run once complete — pulled
from the hidden `completewheresteps` field on the `v4qualifiersexcel.php`
form, reached via the same recall→quals fetch pipeline as the raw TSV
caching below, but stopped one step earlier (no need to submit that form
and download the TSV — much cheaper per slot).

Per CEO instruction, the odds band (already validated per-slot in the audit
workbooks) will be joined onto this data before comparing systems — two
systems can share identical HRB criteria but bet completely different price
ranges, so the criteria string alone isn't the whole picture.

**Status: complete for all 5 accounts** (noggin 92/92, noggin2 88/88,
noggin3 82/82, noggin4 93/93, noggin5 68/68 — 423 systems total). Output in
`System_Audits/filters/noggin{,2,3,4,5}_filters.jsonl`.

### Similarity/duplicate results (2026-08-02)

`System_Audits/filter_similarity_analysis.py`, output in
`System_Audits/filter_similarity_report.txt` and
`System_Audits/filter_similarity_systems.csv`. Compares every system's
normalized criteria set (each filter split into individual `AND` conditions,
the universal `dateyears >=2003` floor dropped since it carries no
discriminating information) plus its validated odds band against every
other system, for exact matches and near-duplicates (Jaccard similarity).

**The portfolio is far less redundant at the criteria level than the bet-
level overlap analysis might suggest**: only 4 exact-duplicate groups (8
systems) and 4 near-duplicate pairs (8 systems) out of 423 — 407 systems
have genuinely distinct criteria+band combinations. The 60%+ bet-level
overlap documented above is a portfolio-construction problem (many
different, legitimate systems converging on the same well-known horses),
not repeated systems under different names.

Two of the four exact duplicates are within a single account (the cheapest
to prune, no cross-account story needed): noggin5 slot 30 = slot 98 ("Ascot
HUNT CUP AW WIN LTO" / "Ascot HUNT CUP Hdgr"), and noggin2 slot 39 = slot 88
("Elliott Gordon Hurdles NH Flat ALL BSPs" / "SS NH Elliott Gordon Hurdles
NH Flat ALL BSPs" — the near-identical names suggest an accidental re-save).
The other two are cross-account: noggin3 slot 23 = noggin5 slot 23 (same
slot number and name too); noggin2 slot 75 = noggin5 slot 31 ("2021
MeehanB(J) 2021" / "TURF 2021").

Two things learned worth keeping for future extraction passes: (1) the
browser's console history buffer accumulates across the whole session
rather than clearing between reads, so a naive "read the console, take the
first match per slot" approach picks up stale duplicates from earlier
accounts — fixed by taking the *last* occurrence of each slot number
instead. (2) A batch that appears to "time out" from the tool's perspective
may still be running in the browser in the background; firing a second
batch on top of it briefly sends two concurrent request streams to HRB —
exactly the pattern that caused account 1's original rate-limit lockout.
Safer pattern: fire each batch as a non-blocking background task
(`(async () => {...})()` without awaiting it at the top level) and poll an
explicit completion flag (`window.__batchN_done`) before starting the next
batch, rather than trusting the tool call's own timeout/success signal.

**Rate limiting is the main operational risk.** Account 1 got locked out
from going too fast the first time round. The working rule since: process
**one system at a time, with a real pause between each** — no
parallel/batched requests to the HRB server.

### Fetching per-bet data via in-page `fetch`, not real downloads

For account 1's remaining 37 slots (2026-07-31), the real click-through
downloads that worked for noggin2 stopped working partway through -
Chrome silently blocks "automatic" file downloads after a couple of
non-interactive ones in a session, with no visible page-level signal
(the block is a native browser UI element, invisible to the page DOM).
Real `computer` clicks on the XLS button and JS `.click()` calls both
went silent with no error and no file.

**Fix: use `fetch()` from within the page instead of a real download
click.** Same recall → Quals flow, but for the XLS step, clone the XLS
form's `FormData` and `fetch(form.action, {method:'POST', body:
new FormData(form)})` — the TSV comes back as the response body,
entirely in-page, no download machinery involved, no blocking. The
odds-band-parse + saved+1-date-filter + BF-commission-formula pipeline
(same logic as `build_noggin2_audit.py`) was ported to JS and run
**in-browser** on the fetched text, returning just the final aggregate
row (few hundred bytes) rather than the full ~150-200KB TSV — avoids
both the download-block issue and the return-value truncation limit
on `javascript_exec` (~1300 chars). Cross-validated against the Python
reference on slot 58's data: identical Bets/Wins/P&L(SP)/P&L(BF).

**Trade-off: no raw TSV cached to disk for account 1's 37 re-audited
slots** (unlike noggin2, where every raw TSV lives in `noggin2_raw/`).
Only the final computed row per slot was kept. If a slot's numbers ever
need re-deriving without hitting HRB again, that option isn't available
for these 37 - would need a fresh fetch.

**How to verify (and fix) a capped slot (CEO-suggested method, 2026-08-01).**
The 10,000-row export cap applies to the full unfiltered history returned
by the XLS/CSV download, before any local date/odds filtering. Rows come
back newest-first, so whether a capped download is actually a problem
depends entirely on whether the *oldest* row in that capped set is
before or after the system's saved date:
- Oldest row before the saved date → the whole "since saved date" window
  is inside the capped download; the figure is complete despite hitting
  the cap.
- Oldest row after the saved date → the download runs out before
  reaching the saved date; the reported bet count is a **floor**, not
  the true figure - some real post-saved-date bets are invisible and
  never had a chance to be filtered in or out.

The check itself is cheap: look at the last row of the capped TSV. The
fix, if needed, is to reduce the row volume returned by the underlying
query so the cap isn't hit (or is hit further back in time):
1. On the **Breakdown** tab, tick **Odds (BFSP)**, Proceed, then select
   the Min/Max radio buttons on the bucket rows that bracket the
   system's true odds band (round **outward** to the nearest bucket
   boundary so the server-side filter is a superset of the true band -
   the precise band still gets re-applied locally against the real
   `Odds_Exchange` value afterward, so a wider server filter costs
   nothing but download volume).
2. Click Go, then Quals, then fetch the XLS/CSV as normal. Check the
   `Bets` total shown on Overview first - if it's already under 10,000
   for the system's entire history, the download can no longer be
   capped regardless of date range.
3. If still capped, check the oldest row's date again. If it's still
   after the saved date (very high-volume system even after odds
   filtering), add a **Date (Year)** category on top of the odds filter,
   covering the years between the saved date and the oldest date the
   first download reached. Fetch that second download, then locally
   merge the two: keep everything from download 1, and from download 2
   keep only rows dated `>= saved+1` and `< the earliest date already
   covered by download 1` (to avoid double-counting the overlap).
4. Systems with **no odds band at all** can't be pre-filtered this way -
   just check the oldest row of the plain unfiltered download directly.

Applied retroactively to noggin5's 16 capped slots (2026-08-01): 15 were
already complete despite hitting the cap (oldest row well before the
saved date in every case - some of these systems have qualifier history
going back to 2005-2013). One, **slot 39** ("HDGR DIFF v2 14.01-80.00",
saved 2021-04-02), was genuinely truncated - even after odds-filtering
the download still only reached back to 2023-06-04, short of the
2021-04-02 saved date. Fixed with the year-split-and-merge method above.
The corrected figure is dramatically different from the original:
Bets 4,549→16,928, Wins 181→687, P/L(BF) +73.70→**+419.14**, ROI(BF)
1.62%→2.48%. This account had 16 capped slots vs. a handful in prior
accounts, likely worth spot-checking noggin/noggin2/noggin3/noggin4's
capped slots the same way at some point, though that hasn't been done.

**Update 2026-08-01: done.** Checked every capped slot across all five
accounts. noggin's one capped slot (82, "MM") is a test slot the CEO
confirmed isn't in use - skipped. noggin2's 13 capped slots were all
verifiable from cached raw TSVs with no live account access needed -
all 13 already complete. noggin3 (slot 51) and noggin4 (slot 97) each
had one genuinely truncated slot, both fixed with the year-split-and-
merge method. **noggin4 slot 97 is the standout finding**: P/L(BF)
flipped sign entirely, from -83.94 (apparently a small loser) to
+516.64 (actually solidly profitable) - a reminder that a system
sitting right around break-even is exactly the case where a truncated
"since saved date" window is most likely to give a wrong verdict, not
just a wrong magnitude.

**Bug found on noggin5 (2026-07-31): TSV columns are double-quoted.**
Each field in the fetched TSV comes back as e.g. `"2"` not `2`. A JS
reimplementation of this pipeline (rebuilt from scratch after a context
reset, since the in-page JS itself isn't persisted anywhere) compared
`Position === '1'` without stripping the quotes first, so no win was
ever detected - the first several slots computed 0 wins each, silently
wrong (P/L(SP) and P/L(BF) both came out as `-1 * bets`, which looks
plausible enough to miss without cross-checking against HRB's own
baseline). Caught by cross-checking slot 1's odds-band-free result
against HRB's own bulk-report baseline figures, which must match
exactly when there's no odds filter - they didn't, until every column
was run through `.replace(/^"|"$/g, '')` before comparison. All slots
computed before the fix (all of them, since it was caught immediately)
were redone. Worth checking for on any future account too.

One slot (82, named just "MM") hit the 10,000-row download cap - the
true bet count since its saved date may be higher than what's captured;
flagged in its Odds Parsing Note column rather than treated as final.

## Selection-quality refinement (2026-08-02)

A chain of follow-up questions, each script building on the last, all
using `cross_account_all_system_bets.csv` (every system-bet row from the
overlap analysis) as the source data. Full detail and headline numbers
for each are in CHANGELOG.md; this section is the map of how they connect.

1. **`system_combination_performance.py`** - which *combinations* of
   systems perform best/worst together (pairs, then triples with a
   large-sample tier). Finding: the best combinations are variations
   within the same proven family (e.g. "4YO STRAIGHTS"), not random
   pairings.
2. **`filtered_agreement_report.py`** - restricts the agreement-count
   analysis to systems with >=100 standalone bets and standalone ROI
   >= -5% (`MIN_BETS`, `MAX_LOSS_PCT`), with the 4 exact-duplicate systems
   from the similarity analysis dropped first so a system saved twice
   can't double-vote (`EXACT_DUPLICATES_TO_DROP`). 220 of 414 systems
   qualify; filtered ROI 9.28% vs 5.63% unfiltered. This filtered universe
   (`load_all_bets()` / `standalone_performance()`) is imported and reused
   by every later script in this section.
3. **`collapsed_agreement_2022_2026_report.py`** - same filtered universe,
   2022 onward, agreement collapsed to single-vs-multi (2+). Multi beats
   single overall (12.69% vs 5.88%), but single was still ahead in 2022
   (20.04% vs 11.64%) - the reversal over time is what the next script
   investigates.
4. **`single_selection_erosion_report.py`** - confirmed the CEO's "stolen
   picks" hypothesis with a specific mechanism: bets promoted out of
   single-selection by a *newer* system return well above bets that
   stayed single, but that promoted-bet ROI itself collapsed after 2024 -
   not because confirming systems got less proven (their age at
   confirmation actually rose), but because the sheer *population* of new
   systems grew ~25x, so "a new system agreed" stopped being a meaningful
   independent second opinion. A separate old+old vs promoted split
   confirmed this is specific to the new-system-confirmation pathway, not
   a general decay of narrowing-by-agreement (old+old confirmation is
   still positive in 2026).
5. **`race_dilution_report.py`** - a second, independent dilution
   mechanism: more systems also means more *different* horses backed in
   the same race (avg 2.14/race in 2022 -> 4.36 in 2026), which is a
   distinct effect from same-horse multi-system agreement. The
   4+-selection-race breakdown by BF odds band (heavy losses at short
   odds, strong gains from ~32.00+ upward) is what prompted the "Value"
   discussion and the next script.
6. **`value_ratio_staking_report.py`** / **`marginal_systems_staking_report.py`**
   - tests a CEO-proposed stake-scaling formula, `stake = min(cap,
   Odds_Exchange / Runners)` (Phil Bull-style: bet more when the price is
   longer relative to field size, i.e. further "from the crowd"). Real
   effect confirmed in the 16-128 odds range specifically (not a clean
   universal law - inverts at the very short and very long extremes, the
   128+ inversion traced to a handful of Betfair's 1000.00-price-ceiling
   wins, not a genuine pattern). Staking backtest: flat 9.28% ROI -> 18.62%
   at cap 5, but drawdown grows roughly as fast as the cap and uncapped
   staking produces single stakes of 250+ points - cap 3-5 is the sane
   range. Tested separately against systems with no query-time odds
   restriction (almost the whole universe, 399/414) and against the 22
   weakest-but-still-qualifying systems (breakeven to -5% ROI): **not a
   reliable rescue for weak systems** - helps some, actively worsens
   others, because it amplifies whatever a system's own odds/ROI
   relationship already is rather than adding independent value. Should
   be applied per-system by inspection, not blanket-applied to "the weak
   ones."

**None of this has been wired into a live pipeline yet** - see the next
section for where BFBM execution actually stands.

## Live execution pipeline - BFBM tips-import (investigated 2026-08-02)

CEO asked how the value-ratio staking formula could actually be
implemented in BFBM, which led to checking whether a live automated
pipeline exists at all, rather than assuming one does.

**Finding: no live pipeline currently exists.** Every strategy configured
in BFBM (`C:\Users\User\AppData\Local\bfbotmanager.com\Bf Bot Manager
V3\`) is an untouched vendor "EXAMPLE - ..." strategy. `log.txt` shows
every tips-import attempt on record dates to 04-06 February 2020 (the
CEO's own early testing), and every one failed - either a file-lock error
(the CSV was open elsewhere) or, for one malformed test file, a
column-mapping error. No import has been retried since.

**But the feature itself is not broken or removed** - it's still
documented in the current manual and the installed version is still
actively running (3.1.30.2023, log active as recently as 30/07/2026). One
of the 2020 test files, `E:\racing\BFBOTManager\from BFBM.csv`, already
has the correct column header the manual documents and, per the log,
never actually reached the parsing stage - only the file-lock error. It's
currently unlocked and references a long-settled 2020 race, making it a
safe, zero-risk candidate to retry the import with.

**How a computed stake would actually reach BFBM**: the "Bet on imported
selections/tips" strategy condition reads the CSV's `Size` column
directly as the stake - no formula engine exists on BFBM's side (no
free-text expression box, and no runner-count variable in any of its
native staking plans), so any formula like the value-ratio one above has
to be computed externally, before export, and written straight into
`Size`. Confirmed via the manual that importing a tip alone can never
place a bet by itself - a bet only happens if a *Started* strategy uses
that staking rule, and none currently is.

**Known limitation - can't patch a stale stake by re-importing.** A
duplicate tip (same selection + same `Provider` name) is silently
dropped, not updated. This matters because field size (`Runners`, the
denominator of the value-ratio formula) can shrink after export if a
different horse in the race is declared a non-runner - and since a
correction can't be pushed via a second import, the only mitigation is
computing/exporting the stake as late as practically possible (after most
declarations are in), plus keeping BFBM's native "removed runner"
tip-filter on as a backstop for the narrower case where the *selection
itself* is scratched (that filter doesn't cover a different runner being
scratched, which is the harder case for this formula).

**Status: waiting on a live re-test.** Next step is retrying `Manage tips
-> Import tips from file` with `from BFBM.csv`, with no strategy started
(so even success can't place a real bet against the already-closed 2020
market), to confirm the 2020 bugs don't recur before any pipeline work
starts on top of this.

## How the audit actually works (HRB mechanics)

This took a full session to reverse-engineer via live browser
exploration (Claude in Chrome) — no prior documentation existed. Worth
preserving in full so it never has to be rediscovered.

### Getting the list of systems and their saved dates

`https://www.horseracebase.com/v4savedsystems.php?userchoicego=1`
("My Performance Report") — set the period dropdown
(`select[name="period"]`) to value `999` ("Performance since saved
date") and submit that form. **One request returns every system on the
account** — slot, name, SAVED date, and baseline (odds-unfiltered)
Bets/Wins/Win%/P-L(SP)/Places/Place%/ROI(SP)/P-L(BF)/ROI(BF)/A-E. This
baseline P-L(BF) is NOT what we want (see below) but the SAVED dates
and slot→name mapping from this one page are exactly what's needed to
drive the rest of the audit, and it costs only one request for the
whole account.

### Getting per-bet history for one system

For a given slot N:

1. On `v4savedsystems.php`, submit the hidden form
   `recallslot=N` → `Recall sN` (POSTs to `v4builder.php`). This loads
   that system's criteria into the session ("You are editing your
   system saved in slot N named '...'").
2. On the resulting `v4builder.php` page, click **Quals**. This shows
   the per-bet qualifier list (200 rows on-page, but see step 3 for the
   full set).
3. That page has an **XLS** button whose form POSTs to
   `v4qualifiersexcel.php` and returns up to **10,000 rows** as
   tab-separated text (mislabelled as `.xls`, actually TSV). Columns:
   `RTime, Date, track, Qualifier, Odds_Numeric, Odds_Exchange,
   Race_Type, Position, Runners, Jockey, Trainer, Age, DaysSinceRun`.
   - `Odds_Numeric` = SP price in "to-1" form (e.g. `18.00` for 18/1 —
     **not** decimal odds; win profit = `Odds_Numeric`, not
     `Odds_Numeric - 1`).
   - `Odds_Exchange` = the actual archived Betfair SP, in true decimal
     odds (e.g. `24.25`); win profit = `Odds_Exchange - 1`.
   - **This download is the system's full history, not filtered to
     "since saved date"** — that filtering has to be done locally in
     Python using the SAVED date from the bulk report above.
   - The best way to drive this from Claude in Chrome:
     `fetch(form.action, {method:'POST', body: new FormData(form)})` —
     do NOT hand-build the FormData, cloning the live form is required
     or the server returns a 1-byte response (see
     `trainerruns-fetch` skill for the same gotcha in a different HRB
     endpoint).
   - Response is ~1-1.5MB of text for a busy system. To get it out of
     the browser context: gzip + base64 in-page
     (`CompressionStream('gzip')`), `console.log` it with start/end
     markers, then `read_console_messages` (large payloads get
     auto-saved to a `tool-results/*.txt` JSON file — decode that file
     in Python rather than trying to inline the payload).

### Odds band parsing (from the system name, not from any UI field)

HRB has no explicit "odds band" field on a saved system — the CEO
encodes it directly into the system's name as free text, e.g.:

- `SS NH CHP LTO 2.01 - 300.00 IRE` → min 2.01, max 300.00
- `IRISH FLAT FMs 10.00-500.00` → min 10.00, max 500.00
- `MidgleyPT 6f-7f` → no odds band (the numbers here are a distance
  range, not a price range — the regex requires decimal-looking values
  ≥ 1.0 either side of the dash to avoid false positives)

Parsing regex: `(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)`, reject if either
side < 1.0. Ambiguous cases (e.g. "10.01 PLUS" with no explicit max, or
a second number in the name whose meaning is unclear) should be
flagged in an `Odds Parsing Note` column rather than guessed — this was
the account-1 convention and should be kept.

Words known so far to precede/follow a genuine-looking number range
that is actually something else (race class, week number, days-since-
last-run, runner counts) and must be excluded even though both sides
are ≥ 1.0:
- preceding: `class`, `week`/`wk` (e.g. noggin3 slot 31 "WEEK 16 - 24
  9.01 - 1000.00" — the regex's first match "16 - 24" is a week-number
  range, not odds; the real band is later in the name)
- following: `dslr`/`dslrs`, `sof`, `claimjock`, `run`/`runs`/`runtr`
  (e.g. noggin3 slot 52 "CHELT FEST IRISH 3-4runTR" — "3-4" is a
  runners-count range, not odds)
- preceding: `n` (noggin4 only — this account's names sometimes carry a
  bare cross-reference code to another slot in the same account, e.g.
  slot 3 "N4-97 0 RUNS HDGR NH COMP 6.01 - 300.00" and slot 81 "...see
  N4-36" — "N4-97"/"N4-36" is not an odds band, the regex's preceding-word
  capture on a bare "N" immediately before the digit catches this)

**Alternate separator**: noggin4 slot 41 "DSLR and 2ndLR 12.0 to 35.0
BSP" spells its odds band with the word "to" instead of a dash. The
regex was extended to accept `-` or `\bto\b` as the range separator
for that account; worth checking for on any future account too.

When adding a new exclusion word, match on the **single word closest**
to the number (not the whole preceding/following text) — and make sure
the regex actually reaches it: leading/trailing whitespace between the
number and its neighboring word breaks a naive `$`/`^` anchor. Use
`([A-Za-z]+)\s*$` for the preceding-word check and
`^\s*([A-Za-z]+)` for the following-word check.

The odds band is applied by filtering the per-bet download to rows
where `Odds_Exchange` (the real archived BFSP) falls within
`[min, max]` — i.e. simulating "would this bet actually have been
placed given the system's own price restriction". This is the whole
reason the per-bet download is needed instead of just trusting HRB's
aggregate report.

### P/L(BF) — a subtlety that cost real time to figure out

HRB's own "P/L(BF)" figure (in both the bulk report and the
individual-system "Stats" table) is **not** the real archived Betfair
SP result. Per HRB's own help page
(`horse-racing-systems.php#bfbacklay`): *"BF_Back — the theoretical
return from backing all selections matching criteria using your
Betfair Backing Estimated Price Settings."* It's a configurable
estimate, not ground truth. Confirmed by direct comparison: on a
system with no odds filter (so the two approaches should agree if
using the same source data), P/L(SP) matched HRB's own figure closely,
but P/L(BF) computed from raw `Odds_Exchange` was wildly different
from HRB's reported figure — until using the **real** archived
`Odds_Exchange` column with the formula agreed with the CEO:

```
win profit = (Odds_Exchange - 1) * 0.95     # 5% Betfair commission on winnings only
loss       = -1                              # unit stake, no commission on losers
```

This is deliberately **not** trying to reproduce HRB's own theoretical
BF figure — it's using the real historical price, which is the more
rigorous and more useful number for deciding whether a system is
actually worth including in the live pipeline.

### "Races" / "Race%" — also not what they first look like

Per HRB's own terminology (same help page): **Races** = the number of
distinct races among the qualifying bets (grouped by Date + RTime +
track — relevant when a system throws up more than one qualifier in
the same race, e.g. dutching-style systems). **Race%** = the percentage
of those distinct races that contained at least one winning qualifier.
This is different from "Places" (each-way place terms), which the
audit does not attempt to reproduce.

## Output format (per CEO spec, 2026-07-31)

One row per system:

```
Slot | Name | Saved | Odds Band | Bets | Wins | Win% | P/L(SP) | Races |
Race% | ROI(SP) | P/L(BF) | ROI(BF) | P/L(BF) 2018 | P/L(BF) 2019 | ...
```

P/L(BF) is broken into **one column per calendar year** (not a single
semicolon-packed string, which is how the original noggin account-1
workbook did it — the CEO asked for separate columns this time).

Each HRB account gets its **own separate output workbook** (not tabs
in one file) — e.g. `HRB_System_Performance_Audit_noggin2.xlsx` — since
the five accounts' systems are unrelated to each other.

## Reusable pipeline script

`System_Audits/build_noggin2_audit.py` — takes a `{slot: (name,
saved_date)}` dict and a folder of `slotN_quals.tsv` raw downloads,
applies the odds-band parse + saved+1 date filter + BF commission
formula, and returns one dict per slot with all the required fields
(including a `P/L(BF)ByYear` dict). Currently hardcodes the 4 test
slots — needs extending to loop over all 88 noggin2 slots (list
already captured from the bulk report during the test) once the CEO
signs off on the test output.

Raw per-bet TSV downloads live in `System_Audits/noggin2_raw/` (one
file per slot processed so far: 4, 28, 58, 69) — kept so the analysis
can be re-run/adjusted without re-hitting the HRB server.
