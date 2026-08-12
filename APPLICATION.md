# AI Builders Fellowship — application

*Draft. Written from what has already been built and measured, not from what is
planned. Every figure below is reproducible from the repository.*

---

## 1. The project

**The archive is a scientific instrument that has been running for a hundred
years, and nobody has ever read its output.**

Internet Archive Canada holds 104,241 scanned Canadian government publications —
22.1 million pages, 1841 to 2013. Inside them are measurements of the physical
condition of the country: the air, the water, the soil, town by town, year by
year. The median document in that collection has been downloaded **90 times**.

Every civil servant who ever wrote a measurement down was a node in a sensor
network that ran for 150 years and covered a continent, and it was never once
read *as a network*, because each node published to paper and the paper went
into a box.

I want to spend six weeks reading it back out.

### Why this is possible now and was not before

The finding the whole project turns on, and I found it before applying:

**OCR preserved prose and destroyed tables.** A province-wide summary table comes
back from the 2013-era scanner like this:

```
9 /zLA' y 1? in" y 1'\ Vnlump 41 Q sailor
```

Nothing survives that. But the narrative reads perfectly — and in these reports
*the measurements are in the narrative*. Owen Sound, 1969:

> "The average influent BOD and suspended solids were 104 mg/1 and 224 mg/1
> respectively. The average effluent BOD and suspended solids were 37 mg/1 and
> 36 mg/1 respectively, giving an average removal of 64% BOD and 84% suspended
> solids."

Station, parameters, values, units — a complete observation set in readable
English. So the hard problem is **reading**, which language models now do
reliably, not table-recognition off a degraded scan, which they do not.

And then, this month, the second half of the argument arrived. A model released
while I was building this reads the destroyed tables too. Given that same
scanner wreckage — `TABLE I FLOW - MILX.IQN GALLOLS ... AVa. DAILY r .LOW` — it
returned 27 measurements and **every one of the twelve values that survived in
the OCR, exactly**, rebuilt the header row the scanner had eaten, and filed each
value under its month. Across four documents as unlike each other as Statistics
Canada salt production in 2003, Alberta Liquor Control in 1942 and a Simcoe well
supply report in 1990: **58 of 58 values are on the page.**

That is the strongest form of "only possible now" I can give you. **The tables
were never lost. They were merely unreadable by the software that existed when
the pages were scanned.** They have been sitting in public, and inaccessible,
for a decade.

### It already works

Not a proposal. A measured artifact, running today:

| | |
|---|---|
| Extraction precision / recall | **88.7% / 82.5%** against hand-checked ground truth |
| Blind page (annotated before any run) | **88% / 88%** |
| Kind accuracy — measurement vs design spec vs regulatory limit | **100%** |
| Quotes failing verification across 286 records | **0** |
| Table values found on their own scanned page | **58 of 58**, four documents, 1942–2003 |
| Measurements settled / contested / unsupported | **624 / 57 / 14**, with nobody adjudicating |
| Code / tests | 411 tests · zero required dependencies in the core |

Every recovered number carries the verbatim sentence it was read from, that
sentence is verified to occur on the page, and the page is one click away. A
measurement recovered by a model from a sixty-year-old scan has no authority on
its own. It earns authority by being trivially easy to disprove.

### What it has already found

Each with the control that makes it a finding rather than an artefact:

**72 of 107 Ontario municipalities stop filing water pollution control plant
reports in 1975.** A whole series vanishing at once usually means the scanning
stopped, so it was checked: Ministry of the Environment publications in the same
collection run 1,449 before 1975 and 3,800 after, steady at 83–141 items a year
straight through. The archive kept growing. This series died.

**539 of 1,119 Ontario river gauges are discontinued** — 48%, from live ECCC
data. The same winding-down of measurement, still happening.

**Whose effluent was in whose water.** Plants tied to river gauges and ordered by
catchment area, which necessarily grows downstream: Fergus → Brantford → Cayuga
on the Grand; Orangeville → Streetsville → Clarkson on the Credit.

