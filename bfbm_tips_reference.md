# BFBM Tips Import — Reference for UK/Irish WIN Market Workflow

Distilled from Bf Bot Manager v3 manual (632pp, June 2026 build) for the
narrow case: pre-selected horses, UK/Irish WIN markets, min/max odds
conditions, hands-free daily import.

Page references point back to the manual for anything needing detail.

---

## The CSV format

**Minimum required columns for horse racing:** `Provider`, `MarketType`,
and either `SelectionName` or `SelectionId`. (Manual p183–184)

Smallest valid file:

```
Provider,MarketType,SelectionName
test horse tip 1,WIN,1. Captain Bart
```

**Columns relevant to this workflow** (full list p181–182):

| Column | Required? | Notes |
|---|---|---|
| `Provider` | Effectively yes | Tipster/system name. **Case sensitive.** Your routing key to strategies. |
| `MarketType` | Yes | `WIN` for win markets. |
| `SelectionName` | Yes (or SelectionId) | Must match Betfair's selection name. See name-format caveat below. |
| `SelectionId` | Alternative to name | Betfair numeric selection id. Requires API access to obtain. |
| `MinPrice` | Optional | Min price at which bets can be placed on this selection. |
| `MaxPrice` | Optional | Max price at which bets can be placed on this selection. |
| `BetType` | Optional | `BACK` or `LAY`. |
| `MarketId` | Optional | Disambiguates same-named runners; also lets bot auto-load the market. |
| `EventId` | Optional | Alternative disambiguator. |
| `StartTime` | Optional | Universal time the market starts. |
| `Size` | Optional | Bet amount for this selection. |
| `Price` | Optional | Forces bets at this exact price regardless of market — can leave bets unmatched. Not the same as MinPrice/MaxPrice. |
| `BSP` | Optional | true/false — place as full Betfair Starting Price bets. |
| `Points` | Optional | Requires Level/Initial stake configured in strategy. |

Columns not needed here: `Handicap`, `MarketName`, `EventName`,
`SportMonksFixtureId` (football/SportMonks tipping services only).

---

## Open questions to resolve empirically

**Does `SelectionName` need the cloth number prefix?** The manual's own
example shows `1. Captain Bart` — with a leading cloth number and
period. Unclear from the text whether this is required or just what
BFBM's exporter emits.

**Resolution method (manual's own advice, p183):** go to EVENTS &
MARKETS, tick a horse's "My S." checkbox, click "Export My S. to tips
file", give it a provider name, save, and open in a text editor. That
shows the exact expected format with no guesswork. Do this once before
generating bulk files.

The same trick settles any `MarketType` uncertainty (p185): make a test
tip, export it, read the exact value.

---

## Hard constraints

**1 tip = 1 bet.** Each tip/selection is bet on once only. To have two
strategies bet the same horse, the selection must appear twice under two
*different* provider names. (p85)

**Duplicates are silently dropped.** Only identical tips with different
provider names can coexist. A true duplicate won't appear in Manage Tips
at all. (p86)

**Same-named runners are ambiguous.** Provider/MarketType/SelectionName
alone fails when two runners share a name — add `EventId` or `MarketId`
to disambiguate. Detect and flag these when generating files. (p183)

**Imported fields can be overridden.** Strategy config includes an option
to ignore imported fields such as stake size, MinPrice and MaxPrice. If
set, your odds bands are silently discarded. Check this if bets appear
outside your intended prices. (p454)

**Today's card only.** Markets for future days generally aren't loaded,
so filter to today before importing.

---

## File handling gotchas

**Never save from Excel directly.** Excel converts MarketIDs to number
format and truncates trailing zeroes. If you must use Excel, import
"from text" and explicitly set columns to import **as text**. (p85)

Writing CSV programmatically avoids this entirely — preferred.

**Close the file before importing.** Excel locks open files; BFBM can't
read a locked file and the import silently fails. (p85)

**Must be `.csv`**, not `.xlsx`.

---

## Market loading

Without `MarketId` in the tips file, BFBM needs the relevant markets
already loaded. Set up an autoload rule for all UK/IRE horse racing
markets: Events & Markets screen → Auto load button → add New.
(Manual §3.3.3, p106; §3.3.4 covers auto-loading from imported tips,
p108.)

With `MarketId` present, the bot loads markets for the tips
automatically — but obtaining MarketIds requires Betfair API access
(and therefore the paid live app key), so autoload is the cheaper route.

---

## Automation path

`Tips auto loading` (§7.3.22, p194) can pull tips from a URL on a
schedule (every few minutes/hours). If the daily tips file can be
published to a local or private URL, this removes the manual import
step entirely — the missing piece for truly hands-free operation.

Worth investigating once manual import is proven working.

---

## Relevant manual sections

| Topic | Section | Page |
|---|---|---|
| Import tips from file | 7.3.18 | 181 |
| Horse racing tip file example | — | 183 |
| Export "My S." to tips file | 7.2.5 | 163 |
| Tips auto loading | 7.3.22 | 194 |
| Auto-loading markets (Auto Load) | 3.3.3 | 106 |
| Auto-loading markets (Imported Tips) | 3.3.4 | 108 |
| Bet on imported tips (bet type) | 2.1.7 / 14.x | 454 |
