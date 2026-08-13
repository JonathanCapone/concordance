# Concordance

**A free website where anyone can look up what was measured where they live —
the pollution readings, the water quality, the air — going back to the 1800s,
with every number linked to a photograph of the government page it was read
from. Plus the open dataset underneath it, which does not currently exist
anywhere.**

*AI Builders Fellowship application. Written from what is already built and
measured rather than planned; every figure below is reproducible from the
repository.*

---

## 1. The project

Internet Archive Canada holds **104,241 scanned Canadian government
publications** — 22.1 million pages, 1841 to 2013. Inside them are measurements
of the physical condition of the country, town by town, year by year: how much
sewage a town discharged into its river, what was in the drinking water, what
came out of the smelter.

The fellowship brief describes the collection as roughly 48 TB. That is the
page images. **The text layer inside them is about 59 GB** — the entire written
output of the Canadian state, as digitised, fits on a cheap thumb drive. That is
the fact that makes reading all of it tractable rather than absurd.

The median document in that collection has been downloaded **90 times**. The
numbers inside are not in any database. To find out what your town's sewage
plant was discharging in 1969 you would have to know the report exists, find it,
and read it.

Every civil servant who wrote one of those measurements down was, in effect, a
sensor. Together they formed a monitoring network that ran for over a century
and covered the country — and it was never once read *as a network*, because
each of them published to paper and the paper went into a box.

I want to spend six weeks reading it back out, and putting the result somewhere
a person can use it.

### How it works, in one paragraph

There is no central machine that reads the archive. **The reading happens on the
computer of whoever asks.** You open the site and look up your town: if somebody
has already read it, you get the answer instantly, from data everyone shares. If
nobody has, the site says so — *"Nobody has read this one. 12 scanned reports
are waiting, about an hour on this machine"* — and you can press a button. Your
own laptop then fetches those scans and reads them, which takes roughly a minute
a page, and the result is published back so the next person gets it instantly.
No account, no install beyond the software itself, nothing running in the
background afterwards.

That is why there is no compute budget below, and it is the difference between a
dataset that is finished when the grant ends and one that keeps growing.

### Why this is possible now and was not before

Scanned documents are turned into searchable text by OCR — optical character
recognition, the software that looks at a picture of a page and works out which
letters are on it. The finding this project turns on, which I made before
applying:

**OCR preserved the prose and destroyed the tables.** A province-wide summary
table comes back from the 2013-era scanner like this:

```
9 /zLA' y 1? in" y 1'\ Vnlump 41 Q sailor
```

Nothing survives that. But the narrative paragraphs read perfectly — and in
these reports *the measurements are in the narrative*. Owen Sound's sewage
plant, 1969:

> "The average influent BOD and suspended solids were 104 mg/1 and 224 mg/1
> respectively. The average effluent BOD and suspended solids were 37 mg/1 and
> 36 mg/1 respectively, giving an average removal of 64% BOD and 84% suspended
> solids."

*Influent* is what flowed into the plant, *effluent* what came out. *BOD* —
biochemical oxygen demand — is the standard measure of how much organic
pollution is in water; higher is worse. So that sentence says the plant removed
64% of the pollution it received that year, and it gives the numbers.

That is a complete set of readings in ordinary English. So the hard problem is
**reading**, which language models now do reliably — not recognising a table in
a degraded scan, which they do not.

Then, while I was building this, the second half of the argument arrived. A
newly released model reads the destroyed tables too. Given that same wreckage —
`TABLE I FLOW - MILX.IQN GALLOLS ... AVa. DAILY r .LOW` — it returned 27
measurements, got **every one of the twelve values still legible in the OCR
exactly right**, rebuilt the header row the scanner had eaten, and filed each
value under its month. Across 24 table pages from 11 collections, in documents
as unlike each other as Statistics Canada salt production in 2003 and the
Georgian Bay Ship Canal Survey of 1909, it recovered **535 measurements**.

I could check 461 of those against the page's own surviving OCR text — the other
74 sit on pages whose text layer was destroyed entirely, so there is nothing to
check them against. **Of the 461 checkable, 411 (89%) were confirmed.** The
pages where this matters most are the pages where its own corroboration cannot
reach, and I would rather say that plainly than quote 89% as though it covered
everything.

**The tables were never lost. They were unreadable by the software that existed
when the pages were scanned**, and they have been sitting in public, and
inaccessible, for a decade.

### It already works

Not a proposal — a running artifact. Every figure carries the size of the sample
it came from, because a percentage without a denominator is not a measurement:

