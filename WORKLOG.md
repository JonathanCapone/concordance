# Work log

Notes from building Concordance. Written as it went, kept honest on purpose —
the wrong turns are most of the value here, and every one of them is still in the
git history if you want to check.

---

## The thing that made this possible

I nearly didn't start. The plan was to pull measurements out of scanned
government reports, and the obvious problem is that measurements live in tables,
and OCR from 2013 destroyed the tables. Here is a provincial summary table, as
the scanner left it:

```
9 /zLA' y 1? in" y 1'\ Vnlump 41 Q sailor
```

There is nothing in there. If that were the whole story the project would need a
vision model reading twenty-two million page images, and it would be a research
project with a hardware budget rather than something one person could start on a
Tuesday.

Then I read the Owen Sound annual report for 1969 properly, and the narrative was
perfect:

> "The average influent BOD and suspended solids were 104 mg/1 and 224 mg/1
> respectively. The average effluent BOD and suspended solids were 37 mg/1 and
> 36 mg/1 respectively, giving an average removal of 64% BOD and 84% suspended
> solids."

Station, parameter, value, unit. A complete set of measurements, in a sentence a
model can read without effort. **OCR preserved the prose and destroyed the
tables, and in these documents the measurements are in the prose.**

That is the whole project. Reading, not table recognition. It is why six weeks is
a plausible amount of time and why the thing runs on a consumer GPU.

---

## The number that was wrong

The first accuracy run came back at **49% precision** and I nearly narrowed the
whole project on the strength of it. Half of what it extracted was apparently
junk. That is the kind of number that makes you retreat to a smaller claim.

I went through the records it had marked wrong before believing it, and nearly
all of them were right. The scorer couldn't tell that "3.0 million gallons" and
"3000000 gallons" are the same measurement. My hand-written answer key had six
entries for a page with twenty-six values on it, so twenty correctly-read
specifications counted as fabrications.

I fixed the *measurement*. I changed nothing about the extractor. Precision went
from 49.1% to **88.7%**.

I keep coming back to this one. If I had published the first figure, I would have
cut scope, apologised for the accuracy, and shipped something smaller — and every
step of that would have felt like rigour.

---

## The 1975 cliff

I built a thing to find what stopped being measured, ran it across Ontario's
municipal sewage reports, and got a result that looked too good: **72 of 107
towns stop filing in the same year, 1975.**

A whole series vanishing at once almost always means the scanning stopped, not
the reporting. So before getting excited I checked whether the archive itself
stops in 1975. It does not. Ministry of the Environment publications in the same
collection run 1,449 before that year and 3,800 after, at a steady 83 to 141
items a year straight through. The archive kept growing. This one series died.

I still don't know *why*. The Ontario Water Resources Commission was folded into
the Ministry of the Environment in 1972, which is a plausible cause and nothing
more than that. Finding out needs a document, not an inference.

Later, pulling live river gauge data for something else entirely, I found that
**539 of Ontario's 1,119 hydrometric stations are discontinued** — 48%. The same
winding-down of measurement, still going on, and now visible with a fifty-year
run-up behind it.

---

## Two Sydenham Rivers

The watershed network was the most fun to build and the most humbling. Treatment
plants get tied to the nearest river gauge and ordered by catchment area, which
necessarily grows downstream — so the towns sort themselves without any flow
routing at all. It produced the right geography on the first run: Fergus to
Brantford to Cayuga on the Grand, Orangeville to Streetsville to Clarkson on the
Credit.

And one confident, complete fabrication: Owen Sound to Wallaceburg on the
"Sydenham River". Ontario has two Sydenham Rivers. One drains to Georgian Bay,
the other to Lake St. Clair, and they have never been connected to each other in
the history of the province. My distance guard was 300 km, picked out of the air,
and their gauges are 244 km apart.

I recalibrated against the actual data instead of guessing again. Real rivers in
this set reach 127 km of gauge spread (the Thames); the Sydenham pair spans 244.
150 km separates them cleanly. Anything excluded is reported rather than dropped,
because a genuinely long river would fail the same test.

The portal shows what the method *refused* to link, next to what it linked. A
page that displays only its successes teaches nobody where it fails.

---

## Measuring away the thing being measured

The silence detector took its cutoff year from the data it was testing. Every
parsed town's last report was 1974, so the horizon became 1974, so no town could
ever register as having gone silent. It confidently reported **9** municipalities
instead of **72**.

That one is almost funny. The measurement defined away the thing it was
measuring, and the output looked completely reasonable.

---

## The chart that was plotting the wrong quantity

Parameters were being matched by substring, which is fine until you notice that
"suspended solids" is inside "suspended solids removal". The chart labelled
*effluent concentration* was plotting *removal percentages*.

Both are small positive numbers that go down when a plant improves. It looked
entirely sensible. Nothing about it was.

The same class of thing showed up again in Brantford's 1962 report, which says
the Commission's objective for BOD "was exceeded only 20 per cent of the time".
That arrived as **BOD removal: 20%** — and the meaning inverts. 20% exceedance is
a good year. 20% removal is a failing plant.

---

## Four attempts at a regex

Fixing that took four goes, and three of them failed for a reason that took an
embarrassingly long time to see: I was writing the pattern through a shell
heredoc, which collapsed every `\b` into a literal backspace character. The
pattern printed identically to a correct one and matched nothing at all, because
it was demanding actual control characters in the input.

The repository is now checked for stray control bytes rather than assumed clean.

---

## Provenance that lied

The whole trust model here is one sentence: *this number came from that sentence
on that page*. Everything else rests on it.

