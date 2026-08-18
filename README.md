# Concordance

**Canada's municipal water record, page by page.**

In 1969, the sewage plant in Owen Sound, Ontario measured what it discharged into
the river, wrote it down, and filed the report with the government. The report was
scanned decades later. Almost nobody has ever read it.

Concordance is a free, open-source website that turns reports like that into a
searchable public memory. Type in a town and see what officials measured there —
effluent, drinking water, flows, and related municipal conditions — across decades.
Every value carries the sentence it came from and a link to the scanned page.
Measurements made in incompatible ways stay separate instead of becoming a clean
but fictional trend.

**Live: [concordance.jonathancapone.com](https://concordance.jonathancapone.com)** —
6,554 records across 24 towns, each one linked to the page it was read from.

The source collection holds 104,241 scanned Canadian government publications, about
22.1 million page images. The median document in it has been downloaded 90 times.
There appears to be no national, machine-readable database that brings these
municipal measurements together with page-level provenance.

---

## Read a town in your browser

The shortest way to understand the project is to use it. On the live site, pick a
town nobody has read and press one button: a language model downloads into your
browser tab, reads that town's scanned reports page by page on your own graphics
card, and sends what survives its checks back to the site, which re-verifies every
quoted sentence against the archive before publishing anything.

Nothing to install. No account. No API key. No server of ours runs a model for you.

Ingersoll was read this way — sixteen pages of prose, twenty-three records
published, refusals shown on screen as they happened.

The browser reader is deliberately partial, and now measured: against the four
pages a person read by hand it finds **57.4%** of the values they found, and
**81.2%** of what it publishes matches one of them. It fabricated nothing —
every number it published appears in the sentence it quoted. Of the nine
records that missed the answer key, eight are real readings the key does not
list on their own, and one is a real misreading: where the page prints
"0. 196 mil gal" it returned 196. For the rest of a town's record there is the installed
reader below, which uses a larger model and scores 96.8% precision on the same
pages. Method and full report: [`data/results/browser_gold_report.json`](data/results/browser_gold_report.json).

## Why this is possible at all

OCR from 2013 often destroyed the tables in these documents while leaving the prose
readable. A province-wide summary table comes back from the scanner like this:

```
9 /zLA' y 1? in" y 1'\ Vnlump 41 Q sailor
```

There is nothing in there. But the narrative on the same page survived — and in
these reports, **the measurements are in the narrative**. Owen Sound, 1969:

> "The average influent BOD and suspended solids were 104 mg/1 and 224 mg/1
> respectively. The average effluent BOD and suspended solids were 37 mg/1 and
> 36 mg/1 respectively, giving an average removal of 64% BOD and 84% suspended
> solids."

Station, parameter, value, unit — a complete set of measurements, in a sentence a
model can read without effort. That is why this is a reading problem rather than a
table-recognition problem, and why it runs on ordinary hardware.

## How the record grows

Nobody pre-processes the archive. Somebody asks for a place, the machine in front
of them reads it, and the answer is there for everyone afterwards. The cost falls on
whoever cares first, which is also the person most willing to wait, and the archive
gets read in the order people actually want to know things.

Two ways to be that machine:

- **In your browser**, from the site — one press, nothing installed, partial but honest.
- **The installed reader**, for a whole town with the full model:
  `python scripts/share.py read --place "Fergus" --to https://concordance.jonathancapone.com`

Either way the site re-checks every cited sentence on arrival before publishing.
Verification is what makes this safe to accept from strangers: the check asks the
archive, not the person, so a contribution about a subject nobody here understands
can still be accepted or refused on evidence.

## Four kinds of record, kept apart

| Kind | Meaning |
|---|---|
| `observation` | What was actually measured, here, then |
| `standard` | The regulatory limit **of that era** |
| `design` | What the equipment was **built** to handle |
| `conclusion` | The author's judgement |

This distinction is load-bearing. The Owen Sound report states **BOD 180 mg/L** on
its design sheet and **BOD 104 mg/L** in its review — same parameter, same unit,
same plant, same document. One is engineered capacity, the other is what actually
flowed through. Conflating them produces a clean, plausible, entirely fictional
trend. And `standard` exists because you cannot answer *"was 104 mg/L bad?"*
without knowing the limit in 1969.

## Trust

No number here is unfalsifiable.

- Every prose record carries its **verbatim source sentence**. Before a record is
  accepted, that sentence and the complete numeric token are checked against the
  OCR of the page it cites.
- Every record deep-links to **the scanned page**, with a focused crop of the
  sentence where the image service allows one.
- Reading confidence is the model's own certainty multiplied by how legible the
  scan was.
- Anyone can challenge a reading. A challenge must cite a page and quote a
  sentence to change the record; an objection with no evidence is counted and
  shown but changes nothing, because the moment it could outrank a sentence on a
  page, somebody would have to judge the objection.

**What verification cannot do:** it catches fabrication, not misreading. "104 mg/1"
really being on the page says nothing about whether it is influent or effluent.
When two source-backed readings disagree, nobody adjudicates — both stay visible
with both crops, and a reader decides.

## Accuracy

Ground truth is hand-read from the scans by a person; nothing in it was copied from
a model. The scoring script reports value precision and recall **and, separately, kind and
stream accuracy** — because a perfectly-read number filed as the wrong kind, or an
effluent value recorded as influent, is not a small error. The second turns a
working treatment plant into a polluting one.

Current run — `gemma4:12b`, local, no API key. Reproduce with
`python scripts/rescore.py`, which re-scores published records without calling a model:

| Page | Precision | Recall | Kind | Stream | Blind? |
|---|---|---|---|---|---|
| Owen Sound 9 — design specification sheet | 100% | 92% | 100% | 67% | **no** |
| Owen Sound 10 — mixed narrative and spec | 93% | 93% | 92% | 100% | yes |
| **Owen Sound 11 — narrative prose** | **94%** | **94%** | **100%** | **100%** | **yes** |
| Hamilton 20 — a magazine, not a data report | 100% | 64% | 100% | 100% | yes |
| overall | 96.8% | 88.2% | 98.3% | 88.9% | — |

Four pages, two documents, 68 hand-read values. That is a smoke test, not a
defensible accuracy claim, and it is quoted that way everywhere. The second document
is deliberately not a water report: a benchmark measured only on the documents a
method was designed for measures nothing.

**Page 11 is the honest headline** — 94/94, annotated blind before any extraction
run, on exactly the clean narrative prose the project rests on. **Page 9 is not
blind**: its answer key was expanded after an audit found it covered 6 of the page's
~26 design values, by which time the annotator had seen model output. Its figures
are optimistically biased, reported anyway, labelled.

Three real weaknesses rather than measurement artefacts: kind accuracy is 98.3% and
not 100% (one conclusion filed as an observation — the dangerous error class, so it
is named rather than rounded away); stream accuracy is 67% on the design sheet,
where raw vs influent vs effluent is genuinely ambiguous; and 8 values are missed
entirely, six of them on the magazine page.

### The first number was wrong, and it was the ruler

The first scored run reported **49% precision**. Auditing the records it called
wrong showed nearly all of them were right: the scorer could not tell that "3.0
million gallons" and "3000000 gallons" are the same measurement, and the answer key
was incomplete. Fixing the *measurement*, with no change at all to the extractor,
moved precision from 49.1% to 88.7%.

Publishing 49% would have narrowed this project for no reason — and every step of
that would have felt like rigour. It is why runs are published in `data/results/`
including their failures, and why the plan freezes a wider benchmark before tuning.

## What has been found

- **All 107 parsed municipal report series end by 1974; 72 end in that exact year.**
  Broader Ministry publishing continues — 1,449 indexed items before 1975 and 3,800
  after — which argues against a collection-wide scanning stop. It does not explain
  any individual gap, and the site says so.
- **Owen Sound**: 120 source-linked records from 10 scanned reports; the sewage
  series runs 1963–1972 and the drinking-water reports 1990–1992, kept apart
  because they measure opposite things.
- **13,429 catalogue corrections** offered to Internet Archive Canada for review —
  11,151 language-code normalizations and 2,278 publication-year proposals.
- **The first trend the project produced was a refusal.** Owen Sound's daily flow
  rises 175,000 gal/day per year — and the same line reports p=0.71, a 90% interval
  spanning zero, only 62% of bootstrap replicates agreeing on direction once reading
  confidence is carried through, and two of six points flagged as probable scan
  damage. A naive pipeline publishes the slope. That refusal is the product.

## Run it yourself

Python 3.11+. The core has no required package dependencies; new extraction also
needs [Ollama](https://ollama.com) and a local model.

```bash
git clone https://github.com/JonathanCapone/concordance.git && cd concordance
pip install -e .
ollama pull gemma4:12b
python -m concordance.server
```

That serves the whole site locally — map, town records, findings, and the reader —
at `http://localhost:8765`. On your own machine the reading buttons work; a shared
instance politely refuses to spend its processor on visitors and hands them the
command instead.

Read one town, score the benchmark, or move readings between machines:

```bash
python scripts/share.py read --place "Fergus"      # read it here
python scripts/run_gold.py --model gemma4:12b      # score against ground truth
python scripts/share.py export --place Fergus --out fergus.bundle.json
python scripts/share.py import fergus.bundle.json --verified-only
```

A bundle is a file. It travels by email, USB stick, or a link in a forum post —
none of which need a server anybody has to run, pay for, or be trusted to keep
honest. **Trust does not travel with it**: an imported bundle is rechecked against
the cited pages on the importing machine, record by record. `GET /api/library.json`
returns the whole dataset, so anyone who mistrusts an instance can take everything
it has and run their own.

## Layout

```
concordance/
  models.py      record types, provenance, page text with word boxes
  archive.py     Internet Archive adapter: index, OCR, page boundaries, images
  router.py      per-page classification into extraction paths
  extract.py     path A — reading measurements out of prose
  vision.py      path B — reading the tables OCR destroyed, off the scan
  parameters.py  what was measured, resolved to a canonical quantity
  places.py      where it was measured, across 150 years of renaming
  units.py       convert what is comparable, refuse the rest
  science.py     trend with reading-uncertainty, changepoint, silence
  watershed.py   who was downstream of whom
  decisions.py   who moved what, who seconded, and how each person voted
  citations.py   page links plus focused scan crops when available
  contribute.py  verifying a bundle of readings against the pages they cite
  disputes.py    open contribution and correction, with nobody adjudicating
  library.py     ask for a place; if nobody has read it, your machine does
  frontier.py    what reading a document would unlock, and for whom
  chrome.py      one masthead and menu, shared by every page
  portal.py      the map portal, forked from OMEGA-wave
  server.py      a running instance you can click, standard library only
scripts/
  build_browser_reader.py  the in-browser reader page
  run_gold.py / rescore.py score against hand-read ground truth
  share.py                 read a town, export, import, push, pull
data/
  gold/     hand-checked ground truth
  results/  published runs: accuracy, metadata proposals, silence report
```

Two modules exist because the corpus forced them. `units.py` was written after
finding the same specification recorded as "180 PPM" in 1963 and "180 mg/1" in
1969. `parameters.py` was written after discovering that matching parameter names
by substring had been plotting *removal percentages* on a chart labelled effluent
*concentrations* — both small numbers that fall when a plant improves, so it looked
entirely reasonable.

## Known limitations

Stated here rather than discovered later:

- **Coverage is a classifier estimate, not a promise.** A 120-item, 23,729-page
  random sample put pages worth reading at 53.1% (95% CI 52.5–53.8%), extrapolating
  to roughly 11.6–11.9 million pages. A later routing fix raised that on a
  non-random sample; the router has changed again. Coverage, the prose/table split
  and the cost model must be re-measured together before any corpus-wide budget is
  quoted.
- **Tables are the honest hole.** Prose distributes to volunteers; tables mostly do
  not, yet. A newer local model recovered 10 of 12 known values on a 1962 flow page,
  but trial throughput was about eight minutes a page on an RTX 2080 where only 18%
  of the model fits in VRAM.
- **The Pettitt changepoint test** is far too conservative at the sample sizes
  annual reports give, so a null result from it means nothing.
- **The watershed network** is name-matching and drainage area, not routed
  hydrology, and should be checked against the National Hydro Network before any
  claim about a specific community's water.
- **Verification catches fabrication, not misreading** — see Trust, above.
- **Not built:** figure extraction (reading a plotted line back into numbers) and
  corpus-scale extraction, which is what the cost model is about.

## The work log

[WORKLOG.md](WORKLOG.md) records what was built, what was measured, and mostly what
turned out to be wrong. Every serious mistake here has been plausible-wrong rather
than crash-wrong — a 49% accuracy figure that was really a broken ruler, a chart
quietly plotting removal percentages as concentrations, two unconnected rivers
linked by a guessed threshold — and none of them would have thrown an error. That
pattern is the most useful thing in this repository.

## Licence

MIT — see [LICENSE](LICENSE). Code is MIT; derived data is published only where the
source rights support reuse.

## Acknowledgements

Built on the [Internet Archive Canada](https://archive.org/details/governmentpublications)
government publications collection, and on Internet Archive's decision to keep the
OCR, the page coordinates and the scans openly available. This project is only
possible because that infrastructure exists and is free.