| | |
|---|---|
| Extraction precision / recall | **96.8% / 88.2%** — on 4 pages hand-read by a person, 68 values |
| ...of which, the one page annotated *before* any run | **94% / 94%** — 17 values |
| Telling a measurement from a design spec from a legal limit | **98.3%** — 60 matched values |
| Telling water going in from water coming out | **88.9%** — 18 judged pairs |
| Quoted sentences that could not be found on the page they cite | **0** of 286 |
| Table measurements recovered | **535** from 24 pages across 11 collections, 1879–2003 |
| Towns read end to end | **6**, 1,470 measurements |

*Precision* is how much of what it produced was correct; *recall* is how much of
what was there it found. Both are measured against a set of pages a human read
by hand first. Four pages is a small sample and I would not defend it as more
than an early signal — widening it is the first thing in the work plan.

Every recovered number carries the verbatim sentence it was read from, that
sentence is verified to occur on the page, and the page is one click away. A
measurement pulled by a model out of a sixty-year-old scan has no authority on
its own. It earns authority by being trivially easy to disprove.

### What it has already found

Each with the check that makes it a finding rather than an artefact:

**72 of 107 Ontario municipalities stop filing sewage-plant reports in 1975.**
A whole series vanishing at once usually means the *scanning* stopped, so I
checked: publications from the same ministry in the same collection run 1,449
before 1975 and 3,800 after, steady at 83–141 items a year straight through. The
archive kept growing. This series died.

That rules out a digitisation artefact. It does **not** yet rule out a change in
what the ministry required to be filed, which would look identical from here, so
this is a finding about the *record* and not yet one about the *rivers*. Closing
that gap is in the plan below.

**539 of 1,119 Ontario river gauges are discontinued** — 48%, from live federal
data. The same winding-down of measurement, still happening.

**Whose sewage was in whose drinking water.** Plants matched to river gauges and
ordered by catchment: Fergus → Brantford → Cayuga on the Grand; Orangeville →
Streetsville → Clarkson on the Credit.

**13,429 metadata corrections** for the collection itself, to be offered back to
Internet Archive Canada. 57% of its items have no subject tag and 32% have no
year, which is why most of it cannot be found by anyone looking.

**A fifth of the archive was being thrown away, by me.** My code counted a page
as prose only if its lines held eight or more words. That is a fact about
typography, not about content, and it was quietly deciding which parts of the
public record exist. A 1983 city magazine set in narrow columns — 149 lines of
unbroken prose, median four words to the line — scored zero, and every page went
in the bin, including one recording how many schools Hamilton had. Fixing it
moved the share of the collection worth reading from **53% to 69.5%**, about
**3.6 million more pages**. The loss fell hardest on the legislative record,
because that is how minutes have always been typeset: Acts of the Parliament of
Canada went from 265 usable pages to 861.

I did not find that. Someone looked at a document and said *that doesn't sound
right*. It is in the work log with the rest of my mistakes, and it is the best
argument I have for building this in the open.

**The archive knows who voted for what.** Minutes, agendas and commission
hearings are 13,604 items. One volume of Hamilton council agendas from 1992
yields 94 decisions, 64 named people and 44 recorded votes — including full roll
calls, and the divisions where one alderman stood alone against the Red Hill
Creek Expressway. That needs no model at all; a text pattern finds it, free, on
a laptop.

### How big the job actually is

Measured from a random sample of 120 documents and 23,729 pages:

- **90.8%** of documents contain measurements (95% confidence interval
  84.3–94.8%, meaning the true figure is very likely in that range)
- **69.5%** of pages are worth reading at all
- which is about **15.4 million pages** across the collection

Splitting those by how they have to be read:

|  | share of pages | measurements per page | share of the data |
|---|---|---|---|
| **Prose** — ordinary paragraphs | 73% | 4.2, and a third of pages yield none | ~31% |
| **Tables** | 27% | ~18 | **~69%** |

**Most of the data is in the quarter of pages that are hardest to read.** That
single fact drives the entire plan below.

### What the money is for

The fellowship is $5,000. **All of it is six weeks of my time.** There is no
compute line, and that is a deliberate design choice rather than an omission.

The obvious thing to do with money and an archive this size is rent GPUs and
read the whole thing. I costed that — **$4,251–8,502** — specifically so I could
argue against it. A corpus bought in one batch is finished the day the money runs
out. It covers whatever was current in October 2026, it never extends, and the
next person who wants a document nobody thought to read has no way to get one.

**So reading happens because somebody wanted to know something.** You ask for a
place. If it has been read, you get it instantly. If you are the first to ask,
your own computer reads it — and then it is there for everyone after you. No
account, no queue, no volunteering. The cost falls on whoever cares first, who
is also the person most willing to wait twenty minutes for it.

Results move between machines and are re-checked against the original scans on
arrival, so nobody has to trust or pay for a central server. **The rest of the
archive fills in as people ask for it, indefinitely, at no recurring cost to
anyone** — and in the order people actually want to know things, which is a
better order than any I would impose.

