# Work log

Notes from building Ground Truth. Written as it went, kept honest on purpose —
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

## Where it stands

| | |
|---|---|
| Commits | 38 |
| Tests | 331 |
| Documents read | 22 of 104,241 |
| Precision / recall | 88.7% / 82.5% — blind page 88/88 |
| Quotes failing verification | 0 of 286 |
| Dependencies in the core | none |

The pipeline works and is measured. It has barely been pointed at anything. Those
are both true and the second one is the point: what needs funding isn't the
tooling, which exists — it's the reading.