**13,429 metadata corrections** proposed for the collection itself, to be offered
back to Internet Archive Canada.

**A fifth of the archive was being thrown away, by me.** A page counted as prose
if a line held eight words. That is a fact about typography, not about content,
and it was silently deciding which parts of the public record exist: a 1983 city
magazine set in narrow columns — 149 lines of unbroken prose, median four words
to the line — scored zero and every page went in the bin, including one stating
how many schools Hamilton had. Measured across 8,372 pages from 34 documents in
26 collections, fixing it moved the corpus from **48.5% to 69.5%** readable,
about **6.3 million pages**. The loss fell hardest on the legislative record,
because that is how minutes have always been set: Acts of the Parliament of
Canada went from 265 usable pages to 861.

I did not find that. Someone looked at a document and said *that doesn't sound
right*. It is in the work log with the rest of my mistakes, and it is the best
argument I have for building this in the open.

**The archive knows who voted for what.** Minutes, agendas, hansard and
commission hearings are **13,604 items, 13.1% of the collection**. One volume of
Hamilton council agendas from 1992 yields 94 decisions, 64 named people and 44
recorded votes — including complete roll calls, and the divisions where one
alderman stood alone against the Red Hill Creek Expressway. That spine needs no
model at all; a pattern finds it, free, on a laptop.

### How big the job actually is

Measured, not guessed. From a random sample of 120 items and 23,729 pages, and
revised upward after the routing fix above:

- **90.8%** of documents carry measurements (95% CI 84.3–94.8%)
- **69.5%** of pages are worth reading — was 48.5% before the fix
- extrapolated: **about 15.4 million pages**, up from 11.7 million

Of those, roughly **73% is text** a consumer machine can read at about 91
seconds a page, and **27% needs the vision path**. But a prose page averages 4.2
measurements and a third yield none, while a table page yields around eighteen —
so the tables are likely the majority of the actual measurements while being a
quarter of the pages.

At the throughput measured on my own hardware a corpus-wide pass is roughly 62
machine-years of prose plus 73 of tables. **So it is not a local job, and I will
not pretend otherwise.** It is a funded batch run, performed once, after which
the resulting dataset costs everyone else nothing. That is what the money is
for: not tooling, which exists, but the read itself.

Costed properly, with the two paths separated, the number moved against me:

| | rented GPU |
|---|---|
| Text pages only — leaves most measurements unread | **$1,510–3,019** |
| Both paths, the whole thing | **$4,251–8,502** |

The earlier draft of this application said roughly $1,500, and that figure was
the prose path alone against a corpus a third smaller than it turned out to be.
The honest version is that **a complete read sits at the edge of a $5,000
fellowship rather than comfortably inside it**, and the expected yield is about
122 million measurements, 61% of them from the table pages that are only 27% of
the work.

I would rather show you that arithmetic than the flattering version. The first
thing a funded run should do is measure rented throughput on a thousand pages
and re-derive this, because the vision throughput penalty is currently a guess
and it is now most of the cost.

That division is also the answer to the obvious objection about distributed
contribution. The central run does what is expensive and uniform — the
vocabulary, and the tables — once. People do prose, on demand, on their own
machines, which is where places, dates, narrative and the whole deliberative
record live.

---

## 2. Work plan

Structured as arcs rather than weeks, because that is how I planned OMEGA and it
survived contact with reality. Each arc ends in something demonstrable, and the
order is chosen so that stopping early still leaves a complete artifact.

**Arc A — Read at scale (weeks 1–2)**
Bulk text acquisition across the collection; the cheap local filter that decides
which pages earn a model; the funded extraction run itself. Ends with: the
dataset exists.

**Arc B — Trustworthy at scale (weeks 2–3)**
The gold set expanded across document types and eras, not just the three pages
it covers now; accuracy published per era and per parameter rather than as one
number; the record audit run over everything. Ends with: an accuracy figure I
would defend in public, including where it is bad.