### The hole in that, named

The model has one real weakness. Tables are 27% of pages and most of the
measurements, and they need a model that will not fit on an ordinary computer:
on my own graphics card a table page takes eight minutes, because only 18% of
the model's layers fit in the card's memory and the rest is shuffled in and out.

I am not asking for money to brute-force past that, because that would buy a
fixed corpus and abandon the model that outlives the grant. Two things get tried
first, and both are measurable:

- **A smaller vision model may be adequate.** That is a question, not a hope,
  and I have not measured it yet.
- **Tables get read once and shared.** One person with a good graphics card
  reads a document's tables; everyone else re-verifies the result against the
  original scan instead of re-reading it. That path is built and tested.

If both fail, the honest answer in the write-up is that 27% of this archive
needs hardware most people do not own. That is worth knowing too, and it is a
better outcome than a number that hides it.

---

## 2. Work plan

**What the six weeks buys, in priority order.** The two things below are what
the money is actually for. They are the two that the evidence above says are
unfinished, and if only these land the project is still worth having.

**Weeks 1–3 — Make the accuracy figure real.** The benchmark is four pages hand
-read by one person. That is enough to justify continuing and not enough to
publish a dataset on. So: bulk text acquisition across the collection; a much
larger hand-read benchmark spanning document types, agencies and eras; accuracy
published per era and per parameter rather than as one number; and the
comparability work below, which is what stops the whole thing producing
confident nonsense. *Ends with:* an accuracy figure I would defend in public,
including where it is bad, and a seed corpus of towns and years.

**Weeks 3–5 — The tables.** 27% of pages hold about 69% of the measurements and
need a model that will not run on an ordinary machine. Owen Sound's 1973 and
1974 reports contain *zero* readable prose pages between them; those years are
unreachable without this. The first vision model I tried invented table
structure that was not on the page; the current one does not. So this is no
longer "can it be done" — it is throughput, cost, and whether a model small
enough for a contributor's machine is good enough. *Ends with:* either tables
distribute, or the limit is named with a number attached.

**Week 6 — Publish.** The dataset released openly with its methodology and its
failures; the metadata corrections offered to Internet Archive Canada; the
write-up; the showcase on October 28.

### What happens after, and is not being funded here

I would rather name these as intentions than pad six weeks with them: running
the silence detector nationally, cross-referencing agencies whose records have
never been in the same room, and pointing the pipeline at other scanned
archives. All three are things this design makes possible and none of them are
promises for October.

### Comparability, which is the real scientific risk

A number from 1961 and a number from 2001 are not automatically comparable, and
this is where a project like this most easily produces a confident, plausible,
entirely fictional trend. "BOD" was measured by different methods, in different
laboratories, against different detection limits and different reporting rules
across 1841–2013. Imperial and US gallons differ by a fifth. A plant that
changes what it reports looks exactly like a plant that changes what it
discharges.

Some of the machinery for this exists already: units are converted through a
layer that knows the era, readings whose units are not comparable are **rejected
and reported rather than silently converted**, and a record can carry a note
saying why it should not be compared with its neighbours. What does not exist
yet is the method and detection-limit metadata alongside each value, and the
rule that a series must not be plotted across a known methods change.

Two commitments that follow, both of which cost me findings:

- **"The series stopped" stays unproven until an administrative explanation is
  ruled out**, the same way I already rule out "it was never scanned". The 1975
  collapse above has the scanning control and does not yet have the reporting-
  format control, and it should not be published as an environmental finding
  until it does.
- **No uncertainty column unless there is a real method behind it.** A
  fabricated uncertainty is worse than none, because it invites exactly the
  statistical use it cannot support.

### What I have not tested, and who has not used it

The rest of this document is careful about its numbers. It would be dishonest to
be careful there and silent here.

**Nobody outside this project has used it.** Not one stranger has looked up
their town, and nobody has been asked to. The contribution model — a person
presses a button and their laptop reads a document for everyone — is built,
tested and entirely unproven as a *human* proposition. I believe people will do
it for the town they grew up in. I have no evidence, and the fellowship is the
first chance to get some.

If they do not come, the project does not fail: it becomes a smaller dataset
plus a very good finding aid, because every reading published still carries its
scan and the machinery still works for whoever runs it. That is the fallback and
it is worth saying out loud rather than discovering in week five.

**No institution has agreed to anything.** The 13,429 metadata corrections are
offered to Internet Archive Canada, not accepted by them — I have not asked yet,
because offering a diff is more useful than offering a promise. Same for the
municipalities whose records these are.

