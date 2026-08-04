# Changelog

All notable work on this project, newest first. See
[PROJECT.md](PROJECT.md) for the full picture — this file is a log of
what happened and when, not a spec.

## 2026-08-04 (imported today's 135 selections - autoload didn't survive a BFBM restart)

- Imported the day's real tips CSV (135 selections) - initially none
  showed a resolved `MarketId`/`EventId` via the Column chooser. A
  transient DNS failure (`api.betfair.com` unresolvable) appeared in
  `log.txt` around the same time but had already cleared itself within
  ~7 minutes - not the actual cause.
- CEO restarted BFBM as a troubleshooting step; still no resolution
  afterward. Checked the Events & Markets screen directly rather than
  guessing further from Manage Tips alone: **it was completely empty -
  no markets loaded at all.** Confirmed the fix is re-triggering market
  loading (not re-importing the tips, which would have done nothing -
  the tips were already correctly imported, there was simply nothing
  for them to resolve against).
- **New operational finding, recorded in the `bfbm-tips-reference`
  skill: autoload does not reliably survive a BFBM restart.** Worth
  checking Events & Markets for an empty list first, before assuming a
  tips/CSV problem, any time resolution fails after restarting BFBM
  mid-session.

## 2026-08-04 (second day's real run - two more data-format bugs found and fixed)

- First real run of `Daily_Pipeline` on a genuinely new day, run in the
  morning (10:25) before racing started - deliberately following the
  operational lesson from 2026-08-03 (run it before the day's racing,
  not mid-afternoon). CEO exported all 5 accounts' qualifiers and this
  time it showed exactly why that lesson matters: **135 selections**
  from today's full day, vs 56 the previous day after most races had
  already gone off.
- **Bug 1 - the `Date` column's format is not consistent day to day.**
  2026-08-03's export used ISO dates (`2026-08-03`); 2026-08-04's used UK
  format (`04/08/2026`, day/month/year). Pandas' default date parser
  assumes month-first for ambiguous slash-separated dates, so it silently
  misread every race as being in April instead of August - making every
  single row look like it had already run, producing **0 selections**
  on the first attempt. Fixed by passing `dayfirst=True` to
  `pd.to_datetime` in `ingest_hrb.py` - a no-op for the unambiguous ISO
  case, correct for the UK-format case.
- **Bug 2 - `slot` got read as a float, not an integer**, on this day's
  files (`1.0` instead of `1`) - almost certainly because a blank/NaN
  slot value somewhere in one of the 5 files forced pandas to infer
  float64 for that whole column. This silently broke every `sys_key`
  join against the quality-filtered system list and the odds-band
  lookup (`noggin2:1.0` matches nothing), excluding all 336 remaining
  rows as "not quality-filtered" even though they should have qualified.
  Fixed by explicitly converting `slot` via
  `pd.to_numeric(...).astype("Int64").astype(str)` before building
  `sys_key`, regardless of how pandas happened to infer the column's
  dtype that day.
- **Lesson for this pipeline going forward: HRB's own export format is
  not stable day to day** (at minimum, date format and slot dtype have
  both varied within two days of testing) - `ingest_hrb.py` needs to
  stay defensive about exact formatting, not just column names.

## 2026-08-03 (first real BFBM import attempt - found and fixed a whole-file-breaking bug)

- CEO tried importing the real 86-selection pipeline output into BFBM for
  the first time (only a few days left on the BFBM trial, so moved
  straight to a real test rather than more synthetic ones). Result:
  **"Number of Tips Imported: 0"** - not silent/ambiguous like every
  earlier test, an explicit zero.
- Diagnosed via a systematic bisection of small hand-built CSVs (isolate
  one variable at a time: integer vs decimal `Size`, blank vs populated
  `MinPrice`/`MaxPrice`, then every pairwise/triple combination of the
  extra columns) rather than guessing. Root cause, confirmed with a single
  isolated row: **a blank `MinPrice`/`MaxPrice` value causes BFBM's
  importer to reject the ENTIRE file, not just that row** - even one
  lone row with a blank band, on its own, imports as 0. The original
  86-row file had 4 genuinely-unrestricted selections written with blank
  bands, which poisoned the whole file.
- **Fixed in `write_bfbm_csv.py`**: never write an empty price field.
  Genuinely-unrestricted selections now get Betfair's actual tradable
  range (`1.01`-`1000.0`, new `config.UNRESTRICTED_MIN_PRICE`/
  `UNRESTRICTED_MAX_PRICE`) instead of a blank - functionally equivalent
  to "no restriction" but a real number BFBM's parser accepts.
- Re-ran the pipeline (by then down to 56 eligible selections - more
  races had gone off in the time spent diagnosing, see below) and
  **imported 56 of 56 successfully** - confirmed via BFBM's own count,
  not just "no error."
- Also confirms something worth remembering operationally: the CEO
  reasonably asked why the count dropped from 86 to 56 - purely because
  real time passed between generating the file and importing it, and
  more races finished in that window (the pipeline only ever includes
  races still ahead of "now" at run time). **This pipeline needs to run
  close to when you actually intend to import, ideally before the day's
  racing starts** - running it mid-afternoon understates the day's real
  opportunity set.
- Cleared the many diagnostic test tips from Manage Tips afterward (tick
  each row's checkbox -> Delete selected, or delete-all if clearing
  everything - no ctrl/shift multi-select on this grid, per the manual).
- **Checked resolution at real scale (not just 1-2 synthetic tips):
  all 56 imported selections show populated `MarketId`/`EventId`** via
  the Column chooser - every one resolved to a real live market by name
  alone, zero unmatched. This is the first end-to-end validation of the
  whole chain (HRB qualifiers -> Daily_Pipeline -> BFBM CSV -> import ->
  name-based market resolution) at real scale. No strategy has been
  Started at any point - tips sit in Manage Tips only, nothing has been
  bet on.

## 2026-08-03 (first real bet placed and settled - in Simulation Mode - plus a real config gotcha found)

- CEO's BFBM trial has limited days left, so moved straight to testing a
  real bet via the vendor-shipped `EXAMPLE - Bet on all imported tips`
  strategy (BFBM's own Simulation Mode confirmed on, so no real money
  at risk). Set its `TipsCondition` Provider filter to `BFBM_HRB_v1` and
  started it.
- **5 bets placed early on, all with `sizeMatched: 0`** (per `log.txt`),
  then nothing for over an hour despite eligible races (Windsor 18:00)
  passing with no bet fired. Looked like something had broken.
- **Root cause, found by diffing BFBM's own pre-today strategy backup
  (`strategies_backup/2026-08-02_multiple_strategies_conditions.gz`)
  against the live config, not by guessing**: the vendor default for
  this strategy's `MinMaxSelectionPriceCondition` is **`1.01 - 20`, with
  `UseCustomPriceRange=false`** - silently rejecting any selection
  trading above 20, regardless of the tip's own `MinPrice`/`MaxPrice`.
  Since most of this project's systems have odds bands well above 20
  (many to 65-1000), this alone explains why only a handful of the 56
  real selections could ever have fired - unrelated to the Provider
  field or "time to bet" setting the CEO had also been adjusting while
  troubleshooting.
