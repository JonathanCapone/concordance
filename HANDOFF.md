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
| Showcase | 28 Oct 2026, Vancouver |
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

**5,147 source-linked records across 14 municipalities**, 539 tests, zero required dependencies in
the core. Every published figure below is reproducible from the repo.

| | |
|---|---|
| Extraction precision / recall | 96.8% / 88.2% on 4 hand-read pages, 68 values |
| Kind accuracy (measurement vs design spec vs legal limit) | 98.3%, 60 matched values |
| Stream accuracy (influent vs effluent) | 88.9%, 18 judged pairs |
| Source-sentence mismatches in a 286-record audit | 0 |
| Table measurements recovered by the vision path | 535 from 24 pages, 11 collections |
| Dispute ledger | 1,445 settled / 129 contested / 88 unsupported |

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

- **Town batch** (`scripts/run_batch.py`) — reading municipal water reports,
  ~2 hours per town on this machine. Was on Belleville. Restart with
  `python -u scripts/run_batch.py --towns 12 --model gemma4:12b --timeout 900`;
  `--skip-done` is on by default so it will not redo finished towns.
- ~~Vocabulary workflow~~ — **finished and collected.**
  `data/vocabulary/vocabulary.json` holds 200 canonical terms and 1,812 aliases,
  covering 93.4% of the 5,479 observed readings, zero matching collisions. The
  reconcile pass's own notes are in `data/vocabulary/reconcile_notes.json`,
  including the pairs it deliberately refused to merge and the 15 judgement
  calls it wants a human to confirm.

---

## 5. What to do next, in priority order

### A. Finish the vocabulary (highest value, half-built)

The measurement above says this is *the* thing standing between "works on
municipal sewage reports" and "works on the Canadian public record".

1. ~~Build the vocabulary.~~ **Done.** 200 terms in
   `data/vocabulary/vocabulary.json`, loaded and matched by
   `concordance/vocabulary.py`. Verified: "average daily flow" resolves to
   `flow`, "Design Population" to `population`, and the two names the model
   invented — "cost estimate for one boiler at keith station", "width of
   strongly sheared rock" — are correctly flagged NEW rather than absorbed.

   **Every entry is `reviewed: false`.** Nobody has confirmed them. Start with
   the 15 questions in `reconcile_notes.json` and the `deliberately_kept_apart`
   list, which is where the dangerous judgements are (bod concentration vs
   removal vs exceedance frequency vs loading are four different measurements
   and three of them are percentages).

2. **Wire it into extraction — this is now the top task.** `concordance/extract.py` holds `SYSTEM`. Note
   that its current examples actively teach the failure — `"bus leasing share of
   budget"`, `"share of national steel production"` are invented per-sentence
   descriptions. Replace with: here is the vocabulary, choose from it, and if
   nothing fits say so and propose a term. Use
   `vocabulary.load().for_prompt(hint=<document title>)`.
3. **Measure that it worked.** Re-run the sweep and check `model_named_share`
   falls from 0.76. That number is the test.

Every entry carries `reviewed: false` until a person confirms it. Keep that —
the project's line is that the machine proposes and a human decides what a term
*means*, and it has been wrong about exactly this before ("BOD removal" vs "BOD
exceedance frequency" are both percentages and different measurements).

### B. Deploy a public instance (authorised, not started)

He chose this. Blocked on one thing only he can do: **a DNS A record**.

- Droplet `165.227.25.23`, Ubuntu 24.04, nginx + Let's Encrypt. Runbook and
  patterns in `C:/Users/jdcap/Documents/Projects/server-infra` — follow the
  Squishy Store pattern (systemd unit + nginx reverse proxy), not the static
  ones.
- Suggested host `concordance.jonathancapone.com`.
- **Vendor MapLibre first.** `concordance/portal.py` loads it from unpkg and
  pulls tiles from arcgisonline and an S3 terrain bucket. A CDN failure already
  took out all nine views once, and the showcase is on conference wifi.

### C. Remaining audit findings

An adversarial audit found nine confirmed defects; six were fixed. Still open,
from `data/results/` and the audit output:

- `library.ask` reports success and tells the user the data was kept when it
  read nothing.
- `/api/citation` degrades to a broken image with no explanation for 23 of 39
  cited documents.
- The maplibre CDN guard covers a fast failure but not a slow one — a hanging
  unpkg leaves all nine views inert.
- ~154 records store a facility or a piece of plant equipment where a town
  belongs ("digesters", "primary", "Site 1", "Lake Ontario"). Two problems
  mixed: facility strings that contain a town ("Brantford Water Treatment
  Plant") need splitting into place + facility, and genuine non-places should
  inherit the town from the file header.
- One request can trigger a large number of archive.org fetches; there is no
  rate limit on `/api/bundle`. Matters only once public.

### D. Application polish

- Two reader panels have been run (five personas each). The second said 4 of 5
  could now explain the project from the first two screens, up from 0 of 5.
  Their remaining asks are answered in the current draft.
- Not yet done: nobody outside the project has used it, and no institution has
  been approached. The application says so plainly in *"What I have not tested,
  and who has not used it"* — but **the cheapest possible win before the 21st is
  to make that paragraph untrue**: one email to Internet Archive Canada about
  the 13,429 metadata corrections, and five people from a town in the dataset
  clicking the button. A librarian reviewer named this as the single thing
  standing between "lean yes" and "yes".

---

## 6. How this project fails, which is worth knowing before you change anything

Two bug families have each recurred five or more times. When something is wrong
here, look at these first.

**A control stricter than the world, reporting a catastrophe nobody double-
checks.** The first accuracy figure was 49% precision and the extractor was
fine — the *scorer* could not tell that "3.0 million gallons" and "3000000
gallons" are the same number. A page counted as prose only if its lines held
eight words, which silently discarded a fifth of the archive. The bundle
verifier refused all 535 vision records because a table cites headings rather
than a sentence. The value check refused correct readings of "I5 feet deep",
because 1960s scanners write 1 as I.

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

## 7. Map of the code

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
  citations.py    IIIF crops of the sentence on the scan
  science.py      series, trends, Series.sources
  units.py        era-aware conversion, refuses incomparable readings
  dating.py       document year, and which year a reading belongs to
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