I opened the town panel and every single row was quoting the same sentence — the
flow figure, attached to BOD removal, solids discharged, everything. Source
records were being matched on year alone.

Wrong provenance is worse than no provenance. Missing evidence is visibly
missing. Wrong evidence looks like evidence.

---

## The vocabulary was the gap, not the reading

I audited 281 extracted records looking for defects. The best result was the one
with nothing in it: **zero quotes failed verification.** Every source sentence
really was on the page it cited. The hallucination guard holds.

The worst result was that **36.7% of records carried a parameter my table had
never heard of** — hardness, retention time, trihalomethanes, digester gas. All
extracted correctly. All then dropped from every chart without a word, because
nothing knew what they were.

The extractor wasn't the problem. My list was. Adding those terms took unresolved
records from 36.7% to 15.0%, and records with no flag at all from 36% to 69%.

Buried in the same audit: drinking-water reports give trace contaminants in
`ug/L`. Reading 8 ug/L as 8 mg/L overstates it a thousandfold, and both numbers
look completely unremarkable sitting on a page.

---

## One town, two facilities

The Owen Sound extraction walked out of the sewage annual reports and straight
into a 1992 Drinking Water Surveillance report, because both are titled "annual
report" and both say Owen Sound.

One measures what the town put into the river. The other measures what came out
of people's taps. Merged under one name, the chart isn't just wrong, it's
backwards. Owen Sound's record appeared to run to 1992 with a seventeen-year gap
in the middle. It actually ends in 1972, and there is no gap at all.

---

## The first trend was a refusal

The first real trend the system produced, after all of that:

```
daily flow: increasing +1.75e+05/yr  (90% CI -1.31e+06 to +1.36e+06, p=0.707)
  -- not significant
  -- UNSTABLE: only 62% of replicates agree on direction
  SUSPECT: 1968 — value is ~10x from the series median
  SUSPECT: 1972 — 10 mgd against a plant with 3.0 mgd design capacity
```

A naive pipeline publishes the slope. This one produced the number and then took
it apart: not significant, direction unstable once you carry reading confidence
through, and two of the six points probably damaged in the scan.

That refusal is the product. Everything else is plumbing.

---

## What it costs to read all of it

Twenty-two documents are read. There are 104,241. That is **0.02%**, and it took
days.

So I worked out what reading the whole thing would actually cost, because the
honest version of this project has to answer that rather than gesture at it.
11.7 million pages worth reading, 13.9 billion tokens. On my machine: 56
machine-years, which is not a plan. On a rented A100 at spot pricing: **roughly
$1,500 and about two months.** On an H100: less.

The whole Canadian public record, read once, for less than a third of the
fellowship. And it is a one-time cost — afterwards the dataset costs everybody
else nothing forever.

I want to be careful about that number. The rented throughput is estimated rather
than measured, and the first thing a funded run should do is measure it on a
thousand pages before committing to the rest. Tables and figures are 26% of pages
and need a vision pass that is slower and dearer. And any change to the
extraction prompt means paying the whole bill again, so the prompt has to be
settled before the money is spent.

---

## Reading as a side effect of wanting to know

There is no volunteer mode in this, and nothing is asked of anyone.

You ask for a place's record. If it has been read, you get it in milliseconds. If
you are the first person to want it, your machine reads it — and from then on it
is there for everyone.

The cost lands on whoever cares first, who is also the person most willing to
wait. Nobody has to be altruistic. And the archive ends up read in the order
people actually want to know things, which is a better ordering than anything I
would have imposed.

It works because verification doesn't care about the subject. Every record
carries its sentence and its page, so the check asks the archive rather than the
person: is that sentence there, and is that number in it. I can accept a
contribution about school examinations while knowing nothing whatsoever about
school examinations.

Both obvious attacks fail. Invent a sentence and it fails. Change a number while
keeping its real sentence — the poisoning a quote check alone can't see — and it
fails too, because the value has to appear in the sentence it cites.

What it cannot catch is misreading. "104 mg/1" really being on the page says
nothing about whether it is influent or effluent. Verification catches
fabrication, and pretending otherwise would be worse than having no check.

---

## What the archive nearly knows

The last piece is the one I like most.

Some questions are one document away from being answerable. *"Did what Fergus
discharged show up in Brantford's intake?"* needs both towns. Brantford is read.
Fergus is not. So that question has been sitting one document short since 1961,
and nobody knew.

Computing that across everything gives eleven million pages an ordering nobody
otherwise has. Not alphabetical, not chronological — **by what reading it would
unlock.** Right now the top of that list is Fergus, which opens three questions at
once, including the end-to-end picture of the Grand River.

It also replaces a progress bar with something true. "You processed 40 documents"
is a fact about you. "You made the Grand River answerable, and it had been waiting
since 1961" is a fact about the world.

---

## A magazine about Hamilton, and a fifth of the archive

Someone asked me a simple question — what happens to a document like *Hamilton:
An Adventure in Good Living*, a 1983 city booster magazine that isn't data at
all? I said the router handled it: 70% of its pages skipped, one page reaching
the extractor, and that page an advertisement.

Then they said: *there was lots of text in that document.* There was. The router
was throwing away 68% of it.

The cause is one number. A line counted as prose if it had at least eight words.
That magazine is set in narrow columns — 149 lines of unbroken prose on one page,
median four words to the line, not one reaching eight. It scored a prose ratio of
**0.000** and every page went to the bin, including one that says *"75 elementary
schools under the aegis of the Hamilton Board of Education, and 42 operated by
the Hamilton-Wentworth Roman Catholic Separate School Board"* — exactly the kind
of fact nobody has in a database. Another page had nineteen unit matches on it
and was skipped anyway, because the prose gate is tested before units are ever
considered.