- **CEO's own fix (widening it to `MinPrice=1.01, MaxPrice=1000,
  UseCustomPriceRange=true`) was correct, not a mistake** - confirmed by
  a real result: `Star Bayside Boy` (band 9.01-30, crossing the old
  20 cutoff) subsequently bet and settled as a winner, virtual profit
  ~£21 in Simulation Mode. **First full real-cycle validation of the
  whole pipeline**: HRB qualifiers -> Daily_Pipeline -> BFBM CSV ->
  import -> name resolution -> real bet -> matched -> race run ->
  settled -> won.
- Noted for later: the Provider filter is currently blank (not
  restricting to `BFBM_HRB_v1` specifically right now) - harmless today
  since nothing else in Manage Tips shares real horse names with the
  pipeline's tips, but worth resetting once the CEO is confident in the
  setup. The strategy's other untouched vendor defaults (Overround
  100-115%/85-100%, Back/Lay ratio max 15%) still apply and haven't been
  specifically validated against this project's real data yet.
- **Confirmed this is a documented gotcha, not an obscure one**: manual
  p.82 states outright "The Min/Max selection price tells the bot not to
  bet on any odds over 20 in its default setting. So if your tips
  include high odds events, then it may need changing." p.201 repeats
  the same warning for the Proform-tips variant of this example.
- **Two separate price gates exist, and they overlap** - per manual
  §14.2.13 (p.457-458), `MinMaxSelectionPriceCondition`'s "use custom
  price range" mode reads from the Markets/Selections grid's manually-
  entered price (the "My Selections" feature), NOT the imported CSV's
  MinPrice/MaxPrice. Separately, the manual states the `TipsCondition`
  staking rule already automatically enforces each tip's own
  MinPrice/MaxPrice on its own, independent of this other condition. So
  the cleanest setup is to leave `MinMaxSelectionPriceCondition` wide
  open (`1.01`-`1000`, effectively disabled) and let each tip's own CSV
  price band - enforced separately by `TipsCondition` - be the real,
  authoritative constraint. This is exactly what the CEO's fix achieved,
  confirmed correct by the manual rather than just by the result.

## 2026-08-03 (two real bugs caught during CEO's spot-check of the first Daily_Pipeline run)

- **Country-suffix decision reversed - this entry's own earlier claim
  today was wrong.** CEO reported not seeing country suffixes like
  `(IRE)` anywhere in Betfair or BFBM while spot-checking the first run's
  output - directly contradicting the assumption made a few hours
  earlier (below) that HRB's `(IRE)`/`(FR)`/etc. suffixes were genuinely
  part of Betfair's selection names. Verified the fix on real examples
  from today's data (`Arctic Flame (IRE)` -> `Arctic Flame`, `Emiza (FR)`
  -> `Emiza`, `Venosa (USA)` -> `Venosa`) before trusting it. Implemented
  proper stripping in `normalize.py` (the config flag existed but had no
  actual code behind it - it was a no-op) and flipped
  `config.STRIP_COUNTRY_SUFFIX` to `True`. Re-ran the full 5-account
  pipeline: every one of 86 final selections now shows a plain name with
  no suffix.
- **Fixed a reporting bug that made the funnel look broken.** The
  report's "qualifier rows read" counts were actually being counted
  *after* filtering (out-of-scope Multicuts and already-run races both
  already removed), not before - which is why the first run's numbers
  looked inconsistent (278 shown as "read" but 248 excluded as "already
  run" alone, which is impossible). True raw counts are much higher -
  257/96/53/70/130 across the 5 accounts, 606 total. Fixed by having
  `ingest_hrb.load_today()` capture per-account counts before any
  filtering and return them alongside the exclusions, instead of
  counting the already-filtered DataFrame after the fact.
- Both bugs were caught specifically *because* the CEO did the manual
  spot-check the original spec calls for before trusting any output -
  exactly the reason that step exists.

## 2026-08-03 (built Daily_Pipeline - the first real HRB -> BFBM tips CSV pipeline)

- Built `Daily_Pipeline/` per Phase 1 of `claude_code_bfbm_pipeline_prompt.md`
  (HRB only, Racing API deferred): `ingest_hrb.py`, `normalize.py`,
  `quality_filter.py`, `consolidate.py`, `write_bfbm_csv.py`, `report.py`,
  `run_pipeline.py`, `config.py`. Full rationale in PROJECT.md's new
  "Daily_Pipeline" section.
- Got a real sample HRB bulk-qualifier export from the CEO
  (`n_qualifiers_2026-08-03.csv`, the `noggin` account) - confirmed its
  schema empirically rather than guessing, and learned two things that
  shaped the design: `horse_name` already carries breeding-country
  suffixes like `(IRE)` that should NOT be stripped (unlike the
  cloth-number prefix, confirmed unnecessary yesterday), and the file
  mixes already-run and still-to-come races for the day, so eligibility
  is decided by comparing each row's race time against wall-clock now
  rather than trusting the `placing` column.
- Also found `StorageType = "My Multicuts"` rows in that export - a
  different HRB mechanism (slot always `0`) never covered by this
  project's system audit - excluded from v1 and reported as out-of-scope
  rather than forced through the quality gate.
- CEO's filename convention for the 5 daily exports: `n_qualifiers_DATE.csv`
  / `n2_..` / `n3_..` / `n4_..` / `n5_..` (see
  `config.FILENAME_PREFIX_TO_ACCOUNT`).
- Stake sizing decided for v1: flat unit stake, gated only by system
  quality (`filtered_agreement_qualifying_systems.csv`) - explicitly NOT
  agreement-count scaling or the value-ratio formula yet, both deferred
  to v2 pending live validation.
- Ran the full pipeline end-to-end (dry-run) against the real sample:
  137 qualifier rows in, 56 final selections, correctly formatted output
  CSV. Caught and fixed a real bug during this - pandas coerces a mixed
  None/float column to `NaN`, so the original `is None` check for "no
  odds band" missed it and leaked the literal string `"nan"` into
  `MinPrice`/`MaxPrice`; fixed to use `pd.isna()`. Also verified the
  safety rails actually work, not just exist: deliberately lowered the
  daily stake cap and confirmed the pipeline refuses to write rather than
  truncating, and confirmed re-running for the same date refuses to
  overwrite the existing output.
- **Not yet tested**: the other 4 accounts' real exports (only `noggin`'s
  sample was available today), and a real `--live` import into BFBM.
- `.gitignore` extended to exclude `Daily_Pipeline/input/*.csv`,
  `staging/*`, `live_output/*` (kept as empty dirs via `.gitkeep`) - the
  daily exports and generated tips/reports are working data, not source.

## 2026-08-02 (BFBM live-execution pipeline investigated - dormant, not broken)

- CEO asked how the value-ratio staking formula (below) could actually be
  implemented in BFBM, which surfaced a bigger question: is there even a
  live automated pipeline running today? Investigated the actual BFBM
  install (`C:\Users\User\AppData\Local\bfbotmanager.com\Bf Bot Manager
  V3\`) and its manuals rather than assuming.
- **Finding: no live pipeline exists.** Every strategy currently
  configured in BFBM is an untouched vendor "EXAMPLE - ..." strategy.
  `log.txt` shows every `ImportTips`/`ReadTips` event on record dates to
  04-06 February 2020, and every one failed - either a file-lock
  `IOException` (the CSV was open in another program) or, for
  `test1.csv` specifically, a `CsvReaderException: No properties are
  mapped for type 'SelectionCSVData'` (that file's header,
  `Provider,SelectionName`, is missing the columns BFBM's importer
  expects). CEO confirmed this was their own testing at the time.
- **Important distinction: dormant, not removed or broken.** The
  tips-import feature itself is still documented in the current manual
  and the installed version (3.1.30.2023, log shows it running as
  recently as 30/07/2026). `E:\racing\BFBOTManager\from BFBM.csv` (one of
  the two 2020 test files) already has the exact column header the
  manual documents (`Provider, Handicap, SelectionId, MarketId, EventId,
  SelectionName, MarketName, EventName, MarketType, StartTime, BetType,
  Size, Points, Price, MinPrice, MaxPrice, BSP`) and, per the log, never
  actually reached the column-parsing stage - it only ever hit the file
  lock error. It's currently unlocked and referencing a long-settled 2020
  race, so it's a safe candidate to retry the import with, unchanged.
- **Confirmed mechanism for feeding a computed stake in**: BFBM's "Bet on
  imported selections/tips" strategy condition reads the CSV's `Size`
  column directly as the stake (no formula engine needed on BFBM's side -
  the computation has to happen externally, before export). Confirmed via
  the manual that importing a tip alone can never place a bet by itself -
  only a *Started* strategy using that staking rule can, and none is
  currently started.
- **Confirmed limitation: can't patch a stale stake by re-importing.**
  Per the manual, a duplicate tip (same selection + same Provider name) is
  silently dropped, not updated - so "recompute the stake later and
  re-upload" does not work as a way to react to a non-runner declared
  after export. The practical implication (raised by the CEO): field size
  can shrink between export and race-off, making a value-ratio stake
  computed too early stale. Since it can't be corrected after the fact,
  the mitigation has to be timing - compute and export as close to race
  time as practical (after most declarations are in), and keep BFBM's
  native "removed runner" tip-filter switched on as a backstop for the
  case where the selection itself is scratched (that filter doesn't
  address a *different* runner being scratched, which is the harder case).
- **Update 2026-08-03: re-test succeeded, then both remaining open
  questions resolved.** CEO re-imported `from BFBM.csv` with no strategy
  started; all 6 tips appeared correctly - confirms the 2020 failure
  really was just that occasion's file-lock issue, not a broken feature.
  Followed up with the manual's own resolution method (Export "My S."
  from a live market) - confirmed `MarketType=WIN` for certain, though
  that export always uses real Betfair IDs and never exercises
  `SelectionName`. A first name-only test ("Palace Legacy", no IDs) was
  confounded by the race being the next day, outside autoload's
  "today's card" scope. **A clean redo against a same-day race ("All
  Good", Ripon 14:54) confirmed a plain selection name with no
  cloth-number prefix is enough for BFBM to match a tip correctly** -
  verified via the Manage Tips grid's Column chooser (`Start Time` showed
  the exact right race). Also learned tip resolution is a periodic
  rescan, not instant on import - a tip with no `MarketId`/`EventId`
  right after import isn't necessarily a failed match, just not yet
  rescanned. Along the way, found the Manage Tips form can open behind
  other windows (looks like a freeze), defaults to only 3 visible columns
  (`Chance` reads 0 regardless of match status - not a useful signal),
  and has an undocumented-but-working right-click Column chooser for
  `MarketId`/`EventId`/`Start Time`. **All open questions in the
  `bfbm-tips-reference` skill are now resolved** - full detail there.

## 2026-08-02 (value-ratio staking formula tested - odds/field-size based stake scaling)

- CEO proposed a stake-sizing theory: in an N-runner race, the 'fair'
  price under an equal-chance assumption is N, so a selection's own price
  relative to that baseline (`value_ratio = Odds_Exchange / Runners`)
  indicates how far the market has moved it from the crowd - a Phil
  Bull-style "bet more when the signal is stronger" idea, staking
  `min(cap, value_ratio)`. Built `System_Audits/value_ratio_staking_report.py`
  to test it on the quality-filtered universe (systems with >=100
  standalone bets and standalone ROI >= -5%, exact duplicates dropped -
  same filter as `filtered_agreement_report.py`).
- **Ratio bands show a strong pattern** (-3.94% ROI at ratio <0.5, up to
  63.63% at ratio 8.0+), but average field size is nearly flat across
  every band (~11 runners) in this dataset - so on its own this mostly
  re-describes the already-known raw-odds effect, not clear evidence
  field size adds anything new.
- **The real test - does field size add signal beyond raw odds alone?
  Mixed.** Splitting bets within the same odds band at the median ratio:
  in the 16-128 odds range the theory holds clearly (e.g. at 64-128 odds,
  small-field bets returned 47.6% vs big-field 29.2%), but it's flat/
  reversed at the short end (2-8 odds) and inverts hard at the very long
  end (128+, where big-field bets returned 119.6% vs small-field's
  21.0%).
- **Narrowed in on the 128+ inversion (per CEO request) - it's a
  small-sample artifact, not a real effect.** Only ~50 winners exist
  across both halves of that band. The "small field" half's advantage
  comes almost entirely from 3 bets that won at exactly 1000.00 (Betfair's
  maximum tradable price) - those three alone account for ~63% of that
  half's total profit. Whichever half happens to catch a rare
  capped-price winner looks dramatically better purely by chance; not
  reliable evidence either way at this extreme.
- **Staking backtest**: flat 1-point staking on this universe is 9.28%
  ROI; scaling stake by the ratio raises this monotonically with the cap
  (cap 3: 14.94%, cap 5: 18.62%, cap 10: 24.68%, uncapped: 63.52%), but
  drawdown grows roughly as fast as the cap, and uncapped produces a
  250-point single stake on one bet - the exact bank-breaking risk the
  CEO flagged up front. Cap 3-5 looks like the sane practical range.
  Year-by-year (cap 5), the scaled approach beats flat staking in every
  year with a real sample (2016-2026), including through the recent
  erosion years - not a fluke of one good year.
- **Second test (per CEO request): does the formula rescue weak/marginal
  systems?** Built `System_Audits/marginal_systems_staking_report.py`.
  Grepped every system's extracted filter for the `odds_workout` field to
  find systems with no query-time odds restriction at all (399 of 414 -
  confirmed almost the whole universe, not a distinguishing group on its
  own), and separately isolated the 22 systems with >=100 standalone bets
  sitting at breakeven-to-losing-5% ROI (the weakest performers that
  still clear the quality filter). **Result: not a reliable rescue.**
  Aggregate ROI for the 22 weak systems barely crosses into positive at
  cap 5 (-1.36% flat -> +0.13%) and gets worse again at cap 8 (-0.49%).
  Individually it's a genuine mixed bag: 9 of 22 flip from a loss to a
  profit (a couple dramatically), but 13 got worse, several much worse
  (e.g. one system went from -2.21% to -19.60%). Conclusion: the formula
  amplifies whatever a system's own odds/ROI relationship already is - it
  helps systems whose edge sits at long prices and actively hurts systems
  whose weakness is concentrated there, so it should be applied per-system
  by inspection, not blanket-applied to "the weak ones" as a group.
- Outputs: `value_ratio_by_band.csv`, `value_ratio_vs_odds_alone.csv`,
  `value_ratio_staking_backtest.csv`, `value_ratio_staking_by_year.csv`,
  `marginal_systems_staking_summary.csv`, `marginal_systems_staking_detail.csv`.

## 2026-08-02 (race-level dilution - more different horses backed per race)

- Follow-up to the single-selection erosion finding: CEO asked whether
  part of the decline could simply be more systems -> more *different*
  horses backed in the same race -> less profit per winning bet, distinct
  from the same-horse-multiple-systems-agreeing question already covered.
  Built `System_Audits/race_dilution_report.py` (groups by race - Date +
  RTime + track - rather than by horse; every figure still uses one stake
  per distinct horse, exactly as elsewhere).
- **Confirmed, and it's a real, separate mechanism.** Average distinct
  horses backed per race rose from 2.14 (2022) to 4.36 (2026). Races with
  6+ distinct horses backed were 14% of stake volume at +8.09% ROI in
  2022, but 52% of stake volume at -2.33% ROI by 2026.
- **P/L breakdown for 4+-selection races** (CEO-specified threshold), by
  number of runners and by BF odds band: 93,481 bets, 4.96% ROI overall.
  Sweet spot by field size is 12-14 runners (13.31%) and 15-17 (9.69%);
  losers are 2-5 runners (-1.31%) and 21+ (-3.17%). By odds band: losses
  at 2.01-4.00 (-6.54%) and 4.01-8.00 (-1.56%); strong gains from
  32.01-64.00 upward (11.30%, 18.69%, 17.42%) - this odds-band pattern is
  what prompted the follow-up "Value" research and the value-ratio
  staking formula above.
- Outputs: `race_dilution_by_year.csv`, `race_dilution_4plus_by_runners.csv`,
  `race_dilution_4plus_by_odds_band.csv`.

## 2026-08-02 (single-selection erosion - testing the "stolen picks" hypothesis)

- CEO's hypothesis, after seeing single-selection ROI decline over time:
  has building more systems around what already works effectively
  "stolen" the successful selections from the single-selection category?
  Built `System_Audits/single_selection_erosion_report.py` on the same
  quality-filtered universe, with a fixed early/new system split
  (`EARLY_CUTOFF = 2021-12-31`).
- **Confirmed, with a specific mechanism, not just "unproven new ideas
  don't pan out."** Bets that started as an early-system single selection
  and were later "promoted" (confirmed by a newer system) return 10.32%
  ROI (13,015 bets) vs 4.91% for bets that stayed single (39,082 bets).
  Promotion rate climbed from 3.83% (2022) to 47.65% (2026) of early
  singles, while stayed-single ROI collapsed from 22.80% to -9.89% over
  the same period.
- **Unpacked why promoted-bet ROI itself then collapsed after 2024**, via
  two competing explanations: (A) newer/less-tested confirming systems
  getting worse over time - ruled out, confirmer age at the moment of
  confirming actually *rose* (76 days in 2022 to 300+ by 2024-26); (B) the
  sheer population of new systems growing so large that "confirmed" has
  stopped meaning much - confirmed: average new confirmers per early-single
  bet grew ~25x (0.042 in 2022 to 1.055 in 2026), so by 2026 at least one
  new system firing on any given horse is close to guaranteed regardless
  of genuine merit.
- **Follow-up: is this a broad decay of "narrowing by confirmation", or
  specific to new systems doing the confirming?** Added an old+old (both
  confirming systems early, early_count>=2) vs promoted (a new system
  doing the confirming) comparison by year. Old+old agreement shows no
  real trend and is still positive in 2026 (4.28% ROI); the collapse is
  concentrated specifically in the promoted pathway (21.32% in 2022 down
  to -3.19% in 2026). **Conclusion: not a general decay of narrowing by
  agreement - specific to the pathway where a newly-created system does
  the confirming.**
- Practical implication discussed: deleting all systems created after
  2024 was rejected (would gut the best-performing family along with the
  weak ones); recommended instead treating new-system confirmation as a
  weaker signal than old-system confirmation, consistent with the old+old
  vs promoted split above.
- Outputs: `single_selection_erosion_categories.csv`,
  `single_selection_erosion_by_year.csv`,
  `single_selection_erosion_old_vs_promoted.csv`.

## 2026-08-02 (collapsed single- vs multi-selection P/L, 2022-2026)

- Follow-up to the filtered agreement-count report: CEO asked for the
  same quality-filtered universe with every multi-selection (2+ systems
  agreeing) collapsed into one row, restricted to 2022-01-01 onward.
  Built `System_Audits/collapsed_agreement_2022_2026_report.py`.
- **Overall: single 5.88% ROI vs multi 12.69%.** Year-by-year shows 2022
  as the only year single selections beat multi (20.04% vs 11.64%); by
  2026 single is -0.46% while multi is 10.86% - the erosion pattern
  investigated in depth in the next entry.
- Output: `collapsed_agreement_2022_2026.csv`.

## 2026-08-02 (quality-filtered agreement-count P/L report)

- Extends the overlap analysis's "does agreement predict winners"
  question to a filtered universe: only systems with >=100 standalone
  bets and standalone ROI >= -5% are allowed to vote (exact-duplicate
  systems from the similarity analysis dropped first, per explicit CEO
  instruction, so a system saved twice doesn't double-vote). Built
  `System_Audits/filtered_agreement_report.py`.
- **220 of 414 systems qualify.** Filtered universe ROI is 9.28% vs 5.63%
  unfiltered/naive - filtering out unproven or losing systems from the
  agreement count materially improves the picture even before any other
  refinement.
- Also independently re-verified (CEO asked directly whether odds
  filtering was actually being applied to these numbers, not just
  assumed): `System_Audits/verify_odds_band_applied.py` rebuilds the
  odds-band lookup from the audit workbooks directly and checks every row
  against its own system's stated band. **0 violations** across 305,468
  rows.
- Outputs: `filtered_agreement_qualifying_systems.csv`,
  `filtered_agreement_by_count.csv`.

## 2026-08-02 (system combination performance - pairs and triples)

- CEO asked which *combinations* of systems have performed best/worst
  together, not just individual systems or raw agreement-count. Built
  `System_Audits/system_combination_performance.py` - computes
  pairwise and triple-wise co-fired-bet performance
  (`MIN_SAMPLE = 20`, `LARGE_SAMPLE = 300` for a separate high-confidence
  tier, added for triples per CEO follow-up request).
- Best large-sample pair: `noggin3:49 + noggin3:90` (the "4YO STRAIGHTS"
  family), 3,242 co-fired bets, 53.35% ROI. Best large-sample triples
  cluster in the "HDGRdiff class6-7" and "NH CHP LTO" families - i.e. the
  best combinations aren't random pairings, they're variations within the
  same proven family reinforcing each other.
- Output: `system_combination_report.txt`.

## 2026-08-02 (verified odds-band filtering in the combination/agreement reports)

- CEO asked, after the combination-performance and filtered-agreement
  reports, whether any odds filtering had actually been applied to those
  numbers. Confirmed yes, both by re-reading the code and by an
  independent check: `System_Audits/verify_odds_band_applied.py` rebuilds
  the odds-band lookup straight from the audit workbooks and checks every
  row of `cross_account_all_system_bets.csv` (the file every combination
  and agreement report is built from) against its own system's stated
  band directly, rather than trusting `cross_account_overlap.py`'s own
  filtering logic.
- **Result: 0 violations.** 183,976 of 305,468 rows belong to a system
  with a stated odds band, and every one of them falls inside it. The
  remaining 121,492 rows belong to systems whose name genuinely carries
  no odds band ("none" - unrestricted by design), which is correct
  behaviour, not a gap.
- Output: `System_Audits/verify_odds_band_applied_report.txt`.

## 2026-08-02 (system filter extraction complete + similarity analysis)

- Finished noggin4 (93/93 slots) — filter extraction is now complete for all
  five accounts, 423 systems total.
- Built `System_Audits/filter_similarity_analysis.py` (output in
  `filter_similarity_report.txt`): joins each system's HRB criteria with
  its validated odds band, normalizes each filter into a set of individual
  conditions (dropping the universal `dateyears >=2003` floor, which
  carries no discriminating information), then compares every system
  against every other for exact matches and near-duplicates (Jaccard
  similarity, same odds band).
- **Result: the portfolio is much less redundant at the criteria level
  than the overlap analysis might have suggested.** Only 4 exact-duplicate
  groups (8 systems) and 4 near-duplicate pairs (8 systems) out of 423 —
  407 systems have genuinely distinct criteria+band combinations. The
  60%+ bet-level overlap found earlier is a portfolio-construction
  problem (many different, legitimate systems converging on the same
  well-known horses), not a sign the CEO built the same system over and
  over under different names.
- **Two of the four exact duplicates are within a single account** — the
  same criteria and odds band saved twice under different names, with no
  cross-account explanation needed: noggin5 slot 30 "Ascot HUNT CUP AW WIN
  LTO" = slot 98 "Ascot HUNT CUP Hdgr"; noggin2 slot 39 "Elliott Gordon
  Hurdles NH Flat ALL BSPs" = slot 88 "SS NH Elliott Gordon Hurdles NH
  Flat ALL BSPs" (near-identical name too — almost certainly an
  accidental re-save). These are the cheapest ones to prune.
- The other two exact duplicates are cross-account: noggin3 slot 23 = 
  noggin5 slot 23 (same slot number, same name, same criteria — likely
  built once and knowingly copied to a second account); noggin2 slot 75
  "2021 MeehanB 2021" = noggin5 slot 31 "2021 MeehanBJ TURF 2021" (near-
  identical name, one extra space difference aside).
- Output: `filter_similarity_systems.csv` (all 423 systems with their
  account, slot, name, odds band, and P/L, for building a prune list).

## 2026-08-01 (system filter extraction started - for duplicate/overlap detection)

- CEO asked a follow-up to the overlap analysis: with ~420 systems across 5
  unwieldy accounts, how many are actually similar or identical to each
  other under the hood, not just by name? Started extracting the literal
  compiled HRB filter (`completewheresteps`, a SQL-like criteria string,
  e.g. `horse_age BETWEEN 4 and 13 AND nh_flat_aw_id IN (1) AND dateyears
  >=2003`) for every slot in every account, to run a real similarity/
  duplicate analysis once complete. Per CEO instruction, will join this
  against each slot's already-validated odds band before comparing systems
  - two systems can share identical selection criteria but bet completely
  different price ranges.
- Reused the recall→quals fetch pipeline from the raw-TSV-caching phase,
  but stopped one step earlier (read the `completewheresteps` hidden field
  off the `v4qualifiersexcel.php` form instead of submitting it) - much
  cheaper per slot since it skips the actual TSV download.
- **4 of 5 accounts done**: noggin5 (68/68), noggin (92/92), noggin2
  (88/88), noggin3 (82/82 - the 81 originally audited plus one new slot,
  48 "ss 351 D SOF Mv1", added since the audit). noggin4 (93 slots)
  deferred to the next session per CEO instruction.
- Output: `System_Audits/filters/noggin{,2,3,5}_filters.jsonl`. Full
  writeup and resume instructions in
  `C:\Users\User\Desktop\ClaudeTO\FILTER_EXTRACTION_PROGRESS.md`.
- Found and worked around a browser console quirk: the console history
  buffer accumulates across the whole session rather than clearing between
  read calls, so early reads returned stale duplicate matches from earlier
  accounts. Fixed by extracting "last occurrence wins" for each slot number
  rather than trusting the first match - verified correct against several
  slots whose names are already documented elsewhere in this file (e.g.
  noggin3 slot 51 "351 D SOF M", noggin3 slot 86 "3YO UP CLASS", noggin2
  slot 96 "YORK MAY MEETING 240 - 300 dslr").
- Also hit a real concurrency risk worth flagging: a batch that appeared to
  "time out" from the tool's perspective was actually still running in the
  browser in the background, and a second batch fired on top of it for
  about a minute before this was noticed - two request streams briefly hit
  HRB at once, which is exactly the pattern that caused account 1's
  rate-limit lockout earlier in the project. No errors resulted this time,
  but the approach was changed afterward to fire each batch as a
  non-blocking background task and explicitly poll a completion flag before
  starting the next one, rather than trusting the tool call's own
  success/timeout signal.

## 2026-08-01 (re-audited the 17 system-changed slots)

- Re-audited the 17 systems the overlap analysis flagged as
  `system-changed` (not explainable by ordinary daily-qualifier drift):
  16 in noggin slots 1-57, plus noggin3 slot 67. New script
  `System_Audits/reaudit_system_changed.py` recomputes each from the
  already-cached fresh raw TSVs, reusing the Odds Band already validated
  in the workbook (not re-parsed from the name) and the same saved+1 /
  BF-commission formula as every other script in this project, then
  updates just those rows in place in `HRB_System_Performance_Audit_
  noggin_FINAL.xlsx` and `HRB_System_Performance_Audit_noggin3.xlsx`.
- Both workbooks were open in Excel and locked the first attempt; CEO
  closed them and the write succeeded. Verified before finishing: row
  counts unchanged (92 and 81) and every untouched row byte-identical to
  the pre-edit backup - only the 17 targeted rows changed.
- Biggest correction: **noggin slot 53 "NEWTONclaude"** (saved
  2026-07-05, actively worked on) Bets 922->234, P/L(BF) 305.75->36.35.
  Smallest: noggin slot 6, Bets 271->290 (this one gained bets - a genuine
  criteria change, not just narrowing).
- Re-ran the full cross-account validation afterward: all 17 now match
  their raw data exactly (321/421 exact matches, up from 304), and every
  remaining mismatch is accounted for by drift or the 3 known truncated
  slots - no `UNEXPLAINED` bucket.
- **The portfolio overlap conclusions from the prior entry are
  unchanged** - `cross_account_overlap.py`'s Steps 2 onward were always
  computed from the raw per-bet TSVs directly, never from the workbooks'
  summary figures, so re-auditing the workbooks doesn't move the 60.6%
  duplication / +11,893 dedup P/L headline at all. Only Step 1
  (validation) and the two workbooks themselves needed fixing.
- Backups of both workbooks before the edit kept as `*.bak_pre_reaudit`
  in `System_Audits/`.

## 2026-08-01 (cross-account overlap analysis - the audit's punchline)

- Built `System_Audits/cross_account_overlap.py`, extending the old
  single-account `overlap_analysis_noggin2.py` to all five accounts now
  that every account's raw per-bet data is cached. Full output saved to
  `System_Audits/cross_account_overlap_report.txt`.
- **Headline: 60.6% of the portfolio's apparent profit is the same wins
  counted more than once.** Pooling all 418 bet-producing systems gives
  305,468 per-system bet rows but only **175,149 distinct horse+race
  bets** (1.744x overlap - 42.7% of rows are duplicates). Naive summed
  P/L(BF) +30,191 collapses to **+11,893 deduplicated**.
- **The recent picture is far worse than the all-time one.** Restricting
  to 2026 year-to-date (400 systems firing, i.e. close to a real live
  portfolio): naive +5,383 at 7.89% ROI vs **dedup +206 at 0.69% ROI** -
  96.2% of this year's apparent profit is duplication. Last 12 months:
  +9,546 / 9.07% naive vs **+1,748 / 3.57% dedup**. The divergence grows
  over time simply because more systems exist now, so more of them fire
  on the same horses.
- Overlap is genuinely cross-account, not just within-account: **21.3%
  of distinct bets are fired by systems in more than one account**
  (15.5% by two accounts, 4.3% by three, 1.4% by four or five). Every
  account pair shares 14-27% of the smaller account's bets. noggin4 is
  both the largest contributor (119,836 rows) and the most internally
  redundant (1.563x within-account overlap).
- **Agreement looks like a real signal, not just waste.** Deduplicated
  ROI rises monotonically with the number of systems firing on a horse -
  1 system 5.65%, 3 systems 12.05%, 6-9 systems 28.60%, 10+ 36.03% -
  even though strike rate *falls* (10.19% -> 5.49%), because agreement
  concentrates at longer prices. Same direction over the last 12 months
  (6-9: 24.82%, 10+: 59.43%). Caveated in the script: these systems were
  all hand-built by one person so the "independence" is soft, and the
  high-agreement buckets sit where variance is widest. Still, an
  agreement threshold looks like a much better lever for the live
  pipeline than running all 418 systems flat.
- **Data-quality check, after CEO pushback.** The analysis recomputes
  every system from raw and cross-checks it against the signed-off
  workbooks: 304 of 421 match exactly. The CEO challenged the first pass
  on this, pointing out that HRB refreshes system qualifiers daily and
  the raw TSVs were downloaded after the workbooks were built - so drift,
  not staleness, could be the whole story. **Largely correct: 97 of the
  117 mismatches are drift.** The classifier was rewritten to *test* that
  rather than assume it, by asking whether truncating the fresh data at
  some date in the workbook build window (20 Jul 2026 onwards, workbooks
  built 29-31 Jul, raw pulled 31 Jul - 1 Aug) reproduces the workbook's
  bet count exactly:
  - `date-drift` (83) - a cutoff reproduces the figure exactly.
  - `date-drift(cap-shift)` (8) - capped slots, where arriving rows push
    old ones off the bottom of the 10,000-row window, so the count can
    fall as well as rise without anything having changed.
  - `date-drift(partial-day)` (6) - +1 or +2 bets, no exact cutoff because
    the workbook was built partway through a race day.
  - `truncated-raw` (3) - noggin3/51, noggin4/97, noggin5/39 as before.
  - **`system-changed` (17)** - the residue drift cannot explain.
- **The 17 are real.** 16 are noggin slots 1-57 (the rows
  `build_noggin_final.py` copied verbatim from the older account-1
  workbook and never recomputed - it only recomputed 58-100), plus
  noggin3 slot 67. The decisive evidence is direction: 10 of them are
  **uncapped slots returning FEWER bets than the workbook**, and daily
  accumulation can only ever add rows - with no cap there is no window to
  shift. Nor does the odds band, ignoring the odds band, or a
  saved-date-inclusive window reproduce them. So the qualifier sets
  themselves have moved: edited criteria, or dynamic (form/ratings-
  relative) criteria re-evaluating against newer data. The clearest case
  is **noggin slot 53 "NEWTONclaude"** (saved 2026-07-05), an actively
  worked-on slot: 922 bets in the workbook vs 234 now, and its entire
  raw history now starts 2025-01-01.
  **Those 17 rows shouldn't drive include/exclude decisions until
  re-audited** - cheap now that the fetch pipeline works.
- Robustness check: dropping all of noggin 1-57 moves the headline
  duplication share from 60.6% to 62.6% (and 2026 YTD from 96.2% to
  95.6%), so none of the conclusions below depend on those rows.
- noggin slot 82 ("MM", the CEO-confirmed test slot) has no cached raw
  and is excluded; 3 further systems produced zero qualifying bets, hence
  418 contributing rather than 421.
- Outputs: `cross_account_all_system_bets.csv` (every system-bet row),
  `cross_account_dedup_bets.csv` (one row per distinct bet),
  `cross_account_validation.csv` (per-system raw-vs-workbook check).

## 2026-08-01 (raw per-bet TSV caching complete for all five accounts)

- Cached the raw per-bet qualifier TSVs for **noggin5's 68 slots** to
  `System_Audits/noggin5_raw/` — the last account whose raw downloads
  weren't yet saved to disk (its original audit was computed via the
  in-browser JS pipeline without caching the raw TSVs, same as account
  1's 37 re-audited slots). noggin, noggin2, noggin3, and noggin4 were
  already cached from earlier sessions.
- Pipeline was driven entirely via in-page `fetch()`, no real navigation:
  POST `recallslot=N` to `v4builder.php`, parse the response for the
  "Quals" submit button's form, POST that, parse the result for the
  `v4qualifiersexcel.php` XLS form (the one without a `csv` field), POST
  that to get the raw TSV. Verified against a real button click first to
  confirm server-side session state ("You are editing your system saved
  in slot N...") persists correctly across fetch-only calls before
  relying on it for all 68 slots.
- Processed in batches of 9, each slot's TSV gzip+base64'd and
  `console.log`'d immediately after fetching (not batched in JS memory),
  then flushed to disk via `System_Audits/extract_console_payloads.py` +
  a gzip-decode step before starting the next batch, per explicit
  instruction to save progress incrementally after this project lost a
  session's work to a context/token cutoff before.
- 3-second pause between slots, matching every prior account's pacing to
  avoid repeating account 1's rate-limit lockout. No blocks encountered.
- All 68 output files verified to start with the `RTime` TSV header
  (i.e. correctly decoded, not left as raw base64) before finishing.
- **All five HRB accounts now have their raw per-bet TSVs cached to
  disk.** Next step (not started): cross-account overlap analysis.

## 2026-08-01 (retroactive capped-slot check: noggin, noggin2, noggin3)

- Extended yesterday's noggin5 fix to the other four accounts, per the
  CEO's request. Found each account's capped slots via `grep` for the
  cap note in each account's build script (noggin2 needed checking its
  10,001-line raw TSV files instead, since it never got the cap-note
  treatment).
- **noggin (account 1), slot 82 "MM"** - CEO confirmed this is a test
  slot not actually in use, skipped per instruction. Not fixed.
- **noggin2** - 13 capped slots (2, 4, 5, 7, 11, 21, 31, 61, 69, 70, 76,
  90, 99). All still have their raw TSVs cached in `noggin2_raw/` from
  the original audit, so no live account access was needed - checked
  the oldest row in each cached file directly against the saved date.
  **All 13 confirmed complete**, no corrections needed.
- **noggin3, slot 51 "351 D SOF M"** - genuinely truncated, same failure
  mode as noggin5's slot 39: no odds band to pre-filter on, and the raw
  unfiltered download (10,000 rows) didn't reach back to the 2015-04-06
  saved date - it stopped at 2016-05-27. Fixed with the year-split-and-
  merge method (added a Date (Year) 2015+2016 filter, fetched a second
  download, merged the non-overlapping date ranges). **Corrected**: Bets
  10,000→11,289, Wins 978→1,111, P/L(SP) -1,674.19→-1,954.47, P/L(BF)
  +527.51→**+380.26**, ROI(BF) 5.28%→3.37%. Still profitable, but the
  extra 2015-2016 history pulled the true figure down, not up - a
  reminder that "the real number is higher" isn't a safe assumption,
  only "the real number is different" is.
- Rebuilt `System_Audits/HRB_System_Performance_Audit_noggin3.xlsx`
  with the corrected slot 51 row; still 81 rows. Sent to the CEO.
- **noggin4, slot 97 "0 RUNS HDGR NH COMP"** - confirmed truncated once
  the CEO logged into noggin4: the raw download (this system also has a
  built-in Odds(SP) 1.50-34.00 criterion baked into the system itself,
  separate from the name-parsed odds band, but that alone wasn't enough
  to dodge the cap) stopped at 2021-05-04, short of the 2019-08-27 saved
  date. Fixed with the same year-split-and-merge method (Date (Year)
  2019+2020+2021, merged non-overlapping with the original download).
  **This is the biggest correction of the whole retroactive check - it
  flips the system's sign**: P/L(BF) went from **-83.94** (apparently a
  narrow loser) to **+516.64** (actually solidly profitable). Bets
  10,000→13,635, Wins 1,267→1,701, ROI(BF) -0.84%→3.79%.
- Rebuilt `System_Audits/HRB_System_Performance_Audit_noggin4.xlsx` with
  the corrected slot 97 row; still 93 rows. Sent to the CEO.
- **Retroactive capped-slot check is now complete** for all five
  accounts (noggin's one capped slot was a known test slot, skipped by
  CEO instruction; the other four accounts' capped slots are all
  checked and correct). Three genuine truncation bugs found and fixed
  across the whole project: noggin5 slot 39, noggin3 slot 51, noggin4
  slot 97 - all via the same server-side-prefilter-then-year-split
  method now documented in PROJECT.md.

## 2026-08-01 (noggin5: fixed a real truncation bug in capped slots)

- **The CEO spotted wonky numbers on slot 39** ("HDGR DIFF v2 14.01 -
  80.00") that didn't match what HRB's own site showed when the odds
  filter was applied before downloading, and suggested the fix:
  1. load the system, 2. apply the odds filter via the Breakdown tab's
  **Odds (BFSP)** category *before* downloading qualifiers, so the
  10,000-row cap applies to the odds-filtered set instead of the raw
  unfiltered history.
- This exposed a real gap in the noggin5 methodology: a capped
  10,000-row download only reaches back a certain distance in time -
  whether that distance covers the system's saved date is silently
  unknowable without checking the oldest row's date. For slot 39, even
  odds-filtering wasn't enough - the download still hit 10,000 rows and
  only reached back to 2023-06-04, short of the 2021-04-02 saved date.
  Fixed by adding a second download restricted to years 2021-2023 (via
  a **Date (Year)** breakdown category) and merging the two non-overlapping
  downloads locally. Full method now documented in PROJECT.md.
- **Slot 39 corrected**: Bets 4,549→16,928, Wins 181→687, P/L(SP)
  -1,052.50→-3,552.00, P/L(BF) +73.70→**+419.14**, ROI(BF) 1.62%→2.48%.
  Still profitable on BF, but the original figure was a genuine ~6x
  understatement of the true magnitude - not just an ambiguous "review
  manually" flag, an actual wrong number.
- **Checked all other 15 capped noggin5 slots the same way** (3, 7, 8,
  9, 10, 16, 22, 27, 40, 41, 42, 53, 57, 90, 91) - all 15 confirmed
  complete (the oldest row in each capped/pre-filtered download predates
  that slot's saved date), no other corrections needed. Updated their
  Odds Parsing Notes from the old generic "review manually" cap flag to
  a note confirming they were specifically re-verified and found
  complete.
- Rebuilt `System_Audits/HRB_System_Performance_Audit_noggin5.xlsx` with
  the corrected slot 39 row and updated notes; still 68 rows, no
  duplicates. Sent to the CEO.
- **Not yet done**: the same capped-slot verification hasn't been
  applied retroactively to noggin/noggin2/noggin3/noggin4's capped
  slots. Worth doing at some point, flagged in PROJECT.md.

## 2026-07-31 (noggin5 account 5 completed - final account)

- **Completed the noggin5 (account 5) system audit** - all 68 slots, the
  last of the five HRB accounts. Session was interrupted mid-run by a
  context reset after 21 slots; resumed and finished the remaining 47
  the same day using the same in-browser fetch+compute pipeline as
  accounts 1/3/4.
- **Found and fixed a real correctness bug on resume**: the fetched TSV
  columns are double-quoted (e.g. `"2"` not `2`), and the win-detection
  check (`Position === '1'`) never stripped the quotes, so no win was
  ever counted - every slot computed before the fix showed 0 wins with
  P/L(SP) and P/L(BF) both equal to `-1 * bets`. This is silently
  plausible-looking (not an obviously broken number) and was only
  caught by cross-checking slot 1's odds-band-free result against HRB's
  own baseline report, which must match exactly with no odds filter
  applied - it didn't. Fixed by stripping quotes from every column
  before comparison/parsing; every slot computed up to that point
  (including the two already "done" before the reset, since the JS
  pipeline itself isn't persisted across a reset) was recomputed. See
  PROJECT.md "Fetching per-bet data" for the full writeup.
- **This account had the most 10,000-row-cap slots of any account so
  far** - 16 of 68 slots hit the cap (3, 7, 8, 9, 10, 16, 22, 27, 39,
  40, 41, 42, 53, 57, 90, 91), all flagged in their Odds Parsing Note.
  Several of this account's systems date back to 2018-2021 with very
  high qualifier volume.
- Two new odds-band exclusion patterns confirmed (no new words needed,
  existing account-4 exclusion lists already covered them): slot 38
  "1-5DSLR" (glued, no space) and slot 91 "61-240DSLR" (glued) both
  correctly skipped via the existing `dslr` following-word exclusion;
  slot 57 "0-6 RUNS" correctly skipped via `runs`.
- Merged into `System_Audits/HRB_System_Performance_Audit_noggin5.xlsx`
  via new `System_Audits/build_noggin5_audit.py`. All 68 real slots
  present, no duplicates, verified against the bulk-report slot list.
  Sent to the CEO.
- **Status: all five HRB accounts (noggin, noggin2, noggin3, noggin4,
  noggin5) are now fully audited.** The system-profitability audit
  phase of the BFBM project is complete. Next phase per PROJECT.md is
  the selections→BFBM CSV import pipeline - not started, not requested
  yet.

## 2026-07-31 (noggin4 account 4 completed)

- **Completed the noggin4 (account 4) system audit** — all 93 slots in
  one pass, same in-browser fetch+compute pipeline as noggin3.
- **Extended the odds-band parser with two more account-specific
  exclusion rules**, found via inline review while processing (see
  PROJECT.md "Odds band parsing" for details):
  - Added `n` to the preceding-word exclusion list, to catch this
    account's internal cross-reference codes like "N4-97" (slot 3) and
    "N4-36" (slot 81) — these reference another slot number, not an
    odds band, and would otherwise have been misread as e.g. a
    "4 - 97" price range.
  - Extended the range-separator regex to accept the word "to" as well
    as "-", after finding slot 41 "DSLR and 2ndLR 12.0 to 35.0 BSP"
    used a different spelling convention than every other slot seen so
    far across all four accounts.
- Both new rules were spot-verified against their trigger slots (41,
  57 for "to"; 3, 81 for "N4-") before trusting them for the rest of
  the run.
- One slot (97 "0 RUNS HDGR NH COMP") hit the 10,000-row download cap,
  flagged the same way as prior accounts' capped slots.
- Merged into `System_Audits/HRB_System_Performance_Audit_noggin4.xlsx`
  via new `System_Audits/build_noggin4_audit.py`. All 93 real slots
  present, no duplicates, verified against the bulk-report slot list.
  Sent to the CEO.
- **Status: noggin, noggin2, noggin3, and noggin4 audits are now all
  complete.** Account 5 still not started.

## 2026-07-31 (noggin3 account 3 completed)

- **Completed the noggin3 (account 3) system audit** — all 81 slots in
  one pass, using the same in-browser fetch+compute pipeline built for
  noggin's re-audit earlier the same day (no real downloads, no raw
  TSVs cached to disk).
- **Found and fixed two odds-band-parsing false positives** that the
  account-1/noggin2 exclusion list didn't cover, both caught by manual
  review of the parsed output before finalizing (see PROJECT.md "Odds
  band parsing" for the details and the general lesson about anchoring
  the preceding/following-word regex correctly):
  - Slot 31 "TURF STRAIGHTS GB WEEK 16 - 24 9.01 - 1000.00" — regex's
    first match "16 - 24" is a week-number range, not odds. Added
    `week`/`wk` to the preceding-word exclusion list. Recomputing with
    the real band (9.01-1000) changed this slot from 388 bets/P&L(BF)
    9.23 to 1956 bets/P&L(BF) 94.42 — a large enough swing that the
    first pass would have been materially wrong if left unreviewed.
  - Slot 52 "CHELT FEST IRISH 3-4runTR" — "3-4" is a runners-count
    range, not odds. Added `run`/`runs`/`runtr` to the following-word
    exclusion list.
  - Root cause for both: the preceding-word regex used `$`-anchoring
    without allowing for whitespace between the word and the number
    (`([A-Za-z]+)$` fails to match "WEEK " with a trailing space) —
    fixed to `([A-Za-z]+)\s*$`. Re-verified slots 1–30 (processed
    before the fix) by inspection — none of them had a second number
    range or an exclusion word adjacent to the real one, so no
    re-computation was needed for those.
- Also mistakenly skipped two real slots (59 "7YO 8YO 46+ DSLWR" and
  86 "3YO UP CLASS") partway through, having confused this account's
  slot-number gaps with account 1's — caught by a row-count check
  against the bulk report (expected 81, only had 79) before finalizing,
  and both slots were fetched and added.
- One slot (51 "351 D SOF M") hit the 10,000-row download cap, flagged
  the same way as noggin's slot 82.
- Merged into `System_Audits/HRB_System_Performance_Audit_noggin3.xlsx`
  via new `System_Audits/build_noggin3_audit.py`. All 81 real slots
  present, no duplicates, verified against the bulk-report slot list.
  Sent to the CEO.
- **Status: noggin, noggin2, and noggin3 audits are now all complete.**
  Accounts 4 and 5 still not started.

## 2026-07-31 (noggin account 1 completed)

- **Completed the noggin (account 1) system audit** - the 37 slots still
  pending after this morning's rate-limit lockout, once the CEO
  re-logged into the account and handed off the browser session.
  Same odds-band-parse / saved+1-date-filter / BF-commission-formula
  pipeline as noggin2, ported to JS and run in-browser (see PROJECT.md
  "Fetching per-bet data via in-page fetch" for why: real download
  clicks silently stopped working partway through, Chrome was blocking
  automatic downloads with no page-visible signal).
- Paced one slot at a time with a ~3s gap between each, per the CEO's
  explicit instruction to match noggin2's pace and avoid repeating the
  account-1 lockout. No blocks encountered this time.
- Slot 82 ("MM") hit the 10,000-row per-request download cap - flagged
  in its Odds Parsing Note rather than treated as a final number, since
  the true post-saved-date bet count may be higher.
- Fixed a bug loading the pre-existing 55 "Done" rows: two of them
  (slots 11, 14) had a corrupted "P/L by Year (BF)" cell in the
  original account-1 workbook - Excel had auto-formatted a
  single-year "YYYY: value" string as a time value. Detected and
  skipped just the by-year breakdown for those two rows (their totals
  were unaffected); flagged in script output rather than silently
  dropped.
- Merged into `System_Audits/HRB_System_Performance_Audit_noggin_FINAL.xlsx`
  via new `System_Audits/build_noggin_final.py` - all 92 real slots
  present (gaps at 21, 31, 59, 72, 76, 77, 81, 86 don't exist on this
  account), no duplicates. Sent to the CEO.
- **Status: both noggin and noggin2 audits are now complete.** Accounts
  3, 4, 5 still not started.

## 2026-07-31 (post-review fix)

- **Fixed a name-parsing bug in the odds-band regex**, caught by the CEO
  reviewing slot 96 (`YORK MAY MEETING 240 - 300 dslr`) — the "240 -
  300" was Days Since Last Run, not an odds band, and was wrongly
  applied as a price filter (giving 0 bets). Scanned all 88 names for
  the same pattern before patching just the one slot — found **8
  affected systems total**: 11, 21, 43, 68, 70, 96, 97, 100. In three of
  them (21, 43, 70) the false match was masking a genuine odds band
  later in the same name, so those weren't just missing data, they were
  wrong.
- Fixed `parse_odds_band()` in `build_noggin2_audit.py` to skip a
  matched number range when it's glued to "class" (race class, e.g.
  "class6 - 7") or immediately followed by "DSLR"/"SOF"/"ClaimJock"
  (none of which are odds), and keep scanning for a later genuine match
  in the same name instead of just taking the first regex hit.
- Added an **Odds Parsing Note** column to the output so any
  skip/rejection is visible rather than silent.
- Recomputed all 88 systems from the already-downloaded raw TSVs — no
  new HRB requests needed, this was a pure local parsing fix. Updated
  `HRB_System_Performance_Audit_noggin2.xlsx` sent to the CEO.

## 2026-07-31 (overnight, unattended)

- **Completed the noggin2 (account 2) system audit.** Fetched raw
  per-bet qualifier history for all 84 remaining slots (everything in
  the `SLOTS` dict except the 4 already done in the earlier session:
  slots 4, 28, 58, 69) via the Recall → Quals → XLS flow documented in
  PROJECT.md, using Claude in Chrome against the already-authenticated
  `noggin2` session.
- No blocks or rate-limit issues encountered — paced requests with a
  few seconds' gap between each slot the whole way through, per the
  explicit instruction to avoid repeating account 1's lockout. All 84
  slots completed cleanly in one pass.
- Raw TSV downloads for all 84 slots saved to `System_Audits/noggin2_raw/`
  (now 88 files total, one per slot, 4-100 excluding gaps in slot
  numbering that don't exist on this account).
- Ran `System_Audits/build_noggin2_audit.py` against the full set: it
  reports 88 of 88 systems processed, 0 missing. Final workbook written
  to `System_Audits/HRB_System_Performance_Audit_noggin2.xlsx`
  (supersedes the earlier 4-row `..._TEST.xlsx`). No changes made to
  the audit formulas (odds-band parse, saved+1 filter, P/L(BF)
  commission formula) — used exactly as validated in the test batch.
- Note: during decoding, one intermediate console-message payload
  (slot 3, first attempt) came back corrupted from a manual
  copy/paste transcription step and had to be re-fetched — fixed by
  padding all subsequent console.log payloads so they reliably route
  through the tool's auto-save-to-file path instead of being echoed
  inline. No data integrity issue in the final files — verified by
  comparing decoded byte length against the browser-reported original
  fetch length for every slot.
- **Status: noggin2 audit is now complete and ready for CEO review.**
  Accounts 3, 4, 5 still not started. Account 1 (noggin) still has 42
  slots pending, blocked on the rate-limit lockout from 2026-07-31
  morning.

## 2026-07-31

- **Wrote PROJECT.md and this CHANGELOG.md** so the project can survive
  a context reset without the CEO having to re-explain everything from
  scratch. Prompted by exactly that happening this session.
- **Resumed the system audit on account 2 (noggin2)**, since account 1
  (noggin) is still locked out from this morning's rate-limit incident
  (HRB blocked it for sending requests too fast; block was noted to
  lift "~31 Jul 2026 11:44").
- Initially assumed noggin2's slot numbers would mirror account 1's —
  **wrong**. Confirmed with the CEO that all five HRB accounts hold
  completely independent sets of systems. Course-corrected before doing
  any real work on the wrong assumption.
- Lost the methodology context from a prior session (this session's
  memory didn't retain it) and had to ask the CEO to re-explain the
  project goals and audit approach from scratch. This is the direct
  reason PROJECT.md now exists — should prevent a repeat.
- Reverse-engineered the full HRB mechanics for pulling per-system,
  per-bet historical data via live browser exploration (Claude in
  Chrome) — see PROJECT.md "How the audit actually works" for the full
  writeup. Headline discoveries:
  - `v4savedsystems.php?userchoicego=1` with period=999 gives every
    system's SAVED date + baseline stats in one request (huge
    efficiency win vs. checking each slot individually).
  - Recall → Quals → XLS gives up to 10,000 rows of real per-bet
    history (`Odds_Numeric` = SP "to-1", `Odds_Exchange` = real
    archived Betfair SP decimal) — full history, not filtered by saved
    date, so that filtering happens locally.
  - HRB's own reported "P/L(BF)" is a theoretical estimate (per HRB's
    own help docs: "Betfair Backing Estimated Price Settings"), not the
    real archived price. Decided with the CEO to compute our own,
    correct figure from real `Odds_Exchange` data instead:
    `(Odds_Exchange - 1) * 0.95` on wins, `-1` on losses.
  - Odds bands are parsed from the system's name text (no dedicated UI
    field exists for this) — same convention as the account-1 workbook.
- Validated the full pipeline on a 4-slot test batch (slots 4, 28, 58,
  69) before committing to all 88 slots, per the CEO's request to keep
  the pace slow after this morning's lockout. Slot 58 (no odds
  restriction) matched HRB's own SP and BF figures exactly, confirming
  the formulas are correct.
- Built `System_Audits/build_noggin2_audit.py` (reusable computation
  script) and `System_Audits/HRB_System_Performance_Audit_noggin2_TEST.xlsx`
  (4-row output for review).
- Raw per-bet downloads for the 4 test slots saved to
  `System_Audits/noggin2_raw/` for reuse.
- **Status at end of session: waiting on CEO review of the test output**
  before running the remaining 84 slots on noggin2.

## 2026-07-30 and earlier (reconstructed from repo state, not directly observed)

- Initial commit, `.gitignore` added (`.env` excluded).
- `bfbm_tips_reference.md` and `claude_code_bfbm_pipeline_prompt.md`
  added — the spec for the eventual selections→BFBM CSV pipeline
  (phase 2 of the project, not yet started).
- Account 1 (noggin) system audit begun:
  `System_Audits/HRB_System_Performance_Audit_noggin.xlsx` — 58 of 100
  slots completed ("Done"), remaining 42 marked
  `PENDING - blocked by HRB System Builder rate limit` after the
  account got rate-limited from requests being sent too fast.
