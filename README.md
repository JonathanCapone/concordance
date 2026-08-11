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

Page classes, from a 219-item random sample:

| Class | Share | Extraction path |
|---|---|---|
| **Mixed** | **55.3%** | Router decides **per page** |
| Narrative | 35.2% | Prose — works today |
| Tabular | 9.6% | Vision, off the page image |

Because most documents are *mixed*, routing happens per **page**. A document-level classifier would
send a 1969 annual report down one path and discard whichever half didn't match.

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

Run the accuracy harness against hand-checked ground truth:

```bash
python scripts/run_gold.py --model gemma4:12b
```

`ANTHROPIC_API_KEY` is picked up automatically if present, but is never required.

## Accuracy

The gold set is hand-read from the scans by a human; nothing in it came from a model. The harness
reports value precision/recall **and, separately, kind accuracy and stream accuracy** — because a
perfectly-read number filed as the wrong kind, or an effluent value recorded as influent, is not a
small error. The second turns a working treatment plant into a polluting one.

Results are published in `data/results/` including failures. An archive that has been misread at
scale is worse than one that has not been read at all, because the errors look like findings.

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
  models.py    record types, provenance, page text with word boxes
  archive.py   Internet Archive adapter: index, OCR, real page boundaries
  router.py    per-page classification into extraction paths
  extract.py   path A — reading measurements out of prose
  score.py     the accuracy harness
data/
  gold/        hand-checked ground truth
  results/     published accuracy runs
scripts/
  run_gold.py  extract the gold pages and score them
```

## Status

Early. The archive adapter, router, prose extractor and accuracy harness work end to end on real
documents. Vision extraction (tables, figures, maps), entity resolution across 150 years, the
silence detector and the map portal are not built yet.

## Licence

MIT — see [LICENSE](LICENSE).

## Acknowledgements

Built on the [Internet Archive Canada](https://archive.org/details/governmentpublications)
government publications collection, and on Internet Archive's decision to keep the OCR, the page
coordinates and the scans all openly available. This project is only possible because that
infrastructure exists and is free.
