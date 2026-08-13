# Handoff

Everything a person or agent picking this up needs, in the order they need it.

---

## 1. What this is, and the clock

**Concordance** reads measurements out of ~104,000 scanned Canadian government
publications and publishes each one with a link to the scanned page it came
from. Repo lives at `C:/Users/jdcap/Documents/Projects/ground-truth` (directory
still has the old name; everything inside is renamed).

It is being submitted to the **BC + AI / Internet Archive Canada AI Builders
Fellowship**.

| | |
|---|---|
| **Application deadline** | **21 August 2026** |
| Review | 22–30 Aug, selection 31 Aug |
| Build window | 1 Sept – mid-Oct 2026 |
| Conditional showcase | 28 Oct 2026, Vancouver, if the work is ready |
| Award | $5,000, six weeks |
| Judged on | useful · imaginative · open source · achievable |

**The application form is eight free-text boxes**, seven at 2,000 characters and
the success metric at 600 — not a document. Answers are written and sized in
[`APPLICATION-FORM.md`](APPLICATION-FORM.md); `python scripts/check_form.py`
counts each one the way the form will and fails if anything overruns. Four of
eight sit within 120 characters of the limit, so **re-run it after any edit**.

`APPLICATION.md` is the long-form version, kept as the reference the README
points at. It is *not* what gets pasted into the form.

---

## 2. Standing constraints — do not break these

1. **Never put Jonathan's email in the repository.** Commits use
   `jdcap@users.noreply.github.com`. This has been checked and holds; re-check
   before making the repo public.
2. **Never add AI attribution to a commit message.** No `Co-Authored-By`, no
   "Generated with", no robot emoji. This is in the user's global CLAUDE.md and
   it overrides the default. The reasoning: these repos are his portfolio
   surface, a trailer is baked into the commit SHA, and removing it later means
   rewriting history.
3. **The repo is PRIVATE and must be made public before submitting.**
   `github.com/aminalnam/concordance`. He chose private-now / public-before-
   submission deliberately. Open source is one of four judging criteria and the
   application invites the reader to check the code, so a 404 on 21 Aug is
   worse than no link. Do it a day early.
4. **Ask before anything outward-facing.** Publishing, deploying, sending. He
   has authorised: the private repo (done), and a droplet deploy (not done).

---

## 3. Where it stands

**5,147 source-linked records across 14 municipalities** at the frozen `f8fbca2`
application checkpoint, 779 tests, zero required dependencies in the core. Core
benchmark figures are tied to named snapshots; live estimates must be dated and labelled.

| | |
|---|---|
| Extraction precision / recall | 96.8% / 88.2% on 4 hand-read pages, 68 values |
| Kind accuracy (measurement vs design spec vs legal limit) | 98.3%, 60 matched values |
| Stream accuracy (influent vs effluent) | 88.9%, 18 judged pairs |
| Source-sentence mismatches in a 286-record audit | 0 |
| Vision-table trial output | 535 records from 24 pages, 11 collections; no hand-read accuracy score yet |

Re-score without a model: `python scripts/rescore.py`. Full accuracy run needs
Ollama: `python scripts/run_gold.py --model gemma4:12b`.

**The biggest measured finding, from an overnight stratified sweep:** the
archive's measurement vocabulary does not saturate. 1,416 readings across 25
collections reached 44% coverage; Chao1 estimates ~727 distinct measurement
types (95% CI 557–987); and **76% of readings outside water reports used a
parameter name the model invented rather than one the archive uses**, against
32% inside them. Report in `data/results/vocab_coverage.stratified.json`.

---

## 4. In flight right now

- **Town batch** — the pre-fix runner is still active; inspect its child before
  touching any recently written result or starting another model job. It
  predates completion receipts, so it will not create one. A receipt is now
  available only to a fresh managed run whose marker existed before its result;
  it proves completion of the exact ordered selection and matching result, not
  that later code reread old pages. A clean legacy incremental pass instead gets
  a separate result/selection-bound scheduling checkpoint explicitly marked
  `receipt_backed: false` and `fresh_verification: false`; this prevents it from
  starving new towns without upgrading its provenance. Result, receipt, marker
  and legacy paths use one contained Windows-safe slug. There are currently no
  receipts.
