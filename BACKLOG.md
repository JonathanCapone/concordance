# BACKLOG

Synthesised from seven audits and their refutations. Everything here survived a refutation pass; everything dropped is listed at the end with the reason, so it is not re-proposed.

Legend: **$** = must land before money is spent on the funded run (a prompt, schema, router or unit change afterwards means paying twice). Hours are the refutation-corrected estimates, not the audit's.

---

## BEFORE THE DEADLINE (21 Aug)

Ordered by (what it unblocks) × (chance it is wrong if left) / hours. B1–B9 are the cut line: if the days run out, ship those and nothing else.

### B1. Fix `score.norm_unit` before anything else touches the headline number — 30 min
`norm_unit` computes `u2 = u.replace(" per ", "/")` and then returns `u` (`score.py:35-65`). Six of sixteen current errors are that one line; patching it moves the stored gold set from 88.7/82.5 to 96.2/89.5 on four pairs that are numerically identical.
*Rationale:* highest value per minute in the repo — a four-line fix that un-depresses the one number the application rests on, and it must precede B3 or the re-run inherits the bug.
**Acceptance:** `norm_unit("pounds per month") == "lb/month"`; a regression test pins the four pairs (`2696 lb/month`, `258000 gal/month`, `125000 gal/month`, `600 gal/ft²/day`) as matches; `python scripts/rescore.py` on the stored records reports precision ≥ 0.96.

### B2. Micro-average `stream_accuracy`; delete the vacuous 1.0 default — 1 h
`score.py:174-180` returns 1.0 for a page with no stream-bearing gold and `:249` macro-averages it. A second gold document (`hamiltonadventur00unse`) with **zero** extracted records currently *raises* the published figure from 86.7% to 90.0%.
*Rationale:* one command (`rescore.py`) away from writing a flattering number into the file the portal serves; a control looser than the world in a public metric.
**Acceptance:** a page with no stream-bearing gold contributes 0/0; a test asserts that appending an all-miss gold page cannot increase `stream_accuracy`; the regenerated `gold_report.json` reports the micro figure.

### B3. Re-run the gold set on the current extractor, both documents, and republish — 4–6 h **$**
`gold_report.json` predates four `extract.py` commits including the prompt widening. `rescore.py` re-scores stored records, so it reproduces precision forever and cannot see the extractor move. A trial re-run gives 87.1/79.4 over four pages, **85.5% precision on the identical three pages**, and kind accuracy 98.2% — not the published 100%.
*Rationale:* the single number the application rests on, currently unreproducible; and re-measuring the widened prompt is the precondition for spending anything on it.
**Acceptance:** `gold_report.json` mtime > `extract.py` mtime and carries an `extractor_commit` field; the README and APPLICATION result tables are generated from that file, not typed; no document asserts kind accuracy 100% unless the file says so; the per-page table matches the file row for row.

### B4. Brantford's headline chart says "BOD removal · % = 1149", cited to a sentence about tonnage — 4–5 h
Three faults stacked: `parameters.resolve` collapses percentage-removed, tons-removed, cubic-feet-of-air-per-lb and percent-of-time-exceeded into one `bod|removal` key; `science.py:575-582` labels the series with the first parseable unit in record order (a rejected `%` record) instead of the majority (`cuft`); and `server.py` matches the source row on year + parameter + stream, which is not unique, so the quote belongs to a different number.
*Rationale:* the only unconditional wrong number on screen today, on a project whose entire argument is that publishing an unaudited bad number is worse than publishing nothing.
**Acceptance:** a test over every file in `data/results/` asserts no series labelled `%` contains a value > 100; `unit` comes from `normalize_series`'s majority and the dead loop at `:574-578` is gone; the row displayed beside a value contains that value's digits; Brantford's BOD panel shows the real percentages or nothing.

### B5. Exact place matching kills the project's flagship trend — 45 min
`server.py:297-298` and `tools.py:359` match `place` with `==`. Owen Sound's BOD-removal series is filed under three place strings, so the portal plots one point where three exist and `spark()` draws no line at all. 96 of 909 records are discarded this way. The static town page shows the trend; the live portal does not.
*Rationale:* "BOD removal rising from 46.4% to 64%" is the sentence both documents lead with, and a judge who clicks Owen Sound sees a single dot.
**Acceptance:** `/api/town` for Owen Sound returns BOD removal with `[(1963,46.4),(1964,46.4),(1969,64.0)]`; a test pins those three points; Brantford's `water supply system` records are still excluded from the wpcp panel by the facility split.

### B6. `portal/index.html` publishes 49% extraction precision — 30 min
The committed landing page is stale (rebuild gives 89%), and rebuilding does *not* fix its second error: `build_index.py:66-71` spans all 120 Owen Sound records including 33 drinking-water ones, so the card promises 1963–1992 while the page it links to shows 1963–1972.
*Rationale:* the most double-clickable file in the repo publishes the exact number the README exists to disown.
**Acceptance:** a test asserts the committed page's precision equals `gold_report.json`'s; the Owen Sound card reads 1963–1972; `build_index.py` uses the facility split already written in `build_town_page.py:118-122`.

### B7. Hoist `LOADERS` above the map construction — 10 min
One unreachable CDN request makes `maplibregl` undefined at `portal.py:489`, the inline script dies before `const LOADERS` at `:588`, and **all nine views** throw `ReferenceError` inside a swallowed event handler. Each panel keeps its heading and lede, so it reads as deliberately empty rather than broken.
*Rationale:* ten minutes converts "nine dead views on conference wifi" into "eight working views and no map"; it is the worst thing that can happen on 28 Oct and it is unguarded.
**Acceptance:** with the unpkg host unresolvable, every non-map view renders its data; exactly one console error; a note in the demo runbook.

### B8. Vendor `maplibre-gl.js` and `.css` into `groundtruth/static/` — 1.5 h
`build_portal.py:1` already states the lesson ("no server and no network — which matters for showing it on conference wifi"); it was applied to the static exports and not to the thing that gets demoed.
*Rationale:* removes the remaining network dependency in the demo path; separable from B7, which is the emergency half.
**Acceptance:** `grep unpkg groundtruth/` returns nothing; the portal renders fully with the network disabled after first byte.

