# Concordance

**Reading Canada's public record as a hundred-year instrument.**

An August 11 catalogue snapshot holds 104,241 scanned Canadian government publications —
about 22.1 million page images with a separate OCR text layer. This project scopes the
historical run from 1841 to 2013. Inside are
measurements of the physical condition of Canada: the air, the water, the soil, town by town,
decade by decade.

The median document in that collection has been downloaded **90 times**.

Historical measurements across these publications can be treated as nodes in a long-running
distributed record. I have not found evidence that this collection has been analyzed as one
connected historical monitoring network.

This project reads it back out.

> Explore the source collection at
> [archive.org/details/governmentpublications](https://archive.org/details/governmentpublications).

---

## The finding this rests on

OCR often preserves narrative prose while damaging table layout; values may survive even when
row and column structure is lost.

A province-wide summary table comes back from the scanner like this:

```
9 /zLA' y 1? in" y 1'\ Vnlump 41 Q sailor
```

But much of the narrative remains legible — and in these reports, **the measurements are in the narrative**.
Owen Sound water pollution control plant, annual report, 1969:

> "The average influent BOD and suspended solids were 104 mg/1 and 224 mg/1 respectively. The
> average effluent BOD and suspended solids were 37 mg/1 and 36 mg/1 respectively, giving an
> average removal of 64% BOD and 84% suspended solids."

Station, parameters, values, units — a complete observation set, in readable English.

So prose extraction is a **reading** task; the current four-page benchmark measures 96.8%
precision. Table recognition on degraded scans remains the harder, less certain path.

## Three properties that make it an instrument

1. **Reading is the sensing act.** The "sensor" is a model reading a sentence.
2. **The error is linguistic, not electronic.** A sensor's accuracy comes from a spec sheet. A model
   reading a smudged scan is sometimes confident and sometimes guessing. That uncertainty has to
   propagate into every trend line, or a guess gets presented as a fact.
3. **Silence is the signal.** In a live sensor network a quiet station is a fault to fix. In an
   archive, a town vanishing from the record is *history* — a plant closed, a programme was
   defunded, records were lost. **The negative record is the finding.**

## What the corpus actually looks like

Measured over all 104,241 items, not assumed:

| | |
|---|---|
| Items with **no subject tag** | 59,819 (**57%**) |
| Items with **no year** | 33,844 (32%) |
| Language field spellings for two languages | 8 (`eng`/`English`/`Eng`/`ENG`/`fre`/`fra`/`French`/`FRA`) |

Province totals are not quoted here: catalogue geography is inconsistent, and
simple keyword counts undercount British Columbia material.

Because most documents mix narrative and tables in one file, routing happens per **page**. A
document-level classifier would send a 1969 annual report down one path and discard whichever half
didn't match.

## How much of it is worth reading

Measured over a random sample of 120 items and 23,729 pages:

| | |
|---|---|
| Items with at least one prose/table candidate | **90.8%** (95% CI 84.3–94.8%) |
| Pages flagged for some reading path | **53.1%** (95% CI 52.5–53.8%) |
| Extrapolated under that frozen router | **11.6–11.9 million pages** |

These are classifier outputs, not proof that a document contains measurements. A later
8,372-page convenience sample produced 69.5% after a routing fix; it was not random and cannot
replace this census. The router has changed again. Coverage, the prose/table split and the cost
model must therefore be re-measured together before any corpus-wide budget or yield is quoted.

That uncertainty changes the plan rather than decorating it. A corpus bought in one batch is
finished the day the money runs out; it never extends, and the next person who wants an unread
document has no way to get one. The local reader and sharing path are built: `scripts/share.py` moves a
result between machines — as a file, or pushed to a shared instance — and its cited page evidence is
rechecked on arrival. The safe one-click handoff from the public website to that local reader is
not built yet; the site does not start an hours-long model job from a web request.

**The honest hole in that** is the vision path. Its corpus-wide share is not currently measured
reliably, and trial pages take about eight minutes each on an RTX 2080 because only 18% of a 29.6 GB
model fits in 8 GB of VRAM. Prose distributes; tables mostly do not, yet. Whether a smaller model
closes that gap is a measurable question and it has not been measured.

## Four kinds of record

Keeping these apart is load-bearing:

| Kind | Meaning |
|---|---|
| `observation` | What was actually measured, here, then |
| `standard` | The regulatory limit **of that era** |
| `design` | What the equipment was **built** to handle — a specification |
| `conclusion` | The author's judgement |

`design` exists because of a real trap. The Owen Sound report states **BOD 180 mg/L** on its design
data sheet and **BOD 104 mg/L** in its review. Same parameter, same unit, same plant, same document.
One is engineered capacity; the other is what actually flowed through. Conflating them yields a
clean, plausible, entirely fictional trend.

And `standard` exists because you cannot answer *"was 104 mg/L bad?"* without knowing the limit
**in 1969**.

## Trust

No number in this system is unfalsifiable.

- Every prose record carries its **verbatim source sentence**; table records carry row/column
  locators. The sentence and complete numeric token are checked on the cited page before a prose
  record is accepted.
- Every record deep-links to **the scanned page**. When word boxes and the image service permit,
  prose gets a focused crop; otherwise the page link remains with an unavailable state.
- Reading confidence is the model's own certainty **multiplied by how legible the scan was**.

## Install and run

Requires Python 3.11+. No API key is required for the core local workflow;
new extraction also requires Ollama and a downloaded model.

```bash
git clone <this repo> && cd concordance
pip install -e .
```

Extraction runs on a local model by default via [Ollama](https://ollama.com):

```bash
ollama pull gemma4:12b
```

Run it:

```bash
python -m concordance.server
```

Opens a map of municipalities represented in the loaded result set. Orange dots
have records; click one for selected series, archive page links and, when
available, focused citation crops.

Optional external clients may use a user-supplied key. The portal is not fully
offline: the serving layer pulls MapLibre and its basemap tiles from
public CDNs, and the citation crops come from archive.org's IIIF endpoint. All
of those are keyless and free, and none of them are in the core — the extraction
and verification path has no network dependency beyond the archive itself, so a
stranger can check a measurement without standing up a web stack.

Once fetched, OCR text, page structures and word boxes are cached locally.
Scan images and citation crops still come from Archive.org unless separately
cached. A fresh clone has no cache, so its first archive operation needs the
network; many later evidence views can answer from disk.

Share what you have read, and take what somebody else read:

```bash
python scripts/share.py export --place Fergus --out fergus.bundle.json
python scripts/share.py import fergus.bundle.json --verified-only
```

A bundle is a file. It can travel by email, USB stick or a link in a forum post,
none of which need a server anybody has to run, pay for, or be trusted to keep
honest. **Trust does not travel with it** — an imported bundle's cited OCR
sentence and complete numeric token are rechecked on the importing machine,
record by record. Locator-only table claims currently abstain: headings anywhere
on a page do not prove which number occupies their intersection. This verifies
prose evidence presence, not semantic interpretation.

Or send it to a running instance, and take everything one holds:

```bash
python scripts/share.py push fergus.bundle.json --to https://example.org
python scripts/share.py pull --frm https://example.org --out theirs.bundle.json
```

An instance evaluates each submitted record's cited page evidence and reports
what it accepted or refused; locator-only table claims currently abstain. It is a convenience, not an
authority: `GET /api/library.json` returns the whole dataset as a bundle, `pull`
saves it without believing any of it, and `import --verified-only` is what
decides — on your machine, against cited page evidence. Anyone who mistrusts an instance
can take everything it has and run their own.

> A note on identity, since it is the kind of bug this project exists to catch.
> Deduplication compares a reading's identity, and that identity is a hash of the
> reading's own content — recomputed on both sides of every comparison, never
> read from the `key` field stored in a results file. Those stored keys are
> snapshots taken before later normalisation and no longer match their own
> records. Trusting them made an instance merge 19 of 20 of its *own* readings
> back in as new, which would have doubled the dataset on every round trip.

Run the accuracy harness against hand-checked ground truth:

```bash
python scripts/run_gold.py --model gemma4:12b
```

The extraction clients can optionally use an Anthropic key, but Jay itself uses
the configured local Ollama endpoint only.

## Accuracy

The gold set is hand-read from the scans by a human; nothing in it was copied from a model. The
harness reports value precision/recall **and, separately, kind accuracy and stream accuracy** —
because a perfectly-read number filed as the wrong kind, or an effluent value recorded as influent,
is not a small error. The second turns a working treatment plant into a polluting one.

Current run — `gemma4:12b`, run locally, no API key. Reproduce with
`python scripts/rescore.py`, which re-scores the published records without calling a model:

| Page | Precision | Recall | Kind | Stream | Blind? |
|---|---|---|---|---|---|
| Owen Sound 9 — design specification sheet | 100% | 92% | 100% | 67% | **no** |
| Owen Sound 10 — mixed narrative and spec | 93% | 93% | 92% | 100% | yes |
| **Owen Sound 11 — narrative prose** | **94%** | **94%** | **100%** | **100%** | **yes** |
| Hamilton 20 — a magazine, not a data report | 100% | 64% | 100% | 100% | yes |
| overall | 96.8% | 88.2% | 98.3% | 88.9% | — |

Four pages across two documents, 68 hand-read values. The second document is deliberately not a
water report: *Hamilton: An Adventure in Good Living* is a promotional magazine, included because a
harness measured only on the documents a method was designed for measures nothing.

**Page 11 is the honest headline**: 94/94, annotated blind before any extraction run, on the clean
narrative prose that the core finding is about.

**Page 9 is not blind.** Its gold set was expanded after an audit showed the original annotation
covered 6 of the page's ~26 design values, and by then the annotator had seen model output. Its
figures are optimistically biased and are reported anyway, labelled, rather than quietly dropped.

Three weaknesses that are real rather than measurement artefacts. **Kind accuracy is 98.3%, not
100%** — one conclusion was filed as an observation, which is the error class this README calls the
dangerous one, so it is named here rather than rounded away. **Stream accuracy is 67% on the design
sheet**, where raw vs influent vs effluent is genuinely ambiguous. And **8 gold entries are still
missed entirely**, six of them on the magazine page.

> These numbers were wrong in this file until an audit checked them against the artifact. The table
> published 88.7%/82.5%/100%/86.7% — figures from a run that predated the prompt widening, left in
> place while `data/results/gold_report.json` said something else. The real numbers were *better* on
> every axis except the one this README had rounded up to 100%. A stale accuracy claim is not a
> harmless one even when it understates: it means nobody was re-reading the ruler.

### The first number was wrong, and it was the ruler

The first scored run reported **49% precision**. Auditing the records it called spurious showed
nearly all of them were correct — the harness lacked unit-scale conversion (`3.0 million gallons`
scored as a miss against `3000000 gallons`), lacked rate reconciliation, and was checking against an
incomplete gold set. Fixing the *measurement*, with no change at all to the extractor, moved
precision from 49.1% to 88.7%.

Publishing 49% would have caused the scope to be narrowed for no reason. This is why runs are
published in `data/results/` including the failures: an archive that has been misread at scale is
worse than one that was never read, because the errors look like findings.

## Credentials

Keyless by default; the planned public instance will use only keyless sources.

| Tier | Auth | Rule |
|---|---|---|
| 0 | none | Everything core runs on these alone |
| 1 | free, user-supplied | Optional enrichment, never required |
| 2 | paid, user-supplied | Never required, ever |

No key is committed to this repo or required by the planned public instance.

## Layout

```
concordance/
  models.py      record types, provenance, page text with word boxes
  archive.py     Internet Archive adapter: index, OCR, real page boundaries, page images
  router.py      per-page classification into extraction paths
  extract.py     path A — reading measurements out of prose
  vision.py      path B — reading the tables OCR destroyed, off the scan
  parameters.py  what was measured, resolved to a canonical quantity
  places.py      where it was measured, resolved across 150 years of renaming
  units.py       the methods-drift layer: convert what is comparable, refuse the rest
  science.py     trend with reading-uncertainty, changepoint, silence
  watershed.py   who was downstream of whom
  providers.py   external data, keyless first, tiers enforced by tests
  decisions.py   who moved what, who seconded, and how each person voted
  dating.py      publication year from the text, and whether a value's year is safe
  citations.py   page links plus focused scan crops when available
  contribute.py  verifying a bundle of readings against the pages they cite
  disputes.py    open contribution and correction, with nobody adjudicating
  library.py     ask for a place; if nobody has read it, your machine does
  frontier.py    what reading a document would unlock, and for whom
  vocab_builder.py  proposals a person accepts or rejects; never automatic
  vocab_sample.py   deciding when enough of the vocabulary has been seen
  tools.py       the archive-native tool layer an agent needs to be useful here
  jay.py        the agent itself, over that toolset
  repair.py      Tier 0 — proposed metadata corrections for the whole collection
  score.py       the accuracy harness
  portal.py      the map portal, forked from OMEGA-wave
  server.py      a running instance you can click, standard library only
data/
  gold/          hand-checked ground truth
  results/       published runs: accuracy, metadata proposals, silence report
scripts/
  run_gold.py         extract the gold pages and score them
  rescore.py          re-score a saved run without calling a model
  extract_place.py    read every surviving report for one town
  analyze_place.py    turn those records into trends and findings
  silence_report.py   map title-derived catalogue gaps, with a collection control
  propose_metadata.py generate the catalogue repair diff
  build_portal.py     render the reporting cliff as a self-contained page
  build_town_page.py  render one town's record, every number linked to its scan
portal/
  silence.html   the 1975 cliff
```

Two layers exist because the corpus forced them, not because they were planned.
`units.py` was written after finding the same specification recorded as
"180 PPM" in 1963 and "180 mg/1" in 1969. `parameters.py` was written after
discovering that matching parameter names by substring had been plotting
*removal percentages* on a chart labelled as effluent *concentrations* — both
small numbers that fall when a plant improves, so it looked entirely reasonable.

## Status

Early, but measured. The repository contains reading, routing, prose and table extraction,
accuracy scoring, unit and parameter resolution, place resolution, science, watershed, provider,
decision, citation, dispute and assistant components. They run on real documents and the full test
suite passes; only the four-page prose benchmark currently has a hand-read accuracy score. The core
has zero required package dependencies.

**What has actually been found, each with its own control attached:**

- **72 of 107 parsed municipal report series have no dated entry after 1974.** Broader Ministry
  publishing continues — 1,449 indexed items before 1975 and 3,800 afterward — arguing against a
  collection-wide scanning stop. The artifact does not explain any individual series gap.
- A live ECCC query suggested that about **48%** of returned Ontario gauge records were marked
  discontinued. Its exact response was not preserved, so it is not a frozen benchmark.
- **Owen Sound, 1963–1972**: 120 source-linked records from 12 scanned reports, including 69
  observations; the extracted BOD-removal series rises from 46.4% to 64%.
- **13,429 language/year metadata proposals** across all 104,241 items, offered for review.

**The first trend the project produced was a refusal, and that is the point.** Owen Sound's daily
flow rises 175,000 gal/day per year — and the same line reports p=0.71, a 90% interval spanning
zero, only 62% of bootstrap replicates agreeing on direction once reading confidence is carried
through, and two of six points flagged as probable scan damage. A naive pipeline publishes the
slope.

**Tables may be recoverable, and that changed the plan.** llava invented table structure and was
worse than useless, because a fabricated table is indistinguishable from a recovered one. On the
Brantford 1962 flow page, a newer local model returned 27 records and recovered 10 of 12 values
identified in the OCR beforehand.

Across **24 table pages from 11 collections**, 1879 to 2003, the trial returned **535 records**.
The stored trial checked 461 of those records for a matching digit sequence in page OCR and found
411 (89%). That is a permissive consistency check, not an accuracy score: short numbers match by
chance, 50 did not match, and the artifact does not preserve why 74 records were excluded. Their
status is unknown; all 24 pages had OCR text. Trial throughput was about eight minutes a page on an
RTX 2080, where only 18% of the model fit in VRAM.

**Not built:** figure extraction — reading a plotted line back into numbers — and corpus-scale
extraction, which is what the whole cost model is about.

**Known limitations, stated rather than discovered later:** the Pettitt changepoint test is far
too conservative at the sample sizes annual reports give, so a null result from it means nothing;
the watershed network is name-matching and drainage area, not routed hydrology, and should be
checked against the National Hydro Network before any claim about a specific community's water;
verification catches some fabrication but not misreading, so a value filed as influent when the
page meant effluent can pass — which is why contested readings remain side by side. Each keeps a
page link; prose uses sentence evidence, while table records retain row/column locators but are not
accepted as verified without localized cell proof. Crops can also be unavailable.

## The work log

[WORKLOG.md](WORKLOG.md) records what was built, what was measured, and mostly
what turned out to be wrong. Every serious mistake in this project has been
plausible-wrong rather than crash-wrong -- a 49% accuracy figure that was really a
broken ruler, a chart quietly plotting removal percentages as concentrations, two
unconnected rivers linked by a guessed threshold -- and none of them would have
thrown an error. That pattern is the most useful thing here.

## Licence

MIT — see [LICENSE](LICENSE).

## Acknowledgements

Built on the [Internet Archive Canada](https://archive.org/details/governmentpublications)
government publications collection, and on Internet Archive's decision to keep the OCR, the page
coordinates and the scans all openly available. This project is only possible because that
infrastructure exists and is free.
