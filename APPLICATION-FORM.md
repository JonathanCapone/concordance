# Concordance — answers for the BC + AI application form

Each answer is written to stand alone, because they are read as separate fields
in a review database and a reviewer may not read them in order. Character counts
are checked by `scripts/check_form.py`; the limits are the form's own.

---

## Project title

Concordance

---

## Project summary — *What do you want to build or create?* (2000)

Concordance turns a century and a half of scanned public records into a free
neighbourhood instrument panel: ask what was measured where you live — sewage
in the river, what was in the drinking water, what came out of the smelter —
then challenge any published number on the exact government page it came from.

Open Owen Sound, 1969. The town's water pollution control plant reported that
the treated sewage it released averaged 37 mg/L BOD. That number asks for no
trust: it links to the scanned page in this collection and quotes the sentence
it was read from — "The average effluent BOD and suspended solids were 37 mg/1
and 36 mg/1 respectively" — with, where the image service permits, a cropped
photograph of that sentence. It is one of 5,147 source-linked records across
14 Ontario municipalities at frozen checkpoint `763d4c0`.

I found no usable national database of these numbers. My August 11 catalogue
snapshot holds 104,241 scanned government publications and 22.1 million pages;
the project scopes 1841 to 2013. To learn what your town's plant discharged in
1969, you would have to know the report exists, find it, read it. The
fellowship brief puts the collection at roughly 48 TB; the reader works from
the OCR text layer and fetches page images only as needed.

The fellowship build is the missing bridge. Today a volunteer's computer can
read pages locally and send results to a Concordance site, where every cited
sentence and number is checked again. What the site cannot yet do is hand a
requested town to a volunteer's machine. I will build and test that handoff so
a volunteer can contribute without an account, an API key, or a process left
running — the path to growth without a permanent central compute bill. It is a
deliverable, not something I claim is already deployed.

The fellowship also publishes an open, source-linked seed dataset designed to
grow beyond the pilot communities.

Live: concordance.jonathancapone.com · Code: github.com/JonathanCapone/concordance

---

## Public benefit — *Who could use, question, or learn from this work?* (2000)

**Residents**, first. Somebody who grew up beside a river and wants to know what
the plant upstream was putting in it. That person cannot use an archive; they
can use a search box and a chart, and this is aimed at them.

**Journalists and local historians.** Every one of 107 title-derived Ontario
municipal report series ends by 1974 — 72 of them in that exact year. That is
an archival gap to investigate, not proof that measurement itself stopped —
and exactly the kind of finding this dataset exists to surface.

**Scientists**, who get a machine-readable series with the source page attached
to every value — and explicit refusals where two numbers are not comparable,
rather than a tidy line that hides a change of method.

**A British Columbia pilot community**, chosen before tuning — and the
transfer test has begun: overnight before submission, this reader published
366 quote-verified readings from eight Lower Mainland documents —
budgets, population, dwellings on sewers, by municipality — and met, on BC
paper, the table-column limit Week 4 measures. The collection's 582 BC items
run from the 1915 Hydrometric Survey to a 27-community First Nations
water-rights series.

**And anyone who wants to question it** — which is the part I care most about.
Every prose number carries its source sentence; a table number carries its cell
locator. Both carry the exact page. Prose claims from my reader and a stranger
face the same sentence-and-number check. Table claims currently abstain unless
the value can be localized to the cited cell. An objection without evidence is
counted and displayed but changes nothing; supported disagreements remain visible.

When two readings both survive, neither wins. Both link to the exact archive
page and, when its image service permits, show a cropped photograph of the
cited sentence; the reader decides from the evidence.

A measurement pulled by a model out of a sixty-year-old scan has no authority on
its own. It earns authority by being trivially easy to disprove.

---

## Proposed approach — *core method, tools, and a scope you can finish* (2000)

**The finding: OCR often preserves prose while damaging table layout.** One
summary table becomes `9 /zLA' y 1? in" y 1'\ Vnlump 41 Q sailor`, yet narrative
measurements remain legible: "The average influent BOD and suspended solids were
104 mg/1 and 224 mg/1 respectively... giving an average removal of 64% BOD."