- **Vocabulary workflow** — a conservative first artifact is built and wired
  into extraction. `data/vocabulary/vocabulary.json` holds 697 source-attested
  terms from the frozen `f8fbca2` 5,147-record checkpoint and stratified survey: 229 have
  one consistent existing identity; 468 deliberately leave identity blank; all
  are `reviewed: false`; matching collisions are zero. Grouping is orthographic
  only, so words such as `design`, `total`, `maximum`, `minimum`, `per capita`
  and `24 hour` cannot be silently erased.
- **Publication-year recovery** — the deterministic, model-free OCR detector
  has a fresh 600-item validation at
  `data/cache/dating/year_recovery.json` (ignored, not for commit). Its stored
  detector SHA matches `concordance/dating.py`: 142/145 non-bound guesses agreed
  with held-out catalogue years (97.9%), all 145 were within ±1 year, and a
  separate 300-item yearless residual sample produced 111 date proposals plus
  24 explicitly low-confidence lower bounds. Catalogue agreement is a noisy
  surrogate, not ground-truth publication-date accuracy. The report SHA-256 is
  `da550865185673de28d7811888e44fa7d88eaab8edbd8e3f7b186c6f979a8bcb`.
- **Git boundary** — a prior concurrent agent committed and pushed active result
  snapshots during this handoff. A local pre-push hook now blocks further
  pushes. Do not remove it or publish another correction without the user's
  explicit approval, and always exclude the live result owned by the batch.

---

## 5. What to do next, in priority order

### A. Validate and improve the vocabulary (highest value)

The measurement above says this is *the* thing standing between "works on
municipal sewage reports" and "works on the Canadian public record".

1. ~~Build a safe provisional artifact.~~ **Done.** The deterministic builder
   reads committed evidence by default, validates source attestation and matching
   invariants, and refuses semantic collisions. Reproduce this exact artifact
   with `python scripts/build_vocabulary.py --git-ref f8fbca2 --dry-run`;
   validate the saved file with
   `python scripts/build_vocabulary.py --validate data/vocabulary/vocabulary.json`.

2. ~~Wire it into extraction.~~ **Done.** The model chooses from the prompt list
   or explicitly proposes a reusable term; the extractor independently checks
   that claim, canonicalizes only an exact canonical/orthographic-alias match,
   and records the naming version and vocabulary size in `Record.raw`.

3. ~~Improve prompt retrieval.~~ **Implemented and preflighted.** Selection now
   ranks exact vocabulary phrases from the same title, publisher and 12,000-page-
   character slice the model sees, then word overlap and evidence frequency.
   On 112 survey terms linked to their exact cached source pages, the target was
   selected 112/112 times even at limit 80; production keeps limit 240. This is
   a retrieval preflight, not a post-change model-accuracy result.

4. **Then measure the model.** Re-run the same stratified sweep and check
   `model_named_share` falls from the measured 0.7578 baseline. No post-change
   model run has happened yet; vocabulary membership is only a preflight proxy.

