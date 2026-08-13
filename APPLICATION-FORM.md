# Concordance — answers for the BC + AI application form

Each answer is written to stand alone, because they are read as separate fields
in a review database and a reviewer may not read them in order. Character counts
are checked by `scripts/check_form.py`; the limits are the form's own.

---

## Project title

Concordance

---

## Project summary — *What do you want to build or create?* (2000)

A free website where anyone can look up what was actually measured where they
live — sewage discharged into the river, what was in the drinking water, what
came out of the smelter — going back to the 1800s, with every number linked to a
photograph of the government page it was read from. Plus the open dataset
underneath it, which does not currently exist anywhere.

Internet Archive Canada holds 104,241 scanned government publications: 22.1
million pages, 1841 to 2013. Inside them are measurements of the physical
condition of the country, town by town, year by year. The median document has
been downloaded 90 times.

The brief calls it ~48 TB; that is the page images. **The text inside them is
about 59 GB** — the written output of the Canadian state, as digitised, fits on
a thumb drive.

None of those numbers are in any database. To learn what your town's plant
discharged in 1969 you would have to know the report exists, find it, read it.

**There is no central machine that reads the archive. The reading happens on the
computer of whoever asks.** You look up your town: if somebody has already read
it you get the answer instantly, from data everyone shares. If nobody has, the
site says so — *"Nobody has read this one. 12 scanned reports are waiting, about
an hour on this machine"* — and you can press a button. Your own laptop fetches
those scans and reads them, roughly a minute a page, and the result is published
back so the next person gets it instantly. No account, nothing left running.

That is why there is no compute line in my budget, and it is the difference
between a dataset that is finished the day the grant ends and one that keeps
growing afterwards.

It already runs. Six towns read end to end, 1,470 measurements, 96.8% precision
against pages a human read by hand first, and every quoted sentence verified to
occur on the page it cites — 0 failures in 286 records.

---

## Public benefit — *Who could use, question, or learn from this work?* (2000)

**Residents**, first. Somebody who grew up beside a river and wants to know what
the plant upstream was putting in it. That person cannot use an archive; they
can use a search box and a chart, and this is aimed at them.

**Journalists and local historians**, who currently need to know a report exists
before they can find it. The negative record matters as much: 72 of 107 Ontario
municipalities stop filing sewage-plant reports in 1975, and knowing *when a
place stopped being measured* is often the story.

**Scientists**, who get a machine-readable series with the source page attached
to every value — and, just as importantly, explicit refusals where two numbers
are not comparable, rather than a tidy line that hides a change of method.

**Internet Archive Canada itself.** 57% of the collection has no subject tag and
32% has no year, which is why most of it cannot be found by anyone looking. I
have 13,429 metadata corrections ready to offer back.

**And anyone who wants to question it** — which is the part I care most about.
Every number carries the verbatim sentence it came from, and that sentence is
checked against the scan. Anyone can dispute a value by citing a page and
quoting a sentence, and the archive settles it: the same check that judges my
own output, which never asks who is speaking. Evidence beats no evidence,
automatically. An objection without evidence is counted and displayed and
changes nothing — because the moment it could, somebody would have to sit in
judgement, and I am not willing to be that person or appoint one.

When two readings both survive, neither wins. Both are shown with a cropped
photograph of the sentence each was read from, and the reader decides in
seconds.

A measurement pulled by a model out of a sixty-year-old scan has no authority on
its own. It earns authority by being trivially easy to disprove.

---

## Proposed approach — *core method, tools, and a scope you can finish* (2000)

**The finding this rests on: OCR preserved the prose and destroyed the tables.**
A province-wide summary table comes back from the scanner as
`9 /zLA' y 1? in" y 1'\ Vnlump 41 Q sailor`. Nothing survives that. But the
narrative paragraphs read perfectly — and in these reports the measurements are
*in the narrative*: "The average influent BOD and suspended solids were 104 mg/1
and 224 mg/1 respectively... giving an average removal of 64% BOD."

So the hard problem is **reading**, which language models now do reliably, not
table-recognition off a degraded scan, which they do not. That is what makes
this tractable rather than absurd.