So the tractable first problem is **reading prose**, where my four-page benchmark
measures 96.8% precision. Degraded tables remain the harder, unproven path.

**Method.** A cheap local filter routes each page — prose, table, figure, map,
or skip — so the expensive path only touches pages that earn it. A language
model reads the prose pages into typed records: an observation, a design
specification, a regulatory limit, or a conclusion. Keeping those apart is
load-bearing: one report states BOD 180 mg/L as a design figure and 104 mg/L as
a measurement, and conflating them produces a clean, plausible, entirely
fictional trend.

**Every prose record must quote its source sentence; that sentence and its
complete numeric token are checked on the cited page.** A model that invents a
number often invents the sentence too, so these local checks catch fabrication
without another model call. Table trials carry page, row and column locators,
but public verification abstains until the value is localized to that exact cell.

**Tools.** The core is standard-library Python with zero package dependencies,
so someone with Python can clone it and check a stored measurement without an
API key. New extraction additionally needs Ollama and a local model. Accuracy is
measured against pages a human read by hand, and the harness re-scores without
re-running the model.

**Scope I can finish:** widen the accuracy benchmark far beyond its current four
pages, settle whether tables can be read on ordinary hardware, and publish the
dataset with its methodology and its failures. Not: reading the whole archive.

---

## Dataset interest — *Why does this idea need the Canadian civics and open-government collection?* (2000)

I did not find these local historical readings in a usable national series, and
municipal holdings have not been surveyed here. The evidence survives in
scattered annual reports deposited with government and scanned by Internet
Archive Canada. Concordance can make it searchable together for the first time.

The collection is also uniquely suited to the method, in three specific ways.

**It repeats.** A title search found 546 dated matching reports, 1961–1996; 524
resolve to 107 title-derived place/site reporting series. One schema can turn
those readings into comparable series after duplicate facilities and names are
resolved.

**It is deep enough to show absence.** Silence is the most interesting signal
here — a town that vanishes from the record because a plant closed, a programme
was defunded, or records were lost. You can only detect that against a long
continuous baseline. Broader ministry publishing continued — 1,449 indexed items
before 1975 and 3,800 afterward — so this is not a collection-wide scanning
cutoff. It does not, by itself, explain the gap for any individual place.

**It is civics, not just science.** Roughly 13,600 titles match minutes, agendas
or hearings. They preserve motions and votes
beside the environmental reports, creating the possibility of linking what was
measured to the public decisions around it. That civic parser is promising but
not yet part of the validated measurement benchmark.

Public access to a scan is not a blanket licence for its contents. I will publish
code under MIT and release only derived data I can license, documenting the terms
while preserving each source item's rights.

---

## Work plan — *phases, and where you expect to learn or change course* (2000)

**Week 1 — Freeze the test.** Design and hand-label a benchmark spanning eras,
agencies and document types; choose a British Columbia pilot before tuning.

**Week 2 — Keep unlike records unlike.** Apply the 697-term source-attested
vocabulary already built; test units, methods and reporting changes; publish the
refusal rules for comparisons that are not defensible.

**Week 3 — Measure prose.** Run the benchmark, inspect failures, and publish
precision and recall by era and parameter, not only one flattering average.

**Week 4 — Test tables.** Compare smaller vision models on ordinary hardware
against hand-read pages. *Ends with:* a distributable path, or a measured limit.

**Week 5 — Complete the contribution loop.** Build the browser-to-local handoff,
then test request, preview, source-check and sharing with first-time users. If
the handoff is not safely testable in time, the user test runs on the
already-built share-by-file path and the handoff is published as a measured
limit, like the tables.

**Week 6 — Publish.** Release the seed dataset, accuracy report, methodology and
failures; offer the metadata proposals for review; write up and, if ready,
prepare for the conditional showcase.

**Where I expect to change course:**

1. **The tables may not distribute.** A smaller vision model may or may not be
   good enough for a contributor's laptop. I have not measured it. If it is not,
   the answer is a plain statement of what fraction of this archive needs
   hardware most people do not own — which is worth publishing too.