### B9. `scripts/share.py import` tracebacks on any realistic bundle — 15 min
`share.py:104-111` strips the failed records but passes the original `verdict` (still carrying `failed`) to `merge_bundle`, whose gate rejects it. With `--verified-only` it raises `ValueError`; without it, it exits 1. The command is documented verbatim in the README and the sharing claim is in APPLICATION.md.
*Rationale:* a README-documented command that crashes, on the mechanism the fellowship's distribution claim depends on; fifteen minutes.
**Acceptance:** `python scripts/share.py import <120-record bundle> --verified-only` exits 0 and merges 116 records; without the flag it prints a message and exits non-zero with no traceback; `tests/test_share.py` covers both, and the success line reports `accepted`, not the non-existent `added`.

### B10. Publish the repository — half a day
`git remote -v` is empty. There is no URL in the README (`git clone <this repo>`), no `[project.urls]`, and nothing pointing anywhere. "Open source" is one of the four judging criteria.
*Rationale:* the artifact does not say where it lives, and the fix is a decision plus a leak check, not an edit.
**Acceptance:** `git remote -v` is non-empty; a fresh clone from that URL runs `pip install -e ".[dev]"` and `pytest` green; `git ls-files | grep data/cache` is empty; the README clone line is the real URL.

### B11. `scripts/stats.py`, and regenerate every count in all three documents — 1 h
Three files publish three different test counts (403 / 397 / 426 actual). Ledger figures are 736/78/17 published against 779/85/17 actual; "Documents read: 22" against 51; "Commits: 47" against 86. APPLICATION.md line 4 promises every figure is reproducible.
*Rationale:* the cheapest errors to catch and the most expensive to be caught at — a reviewer who finds the test count wrong reads the accuracy figure differently.
**Acceptance:** `python scripts/stats.py` emits the block; the three documents contain no hand-typed value for any figure it emits; running it twice on an unchanged tree gives identical output.

### B12. Rebuild the cost model — 5–6 h **$**
Six independent errors, all in the same direction: `table_pages = pages - text_pages` treats a multi-path router as a partition and discards the 7.45% of pages needing both calls; `PAGE_CHARS = 899` against a measured 2,897; `SYSTEM_TOKENS = 900` against 1,438 (and charges vision the same, where it is 372); `OUTPUT_TOKENS_PER_PAGE = 260` against a measured 493 (its own comment says 1,400); `VISION_OUTPUT_TOKENS = 900` against 1,360–2,908; figure/map-only pages billed at prose rates and credited 4.2 records each with no extractor. Corrected floor **$6,230**, not $4,251 — 1.5× the fellowship, not inside it. And `cost_model.py:163` still prints "Either fits inside a $5,000 fellowship" while APPLICATION.md says the opposite.
*Rationale:* two numbers the funding ask rests on, wrong by arithmetic a reviewer can redo from the repo's own file, in the flattering direction — inside the section whose whole persuasive move is "the number moved against me".
**Acceptance:** `cost_model.json` carries `calls_per_worth_reading_page`, a figure/map bucket yielding zero records, a storage/egress line (325 GB page cache, ~3 TB images), `days`, and `gpus_required_for_45_days`; the "either fits" line is deleted or conditioned; APPLICATION quotes the new range **and** the N×GPU wall clock ("8 × H100 ≈ 8–16 days, same dollars").