**Method.** A cheap local filter routes each page — prose, table, figure, map,
or skip — so the expensive path only touches pages that earn it. A language
model reads the prose pages into typed records: an observation, a design
specification, a regulatory limit, or a conclusion. Keeping those apart is
load-bearing: one report states BOD 180 mg/L as a design figure and 104 mg/L as
a measurement, and conflating them produces a clean, plausible, entirely
fictional trend.

**Every record must quote the sentence it came from, and that sentence is
verified to occur on the cited page, and the value verified to occur in the
sentence.** A model that invents a number nearly always invents the sentence
too, so this catches fabrication for the cost of a substring search.

**Tools.** Python, standard library only — the core has zero required
dependencies, so anyone can clone it and check a measurement in five minutes
with nothing to install and no API key. Extraction runs on a local model via
Ollama by default. Accuracy is measured against pages a human read by hand, and
the harness re-scores without re-running the model.

**Scope I can finish:** widen the accuracy benchmark far beyond its current four
pages, settle whether tables can be read on ordinary hardware, and publish the
dataset with its methodology and its failures. Not: reading the whole archive.

---

## Dataset interest — *Why does this idea need the Canadian civics and open-government collection?* (2000)

Because the numbers exist nowhere else. This is not a convenient corpus for a
general method — it is the only surviving record of most of what it describes.

Statistics Canada does not hold what Owen Sound's sewage plant discharged in
1969. The province's modern pollutant inventories start in the 1990s. The
municipality itself, in many cases, no longer has the file. The measurement
survives because a civil servant typed it into an annual report, the report was
deposited, and Internet Archive Canada scanned it. **If it is not recovered from
this collection it is not recovered.**

The collection is also uniquely suited to the method, in three specific ways.

**It repeats.** 547 municipal water pollution control plant reports, 1961–1996,
across 411 distinct municipalities, in a standardised recurring form. One schema
generalises across hundreds of places and thirty-five years, which is what turns
isolated readings into comparable series.

**It is deep enough to show absence.** Silence is the most interesting signal
here — a town that vanishes from the record because a plant closed, a programme
was defunded, or records were lost. You can only detect that against a long
continuous baseline, and you can only distinguish it from a digitisation gap if
the collection is complete enough to check. It is: I verified the 1975 collapse
against the same ministry's own publication counts, which run 1,449 before and
3,800 after.

**It is civics, not just science.** Minutes, agendas and commission hearings are
13,604 items. One volume of Hamilton council agendas from 1992 yields 94
decisions, 64 named people and 44 recorded votes, including the divisions where
one alderman stood alone against an expressway. The measurements and the
decisions that produced them are in the same collection, which is the thing that
makes joins possible.

And it is public and openly licensed, so everything built on it can be too.

---

## Work plan — *phases, and where you expect to learn or change course* (2000)

**Weeks 1–3 — Make the accuracy figure real.** The benchmark is four pages read
by hand by one person: enough to justify continuing, not enough to publish a
dataset on. So: bulk text acquisition across the collection, then a much larger
hand-read benchmark spanning document types, agencies and eras, with accuracy
published per era and per parameter rather than as a single number. *Ends with:*
a figure I would defend in public, including where it is bad, plus a seed corpus
of towns and years.

**Weeks 3–5 — The tables.** This is the hard one and it gets two weeks. Tables
are 27% of pages and about 69% of the measurements, and they need a model that
will not run on an ordinary machine. Owen Sound's 1973 and 1974 reports contain
*zero* readable prose pages between them; those years are unreachable without
this. *Ends with:* either tables distribute to contributors' machines, or the
limit is named with a number attached.

**Week 6 — Publish.** Dataset released with its methodology and failures;
metadata corrections offered to Internet Archive Canada; write-up; showcase.

**Where I expect to change course.** Three places, honestly:

1. **The tables may not distribute.** A smaller vision model may or may not be
   good enough for a contributor's laptop. I have not measured it. If it is not,
   the answer is a plain statement of what fraction of this archive needs
   hardware most people do not own — which is worth publishing too.