2. **The wider benchmark may come in materially lower.** All my evidence is
   Ontario water reports. If accuracy drops on other agencies and eras, I will
   publish that and narrow the scope rather than ship a confident dataset nobody
   has checked.
3. **Comparability may bite harder than expected.** If methods changes are
   pervasive, more of this becomes a finding aid and less a dataset. That is a
   real outcome, not a failure.

---

## Expected deliverable — *What working artifact will exist at the end?* (2000)

Four public things: MIT-licensed code, plus open data and methods with source
document rights preserved.

**1. A live website.** For a pilot town, see selected series and source records.
Every value links to its archive page and, when the
image service permits, a focused crop. The plain-language layer uses a documented
contemporary standard when one exists and otherwise gives no verdict. The frozen
seed covers 14 municipalities; the fellowship makes it worth visiting.

**2. The dataset, published open.** Every accepted pilot record carries place,
time, parameter and unit where applicable, plus an exact archive-page link. The
seed is not national coverage; I found no usable national machine-readable series
of historical municipal discharges.

**3. An accuracy report, including the failures.** Precision and recall per era
and per parameter, measured against pages a human read by hand, published with
the methodology and a script anyone can re-run to re-score my own output against
my own answer key. If the number is bad in places, those places are named.

**4. A metadata diff offered back to Internet Archive Canada** — 13,429
catalogue-field proposals so far, language-code normalizations and year
proposals, offered for the Archive's review rather than applied. The
validation evidence, including its limits, is in the repository.

Plus the pipeline itself, documented so it can be pointed at any other scanned
archive. The document-reading method is reusable; place resolution and validation
currently remain Ontario-specific.

**What will not exist:** the whole 22.1-million-page archive read. A full
rented-GPU pass is outside this fellowship, and the current cost model is not
reliable enough to quote. What will exist is the machinery, a seed corpus, an
honest accuracy figure, and a system where the rest can fill in on demand —
without a permanent central inference bill.

---

## Success metric (600)

A resident in each published pilot community — the frozen 14 plus at least one
British Columbia pilot — can look up a measurement, see "unknown" when no verdict
is justified, and open every published record's source page.

Pass/fail: code, data and a benchmark anyone can re-score are public; precision
and recall are reported by era and parameter; and one person outside the project
completes request → local extraction → preview → source-check → share without
assistance. Each published archival gap states what evidence rules out and what
remains unknown. National coverage is a stretch goal.

---

## Relevant experience — *What prepares you to do this work* (2000)

**I have built the hard half already, and you can check it rather than take my
word.** At checkpoint `763d4c0`: 5,147 source-linked records across 14
municipalities and 96.8% precision on four hand-read pages. The full test suite
passes; no core package dependencies are required.

Before this I built OMEGA-wave, an open ocean-sensing system with its own
protocol, gateway, statistics and map portal. Concordance reuses its
standard-library statistics and provider patterns: Mann-Kendall, Theil-Sen,
Pettitt changepoints and keyless Environment Canada/Statistics Canada access.
Six weeks here is not six weeks from zero.

**What I think actually qualifies me is how I handle being wrong**, because that
is the whole risk in this kind of project. Three examples are documented in the
project evidence prepared for publication:

The first accuracy figure I produced was 49% precision — and it was wrong. My
scorer could not tell that "3.0 million gallons" and "3000000 gallons" are the
same number. Fixing the *measurement*, with no change to the extraction, moved
it to 88.7%; improving the extraction prompt then took it to the published
96.8%. Publishing the first number would have narrowed the project for no
reason.

My page router was silently discarding narrow-column prose because it required
eight words on a line — a fact about typography, not content. I did not find
that. Somebody looked at a document and said *that doesn't sound right*.

And days before writing this I ran an adversarial audit over the repository. It
found nine defects, six rated serious, including a check that accepted a number
against a sentence containing only its first digit. The fixes have targeted
regressions, and the full test suite passes.

A project whose entire claim is *check my work* should say what happened when
somebody did.