An eight-word threshold is a statement about typography, not about content, and
it had been quietly deciding which parts of the Canadian public record exist.
Across 8,372 pages from 34 documents in 26 collections:

| | pages worth reading |
|---|---|
| original rule | 48.5% |
| threshold taken from the page's own median line | 68.8% |
| a counted noun ("75 elementary schools") reads as a unit | 69.5% |

Twenty-one points. Extrapolated over the corpus, about **6.3 million pages**.

The loss fell hardest on exactly the material you would least want to lose,
because minutes have always been set in narrow columns:

```
Acts of the Parliament of Canada      265 → 861 pages
Journals of the House of Commons      193 → 542
Ontario Bills, 1952-53                753 → 1169
Journals of the Legislative Assembly  145 → 185
```

Census tables and other tabular items are unchanged, so the fix is targeted
rather than indiscriminate. And the cost model is now wrong in the expensive
direction: 11.7 million pages worth reading becomes about 15.4 million.

I would not have found this. It took someone looking at a document and saying
*that doesn't sound right*.

---

## The council knows who voted for what

The same conversation turned up a second thing: could the archive say who
decided what? It can, and it OCR'd beautifully.

> "It was moved by Alderman Eisenberger and seconded by Alderman Morelli that
> the Building Commissioner be authorized to issue a demolition permit for
> 336-338 Jackson Street West ... CARRIED."

> "Recorded vote. YEAS: Mayor Morrow, Aldermen Cooke, Kiss, Agro, McCulloch,
> Morelli, Copps, Wilson, Agostino, Eisenberger, Charters, Jackson, Merling,
> Anderson, D'Amico, Ross. -16. NAYS: -0."

That is a complete municipal roll call from 1992, naming sixteen people and how
each of them voted, sitting in a scanned volume nobody has opened. Deliberative
records — minutes, agendas, hansard, committee reports, royal commission
hearings — are **13,604 items, 13.1% of the collection**, and they were the
category most damaged by the routing bug above.

One volume of Hamilton council agendas, 353 pages: **94 decisions, 64 people, 44
recorded votes.** Each links to its scanned page, so the divided ones read like
this:

```
[carried] against Copps     Red Hill Creek Expressway property acquisitions
[carried] against Copps     Capital grant to McMaster for campus sports fields
[carried] against Merling   A.M.O.'s response on Apartments in Homes
```

The spine of it needs no model at all. "It was moved by X and seconded by Y that
Z. CARRIED." is a form that has barely changed in a century, so a pattern finds
it — free, fast, and checkable by a person in a way a model's answer is not. A
contributor can extract a full council year on a laptop with no GPU.

The control is the clerk's own tally. That "-16." was written by someone who was
in the room, and if the names parsed disagree with it, the roll was misread. It
earned its place immediately by catching three of my bugs, including one where
an empty NAYS list ran past a speck of scanner dirt and swallowed the following
paragraph, recording twelve councillors as opposing what they had just voted
for.

What this does not claim is that a motion which carried was ever carried out. A
resolution is a promise. Whether the expressway got built lives in a later
document, which makes it a frontier question rather than a fact.

---

## The tables were never lost

The vision path has been built and unproven from the start. llava invents table
structure — it returns plausible rows that are not on the page, which is worse
than useless, because a fabricated table is indistinguishable from a recovered
one. About a quarter of the corpus sat behind that.

qwen3.6 reads them. Given the Brantford 1962 flow table, whose OCR reads:

```
TABLE I FLOW - MILX.IQN GALLOLS MONTH MAX. DAILY r low MIN. DAILY
TOT ^i.r i' low AVa. DAILY r .LOW TOTAL MONTHLY -C ?ow
Jan. 6.976 4.609 5.700 176.547
```

it returned 27 records and **every one of the twelve values that survived in the
OCR, exactly**. It also rebuilt the header row the scanner destroyed and filed
each value under its month. I checked it against the actual scan afterwards, and
the whole table is right.

Across three more pages from completely different documents — Statistics Canada
salt production 2003, Alberta Liquor Control 1942, a Simcoe well supply report
from 1990 — **58 of 58 values are on the page.** A wider run is going.

The honest caveat is speed. Nine minutes a page on my RTX 2080, where only 18%
of the model fits in VRAM. It is a mixture of experts firing 8 of 256 per token,
which is exactly the shape that runs cheaply on rented hardware where the whole
thing is resident — but local bulk table extraction is not practical.

Which raises the question someone put to me directly: **so most of this can't be
done by people?**

Most of the *pages* can. 73% of the work is text a consumer machine handles, at
about 91 seconds a page — a typical document takes an hour and a half, which is
exactly the "ask for your town, come back after dinner" model. But prose pages
average 4.2 records and a third yield nothing, while a table page yields around
eighteen. So tables are probably the majority of the *measurements* while being
27% of the pages.

That is not a retreat, it is where the line falls. The central rented pass does
what is expensive and uniform — the vocabulary and the tables — once, and
everyone inherits it free. People do prose, on demand, which is where places,
dates, narrative and the entire deliberative record live.

---

## A picture of the paper

Every record already carried a page and a sentence, which is enough for someone
to check — except that checking meant opening a 300-page scan and hunting for a
line, so nobody did. The provenance was real and unused, which is most of the way
to not having it.