2. **The wider benchmark may come in materially lower.** All my evidence is
   Ontario water reports. If accuracy drops on other agencies and eras, I will
   publish that and narrow the scope rather than ship a confident dataset nobody
   has checked.
3. **Comparability may bite harder than expected.** If methods changes turn out
   to be pervasive, more of this becomes a finding aid and less of it becomes a
   dataset. That is a real possible outcome and not a failure.

---

## Expected deliverable — *What working artifact will exist at the end?* (2000)

Four things, all public, all open source under MIT.

**1. A live website.** Search a Canadian town, see what was measured there and
when, as charts and as a table. Every value has a button that shows you a
cropped photograph of the sentence on the original scan it was read from. A
plain-language layer answers "was 104 mg/L bad?" against the regulatory limit
*of that era*, not today's. It runs now, over six towns; the fellowship makes it
worth visiting.

**2. The dataset, published open.** Every measurement with place, time,
parameter, unit, and a link resolving to the exact scanned page. Not a sample —
every record. This object does not currently exist: there is no machine-readable
series of what Canadian municipalities discharged, decade by decade, anywhere.

**3. An accuracy report, including the failures.** Precision and recall per era
and per parameter, measured against pages a human read by hand, published with
the methodology and a script anyone can re-run to re-score my own output against
my own answer key. If the number is bad in places, those places are named.

**4. A metadata diff offered back to Internet Archive Canada** — 13,429
corrections proposed so far for items with no subject tag or no year, which is
57% and 32% of the collection respectively.

Plus the pipeline itself, documented so it can be pointed at any other scanned
archive, because nothing in the reading layer is Canada-specific.

**What will not exist:** the whole archive read. 22.1 million pages is roughly
$4,251–8,502 of rented GPU time and I am not asking for that, because a corpus
bought in one batch is finished the day the money stops. What will exist is the
machinery, a seed corpus, an honest accuracy figure, and a system where the rest
fills in as people ask for it — at no recurring cost to anyone.

---

## Success metric (600)

A resident of any Canadian community can look up what was measured where they
live, get a plain-language answer, and click any number through to the scanned
page it came from.

Checkable: the dataset is published open, with place, time, parameter and unit;
**every** record resolves to its scan, not a sample; accuracy is published per
era and per parameter on a benchmark anyone can re-score themselves, including
where it is bad; and where a series stops, the record says what was ruled out —
both "never scanned" and "the reporting rules changed".

---

## Relevant experience — *What prepares you to do this work* (2000)

**I have built the hard half already, and you can check it rather than take my
word.** The repository runs today: six towns read end to end, 1,470
measurements, 96.8% precision against hand-read pages, 531 tests, zero required
dependencies in the core.

Before this I built OMEGA-wave, an open ocean-sensing system with its own
protocol, gateway, statistics suite and map portal — about 30,000 lines with 118
data-provider definitions. Concordance reuses that directly: the statistics
layer (Mann-Kendall trend detection, Theil-Sen, Pettitt changepoint, all pure
standard library, which is why this package still has no required dependencies),
the map portal, the agent framework, and the keyless provider layer that reaches
Environment Canada and Statistics Canada. Six weeks here is not six weeks from
zero.

**What I think actually qualifies me is how I handle being wrong**, because that
is the whole risk in this kind of project. Three examples, all in the public work
log:

The first accuracy figure I produced was 49% precision — and it was wrong. My
scorer could not tell that "3.0 million gallons" and "3000000 gallons" are the
same number. Fixing the *measurement*, with no change to the extraction, moved
it to 96.8%. Publishing the first number would have narrowed the project for no
reason.

My page router was silently discarding a fifth of the archive, because it
counted a page as prose only if its lines held eight or more words — a fact about
typography, not content. I did not find that. Somebody looked at a document and
said *that doesn't sound right*.

And days before writing this I ran an adversarial audit over the whole
repository. It found nine real defects, six serious, including one where the
check that is supposed to catch invented numbers would accept any round number
against any sentence containing its first digit. All fixed and tested against the
attacks that found them.

A project whose entire claim is *check my work* should say what happened when
somebody did.