### B13. Re-run `corpus_census.py` under the current router and report two rates — 3 h **$**
Four values for the headline coverage statistic coexist: 0.5313 (`corpus_census.json`), 0.695 (`cost_model.py`, an unreproducible 8,372-page convenience sample presented in the README under a random sample's provenance), 0.531 (`search.py` default), 0.742 (routing the cache). And `worth_reading` counts pages routed only to FIGURE/MAP, which nothing consumes — 7.81% of the total.
*Rationale:* a reviewer who opens the only census artifact finds 53.1% under a published 69.5%; and this is the multiplier the funded page count is derived from.
**Acceptance:** the census reports `worth_routing` and `has_a_built_path` separately with Wilson intervals, the sample size and the seed; the README coverage table is generated from that file; `grep -rn "8,372\|8372"` returns nothing.

### B14. Fix the vision fabrication control and publish the honest number — 3 h
`vision_trial.rescore()` is unreachable (`__main__` dispatches `main()`, which parses `argv[1]` as an int), so the stored control is stale and reads 151/192 where the current control gives 191/192 — and that stale figure was just promoted into APPLICATION.md as "79%". But 99.5% is not publishable either: a null model of invented numbers scores 74.9% on 1–3 digit values and 2.3% on ≥4 digits.
*Rationale:* "the tables were never lost" is the strongest sentence in the application and the reason the ask is $4,251 rather than $1,510; the published evidence currently reads worse than reality, and the obvious rebuttal is unanswered.
**Acceptance:** `python scripts/vision_trial.py --rescore` runs and the file's stored control equals a recomputation; the published claim is "99.0% of the 105 values with four or more significant digits appear on the page, against a 2.3% chance baseline"; `grep -rn "58 of 58"` and the "every one of the twelve … exactly" sentence are gone (the artifact says 10 of 12).

### B15. Scope the success metric, add the week table, add BC — 3 h
$5,000 against $4,251–8,502 (really $6,230–12,461 after B12) buys 59–118% of the corpus, and the metric says "any Canadian community … not a sample — every one" with no named fallback. The work plan opens by declining the week-by-week format the fellowship asked for. And BC appears **once** in the entire repository, as an unsupported and low count (468 against 556 items, including 27 from BC's own Water Management branch), for a BC fellowship with a Vancouver showcase.
*Rationale:* "achievable" is a judging criterion assessed in exactly this section, and a metric the budget cannot reach reads as arithmetic not done.
**Acceptance:** the metric names a reduced target costable from `cost_model.json` with the full read as stretch; a six-row week table sits under the arcs with one deliverable each; the BC count comes from a script, and a paragraph says what reading BC's 556 items would unlock.

### B16. Add `kind` to the dispute slot key — 1 h
`SLOT_FIELDS` omits `kind`, so an observation and the design spec it is being compared against share a slot: Brantford's 185-vs-170 "dispute" comes out of one sentence that *states the relationship*. Contested drops 65 → 54, and 0 of the 20 kind-mixed slots have a null on either side, so this half is unambiguous.
*Rationale:* a headline number where a third of the contested count is the project's own named identity bug; one tuple.
**Acceptance:** a test asserts a design and an observation never share a slot; the regenerated ledger reports 54 contested; the published counts come from B11's script.

### B17. The Disputed view is unusable cold and lies offline — 2 h
`disputes.py:216-217` never caches a failure, so 1,101 claims over 48 identifiers make 1,101 fetch attempts instead of 48; cold first paint is ~204 s; and `Slot.state` reports an unreachable page as `unsupported`, so a bad network prints "every measurement unverifiable".
*Rationale:* the most original thing in the project, whose failure mode is a giant table announcing a catastrophe — the exact pathology the application is about.
**Acceptance:** with the archive unreachable, `pages()` is called once per identifier and the report shows `unreachable: N` distinct from `unsupported: N`; the view pre-warms in a background thread at startup and first paint is under 5 s.

### B18. Show the caveats the `Series` object exists to carry — 2 h
`server.py:350-354` publishes `label/unit/points/rows` and drops `assumptions`, `rejected` and `suspect`; `tools.py` publishes two of three and drops `suspect`. `find_suspect_readings` fires today on Owen Sound's 1968 flow (`"144:2. 50 million gallons"` — a scan digit-drop) and the portal charts the corrupted point with no warning. Six such warnings exist across four towns. The Imperial note embeds the year, so a 40-year series accumulates 40 near-identical strings.
*Rationale:* a control that works, whose output nobody can see, on the surface that is the whole public argument.
**Acceptance:** Owen Sound's 1968 point renders with its scan-damage warning; a 40-year gallons series shows one Imperial assumption; a series with n < 2 prints "one reading only — not enough for a trend" instead of a bare heading.

### B19. Stop presenting a 41-way tie as a ranking, and drop the non-places — 1 h
`ranked_places` yields four distinct scores over 123 places; the served top-15 is the first 15 of a 41-way tie in `silence_report` file order — which is sorted by number of surviving reports, i.e. exactly the "size" the caption says it is not ranking by. 19 decision questions occupy positions 1–19 and 14 of them are not municipalities (`digester`, `ODWO`, `aeration section`, `Massey Ferguson Company`).
*Rationale:* the frontier's own caption is falsified on screen by the list underneath it, on a view a judge clicks early.
**Acceptance:** every ranked place resolves via `places.resolve` with kind in {city, town, village, township}; the caption states the tie size honestly ("41 places are equally good next reads; here are 15"); a test asserts no ranked place fails to resolve.

### B20. `Ledger.add` invents people — 30 min
`report()["people"]` counts anything matching role + capitalised token: 70 of Hamilton's 122 and 123 of Kingston's 261 have zero appearances (`MAY`, `FINANCE`, `AGENDA`, `Secretary`). *Correction to the audit:* they never reach `most_active`, which sorts them last — the corruption is confined to one published integer.
*Rationale:* WORKLOG's "64 people from one volume" is roughly half non-people; the fix is a gate on `appearances > 0`.
**Acceptance:** `report()["people"]` counts only people with at least one appearance; Hamilton returns 52; a test pins it.

### B21. One truth-in-labelling sweep — 1.5 h total
Nine small items, each a wrong statement rather than a wrong computation: Jay and the portal advise `ANTHROPIC_API_KEY`, which `Jay._chat` never reads (10 min — message only); `search.effort()` computes with `worth_reading=0.531` while its own note says 69.5% and 91 s (10 min); the declared console script `ground-truth-gold` cannot import after `pip install -e .` from anywhere, inside the repo or out (15 min); the README should say `pip install -e ".[dev]"` since plain install brings no pytest (2 min); `groundtruth/static/portal-maplibre.js` is 14 KB of dead Leaflet-era code from another project (2 min); `vision_trial.py:245`'s `med = lambda xs: xs[len(xs)//2]` is not a median (15 min); `library.ask` reports "No documents in the collection match that" when the *title filter* emptied it — true for 33 of 104 frontier places, including Midland's 19 documents (15 min, message only); `/api/read` calls `STATE.reload()` but not `invalidate_ledger()`, so a town you just read still shows as unread (5 min); `jay._what_is_disputed` loads 909 claims where the server loads 1,101 (5 min).
*Rationale:* each is a sentence the software says that is not true; together they are 90 minutes and they are what a careful reader trips over.
**Acceptance:** a checklist of nine, each with the grep or command that shows it fixed.

---

## THE SIX-WEEK BUILD (1 Sept – mid Oct)

Ranked the same way. The **$** items are gates on the funded run — schedule them into weeks 1–2 and do not start the run until they are all green.

### S1. Real-corpus fixtures for the router tests, then the router fixes — 14–20 h **$**
Both TABLE tests use `"\n".join(f"{i} 12.4 88.1 0.03 447 91.2 6" for i in range(30))` — thirty rows that survived OCR intact, which is precisely the case the vision path does not exist for. Real median numbers-per-line is 1.0 on TABLE pages and 0.0 on SKIP. That test is why the rest of this item stayed invisible through 426 passing tests. Then, in order: (a) the FIGURE/MAP routes shadow the prose fallback because `not paths` is non-empty — 2,231 cached pages (~989k corpus-wide) of dense engineering prose blocked by the word "curve"; (b) a `cell_ratio` signal rescues 2,575 pages carrying ≥20 numbers each; (c) `ocr_confidence` is on the object, free, and the router never reads it (SKIP median 0.442 vs TABLE 0.738) — it is the same piece of work as (b), not a second one; (d) tighten `FIGURE_RE` to a caption shape, which is most of (a)'s tail.
*Rationale:* the largest quantified block of unread data, gated behind a test fixture that guarantees any fix gets tuned against a shape the corpus does not contain — and it decides which pages the money pays for.
**Acceptance:** two fixtures taken verbatim from `data/cache` (`labourgazette1963cana` p943, `1915v50i24p30_1137` p16) assert TABLE, the synthetic case kept as the clean-scan control; page 84 of `1909v43i10p19a_0574` routes to prose; a hand-labelled 200-page sample gives the new TABLE gate's precision and recall; the census re-run reports the new shares.

### S2. `Archive.pages()` fails open to one whole-item page — 3 h + 4–6 h of tests **$**
`_parse_djvu_xml` returns the same `None` for "no XML in metadata" and "fetch failed after 4 attempts", and `_fallback_pages` then returns the entire item as one `PageText(page=1)`, of which `extract_prose` reads 12,000 characters. Mean `_djvu.txt` is 420 KB, so **~2.9% of the document is read** with wrong provenance, no log, no counter. It hit 4 of 120 items in the census's own random sample — one at 1.0% of a 377-image *Journals of the House of Commons*. And there is no `test_archive.py` at all: zero tests exercise `Archive`.
*Rationale:* the single mechanism by which the funded run can spend $6,000, appear to succeed, and produce a dataset with an unknown number of documents 97% unread and mis-cited — undetectable afterwards.
**Acceptance:** a test with a stubbed `_get` that raises asserts no fallback page is produced; the two `None` cases are distinct; a run-level counter of degraded items appears in the output; `tests/test_archive.py` covers the retry ladder, the 404 case, cache hits, page numbering across blank pages, and a truncated cache file.

### S3. Atomic writes and guarded cache reads — 2 h **$** (JSONL deferred)
Every cache write is a bare `write_text` and every read parses with no guard. Reproduced: truncating `owen-sound.json` makes `load_done` raise and the town unresumable; truncating a `meta/*.json` makes the item permanently unreadable and never re-fetched. `archive.py:78-79` promises "a run that dies in hour nine resumes in second one."
*Rationale:* a 40-hour rented-hardware job will be interrupted, and today an interruption at the wrong instant destroys the output or poisons a cache entry forever.
**Acceptance:** one `_atomic_write` (`.tmp` + `os.replace`) used by every writer; every cache read falls through to re-fetch on `JSONDecodeError`; a test truncates each of the three file kinds and asserts recovery.

### S4. Pacing in the adapter, not in the callers — 2–3 h **$**
`Archive._get` has no inter-request delay, no jitter, no `Retry-After`, no 429/503 handling, and a 15 s retry ceiling that any real throttle window outlasts — which is exactly how S2 gets triggered en masse. *Correction to the audit:* pacing is not absent from the project — `providers.py:207`, `recover_years._PoliteDelay` (with tests) and `corpus_census --sleep` all exist. The decision is made and documented; it just is not in the layer a funded run uses.
*Rationale:* ~5M requests against a nonprofit that is also the fellowship's co-sponsor; getting blocked mid-run is a plausible way to lose the money.
**Acceptance:** a token-bucket limiter with configurable rate and jitter in `_get`; `Retry-After` honoured; a distinct throttling exception so callers can pause rather than degrade; a test asserts N requests take at least N/rate seconds.

### S5. Work sharding — 12–16 h **$**
`run_batch.py:3-5` states the run is deliberately serial. The corrected model is 85–169 GPU-days against a ~45-day build window; nothing in the codebase runs two GPUs, and there is no shard, lease or merge concept anywhere.
*Rationale:* without this the funded run cannot finish before the showcase at any price; with it the dollars are unchanged and the schedule works.
**Acceptance:** a manifest of page ranges with atomic claim/complete markers that survive the interruption in S3; N workers on one manifest produce the same records as one worker; a documented 4 × H100 ≈ 3-week plan matching B12's numbers.

### S6. The French decimal comma — 1 h **$**
`_to_float` strips commas: `"12,4"` → 124.0, `"0,85"` → 85.0. 15.0% of items are French or bilingual. *The audit's fix is wrong* — 69% of those are `eng+fre`, and branching on the item's language destroys `53,549.66` in the adjacent column of a bilingual StatCan table. Shape-based on the numeral (`\d+,\d{1,2}` not followed by a period = decimal comma; `\d+,\d{3}` = thousands) separates both sets cleanly and needs no language field. And `_to_float` also parses the **confidence** field, so `"0,85"` → 85.0 → clamped to 1.0: a hedged record promoted to maximum confidence, deterministically.
*Rationale:* the only defect that produces *wrong numbers* rather than missing ones, in a public dispute-ledger dataset, latent until the run touches French.
**Acceptance:** the parametrised test in `tests/test_core.py` covers `12,4 / 5,1 / 0,85 / 1 234,5` alongside `53,549.66 / 1,234 / $36.30`; confidence parsing is separated from value parsing and clamped before, not after.

### S7. One Imperial rule, and the four spellings of MGD — 5–8 h **$**
`parse_unit("mgd")` → 1,200,950 gal/day; `"million gallons per day"` → 1,000,000; `"mg"` → ×1.0; `"million Imperial gallons per day (MGD)"` → refused. Same base unit, so `normalize_series` rejects none. Live in Owen Sound: a flat plant reads as a 1965 spike, and Burlington Drury Lane's 1962 report carries three of the four spellings for one quantity. The era guard exists only in the volume branch and is absent from flow, which is the corpus's most common quantity — and the volume branch splits too (`Imperial gallons` vs `gallons` at era 1967). Also `_AMBIGUOUS` covers `mg` but not `MG`/`million gallons`, so "average daily flow of 0.645 million gallons" is filed as a volume.
*Rationale:* every published flow trend and changepoint is unreliable until this lands, and re-deriving them after the run costs the run.
**Acceptance:** a property test asserts every spelling of one unit yields an identical `Quantity`; the era rule is applied identically to volume and flow; `parse_unit` accepts the four MGD spellings, `gallons per minute`, `cubic feet per million gallons`, `pounds per million gallons`; Owen Sound's daily-flow series is flat across 1963–1967.

### S8. Widen `parse_unit` to the units the prompt mandates — 8–12 h **$**
22 of the 27 units `extract.SYSTEM` explicitly instructs the model to produce return `None` (`schools`, `$/month`, `bushels/acre`, `pupils`, `beds`, `dwellings`, `hectares`, `acres`…). `Record.problems()` was widened; `parse_unit` was not; `normalize_series` silently excludes the record from every chart it belongs on. Already biting: 182 of 1,325 records on disk (13.7%). `lbs/100 lbs` is dimensionless and `cubic feet per million gallons` is volume/volume, so this touches `Quantity` and `comparable()`, not just a lookup table.
*Rationale:* the education, housing, agriculture and health data the prompt widening exists to capture is unplottable, so the widening's benefit is invisible — and the widened prompt is what the money buys.
**Acceptance:** a test asserts every unit named in `extract.SYSTEM` parses; the counted branch reuses `models._COUNTED_PARAMETER`; the unparseable share of `data/results/*.json` is under 2%.

### S9. Thread `place`, `facility` and `period` into the vision path — 2 h **$**
`vision.py:357-378` constructs `Record` without `place=` or `facility=`. All 207 table records on disk have both `None`; 17.4% have no period. The dispute slot key is `(place, facility, parameter, unit, period, stream)`, so StatCan salt and Alberta liquor collapse into `'||total production|tonnes|january 2002|unknown'`. Zero collisions today, on the path costed at ~61% of all measurements. The item metadata is already in hand at `vision_trial.py:164` and `backfill_facility.py` already derives facility from the title.
*Rationale:* the identity family, third instance, on the path that will carry most of the data — at scale it manufactures contradictions systematically, and it makes 61% of the dataset invisible on the map.
**Acceptance:** no record in `data/results/` has a null place; a test asserts two table records from different documents never share a slot; the portal map shows a table-sourced place.

### S10. Un-quarantine the vision path — 3–5 h **$**
219 vision records exist and **no consumer reads them**: three divergent skip lists (`tools.py`, `frontier.py`, `disputes.py` — the last excludes `vision_trial*` by name). So `disputes._check_cell`, `_page_can_referee`, `_label_on_page` and `_value_in_damaged_quote`, all written and tested for table readings, have never seen a real claim. `contribute.verify_bundle` has no cell branch either, so **0 of 192** vision records can pass verification or travel in a bundle.
*Rationale:* S9 is pointless without it, and the 27% of the corpus the project's own figures call the data-dense half currently has no way onto or off any machine.
**Acceptance:** one skip list in one module; the ledger's claim count includes the table records; `verify_bundle` verifies a table-cell record; a bundle containing vision records round-trips through `share.py`.

### S11. `library.ask` writes what verified and says what it did — 5–6 h
`ask()` gates the library write on `verdict.accepted`, which requires **zero** failures. At 88.7% precision that never happens: Owen Sound verifies at 96% and is discarded whole. Meanwhile `Answer.describe()` unconditionally says "they are in the library now". Two contributing faults: `verify_bundle` lacks the `_value_in_damaged_quote` fallback the ledger has (25 of 43 failures are the scanner's crime, not the extractor's — `'a maximum of 3ol7 MGD'`), and `library._held` short-circuits on the first matching record so one reading blocks the other twenty reports for that town forever. There are no tests for `library.py`.
*Rationale:* the front door of the contribution model is a no-op that tells the user otherwise — the one thing that cannot be allowed when you are asking a stranger for an hour of electricity.
**Acceptance:** a stub-extractor test produces a 96%-clean bundle and asserts a file appears in `LIBRARY` with the failures listed in the answer; `describe()` reads `self.contributed`; `_held` checks year coverage before short-circuiting; `tests/test_library.py` covers hit, miss, clean read, partial read. Resolve the contradiction between `contribute.py:68-73` and `share.py:93-101` — keep all-or-nothing for a stranger's bundle, partial for a local read — and delete the losing comment.

### S12. `Corpus.load_dir` reads `data/contributions` — 1 h
An accepted human correction verifies, is stored, is reported "on the same footing as everything else", and changes nothing a reader sees — it appears in the ledger view and nowhere else, on any machine, including the contributor's.
*Rationale:* one of the three things the dispute module promises, currently inert; one line, plus the vision-file shape from S10.
**Acceptance:** submitting a correction changes the town chart without a restart; a test asserts the corpus record count rises.

### S13. Guard the catalogue year, and call `period_risk` — 5 h + 3 h **$**
`repair.py:118` skips any item that already has a year, so the entire *Public Accounts of Canada* run catalogued as **1852** with 1993 in its title stays wrong (350 items contradict their own title by >5 years, 74 by 90+). Then `library.py:155` and `scripts/fix_periods.py:29` write that catalogue year into records' `period`. Separately, `dating.py` is 45 KB and no extraction path calls it: `period_risk` has no non-test caller and `Record.comparability_note` exists unused, so the ledger keeps re-deriving as "contested" what a free deterministic function already flags.
*Rationale:* a wrong year is strictly worse than a missing one — the frontier, the silence detector and the 1975 cliff all build on it — and the money buys 1,904 public-accounts items filed under 1852.
**Acceptance:** a `contradicted_year` proposal kind with the title as evidence; `fix_periods.py` and `library.ask` refuse a catalogue year that the title contradicts; `period_risk` runs at record construction and writes `comparability_note`; Brantford's 16 year-less periods are either anchored or recorded in `Series.rejected`.

### S14. The scorer never looks at the parameter — 8–12 h
The match key is `(value, normalised unit)`. Rotate three labels onto the wrong parameters and the page scores 100% precision, 100% recall, 100% kind, 100% stream. Fixing it needs `parameters.py` work first: 5 of the 6 substance conflicts on the current gold set are resolver artefacts, and `_FREQUENCY` matches `exceeded` but not `exceeding` — so "BOD exceeding objective 20%" is filed as 20% BOD removal, the exact inversion the guard was written to prevent, with the test passing because it asserts on the annotator's phrasing rather than the extractor's.
*Rationale:* the headline measures "did we find the right numbers on the page", not "did we produce the right records"; do it before the run so the number that grades the run means something.
**Acceptance:** substance agreement required where both sides resolve, value-only fallback where either does not; `_FREQUENCY` matches the extractor's own output and a test uses the extractor's phrasing; the gold set is re-scored under the new rule and the change is published.

### S15. Parameter identity needs a dimension — 3 h **$**
`resolve()` collapses fraction-removed, mass-removed and air-per-unit-removed into `bod|removal`. B4 fixes the symptom on one panel; this fixes the identity so it cannot recur across the corpus.
*Rationale:* fourth instance of the identity family, and at corpus scale it silently rejects the real values in favour of whatever is most numerous.
**Acceptance:** `resolve()` returns a dimension; a series never mixes dimensions; the test from B4 generalises to every file.

### S16. `decisions.py` fabricates divisions, and its control cannot fire — 5 h
Kingston's volumes carry mirror-image bleed-through OCR; `_split_names` turns a 200-character run of noise into one person and `_plausible` has no length or word cap. Every one of Kingston's 96 divisions is fabricated (670 invented voters), and the module reports `rolls_that_do_not_reconcile: 0` because `Roll.agrees` returns `True` when there is no stated tally — which is 100% of Kingston's rolls and 117 of 254 corpus-wide. The docstring calls that count "the control".
*Rationale:* a control that cannot fire, issuing a clean bill of health over invented divisions, in the module the README calls free, deterministic and checkable. **This is a prerequisite for S17, not a follow-on** — fix S17 first and this is what ships.
**Acceptance:** a roll with no stated count is `unverified`, never `agrees`; `_plausible` caps a name at ~28 chars and 2 words; a division must sit near a motion, an outcome word or `Recorded vote`; Kingston reports 0 rolls, not 96, until the guards pass; `read_page` consults `ocr_confidence`.

### S17. `MOTION_RE` requires "and", so it returns zero outside Hamilton — 2 h
Kingston writes `Moved by Ald. Keyes, Seconded by Ald. Matthews, That …`. Making `and` optional and adding `Ald./Coun./Cllr.` to `ROLES` takes Kingston 0 → 169 and 0 → 204 with Hamilton unchanged, and across 125 cached items 1,374 → 2,430 motions (+77%). It also exposes a live identity split: `Ald. Cook` and `Cook` are different people today.
*Rationale:* the largest untouched stratum (13,604 items) is unreadable everywhere but one city, and the module *reports zero* rather than failing.
**Acceptance:** both clerk styles parse; `Ald. Cook` and `Cook` collapse to one person; `tests/test_decisions.py` covers both volumes; S16's guards are green on the output.

### S18. `minutes_for(place, years)` as a Jay tool — 1 h
`_who_decided` requires the caller to already know an Internet Archive identifier, and no place → minutes lookup is exposed. `search.search_archive` already does the retrieval correctly (top 8 results for "Kingston council minutes" are all Kingston minutes); it is simply not in `build_tools()`.
*Rationale:* one wiring job turns S16+S17 from a parser into an answer, and 8 municipalities have both water reports and minutes.
**Acceptance:** Jay answers "who voted for Kingston's sewage plant" by reaching `kingstoncouncilmin69_1` unaided; a test asserts the tool returns Kingston volumes for "Kingston".

### S19. The deliberative-record pass — 1 overnight, paced
Hamilton has 377 council items 1924–2004; Kingston 119 volumes 1899–1980 overlapping its water-pollution-control-plant reports on **nine** years (1965–1974). Parsing is ~0.7 s per 1.2 M-char volume, but `_djvu.xml` is 13–15× the text, so this is ~2.5–3 GB of download, not "114 seconds of CPU" — it needs S4's pacing and S2's fallback guard, and it must not run before S16.
*Rationale:* "here is who voted for your city's sewage plant, and here is what it discharged for the next ten years" is the only deliverable that is useful, imaginative, open source and achievable at once.
**Acceptance:** a complete named voting record for two cities, every division reconciled or marked `unverified`, each linked to its page; both halves visible in the portal on one screen.

### S20. Sub-annual periods, and the majority unit — 4–6 h
`science.py:567` truncates the period to `[:4]` and then keeps one reading per year by confidence, so a year of monthly monitoring becomes one point and 36 monthly readings report "only 3 readings; need 6". Bare month names raise `ValueError` and are dropped with no record — 16 in Brantford, and they are the trace-contaminant readings the corpus is widening into (`'October' Atrazine 520 ng/L`). `trend` already accepts float time; `changepoint`, `find_suspect_readings` and `silence` assume integers.
*Rationale:* it suppresses the densest data the project has and drops the vocabulary it is expanding into, silently.
**Acceptance:** sub-annual points survive as fractional years; unparseable periods appear in `Series.rejected`; a test asserts a 36-reading monthly series produces a trend.

### S21. Fold `raw` into `influent` — influent leg only — 1 h
Owen Sound BOD influent goes n=1 → n=4, years `[1969]` → `[1967…1970]`; Brantford and Burlington SS 1 → 3. **Do not fold `treated` into `effluent`**: it gains zero points and 63 of Brantford's 71 `treated` records are drinking water, so a symmetric map merges tap water into sewage effluent.
*Rationale:* it suppresses exactly the influent-vs-effluent story the data model exists for, and it unblocks `downstream.MIN_OVERLAP`.
**Acceptance:** a `STREAM_SYNONYMS` map applied at the filter covering `raw`→`influent` only; a test asserts Owen Sound BOD influent has four points and that no series mixes a `water supply system` facility into an effluent panel.

### S22. Watershed ties sever the chain — 1–2 h
Links form only between consecutive entries sorted by drainage area, so a tie skips a link and everything above it is severed with no warning. Five of the real river groups tie: `who_was_upstream('Chatham')` returns `['Westminster Township']` and **Ingersoll disappears**; Holland R. E. Branch and St. Clair produce no links at all.
*Rationale:* "whose effluent was in your drinking water" is the demo, and it names one of two upstream dischargers with a `confidence: "likely"` label.
**Acceptance:** ties emit both links or a warning naming the tied plants; a test covers a three-way tie; Chatham's answer includes Ingersoll.

### S23. Accent folding, French router regexes, French titles — 4 h **$** (router part)
`parameters.resolve` replaces accents with spaces (`"température"` → `"temp rature"`), so even terms whose French spelling differs only by an accent fail — 30 minutes with NFKD, and it is most of the value available today. `COUNTED_RE` matches 0 of 10 French counted phrases and `STANDARD_RE` 0 of 7 regulatory ones, so French pages fail the unit gate and fall to the fallback S1 unshadows. `library.ask` and `run_batch` filter on `"annual report"` (5,588 items) and miss `"rapport annuel"` (363).
*Rationale:* 15% of the collection, and the headline claim is to read *Canada's* public record; these three are bounded edits, unlike the vocabulary work below.
**Acceptance:** `resolve("température")` resolves; the three router regexes match the tested French phrases; the title filters include the French forms; a French page routes to prose.

### S24. `record["place"]` admits things that are not places — 3–4 h
`read_places` contains `digester`, `primary`, `ODWO`, `Site 1`, `Massey Ferguson Company`, `Lake Ontario`. `library._held` substring-matches this field, so `ask("primary")` returns a library hit and `ask("Burlington")` never reads Burlington Skyway. `_towns()` *creates* two of them by stripping "treatment plant" off "secondary treatment plant". Separately, `silence_report` holds truncated names (`'Moosonee Water Supply System And'`) that can never match a title.
*Rationale:* the identity family one level up — the field exists but admits non-identities — and it is the root cause under B19, which only masks it.
**Acceptance:** `place` is validated against the gazetteer at record construction with a fallback field for the unresolved text; a test asserts no place in `data/results/` fails `places.resolve`.

### S25. The frontier's universe is 107 English water-plant titles — 3–4 h
`silence_report.py:33-38` requires the literal `water pollution control plant`; `frontier.build()` takes its coverage from exactly that. So "what is still unread" is defined over 107 towns selected by one English title shape, not over the collection.
*Rationale:* this is the filter whose output really does get recorded as an archive gap, and it caps the frontier's imagination at one province and one subject.
**Acceptance:** the silence report's title patterns are configurable and cover at least water, sewage and their French forms; `n_municipalities` rises and the increase is attributable to named title patterns.

### S26. A read button on the frontier — 1 h (after S11, S24, S25)
The frontier says what to read next and offers no way to read it; the only `/api/read` button lives in the map dock. **Sequence it last of the three** — wired today, roughly half the buttons would produce a false "No documents in the collection match that."
*Rationale:* the join between the two halves of the imaginative claim, and the cheapest fix on the list once its prerequisites land.
**Acceptance:** every row in "Read this next" has a working button; clicking one produces records in the library and the row disappears on reload.

### S27. Single-flight lock on `/api/read`, and ship or announce the 42 MB index — 2 h
First click blocks on a 42 MB catalogue download (47.5 s measured) while the UI says "Working through the scans". `dockBody.innerHTML` rebuilds a fresh enabled button on every dot click, so reopening a town starts a second concurrent extraction on one GPU, starving Ask Jay.
*Rationale:* an enthusiastic visitor clicking dots is the most likely single event on 28 Oct, and its worst case is a saturated GPU for the rest of the session.
**Acceptance:** a second read for the same place returns 409; the UI states the first-read download; a test asserts concurrent calls produce one run.

### S28. `projection` as a record kind — 8 h **$**
`RecordKind` has four literals and neither prompt mentions forecasts. *Population Projections for Canada and the Provinces 1972-2001* (published 1974) has a table captioned "Enumerated and Projected Population … 1971, 1976, 1981, 1986 and 2001" — actuals and forecasts under adjacent headings. The vision path reads them all as `kind="observation"`, `period="2001"`: a fabricated 2001 census datapoint sourced to a 1974 document, with a verbatim quote, a page link, and every guard passed. 147 items state a horizon more than three years past their own publication date. `Record`/`Provenance` carry no publication year, which is why this is 8 h and not 4.
*Rationale:* the `design`/`observation` trap at thirty-year scale, on a prompt change that must precede the money; and it is the precondition for S30.
**Acceptance:** both prompts name the kind; `Record` carries a publication year; `kind == "observation"` with `period` > publication year is a rejection, not a record, with a test.

### S29. Streaming `pages()` and index memoization — 8–12 h + 30 min **$**
`_parse_djvu_xml` holds the raw XML, a second full copy from `re.split`, and the accumulated words simultaneously: 458 MB peak on a 43.7 MB item, and the largest `_djvu.xml` in the collection is 119 MB. `with_words=False` still costs 8.25 s and 367 MB because it deserialises every word list and discards it. `load_index` re-parses 41 MB (4 s, 167 MB peak) on every call, five times in `silence_report` alone.
*Rationale:* decides whether more than one worker fits on a rented machine, and one 119 MB item can OOM a shard.
**Acceptance:** `with_words=False` never materialises word lists; peak RSS on the 43.7 MB item is under 150 MB; `load_index` is memoized and `Archive().load_index()` in `search.py:183` hits the cache.

### S30. The cross-domain question: design population against census population — 12–14 h
103 population/capacity records are already on disk and unused — Owen Sound designed for 25,000, a town of ~18,000, "operating above design capacity 80% of the time". The other half is the census items, and `places.py` already reconciles municipal names across 150 years of renaming, which is the hard part. Needs S9/S10 so the census tables reach a consumer.
*Rationale:* the cheapest question requiring two document families, producing a per-town per-decade answer — and the only item that moves beyond deepening a stratum that is already 100% of the readings.
**Acceptance:** an `overload` question kind in `frontier.py`; at least three towns show design population against measured population with both pages linked.

### S31. Generalise `places.py` beyond Ontario, and read one BC series — 8–16 h
`places.py:102` loads `cgn_on_places.csv`, raises "Ontario gazetteer is missing", and hardcodes `province="ON"` in four places; `build_gazetteer.py` hardcodes the Ontario CGNDB URL. Putting a BC town in the portal is not one document of extraction.
*Rationale:* the fellowship is in BC and the showcase is in Vancouver; 27 of BC's 556 items come from its own Water Management branch, which is the exact genre the extractor was validated on.
**Acceptance:** the gazetteer loads two provinces; one BC municipality appears on the map with a read series and a working "show the page".

### S32. The forecast ledger — 4 h after S28
One sentence per forecast: "In 1974 the Government of Canada projected X for 2001. In 2001 it measured Y." Both halves deep-link to the scan.
*Rationale:* the most arresting claim available, and after S28 it is nearly free; keep it last because it depends on everything above it.
**Acceptance:** at least five forecast/outcome pairs published with both pages linked and the projection scenario named.

---

## WHAT SHOULD NOT BE DONE

- **A French `VOCABULARY` block** (15–25 h, not the audit's 6–9). `models.py:204-207` already argues in-repo that extending a vocabulary per domain is the wrong repair. Do the 30-minute accent fold (S23) and re-measure; decide by harvesting from a French stratum, not by hand-writing terms.
- **A figure-digitisation extractor** (20–30 h). Path D's real target is ~57,000 pages once `FIGURE_RE` is tightened to a caption shape, not the ~1.8 M the route count suggests. It is a nice-to-have, and saying so before the run stops the application promising a path sized from a regex that mostly matches the word "figure" in a sentence.
- **Ink-coverage plate detection.** Page `W`/`H` is cached and free (4–6 h for aspect ratio plus word count, worth doing inside S1); ink coverage needs ~6.6 TB of page images from the charity whose bandwidth `archive.py:160-167` is explicitly designed around not spending.
- **`qualifier` in the dispute slot key.** 16 of the 21 qualifier-mixed slots differ only because one side is null — adding it would silence 16 genuine disagreements by filing them as settled. Normalise the extractor's qualifiers first, then revisit.
- **Committing a page cache for the Disputed view.** Text-only is 9.7 MB but `State.ledger()` reads the same file with `with_words=True` to build the crops, and "the crops are the point". It also reverses an explicit gitignore decision. The failure-cache and pre-warm in B17 get the demo benefit without it.
- **JSONL as the extraction output format now** (8–12 h and it changes the format read by nine modules). Ship the atomic writes in S3 and defer.
- **A tool-calling Anthropic path in Jay** (3–4 h, not 1.5). Fix the message that promises it (B21) and leave the path alone unless the local model becomes the demo's bottleneck.
- **The tribunal reader for Environmental Assessment Board hearings** (16–20 h — `moved by` occurs zero times in the target, so it shares no pattern with `decisions.py`). It is the best lens in the pile and it does not fit six weeks alongside S1–S19. Name it in the application as future work.
- **Changing `RECORDS_PER_TABLE_PAGE`.** With 11 completed trial pages the median is 20 and the mean 17.45 against a constant of 18. The proposed correction to 25.5 rested on eight pages and reverses with more data.
- **Demoting `township`/`concession` in `MAP_RE`.** The 43 early-MAP pages are mostly genuine survey maps and zoning schedules whose "numbers" are bearings; the remedy would break the boundary descriptions that are Path E's actual material, for 0.09% of pages.

---

## DROPPED, AND WHY (do not re-propose)

| Proposal | Why it is gone |
|---|---|
| "Reading confidence never reaches the trend verdict" | The demonstration was an artefact of a strictly monotone test series. On realistic noisy data confidence moves the CI from (-3.39,-0.17) to (-6.45,+2.42) and fires the UNSTABLE warning. Residual kept inside B18: `_mann_kendall` is confidence-blind and `describe()` never prints `mean_confidence` — 1–2 h, not 5. |
| Fold `treated` into `effluent` | Gains zero points in all four towns and would merge a town's tap water into its sewage effluent — 63 of Brantford's 71 `treated` records are drinking-water surveillance. |
| "The cost model's 27% vision share is wrong" | Measured 20.4%, but S1's table rescue takes it to 26.1% against an assumed 27.0%. The constant is right for the corpus; only the partition arithmetic is wrong (kept in B12). |
| "69.5% should really be ~64%" | Re-running the census's own sample under the current router gives 80.0% routed and **74.2% with a built path** — above the published figure, not below. The defect is that the number is stale and mis-attributed (B13), not inflated. |
| "`library.ask`'s empty answer is recorded as an archive gap" | Nothing persists an `Answer`; the frontier's coverage comes from `silence_report`. The real version is S25. Kept from the original only the false message (B21). |
| The early `MAP` return fires on ordinary text | Wrong. The 43 pages are mostly genuine maps, zoning schedules and lot-and-concession boundary descriptions; only one looks like a miss, at 0.09% of pages. |
| Vision trial checkpoints errors as completions | Already fixed in `652c6e9` — the resume guard is now `if key in done and "error" not in done[key]` with a retry ladder. |
| `pytest` runs zero tests on a fresh clone | Already fixed in `da7b6c3` — `scripts/recover_years.py` is tracked; 426 pass from a clone. Kept only the `pip install -e ".[dev]"` README line (B21). |
| "There is no distribution mechanism" | `scripts/share.py` shipped in `0074de9` with export/import over the existing bundle format. Replaced by B9, the 15-minute crash in it. |
| "28 dots cannot be read; passing `raw` fixes them" | 27 dots return zero, and passing `raw` rescues **3**. The other 24 fail under both spellings because the title filter also demands "annual report". Folded into S25 as the real problem. |
| "Phantom people surface at the top of `most_active`" | `most_active` sorts by `-appearances`; zero sorts last. Zero phantoms appear in any published list. The real defect is one integer (B20). |
| "`RECORDS_PER_TABLE_PAGE` is 18, should be 25.5" | Reverses with three more trial pages: median 20, mean 17.45. |
| "The portal serves the stale `page_worth_rate`" | `server.py` reads only `extrapolation.corpus_items` from the census; nothing consumes the rate. The staleness is real (B13); the consequence was not. |
| "13.1% deliberative does not reproduce" | It does, within 2–4%, under two reasonable definitions. What is real is that no script computes it — folded into B11/B13 as a `collection_census.py` that emits every corpus-level figure any document quotes. |
| "`archive.py` has no pacing anywhere in the project" | Three pacing mechanisms exist (`providers.py`, `_PoliteDelay` with tests, `corpus_census --sleep`). The decision is made and documented; it is just not in the shared adapter (S4). |
| "Per-item index parsing costs ~76 hours" | Describes a driver that does not exist; `run_batch` spawns one subprocess per town. Kept the 30-minute memoization (S29). |
| "The README's `ANTHROPIC_API_KEY` promise is false" | It sits in the gold-harness section, where `extract_prose` → `default_client()` does branch on the key. True where it stands. Only the Jay and portal messages are wrong (B21). |
| Widen `library.ask`'s title filter to any matching title | Reverses a written decision (`extract_place.py:70-72`: later one-off studies "would pollute a plant's operating series"). The defect is the message, not the filter. |
| "No `test_score.py` exists" | `tests/test_core.py:203-220` has three `score_page` tests. Thin, not absent — the substance survives in S14. |

---

## PRE-SPEND GATE

Do not start the funded run until every **$** item above is green. In dependency order: **S1** (which pages get paid for) → **S2, S3, S4** (the run survives and does not get blocked) → **S6, S7, S8, S9, S13, S23-router, S28** (prompt, schema and unit changes — every one of these after the run means paying again) → **S5, S29** (it finishes inside the calendar) → **B3, S14** (the number that grades the run means something) → **B12, B13** (the budget and page count are the corrected ones).