Now a record produces a picture of the exact patch of scan its number is written
on. Checking stops being a task and becomes a glance. It costs nothing:
archive.org serves IIIF, so a crop is a URL — no image library, no storage, no
key, no server of mine in the path.

The trap took a while. The two archive.org endpoints number the same sheet
differently — BookReader `n14` and IIIF `$15` are both that flow table — and
feeding one index to the other crops the previous page. I briefly believed this
meant every provenance link in the project was off by one. It doesn't; the
existing links were right and my new module was wrong. The only way to settle it
was to fetch both pages and look at them.

---

## Letting anyone correct anything, with nobody moderating

The usual way to take public contributions is to appoint people who decide which
ones are good. That is the part nobody wants to run, and the part that makes a
project political — whoever holds the delete button holds the record.

One rule avoids it: **every claim must cite a page and quote a sentence, and the
archive decides.** That already governs the machine's own output, and nothing
about it is specific to a model. It never asks who is speaking.

So adding a reading, correcting one, and flagging one become the same operation,
with one deliberate inequality. An evidenced correction replaces an unevidenced
record automatically, nobody in the loop. An unevidenced flag is counted and
shown and changes nothing — because the moment an objection with no evidence can
outrank a sentence on a page, somebody has to judge the objection.

And when two claims both verify, nobody wins. Both are shown with both crops.
That is the honest outcome for what verification genuinely cannot catch: *"the
average influent BOD and suspended solids were 104 mg/1 and 224 mg/1
respectively"* pairs parameters to values by word order alone, so reading it the
wrong way round produces a real number from a real sentence and passes every
check. The machine has no basis to choose. A reader looking at two crops has an
excellent one, and takes about two seconds — which is only possible because of
the pictures. The crop is what makes refusing to moderate workable rather than
wishful.

Run over the machine's own records it immediately found two of my bugs. Influent
and effluent were sharing an identity, so Brantford's 1962 raw sewage at 210 ppm
and its effluent at 10 ppm were reported as a contradiction — they are the plant
working. And the strict digit check was convicting the extractor of the
scanner's crime: 1960s scans render 15 as "I5", so correct readings were being
thrown out.

```
settled     535 → 617
contested    76 → 56
unsupported  29 → 13
```

Then it found something nobody was looking for. 27 of the 56 remaining disputes
are one sentence read two ways, and most are the same shape: a comparison
sentence carrying two years' numbers. *"The average solids concentrations of
5.1% was less than the 1968 average of 5.3%"* files both under 1969. 8.2% of all
records come from a sentence naming another year.

I built the fix — attribute each value to its nearest year — and it was wrong.
It moved fourteen records and got several wrong in a new direction, because in
*"an increase of 0.7 percent over 1967 flows"* the 0.7 is the 1968 increase, not
a 1967 value. Telling those apart is grammar, not proximity. So the sentence is
flagged and a person decides, which is what the contested view is for. An
invisible wrong year turns a flat series into a trend, and that is the failure
this whole project exists to avoid.

---

## The ruler was wrong again

Third time. The corpus-wide vision trial's first page scored **0%** on the
fabrication control — the signal that means the model invented a table.

It hadn't. The page is a Statistics Canada salt table, and Statistics Canada
writes thousands with a space: `69 689`. My control tokenised the page into
number-shaped strings, so that became "69" and "689" and never matched the
model's entirely correct 69689. All twenty-five values were right.

The pattern across all three occasions is worth writing down, because it is not
obvious and it has cost me a day each time: **a control stricter than the world
reports a catastrophe, and a catastrophe is the one result nobody double-checks.**
49% precision, nine silent municipalities, 0% of values on the page. Each time
the instinct was to fix the thing being measured. Each time the measurement was
the problem.

---

## Where it stands

| | |
|---|---|
| Commits | 47 |
| Tests | 397 |
| Documents read | 22 of 104,241 |
| Pages worth reading | 69.5% of the corpus (was 48.5%) |
| Precision / recall | 88.7% / 82.5% — blind page 88/88 |
| Quotes failing verification | 0 of 286 |
| Vision values found on their own page | 58 of 58, across four documents |
| Measurements settled / contested / unsupported | 617 / 56 / 13 |
| Dependencies in the core | none |

The pipeline works and is measured. It has barely been pointed at anything.
Those are both true and the second one is the point: what needs funding isn't the
tooling, which exists — it's the reading.

Three things I would not have found alone, all from someone asking a plain
question about a document: a fifth of the archive being discarded on line width,
the entire deliberative record sitting unread, and the fact that a picture of the
paper is what makes open contribution possible without a moderator.

---

## The controls were the bugs

By the end of one day I had found four measurement errors, and every single one
was in the instrument rather than the thing being measured. Written out
together, because the pattern is more useful than the four stories:

| what it reported | what was true |
|---|---|
| 49% extraction precision | 88.7% — the scorer couldn't convert "3.0 million gallons" |
| 9 municipalities went silent | 72 — the cutoff year came from the data under test |
| 0 of 25 table values on the page | 25 of 25 — Statistics Canada writes thousands with a space |
| 25 census records fabricated | 0 — the heading wasn't contiguous in the OCR |

**A control stricter than the world reports a catastrophe, and a catastrophe is
the one result nobody double-checks.** That is the whole lesson. A number that
looks bad feels like rigour, and rigour is not something you interrogate. Each
of these cost the better part of a day, and each was found by looking at what
the control had thrown away rather than at what it had kept.

The two vision cases were worse than the others in a specific way. The label
check rests on OCR having wrecked a table's *values* while sparing its
*headings*, which are set in larger, cleaner type. That is true of a page whose
text layer is damaged and false of one where it was destroyed — so the check
fired hardest on exactly the pages the vision path exists for. The worse the
scan, the more the model is needed and the less it can be checked, and treating
the text layer's silence as a refusal turns that into an absence of data.