**Arc C — Vision at scale (week 3)**
Tables and figures are 27% of pages and probably the majority of the actual
measurements. Owen Sound's 1973 and 1974 reports contain *zero* prose pages
between them; those years are unreachable without reading the scan itself. The
first vision model I tried failed honestly — it invented table structure that
was not on the page — but the current one does not: 58 of 58 values found on
their own page across four documents from 1942 to 2003. So this arc is no longer
"can it be done". It is throughput, cost, and a control that survives being
wrong, because the fabrication check I wrote for it was itself broken twice
before it was right.

**Arc D — Publish (week 4)**
The dataset released openly with its methodology and its failures; the metadata
diff offered to Internet Archive Canada; the pipeline documented so it can be
pointed at any other scanned archive, because nothing in the reading layer is
Canada-specific.

**Arc E — Make it answerable (week 5)**
Honu over the whole corpus rather than two towns. The agent exists and works; it
needs the data underneath it. Plus the plain-language layer, so a resident rather
than a researcher can ask what their town put in the water.

**Arc F — Findings and the showcase (week 6)**
The silence detector run nationally; cross-domain joins between agencies that
have never been in the same room; write-up; Oct 28.

**Running throughout — open contribution that needs no moderator.**
Not an arc, because it is a property rather than a phase. Every claim in this
system cites a page and quotes a sentence, and the archive checks both. That
rule never asks who is speaking, so a stranger's correction is checked exactly
as the machine's own output is: an evidenced correction replaces an unevidenced
record automatically, and an objection with no evidence is counted, shown, and
changes nothing. When two readings both survive, neither wins — both are
displayed with a **cropped image of the sentence each came from**, and the
reader settles it in seconds.

That last part is what makes the whole arrangement work rather than merely sound
good, and it costs nothing: archive.org serves IIIF, so a citation is a URL. I
would rather ship a record that argues with itself in public than one that is
quietly adjudicated by me.

### Why I can hold that pace

I built OMEGA-wave — an open ocean-sensing mesh with firmware, gateway, protocol
and portal — in **three weeks: 762 commits, ~105,000 lines of Python, ~52,500 of
portal JavaScript, ~390 HTTP endpoints, 25 protocol specs, 14 firmware board
targets**, ending with a self-run adversarial audit that scored it 63/100 and
published the ranked backlog rather than the score alone.

Ground Truth reuses that work directly: the statistics suite, the map portal, the
agent framework and the provider layer are all lifted from it. Six weeks here is
not six weeks from zero.

---

## 3. Success metric

> **A resident of any Canadian community can ask what was measured where they
> live, get a straight answer in plain language with every number traceable to
> the scanned page it came from — and the system can show them what stopped
> being measured, and when.**

Checkable, in four parts:

1. **The dataset exists and is open** — measurements with place, time, parameter,
   unit, uncertainty and a page link, published with its accuracy methodology.
2. **Accuracy is published including failures**, per era and per parameter, on a
   gold set anyone can re-score.
3. **Every number resolves to its scan.** Not a sample — every one.
4. **The negative record is mapped**, with the digitisation control attached to
   every claim, because a silence finding is uninterpretable without it.

### What would count as failure, stated in advance

If extraction accuracy on a broader gold set comes in materially below what three
pages suggested, I will publish that number and narrow the scope rather than
quietly ship a confident dataset nobody has checked. **An archive that has been
misread at scale is worse than one that was never read, because the errors look
like findings.**

That is not a hypothetical caution. The first accuracy figure this project
produced was 49% precision — and it was wrong. The scorer could not convert
"3.0 million gallons" to "3000000 gallons", and the hand-written ground truth was
incomplete. Fixing the *measurement*, with no change at all to the extractor,
moved it to 88.7%. Publishing the first number would have narrowed the project
for no reason at all. Everything in this proposal is built to catch that class of
error, because it is the one that looks like success.

---

## Open source

MIT. Public repository, zero required dependencies in the core — clone it and
verify a measurement in five minutes with no install and no API key. The map
portal and the agent are a separate optional layer, so nobody has to stand up a
web stack to check whether 104 mg/L is what the page says.
