# Ground Truth

**Reading Canada's public record as a hundred-year instrument.**

Internet Archive Canada holds 104,241 scanned Canadian government publications —
22.1 million pages, roughly 59 GB of OCR text, spanning 1841 to 2013. Inside them are
measurements of the physical condition of Canada: the air, the water, the soil, town by town,
decade by decade.

The median document in that collection has been downloaded **90 times**.

Every civil servant who ever wrote a measurement down was a node in a sensor network that ran for
150 years and covered a continent, and was never once read *as a network* — because each node
published to paper, and the paper went into a box.

This project reads it back out.

> Explore the source collection at
> [archive.org/details/governmentpublications](https://archive.org/details/governmentpublications).

---

## The finding this rests on

OCR **preserved prose and destroyed tables**.

A province-wide summary table comes back from the scanner like this:

```
9 /zLA' y 1? in" y 1'\ Vnlump 41 Q sailor
```

But the narrative reads perfectly — and in these reports, **the measurements are in the narrative**.
Owen Sound water pollution control plant, annual report, 1969:

> "The average influent BOD and suspended solids were 104 mg/1 and 224 mg/1 respectively. The
> average effluent BOD and suspended solids were 37 mg/1 and 36 mg/1 respectively, giving an
> average removal of 64% BOD and 84% suspended solids."

Station, parameters, values, units — a complete observation set, in readable English.

So extraction is a **reading** task, which language models do reliably, rather than a
table-recognition task off a degraded 1969 scan, which they do not. That is what makes reading
this corpus tractable rather than absurd.

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
| Ontario / Alberta / BC items | 12,467 / 8,671 / 468 |

Because most documents mix narrative and tables in one file, routing happens per **page**. A
document-level classifier would send a 1969 annual report down one path and discard whichever half
didn't match.

## How much of it is worth reading

Measured over a random sample of 120 items and 23,729 pages:

| | |
|---|---|
| Items carrying measurements | **90.8%** (95% CI 84.3–94.8%) |
| Pages worth reading | **69.5%** |
| Extrapolated to the collection | **about 15.4 million pages** |

Measured again over 8,372 pages from 34 documents in 26 collections, after a routing bug was
fixed. The earlier figures — 53.1% and 11.6–11.9 million — were too low, and the reason is
worth keeping: a line counted as prose only if it held eight words, which is a statement about
typography rather than content. A city magazine set in narrow columns scored **zero** on pages
of unbroken prose, and the loss fell hardest on the legislative record, because that is how
minutes have always been typeset. Fixing it recovered about **6.3 million pages**.

Of what is worth reading, **73% is text** a consumer machine can handle at roughly 91 seconds a
page, and **27% needs the vision path**. Pages are the wrong unit for judging that split, though:
a prose page averages 4.2 measurements and a third yield none, while a table page yields around
eighteen. The tables are probably the majority of the actual data.

Three things follow, and all three change the plan rather than decorate it.

**Nine out of ten documents in this archive contain measurements.** The premise holds.

**Local inference cannot touch the whole thing.** At the throughput measured on a consumer GPU,
reading every page is roughly **56 machine-years**. A corpus-wide pass is therefore not a local
job and should never be described as one: it is a funded batch run, performed once, after which
the resulting dataset costs everyone else nothing. That is a fact about the work, not a caveat
hidden in a footnote.

**Which is why the split is what it is.** The central run does what is expensive and uniform —
the vocabulary, and the tables. People do prose, on demand, on their own machines, which is where
places, dates, narrative and the entire deliberative record live.

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

- Every record carries the **verbatim sentence** it was read from, and that sentence is verified to
  occur on the page. A model that invents a value nearly always invents the sentence too, so this
  catches fabrication for the cost of a substring search.
- Every record deep-links to **the scanned page**, and word-level coordinates mean the source
  sentence can be highlighted *on* the scan rather than merely linked to.
- Reading confidence is the model's own certainty **multiplied by how legible the scan was**.

## Install and run

Requires Python 3.11+. No API key is needed for anything.

```bash
git clone <this repo> && cd ground-truth
pip install -e .
```

Extraction runs on a local model by default via [Ollama](https://ollama.com):

```bash
ollama pull gemma4:12b
```

Run it:

```bash
python -m groundtruth.server
```

Opens a live map of every municipality in the collection. Orange dots have been
read; click one for its measurements, each linked to the scanned page it came
from. No install, no key, no network — the map is projected and drawn from
coordinates rather than pulled from a tile service, so it works offline.

Run the accuracy harness against hand-checked ground truth:

```bash
python scripts/run_gold.py --model gemma4:12b
```

`ANTHROPIC_API_KEY` is picked up automatically if present, but is never required.

## Accuracy

The gold set is hand-read from the scans by a human; nothing in it was copied from a model. The
harness reports value precision/recall **and, separately, kind accuracy and stream accuracy** —
because a perfectly-read number filed as the wrong kind, or an effluent value recorded as influent,
is not a small error. The second turns a working treatment plant into a polluting one.

Current run — `gemma4:12b`, run locally, no API key:

| Page | Precision | Recall | Kind | Stream | Blind? |
|---|---|---|---|---|---|
| 9 — design specification sheet | 88% | 85% | 100% | 60% | **no** |
| 10 — mixed narrative and spec | 91% | 71% | 100% | 100% | yes |
| **11 — narrative prose** | **88%** | **88%** | **100%** | **100%** | **yes** |
| overall | 88.7% | 82.5% | 100% | 86.7% | — |

**Page 11 is the honest headline**: 88/88, annotated blind before any extraction run, on the clean
narrative prose that the core finding is about.

**Page 9 is not blind.** Its gold set was expanded after an audit showed the original annotation
covered 6 of the page's ~26 design values, and by then the annotator had seen model output. Its
figures are optimistically biased and are reported anyway, labelled, rather than quietly dropped.

Two weaknesses that are real rather than measurement artefacts: **stream accuracy is 60% on the
design sheet** (raw vs influent vs effluent is genuinely ambiguous there), and **10 gold entries are
still missed entirely**.

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

Keyless by default, and the public instance uses only keyless sources.

| Tier | Auth | Rule |
|---|---|---|
| 0 | none | Everything core runs on these alone |
| 1 | free, user-supplied | Optional enrichment, never required |
| 2 | paid, user-supplied | Never required, ever |

No key is ever committed to this repo or used by the public instance.

## Layout

```
groundtruth/
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
  citations.py   a picture of the patch of scan a number is written on
  contribute.py  verifying a bundle of readings against the pages they cite
  disputes.py    open contribution and correction, with nobody adjudicating
  library.py     ask for a place; if nobody has read it, your machine does
  frontier.py    what reading a document would unlock, and for whom
  vocab_builder.py  proposals a person accepts or rejects; never automatic
  vocab_sample.py   deciding when enough of the vocabulary has been seen
  tools.py       the archive-native tool layer an agent needs to be useful here
  honu.py        the agent itself, over that toolset
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
  silence_report.py   map what stopped being measured, with a control
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

Early, but measured. Reading, routing, prose and table extraction, accuracy scoring, unit and
parameter resolution, place resolution, the science layer, the watershed network, the provider
layer, the decision record, the citation crops, the dispute ledger and the agent all work end to
end on real documents. 403 tests. Zero required dependencies in the core.

**What has actually been found, each with its own control attached:**

- **72 of 107 Ontario municipalities stop filing water pollution control plant reports in 1975.**
  That pattern usually means a scanning boundary, so it was checked: Ministry of the Environment
  publications in the same collection run 1,449 before 1975 and 3,800 after, at a steady 83–141
  items a year straight through. The archive kept growing. This series died.
- **539 of 1,119 Ontario river gauges are discontinued** — 48%, from live ECCC data. The same
  winding-down of measurement, still happening.
- **Owen Sound, 1963–1972**: 120 readings recovered from 12 scanned reports, BOD removal rising
  from 46.4% to 64%.
- **13,429 metadata corrections proposed** across all 104,241 items.

**The first trend the project produced was a refusal, and that is the point.** Owen Sound's daily
flow rises 175,000 gal/day per year — and the same line reports p=0.71, a 90% interval spanning
zero, only 62% of bootstrap replicates agreeing on direction once reading confidence is carried
through, and two of six points flagged as probable scan damage. A naive pipeline publishes the
slope.

**Tables are now readable, and that changed the plan.** llava invented table structure and was
worse than useless, because a fabricated table is indistinguishable from a recovered one. A newer
local model does not: given the Brantford 1962 flow table, whose OCR reads `TABLE I FLOW -
MILX.IQN GALLOLS`, it returned every one of the twelve values that survived in the OCR, exactly,
and rebuilt the header row the scanner had destroyed. Across four documents spanning 1942 to 2003,
**58 of 58 values are on the page.** The cost is nine minutes a page on an RTX 2080 where only 18%
of the model fits in VRAM, so this is a rented-hardware job rather than a local one.

**Not built:** figure extraction — reading a plotted line back into numbers — and corpus-scale
extraction, which is what the whole cost model is about.

**Known limitations, stated rather than discovered later:** the Pettitt changepoint test is far
too conservative at the sample sizes annual reports give, so a null result from it means nothing;
the watershed network is name-matching and drainage area, not routed hydrology, and should be
checked against the National Hydro Network before any claim about a specific community's water;
verification catches fabrication but not misreading, so a value filed as influent when the page
meant effluent passes every check this project has — which is why contested readings are shown
side by side with a picture of each sentence rather than resolved.

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