I fixed it first with a minimum character count, and a test showed within a
minute why that was wrong: the plot page that catches a model inventing
"Phosphorus / Month" has about 150 characters of OCR, and the table page I had
wrongly emptied has about 1,000. No threshold separates them. What separates
them is that the plot page can find "Phosphorus" and the other page can find
nothing at all — so each page now decides for itself whether its OCR is entitled
to referee. That generalises; a constant tuned to two examples would not have.

I also claimed, in a commit message, that the failures were a French-language
bias, because six of the seven damaged pages were French or bilingual. The
seventh was the Georgian Bay Ship Canal Survey of 1909, entirely in English, and
it disproved me. The real cause had nothing to do with language.

One practical thing came out of all this. The trial had been recording *how
many* records the verifier discarded and not *what they were*, so when the rules
turned out to be wrong the damage could not be replayed and seven pages had to
be read again. Keep the rejects, not the count.

---

## 2026-08-16 — the browser gate, measured the day it was named

The endgame was written into the Work plan today: models small enough to run
inside a browser, gating "read this town" as a button with nothing installed.
Measured the same afternoon, on the existing four hand-read gold pages
(68 values; small sample, stated with every figure):

| model | size | browser-viable | precision | recall | matched |
|---|---|---|---|---|---|
| llama3.2 3B | 2.0 GB | any WebGPU browser | 61.5% | 23.5% | 16 |
| qwen2.5 7B | 4.7 GB | good GPU only | 100% (20/20) | 29.4% | 20 |
| gemma4 12B | 7.6 GB | no (installed) | 96.8% | 88.2% | 60 |

Read: the 2 GB class is both unreliable and blind — not viable. The ~5 GB
class is BLIND BUT TRUTHFUL: nothing it produced was wrong, and it found less
than a third of what is there. That shape fits this project: an in-browser
reader that underreports without fabricating is publishable as a partial
read; one that fabricates is not publishable at all.

The known lever: the extraction prompt was tuned on gemma4 (that tuning moved
gemma4 itself from 88.7% to 96.8%). No prompt work has been done for small
models. Recall-tuning the small-model prompt is now a defined task with a
measured baseline, and the honest expectation is set BEFORE the fellowship
rather than during it.

Reports preserved in session scratch; not added to data/results, which stays
frozen at the application checkpoint.

**Same evening, corrected.** Jonathan asked whether the newest models had been
considered. They had not: the first ladder compared year-old small models to a
current-generation large one. The gemma4 family's own edge editions, measured
on the same pages:

| model | size class | browser-viable | precision | recall | spurious |
|---|---|---|---|---|---|
| gemma4:e2b | ~2B | any WebGPU browser | 100% (30/30) | 44.1% | 0 |
| gemma4:e4b | ~4B | good GPU | 95.0% | 55.9% | 2 |

A year of small-model progress roughly doubled recall while fixing
reliability, and the prompt is still the 12b-tuned one. Verdict revised: the
in-browser reader is buildable now as an honest partial reader -- finds about
half, invents nothing, same verification on arrival -- with prompt tuning and
the next model generation as the recall levers. The corrected question was
better than the first answer.

**Late evening — the browser reader, built and run.** portal/browser-reader.html
(generated by scripts/build_browser_reader.py): one real page of the 1997 Ear
Falls study, read by a model running inside the browser tab on the local GPU,
with the salvage parser and both evidence checks ported to the page and the
raw model output shown for inspection. Four models were run in the tab:

- gemma3-1b: collapsed into repetition ("The The The") — below the class.
- gemma-2-2b (2024): found real values, quoted no sentences — every record
  correctly refused by the checks.
- Ministral-3-3B (2025): two fragments, paraphrased quotes — refused.
- Qwen3.5-4B (2026): burned its budget in a <think> block, then on retry ran
  away past its token cap.

The infrastructure is PROVEN: in-tab GPU inference, streaming, parsing, and
verification display all work, and the checks refused every paraphrase and
every quoteless record — the system's honesty surviving contact with weak
readers. The capability is PROVEN separately (gemma4:e2b via Ollama, same
day: 100%/44%). What is missing is their intersection: no current-generation
edge model is published in the browser catalogue yet. Two bounded tasks
bridge it: publish a gemma4:e2b browser build, and tune small-model reading
instructions (compact v1 written today, unbenchmarked). The demo page states
all of this on its face.

**Later. The published e2b browser build, probed to its exact wall.** A
third-party MLC/WebLLM packaging of gemma-4-E2B-it exists on Hugging Face
(published April 2026). Mirrored locally and loaded successfully after four
compatibility fixes (URL absolutization, the HF path shape, a renamed tensor
cache, window-mode and attention-sink settings its older toolkit omitted).
In the tab it answers a short question correctly ("Paris") -- the deepest
single step of the browser goal, achieved: the RIGHT model executing in a
browser. Then the wall, measured by binary search: prompts fail between 250
and 300 filler words. Its KV cache was compiled at exactly its 512-token
sliding window -- memory for one short exchange. A document page cannot fit
at any prompt arrangement, since the 512 includes instructions, page and
output. The publisher's own validation was "the France/Paris case"; now we
know why. The bridging task is now exact: recompile and republish the e2b
browser build with document-sized KV memory. The demo page states all of
this on its face; its committed form points at the public copy.