**The evidence is Ontario water.** Every worked example above — Owen Sound,
Brantford, Burlington — is an Ontario sewage plant, because that is where the
deepest run of comparable annual reports survives. The collection itself is
lopsided the same way: 12,467 Ontario items against 8,671 Alberta and **468 for
British Columbia**, which is worth stating plainly in an application to a BC
fellowship. The method is not Ontario-specific and nothing in the reading layer
knows what province it is in — but "this works for Canada" is currently an
extrapolation from one province and one subject, and the wider benchmark in
weeks 1–3 is where that either holds or does not.

### Who actually does what

Four kinds of person, and only one of them is asked to do anything.

**Most people just read.** They open the site, look up the town they grew up in,
and see what was measured there and when it stopped. They install nothing and
contribute nothing, and they are the point of the whole exercise. If this works
they are 99% of the users.

**Someone wants a place nobody has read yet.** The site says so plainly —
*"Nobody has read this one. 12 scanned reports are waiting, about an hour on
this machine"* — and they press a button. Their computer does the reading, they
get their answer, and it is now done for everybody. **That is the entire ask.**

**Someone disagrees with a number.** They cite a page and quote a sentence, and
the archive settles it: the same check that judges my own output, which never
asks who is speaking. A correction with evidence replaces a record without it,
automatically. An objection with no evidence is counted, displayed, and changes
nothing — because the moment it could, somebody would have to sit in judgement,
and I am not willing to be that person or to appoint one.

When two readings both survive the check, neither wins. Both are shown with **a
cropped photograph of the sentence each was read from**, and the reader settles
it in seconds. That is what makes the whole arrangement work rather than merely
sound good, and it costs nothing: the Internet Archive already serves page
images, so a citation is just a URL.

**And someone has a good graphics card.** They can read the tables the rest of
us cannot, once, for everyone — the one place where contributing means more than
asking a question.

### What is built, and what is not

| | |
|---|---|
| Look up a town and see every measurement with its scan | **built** |
| Ask for a place nobody has read; your machine reads it | **built** |
| Correct a number, checked against the scan, no moderator | **built** |
| Send readings to a shared instance, re-verified on arrival | **built** |
| Ask a question in plain English and get an answer that cites its pages | **built** — over two towns, needs the data |
| Read the tables on ordinary hardware | **not built** — weeks 3–5 |
| The dataset, published, at scale | **not built** — this is the fellowship |

An instance re-verifies every record it is sent and keeps what the archive
supports, reporting what it refused. It holds nothing anyone else lacks: it will
hand back its entire dataset on request, and anyone who mistrusts mine can take
everything and run their own. That property is why adding a server is safe here
and would not be in a system where the server was the source of truth.

---

## 3. Success metric

> **A resident of any Canadian community can ask what was measured where they
> live, get a straight answer in plain language with every number traceable to
> the scanned page it came from — and can see what stopped being measured, and
> when.**

Checkable, in four parts:

1. **The dataset exists and is open** — measurements with place, time,
   parameter, unit and a page link, published with the accuracy methodology
   beside it. No uncertainty column unless there is a real method behind it, per
   the commitment above.
2. **Accuracy is published including its failures**, per era and per parameter,
   on a benchmark anyone can re-score themselves.
3. **Every number resolves to its scan.** Not a sample — every one. This is the
   one I will not trade away, because it is what makes the rest checkable.
4. **Where a series stops, the record says so and says what was ruled out** —
   both "it was never scanned" and, where I can establish it, "the reporting
   rules changed". A silence finding is uninterpretable without those, and the
   national map of silences is after the fellowship, not in it.

### What would count as failure, stated in advance

If accuracy on a wider benchmark comes in materially below what four pages
suggested, I will publish that number and narrow the scope rather than quietly
ship a confident dataset nobody has checked. **An archive that has been misread
at scale is worse than one that was never read, because the errors look like
findings.**

That is not a hypothetical caution. The first accuracy figure this project
produced was 49% precision — and it was wrong. The scorer could not tell that
"3.0 million gallons" and "3000000 gallons" are the same number, and the
hand-written answer key was incomplete. Fixing the *measurement*, with no change
at all to the extraction, moved it to 96.8%. Publishing the first number would
have narrowed the project for no reason. Everything here is built to catch that
class of error, because it is the one that looks like success.

It keeps happening, which is why I keep building the checks. Days before
submitting this I ran an adversarial audit over the whole repository. It found
nine real defects, six of them serious — including one where the verification
that is supposed to catch invented numbers would accept any round number
against any sentence containing its first digit. All of it is fixed and tested
against the attacks that found it. I am reporting it here because a project
whose entire claim is *check my work* should say what happened when somebody
did.

---

## Open source

MIT licence, public repository. The core has **zero required dependencies** —
clone it and verify a measurement in five minutes, with nothing to install and
no API key. The map and the assistant are a separate optional layer, so nobody
has to stand up a web stack to check whether 104 mg/L is really what the page
says.