Every entry carries `reviewed: false` until a person confirms it. Keep that —
the project's line is that the machine proposes and a human decides what a term
*means*, and it has been wrong about exactly this before ("BOD removal" vs "BOD
exceedance frequency" are both percentages and different measurements).

### B. Prepare a public instance (fresh approval required before deployment)

The deployment design exists, but publishing remains outward-facing work: get a
fresh go-ahead before changing DNS or starting it. The remaining external input
would be a **DNS A record**.

- Droplet `165.227.25.23`, Ubuntu 24.04, nginx + Let's Encrypt. Runbook and
  patterns in `C:/Users/jdcap/Documents/Projects/server-infra` — follow the
  Squishy Store pattern (systemd unit + nginx reverse proxy), not the static
  ones.
- Suggested host `concordance.jonathancapone.com`.
- Set `CONCORDANCE_PUBLIC_HOSTS=concordance.jonathancapone.com` in the service
  environment. POST endpoints trust only loopback hosts by default; the explicit
  value is required behind nginx to keep DNS-rebinding requests out.
- **Vendor MapLibre first.** `concordance/portal.py` loads it from unpkg and
  pulls tiles from arcgisonline and an S3 terrain bucket. A CDN failure already
  took out all nine views once, and any showcase would run on conference wifi.
- **Size the evidence workers before exposing them.** The wire download is
  capped, but one permitted 54 MiB page-cache file expands to roughly 1.4 million
  word entries in memory. Add an item-size/page-count policy or lower concurrency
  for the droplet. App-level direct-peer quotas also become a shared proxy quota
  behind nginx; deliberate per-client limits belong at that trusted edge.

### C. Adversarial audit findings fixed in this pass

- `library.ask` no longer reports or writes a contribution when it recovered
  zero records.
- `/api/citation` now returns an explicit unavailable-image result and keeps the
  whole-page archive link separate, rather than feeding HTML to an image tag.
- A slow MapLibre download degrades only the map after four seconds; all local
  views initialize first, and a late download can still recover the map.
- All model/OCR/external strings are escaped in the portal and external links
  are limited to HTTP(S), closing the public model-reply injection path.
- `/api/bundle` now has byte, record, identifier and page caps; rate and global
  concurrency limits reject excess work before archive verification.
- `/api/read` no longer launches an hours-long local-model job from a GET. The
  public UI labels the browser-to-local handoff as fellowship work instead of
  claiming it already runs on the visitor's laptop.
- Every expensive or mutating public route is JSON POST-only with same-origin,
  size, rate and concurrency guards. Ledger, watershed and frontier first-builds
  coalesce under locks, and failure results are cached rather than retried by
  every visitor.
- Public archive identifiers and collection names have one conservative syntax
  boundary plus resolved cache containment, including Windows drive, device and
  traversal cases.
- Incoming numbers must match complete numeric tokens, not substrings; a value
  `12` no longer passes against `3120`. Bundle IDs are recomputed, and merge now
  performs locked deduplication plus create-new atomic publication, so colliding
  or concurrent submissions cannot overwrite or duplicate accepted data.
- Accepted individual contributions now join the same deduplicated corpus used
  by the downloadable library, town views and Jay; reload constructs a new Jay
  over the new corpus. Cheap flag overlays no longer force archive rechecks.

- Place/facility scoping is now shared by loading, future extraction and bundle
  deduplication. Against the frozen 5,147-record checkpoint it moves 233 plant,
  equipment or locality strings (for example "digesters", "Site 1" and
  "Brantford Water Treatment Plant") under the file's municipality/site scope,
  preserves the model's wording as facility or `raw.reported_place`, and retains
  a genuinely different populated place. The corpus, dispute ledger, share
  export and merge keys all use the same scoping. Existing result JSON is not
  rewritten.

### D. Application polish

- Two reader panels have been run (five personas each). The second said 4 of 5
  could now explain the project from the first two screens, up from 0 of 5.
  Their remaining asks are answered in the current draft.
- Not yet done: nobody outside the project has used it, and no institution has
  been approached. The application says so plainly in *"What I have not tested,
  and who has not used it"* — but **the cheapest possible win before the 21st is
  to make that paragraph untrue**: one email to Internet Archive Canada about
  the 13,429 metadata proposals, and five people from a town in the dataset
  clicking the button. A librarian reviewer named this as the single thing
  standing between "lean yes" and "yes".

---

### E. Lift more from OMEGA — an explicit request, not yet started

**Jonathan asked for this directly and it never got done.** His words: *"I just
think we need to utilize more of the OMEGA code base since the work is mostly
done and it looks good."* The decision he made was: Concordance stays a separate
repository, but stops rebuilding what OMEGA already has.

OMEGA-wave lives at `C:/Users/jdcap/Documents/Codex/OMEGA-wave`. It is a large,
actively changing system; do not repeat old line or provider counts without
measuring the current checkout. Some of it is already here (`science.py`,
`portal.py`, `jay.py`, `static/omega-portal.css` all came from it). A survey ran
subsystem by subsystem and costed each candidate; **its findings were never acted on.** Full
output in the session task file `w5gzy32rc.output`; the headline items, all
stdlib with **zero new dependencies**:

| Lift | From | Replaces | Effort |
|---|---|---|---|
| "Glass bridge" floating panels — map stays live behind every view | `gateway/static/portal.css` (.page-panel, .context-drawer) | `portal.py` `.dock`, a flat opaque slab; and `.view`, which currently *hides the map* on every non-map view | hours |
| `drawLineChart` / `drawMultiSeriesChart` — inline-SVG charts with axes, titles, confidence bands and per-point quality flags | `gateway/static/portal.js:29665–29881` | `portal.py` `spark()`, 12 lines, a bare polyline with no axis or scale | hours |
| `tilecache.py` + prewarm, plus an offline tile pack | `gateway/tilecache.py`, `main.py` | nothing — this is the fix for the CDN dependency | 1–2 days |
| Vendor MapLibre locally (OMEGA has its own precedent for this) | — | the unpkg `<script>` in `portal.py` | hours |

The QC-flag vocabulary in those charts (SUSPECT / FAIL / MISSING) maps almost
exactly onto this project's ledger states (settled / contested / unsupported),
which would let a chart **show which points are disputed** — a capability
Concordance does not currently have.

**One correction to that survey:** it recommends lifting OMEGA's animated sea
turtle as the agent's mark. That was written before the rename. The agent is now
**Jay**, a Canada jay, because a Hawaiian sea turtle was right for an ocean
instrument and wrong for Canadian municipal paperwork. Take the launcher and the
animation machinery if useful; do not take the turtle.

---

## 6. Environment, and one trap that has cost hours three times

Windows 11, **Python 3.14.5**, PowerShell and Git Bash both available. Ollama is
running locally with `gemma4:12b` (the default extractor), `gemma4:26b`,
`qwen3.6:latest` (the vision model) and `llava:latest`.

Measured timings on this machine, so you can plan:

- prose page: **~91 seconds**
- table page via the vision model: **~8 minutes** (only 18% of the model's
  layers fit in 8 GB of VRAM)
- one town, end to end: **~2 hours**
- the stratified vocabulary sweep: **12 hours** for 1,416 readings

Server: `python -m concordance.server`, port **8765**. `STATE` loads everything
at startup, so **any code or data change needs a restart** — this has caused
"my fix didn't work" confusion more than once.

### The trap

**A `` written into a regex through a shell heredoc becomes a literal
backspace byte (0x08).** The file then reads back correctly in every editor and
the pattern silently matches nothing.

This has happened **three times** in this project — in `models.py`, in
`server.py`'s facility-suffix pattern, and once in vision. The second time it
made the flagship trend stay broken *after being fixed*, because "Owen Sound
Sewage Treatment Plant" stopped resolving to "Owen Sound" and nobody could see
why.

`tests/test_vision.py::test_no_source_file_carries_a_control_byte` catches it
and caught the third occurrence. Two habits avoid it entirely: write regexes
with `(?<![a-z])` / `(?![a-z])` instead of ``, and prefer the Write/Edit tools
over heredocs when authoring patterns.

---

## 7. Decisions already made — do not relitigate

Each of these was argued and settled with Jonathan. Reopening them wastes his
time.

- **Separate repository from OMEGA**, but lift its code rather than rebuild.
  Considered merging into OMEGA and rejected: the trust models differ (OMEGA
  trusts a signed node; here the sender is irrelevant and the archive decides),
  and the zero-dependency core is what makes "a stranger's laptop can read a
  document" plausible.
- **No GPU rental in the budget.** The old $4,251–8,502 range was withdrawn: its
  cost model is not reliable enough to quote. A full rented pass is outside the
  fellowship regardless, and a corpus bought in one batch stops when funding does.
- **The vocabulary was done before applying**, not proposed as funded work.
- **Name: Concordance.** Ground Truth was taken. He rejected roughly fifteen
  alternatives before this one — including Verbatim, Gazetteer, Cairn, Portage,
  Baseline — so if you dislike it, keep it anyway.
- **The agent is Jay**, for the Canada jay, which caches thousands of items
  across a territory and remembers where each one is.
- **Never the word "copilot"** for an AI. It is another company's product name.
- **Repo private now, public before submitting.**
- **Deploy to the droplet** rather than only linking the repo.

---

## 8. Working with Jonathan

- **He wants short answers.** Answer first, in a line or two. He has asked for
  this explicitly and it is in the persistent memory file. I repeatedly failed
  at it and he called it out.
- **He catches real errors.** The routing bug that was discarding a fifth of the
  archive was found because he said *"there was lots of text in the Good Living
  document."* When he pushes back on a technical claim, check before defending.
- **He will reject names and framings until one is right.** That is not
  indecision; the naming round took fifteen tries and the result is better.
- He asks for work to continue without check-ins. Do the work, report at the
  end, do not narrate each step.

---

## 8b. Prior investigations, and where their output lives

A lot of analysis was run that is not in the code. The raw results are in the
session task directory
`C:/Users/jdcap/AppData/Local/Temp/claude/.../2b3847e7-.../tasks/<id>.output`
as JSON. **Read these before re-doing the work.**

| id | what it was | status |
|---|---|---|
| `w5qp6221v` | Initial adversarial audit: nine confirmed defects, six rated serious | current fix inventory is §5C; use it plus the final suite to state closure |
| `w5gzy32rc` | OMEGA lift survey, subsystem by subsystem, each candidate costed | **never acted on** — section 5E |
| `w1ume7jp3` | Reader panel 1 on the application — five personas. Verdict: none of five could name the deliverable. | acted on; drove the rewrite |
| `wl1cwxsvo` | Reader panel 2 on the rewrite. 4 of 5 could explain it from line 7. | acted on |
| `wbz5lcp9y` | Vocabulary clustering, 8 domains + reconcile | collected into `data/vocabulary/` |

The reader panels are re-runnable and cheap. If you materially change
`APPLICATION-FORM.md`, run one — both rounds found things no amount of
re-reading it myself would have.

### Commands worth knowing

```bash
python -m pytest -q                      # 779 tests, ~8s, no network
python scripts/check_form.py             # application answers vs the form's limits
python scripts/rescore.py                # accuracy, no model needed
python scripts/recover_years.py --fresh --sleep 0 --checkpoint-every 50 --out data/cache/dating/year_recovery.json  # warm-cache dating validation
python -m concordance.server             # the portal, port 8765
python -u scripts/run_batch.py --towns 12 --model gemma4:12b --timeout 900
python scripts/run_vocab.py --budget 1400 --per-stratum 1 --pages-per-doc 2 --max-strata 25 --out data/results/vocab_coverage.stratified.json
```

Note `data/results/` holds **two** vocabulary reports: `vocab_coverage.json` is
the old single-stratum run over water reports only (90% coverage, ~200 terms,
and misleading for exactly that reason), and `vocab_coverage.stratified.json` is
the real one. Do not quote the first.

---

## 9. How this project fails, which is worth knowing before you change anything

Two bug families have each recurred five or more times. When something is wrong
here, look at these first.

**A control stricter than the world, reporting a catastrophe nobody double-
checks.** The first accuracy figure was 49% precision and the extractor was
fine — the *scorer* could not tell that "3.0 million gallons" and "3000000
gallons" are the same number. A page counted as prose only if its lines held
eight words, which silently discarded a fifth of the archive. The bundle
verifier once disagreed with the ledger about table citations. The shared check
now fails closed: page/row/column headings are retained, but without localized
cell proof all current table claims abstain. The value check also once refused
correct readings of "I5 feet deep", because 1960s scanners write 1 as I.

**An identity missing a field, merging things that are not the same.** Dedup
compared a live record key against a stale stored one, so an instance re-imported
its own library as new. Parameter identity was `substance|measure`, so "Low
Daily Flow" evicted "average daily flow" from a chart. The dispute ledger's slot
omitted `kind`, so a regulatory limit was reported as contesting the measurement
it governs. The vocabulary has the same disease at extraction time: "golf course
size" and "golf course size previous" counted as two measurements.

**The tell for both:** a number that looks good because it was measured on the
easy case, or a number that looks catastrophic because the rule is narrower than
the archive. Check the control before believing the result — the work log
records each instance and how long it hid.

---

## 10. Map of the code

```
concordance/
  archive.py      fetching and caching archive.org items and pages
  router.py       per-page: prose / table / figure / map / standard / skip
  extract.py      the model call and the prompt        <- vocabulary goes here
  vocabulary.py   the archive's own measurement terms  <- new, needs its data
  parameters.py   substance + measure + statistic + scope resolution
  models.py       Record, Provenance, record_key
  contribute.py   bundles, verification, merge
  disputes.py     the ledger: settled / contested / unsupported
  citations.py    IIIF crops when available, with explicit full-page fallback
  science.py      series, trends, Series.sources
  units.py        conversion guards; MGD/Imperial normalization remains unresolved
  dating.py       deterministic document-date proposals; not wired into record periods
  numerals.py     numbers written as words, English and French
  server.py       the portal and the HTTP API
  portal.py       the page itself
  jay.py          the question-answering agent
scripts/
  run_batch.py    read many towns
  run_vocab.py    the stratified saturation sweep
  run_gold.py     accuracy against hand-read pages
  rescore.py      re-score without calling a model
  check_form.py   application answers vs the form's character limits
  share.py        export / import / push / pull readings
```

`WORKLOG.md` is the narrative record of what went wrong and when — it is the
best single document for understanding why the code looks the way it does.
`BACKLOG.md` holds smaller known items with time estimates.