**2026-08-17, small hours. The browser wall is in the kernels, not the
packaging -- measured three ways.** Yesterday's conclusion ("republish the
e2b browser build with document-sized memory") died tonight, killed by
better evidence. A wider search found not one but three published browser
builds of gemma-4-E2B, from two independent toolchains: the April
gemma4-webllm-fork build already probed, a June rebuild of the same fork
whose config advertises an 8192-token context its own wasm refuses to
allocate, and a May build compiled against the real upstream support PR
(mlc-llm #3485, still open), full 131072-token declaration, by a publisher
careful enough to document their own broken variant. Every one of them,
in every window configuration, answers a short question correctly and
falls silent past roughly 512 prompt tokens -- an eighth of a page. The
May build adds a hardware lesson: its 8192-token prefill chunk is one GPU
dispatch, which loses the whole GPU device on a laptop card until capped
to 1024. A four-day-old public demo app runs the same April artifact with
a pinned current engine and only a context override; replicating its exact
recipe changes nothing. Two compile lineages, one failure: the defect is
in the shared TVM WebGPU kernels for this hybrid-attention architecture
(512-token sliding layers interleaved with full-attention layers), and no
recompile we could run tonight escapes it -- our own build would inherit
the same kernels. The model itself is fine; the identical weights read
whole pages locally at benchmark accuracy. So the demo page now carries
the full finding, the public build reads with catalogue models whose
verbatim-quote failures the checks refuse on screen, and the e2b record
sits one flag away (--local-model) for the day the upstream PR lands.
The three builds stay enumerated in the builder for that retest.

**2026-08-17, later. The button works.** Two bugs stood between "the
catalogue models fail the verbatim rule" and a working browser reader, and
neither was the models' fault. First: Qwen3.5-4B's reasoning off-switch
belongs on the USER turn -- in the system prompt it is ignored, and the
model burned 20,000 characters of thinking past the token cap (measured:
the same arithmetic question costs 59 thinking tokens by default, 2 with
the switch placed right; the engine's enable_thinking flag is set too).
Second: the compact instructions' worked example was a sentence from the
demo page itself, seeding an answer -- integrity bug, replaced with an
Owen Sound sentence that also teaches the one-sentence-many-records rule.
With both fixed, the official-catalogue Qwen3.5-4B read the Ear Falls page
inside the browser tab in 42 seconds: 12 records, 9 passing both on-page
checks (sentence verbatim on page, value inside the sentence), and all 9
matching the archive-verified reference for this page -- 0.7 and 0.46
mg/L chlorine residual, 36 and 4 TCU colour, 6.7 and 0.32 NTU turbidity,
the ODWO limits of 5 TCU and 1 NTU, 94 ug/L aluminum. The three failures
were refused on screen, which is the system working. No fork, no local
mirror, no install: current mainline engine (pinned 0.2.84), official
catalogue weights. The gemma4 kernel finding stands unchanged as the
reason e2b itself waits; the page now documents both truths. Next
measurement: this exact browser combination against all four gold pages.

**2026-08-18. The browser reader, measured -- and it was not half.**
The reader page has said since the day it worked that browser-size models
"find roughly half of what a page states". That number was never measured for
the combination a visitor actually runs; it was carried over from an Ollama
run of a different model on the same pages. Measured properly -- same model,
same instructions, same parser, same checks, driven from a page that imports
them from the reader rather than copying them -- it is **17.6%**. Not half.
Two and a half times less than the site claimed, in the one direction that
matters.

The worst of it was a page the reader abandoned completely. On the Hamilton
magazine page -- the one page in the gold set that is deliberately NOT a water
report, included so a method could not be measured only where it was designed
to work -- it produced twenty-one characters of output and zero records
against eleven hand-read values. Every one of those values is a counted noun:
"75 elementary schools", "42 operated by the ... Separate School Board". The
compact instructions gave mg/L, %, hours and persons as the examples of a
unit, so a count did not look like a measurement.

One clause fixed it. "A COUNT is a measurement: 75 elementary schools is
value 75, unit schools" took the whole set from 17.6% to **23.5% recall at
88.9% precision**, and that page from 0% to 36% at 100%. Kind accuracy went
83.3% to 93.8%.

Two other clauses were tried and are now recorded as failures, because both
are the kind of fix that looks obviously right:

* *A specification sheet is a list of measurements, one per line.* Aimed at
  the design page, which yields 6 of 26 values. The model dutifully read
  "PROJECT NO. 2-0069-60" as the value 2 and "TREATMENT Primary" as the value
  3, and found FEWER real specifications. Tell a 4B model every line is data
  and it will believe you about the lines that are not.
* *Never leave the unit empty.* Aimed at a real defect: every record that
  missed the answer key was a correct value with a blank unit, charged twice
  by the scorer -- once as a value missed, once as a record invented. Forcing
  the field turned "200 mg/L of suspended solids" into "200 %". A blank unit
  is honest ignorance; a wrong unit is the concentration-plotted-as-a-
  percentage bug this project already shipped once. Recall fell, precision
  rose, and the trade is not worth taking.

So the reader now carries one new rule and the site carries a measured
number. Two things worth keeping from the exercise. First: the estimate was
wrong in the flattering direction for a month, on a public page, and nothing
but running it would have caught that -- the checks were all working, the
page was honest about everything it could see, and the one number nobody had
measured was the one on the poster. Second: I nearly did not run the unit
experiment at all, on the argument that tuning against four pages before the
frozen benchmark exists contradicts the method. Jonathan pushed back, and he
was right -- the freeze rule exists to stop a tuned score being reported as
independent, not to stop defects being fixed. Running it is what proved the
obvious fix was wrong.

The figure is tuned-on and says so: chosen against four pages, to be
re-measured on the frozen 200-page benchmark. Raw output and report are in
data/results/, re-runnable with scripts/bench_browser_reader.py.

**Same day, the larger half: the filter was throwing away good records.**
Jonathan asked to keep going rather than write up 23.5%, so instead of another
prompt I asked a duller question -- for every record the page refused, WOULD
THE SERVER HAVE REFUSED IT? That check needs no model, only the recorded run
and contribute.py. Seven of the eleven refusals were the browser being
stricter than the referee it fronts for. Three causes, all in the page's own
two checks:

* Numbers the scan split. A page prints "$53, 549. 66" and the model writes
  53549.66; the server joins those before judging and the browser did not.
  Worse, the page can print "8. 8 million gallons" where the model sensibly
  writes 8.8 -- so the join has to happen on BOTH sides before the sentence is
  even looked for.
* A trailing sentence period hiding the number in front of it. "53549.66."
  failed a token test that refused any following dot, where the server refuses
  one only when it begins another decimal.
* Numbers written as words. The server reads "seven vocational schools"
  through numerals.states_value; the browser looked for the digit 7.

Fixing the filter, with the model output untouched, took the same recorded run
from 17.6% to **32.4% recall at 84.6% precision**. Nearly all of the gain is
records that were always correct and always would have been accepted -- the
page was discarding them before the archive ever saw them. Every record that
still misses the answer key is a real value whose unit is blank or worded
differently. Nothing was invented on any of the four pages.

Two things follow. The towns already read in a browser -- Ear Falls, Ingersoll
-- were read through the broken filter, so their published records are a
subset of what those sessions actually found; re-reading recovers the rest.
And the lesson generalises past this bug: a pre-filter in front of a stricter
authority is a place where data dies silently, because nothing downstream can
tell the difference between a record that was never proposed and one that was
thrown away on the way. The check that found it -- replay the refusals against
the real referee -- is now scripts/diagnose_browser_bench.py and costs nothing
to run.

One more entry in the family this log keeps: writing the repair through a
shell heredoc turned a regex backreference into a literal 0x01 byte, silently,
in a file that read correctly in every editor. That is the same trap as the
``-became-backspace incident above, four months on, in the same repository
that added a control-byte test because of it.


**2026-08-17, night. The demo became the tool, and walking it found three
bugs.** The /browser page now reads whole towns, not one hardcoded page.
The server grew two endpoints that hand a visitor's tab the work:
/api/browser/plan serves the document selection -- library.ask's own,
factored into plan_documents() so the installed reader and the browser
reader can never disagree about what a town's record is -- and
/api/browser/pages serves one document's prose-routed pages, capped at the
exact slice extract_prose prompts with. The page reads page by page,
refuses failures in the open, and sends each document's survivors to the
existing /api/bundle door, where the server re-verifies every quoted
sentence against archive.org before publishing. Per document, not per
town, because a read is slow and a browser tab is mortal: what has
survived should not die with it. Re-sends deduplicate, so stopping and
pressing again costs nothing. The unread-town handoff now leads with the
browser ("read it in this browser, nothing installed") and keeps the
installed reader as the bigger-machine path.

Walked end to end locally -- Ear Falls, all three documents, in the tab --
before touching the droplet, and the walk earned its keep. Three bugs,
none visible in 888 passing tests: the page's value check refused "0.20"
read as 0.2 and "13.0" read as 13, honest readings the server's own
referee accepts, so the pre-filter was stricter than the check it fronts
for (this project's oldest bug family, in a browser costume); proxy
502/504s were treated as final when they mean "again in a moment"; and
the #place= deep link -- the way back from the reader to the town it just
filled -- called into a const still in its temporal dead zone and died,
which node --check cannot see and clicking the link found in one second.
The walk's numbers: 31 prose pages read in the tab in 9.3 minutes, 75
records past the page's checks, 40 refused on screen, 68 published after
the server re-verified everything sent -- and 6 refused by the archive
check the page's own checks had passed, which is the two-tier design doing
exactly what it is for. The 1973 summary yielded nothing ("10 pages, none
routed to prose") and the page says so instead of pretending it read them.

Deployed. The live walk -- an unread town, Ingersoll, read entirely in a
browser tab against the public site -- waits on one thing nobody here
controls: archive.org went temporarily offline mid-evening, and both the
pages endpoint (cold fetch) and bundle verification need it. The tool is
live; the archive is the referee, and the referee is out of the room.

**Same night, the referee returned. Ingersoll is read.** The whole loop,
walked on the public site with nothing installed: picked Ingersoll (on the
map since the beginning -- located, two catalogued reports, silent since
1975, nothing read), pressed the one button, and the tab read the town's
four documents -- a 1966 water pollution survey, the 1973 and 1974 plant
summaries, a 1989 gas-plant study. Sixteen prose pages; 25 records passed
the page's checks, 22 refused in the open, and the live server re-verified
every sent sentence against archive.org and published 23: twelve from
1966, five from 1973, six from 1974 (two more refused by the archive's
stricter tokenizer -- the two-tier design working), and the 1989 study
honestly skipped, no prose pages. Ingersoll's dot turned orange. Its page
answers. Design flow 2.25 MGD, raw sewage BOD 200 mg/L, the digester
diameters, the drying beds -- a town's water history, on the record,
because one browser tab asked. This is the loop the project promised, with
the entry cost reduced to a link.

**And the site put on one set of clothes.** Jonathan, mid-walk: "can you
fix the pages so they don't all seem like different websites." They were
three websites -- the live map in dark OMEGA chrome, the reader page in a
similar-but-different dark, the built artifact pages in cream paper.
concordance/chrome.py is now the single source: the live portal's palette
and a masthead naming the site, inlined by the reader page and all four
artifact builders (the artifacts stay self-contained on purpose; they are
opened from disk where no stylesheet is served). Every page now opens
under the same CONCORDANCE masthead on the same dark, with the same
orange doing the same job -- and the town-page charts draw their lines in
it.

**And then the same menu, because the same clothes were not enough.**
"Fix the websites menus, it is not consistent across the pages" -- right:
the front page had the nav rail and every other page had only a wordmark,
so leaving the map meant losing the site. The nav list moved into
chrome.py as the one source; the front page builds its view-switching
buttons from it and every other page renders the same nine entries as
links back -- possible because the front page now honors #view= the way
it honors #place=, and switching views writes the hash, so a view you are
looking at is a view you can send. The standalone artifacts link home by
absolute address, since a file opened from disk has no "/" to point at.
Where you are is marked the same way everywhere: the reader page lights
"Watch it read", the silence exhibit lights "What stopped", a town page
lights "One town, in full".

One more, reported from the same walk-through: selecting an unread town
popped a card with its text cut off at the panel's edge. OMEGA's .empty is
a centered grid for one-line hints, and centered grid items shrink to
their content -- whose minimum is the widest unbreakable line, here a
90-character install command, so the whole handoff rendered 610px wide
inside a 410px dock. Inherited chrome carries inherited assumptions; in
the dock the class is now a plain block and the command chips scroll
themselves.

**Then the structure itself, because the clothes and the menu were never
the real complaint.** "I'm not sure the workflow of concordance is the
best and it feels like not a lot of thought went into the layout of the
menu and how it all works together." Right -- the nine entries were the
modules in build order, renamed into questions a year ago but never
restructured. Two answered the same question two ways ("Find a place" and
"One town, in full" -- two renderers of the same record), one errored for
every visitor of the shared site (Ask Jay needs a local model), and the
reading queue sat four slots from the reader it serves. The menu is now
the loop the site actually is: <b>Find a place</b> (the search browses
the read towns when clicked empty -- the duplicate view, one click
earlier, minus its second renderer), <b>Read a town</b> (the reader,
with the frontier's ranked towns as its pick list), <b>What it found</b>
(what stopped, who decided, disagreements, within reach -- four tabs,
one entry, nothing deleted), <b>Can I trust it</b> (precision and
refusals, with Ask Jay beside them, appearing where a model exists to
answer). Old #view= addresses map into the new structure, tab and all.
Nine doors became four stages, and the tests now pin the property that
mattered all along: consolidating deleted nothing.

**Then Jay came back out. "Jay shouldn't be buried on a page" -- right:**
folding the agent into the trust view solved the dead-button problem by
hiding the feature, which is the wrong trade for the project's own agent.
Ask Jay is the menu's fifth entry again, everywhere, and the real problem
got the real fix: the view says up front, before a question is typed,
where Jay answers. A shared instance shows the local-machine handoff; a
local instance shows nothing but the box, which simply works. A page that
takes your question and then refuses it was the thing to remove -- not
the page.

**And the menu still jumped, because unifying the CSS was not the same as
unifying the header.** "Make one consistent menu, so that every page
doesn't jump around when you select a page." Two causes, both measured
rather than guessed. First: the front page was still building its own
header -- a fixed 210px brand block, a nav wearing the inherited
`icon-nav` class -- while every other page rendered chrome.masthead().
The first menu item sat at x=252 there and x=298 everywhere else, 48px
tall against 35px, and its labels were invisible because `.nav-tip` is a
hover TOOLTIP in the inherited stylesheet, which the earlier pass had
only partly overridden. Second, and worse: the inherited sheet pads
`.app-shell` by 14px and unpads it only for the map route, so choosing
any other section slid the entire chrome 14px down and right. Neither was
the menu drifting; both were the things under and around it. One header
component now, counts included, with every tooltip and hover-lift rule
undone and the shell pinned flush on every route -- walking all five
sections reports one position, 298,9, and the reader page reports the
same. The menu is links everywhere, intercepted on the front page so a
view still opens in place: one markup, no reload, nothing to flash.
Third time this project has learned that inherited chrome carries
inherited assumptions, and the first time it has a test that measures
them.

**It still jumped, and my verification was the reason I thought it
didn't.** I measured at one viewport width -- 1280 -- and reported
"identical to the pixel". At 1280 the front page's headline counts are
hidden by a media query, so I had measured the one width where the
difference could not appear. On a wide screen the counts were visible and
53px tall against a 35px menu row, which made the front page's header
71px against every other page's 54 and dropped the menu 9px. The counts
are now held to the menu's own height: nothing at the far end of a header
may decide where the menu sits.

The other half was never the header at all. The map view is a fixed shell
that never scrolls; the reader is a long document that always does. So
every move between them added or removed a scrollbar and slid the whole
layout 15px sideways. The gutter is now reserved on `html` AND `body`,
because the two pages put their scroll container in different places --
the first attempt named only `html` and did nothing on the front page,
where `body` scrolls.

Measured after, on the live site, across 1920/1440/1280 and every
section: one menu position (297.8, 9.0), one header height (54.4), one
right edge. The lesson is not about CSS. A single-width measurement
reported a property that only holds at that width, and I published it as
though it held everywhere -- the same shape as every ruler this project
has already been burned by, in the one place I had just written a test to
prevent it.
