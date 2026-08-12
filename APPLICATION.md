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
Canada salt production in 2003, a Simcoe well supply report in 1990 and the
Georgian Bay Ship Canal Survey of 1909: across **24 table pages from 11
collections it recovered 535 measurements**, a median of 25 a page, and 89% of
those values can be found in the page's own surviving OCR. The rest sit on pages
whose text layer was destroyed — which is the case the path exists for, and the
case its own corroboration cannot reach.

That is the strongest form of "only possible now" I can give you. **The tables
were never lost. They were merely unreadable by the software that existed when
the pages were scanned.** They have been sitting in public, and inaccessible,
for a decade.

### It already works

Not a proposal. A measured artifact, running today:

| | |
|---|---|
| Extraction precision / recall | **96.8% / 88.2%** against hand-checked ground truth |
| Blind page (annotated before any run) | **94% / 94%** |
| Kind accuracy — measurement vs design spec vs regulatory limit | **98.3%** |
| Stream accuracy — influent vs effluent | **88.9%** over 18 judged pairs |
| Quotes failing verification across 286 records | **0** |
| Table measurements recovered | **535** from 24 pages, 11 collections, 1879–2003 |
| ...of which found in the page's surviving OCR | **411 of 461 (89%)** |
| Measurements settled / contested / unsupported | **736 / 78 / 17** across 1,039 claims, with nobody adjudicating |
| Code / tests | 498 tests · zero required dependencies in the core |

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

### What the money is not for

Buying the whole read would cost **$4,251–8,502** of rented GPU time — a figure
worth having, and not what I am asking for. It is the wrong thing to spend a
fellowship on for a reason that has nothing to do with the price.

**A corpus bought in one batch is finished the day the money runs out.** It
covers whatever was current in October 2026, it is never extended, and the next
person who wants a document nobody thought to read has no way to get it. Anyone
with a credit card can rent an A100. That is not the interesting version of this
project, and it is not the version I have been building.

The version I have been building is that **reading happens because somebody
wanted to know something.** You ask for a place; if it has been read you get it
in milliseconds, and if you are the first to ask, your machine reads it and it
is there for everyone after you. No volunteer mode, no queue, nothing asked of
anyone — the cost falls on whoever cares first, who is also the person most
willing to wait. `share.py` moves the result to other machines as a file, and
every reading is re-checked against archive.org on arrival, so no server has to
be trusted or paid for.

That model has one honest hole, and it is the reason the number above exists at
all.

| | who can do it | why |
|---|---|---|
| **Vocabulary** | must be central | Deciding what a measurement *means* is judgement, not compute. A stratified sample costs about **$30–70**. |
| **Prose** — 73% of pages | anyone | 91 seconds a page on an ordinary machine. A town takes about ninety minutes. |
| **Tables** — 27% of pages, ~69% of the measurements | **almost nobody** | Eight minutes a page on my RTX 2080, because only 18% of a 29.6 GB model fits in 8 GB of VRAM. |

**Tables are the problem, and I would rather say so than budget around it.** The
measurements are concentrated in exactly the pages a contributor's hardware
handles worst. So the fellowship funds the parts that cannot distribute and
proves the parts that can:

- the **vocabulary pass**, central by necessity and cheap — tens of dollars;
- a **measured throughput pilot** on a thousand pages, which is the first thing
  any funded run should do anyway, since the vision figure in the table above is
  a guess and is most of its own cost;
- a **seed corpus** large enough to make the showcase real and the frontier
  meaningful — the towns, the rivers, and the councils that go with them;
- and six weeks of work on the thing that makes the rest self-sustaining.

The remainder of the archive fills in as people ask for it, indefinitely, at no
recurring cost to anybody. That is a slower answer than a batch run and a much
better one: the corpus is read in the order people actually want to know things,
which is a better ordering than any I would impose, and it does not stop when
the grant does.

Two things I will try before conceding that tables need rented hardware. A
smaller vision model may be adequate — that is a measurable question and I have
not measured it. And a page's tables can be read once by whoever has the
hardware and shared as a bundle, which is what `share.py` is for. If both fail,
the honest answer in the write-up is that 27% of this archive needs a graphics
card most people do not own, and that is worth knowing too.

That division is also the answer to the obvious objection about distributed
contribution. The central run does what is expensive and uniform — the
vocabulary, and the tables — once. People do prose, on demand, on their own
machines, which is where places, dates, narrative and the whole deliberative
record live.

---

## 2. Work plan

Structured as arcs rather than a rigid week grid, because the work has
dependencies that do not respect calendar boundaries and I would rather commit
to what each stage ends with than to which Tuesday it lands on. Each arc ends in
something demonstrable, and the order is chosen so that stopping early still
leaves a complete artifact rather than a half-built one.

**Arc A — Harden the loop, then read at scale (weeks 1–2)**
The destination now exists — an instance accepts a bundle, re-verifies every
record against archive.org, and merges what the archive supports. What it needs
next is the unglamorous half: a public instance that stays up, rate limiting so
one sender cannot monopolise it, and a second instance pulling from the first, to
prove the claim that no single one of them matters. A federation of one is just a
server.

Then bulk text acquisition across the collection; the cheap local filter that
decides which pages earn a model; the vocabulary pass; and the throughput pilot
that turns the estimated cost above into a measured one. Ends with: two instances
that agree without trusting each other, a seed corpus, and a per-page cost
somebody could plan against.

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

**Arc C2 — Make the tables reachable (week 3–4)**
27% of pages hold most of the measurements and need a model that will not fit on
an ordinary graphics card. Three things to try, in order of how much they would
change: a smaller vision model that a contributor can actually run; reading a
document's tables once and sharing the result as a bundle, so nobody pays twice;
and failing both, a plain statement of what fraction of this archive needs
hardware most people do not own. Ends with: either tables distribute, or the
limit is named with a number on it.

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

### Who actually does what

Four kinds of person, and only one of them is asked to do anything at all.

**Most people just read.** They open a published page, look up the town they
grew up in, and see what was measured there and when it stopped. They install
nothing, contribute nothing, and are the point of the whole exercise. If this
works, they are 99% of the users.

**Someone wants a place nobody has read.** They ask for it. The panel says so
plainly — *"Nobody has read this one yet. 12 scanned reports are waiting, about
an hour on this machine"* — and they press a button. Their laptop does the
reading, they get their answer, and the reading is now done. **That is the whole
of the ask.** No account, no queue, no volunteering, no task list. The cost falls
on the person who cared first, who is also the person most willing to wait for
it.

**Someone disagrees with a number.** They cite a page and quote a sentence, and
the archive decides — the same check that judges the machine's own output, which
never asks who is speaking. An evidenced correction replaces an unevidenced
record automatically. An objection with no evidence is counted, shown, and
changes nothing, because the moment it could, somebody would have to judge it.

**And someone has a graphics card.** Tables need a model that will not fit on an
ordinary machine, and 27% of pages hold most of the measurements. A person with
real hardware can read those once and publish the result for everyone, which is
the one place where "contributing" means something more than asking a question.

### What is built, and what is not

I would rather be exact about this than let the diagram do the arguing.

| | state |
|---|---|
| Ask for a place, read it locally if nobody has, verify, keep it | **built** — `library.ask`, wired to a button |
| Submit or correct a reading, checked against the scan, no moderator | **built** — `disputes.submit`, with a form |
| Package readings as a file and re-verify them on arrival | **built** — `scripts/share.py`, tested end to end |
| A place to send that file | **built** — `share.py push`, into a running instance |

The last row was the gap until recently, and it was the difference between "your
machine read it" and "it is there for everyone": a bundle had to be handed to
somebody. `POST /api/bundle` closes it. An instance re-verifies every record it
is sent, against archive.org, on exactly the terms it judges its own output —
so it keeps what the archive supports and reports what it refused, rather than
rejecting a whole submission over one bad line. There is no account, no key and
no field recording who sent it, because nothing about the sender is relevant to
whether a sentence is on a page.

**The instance is a convenience, not an authority.** It holds nothing anyone
else lacks: `GET /api/library.json` hands back the entire dataset as a bundle,
and `share.py pull` fetches it and then re-checks it locally before believing a
word of it. Anyone who mistrusts mine can take everything and run their own, and
the readings would be no less true. That property is why a server is safe to add
here and would not be in a system where the server was the source of truth.

Files still work, and are still the fallback that outlives the funding — a
bundle moves by email, USB stick or a link in a forum post, and nothing in the
verification path needs the network to have a centre.

Finding this took a bug worth admitting. Pushing an instance its own library
merged 19 of 20 readings as new: dedup compared a freshly-computed identity
against the one stored in the file, and the stored one was written before later
normalisation, so it never matched. The dataset would have doubled on every
round trip, and round trips are the whole model. Identity is now recomputed from
content on both sides, and a test pushes the library at itself and asserts that
nothing lands.

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

**And readings travel as a file.** `share.py export` packages what a machine has
read; `share.py import` re-checks every record against archive.org on arrival.
A bundle moves by pull request, email, USB stick or a forum link — none of which
need a server anybody has to run, pay for, or be trusted to keep honest. This
project has no infrastructure and now needs none. Nothing about the sender is
examined, because nothing about the sender is relevant: a signature would prove
who sent it, and the archive proves whether it is true.

### Why six weeks is enough

Because most of it is already built, and you can check that rather than take my
word for it.

I previously built OMEGA-wave, an open ocean-sensing mesh with its own protocol,
gateway, statistics suite and map portal. Ground Truth reuses that work directly:
**the statistics layer** (Mann-Kendall, Theil-Sen, Pettitt changepoint — all
pure-stdlib, which is why this package still has zero required dependencies),
**the map portal**, **the agent framework** behind Honu, and **the keyless
provider layer** that reaches ECCC and Statistics Canada. Six weeks here is not
six weeks from zero.

The more useful evidence is this repository. Everything in the results table
above runs today, the accuracy figure regenerates from `scripts/run_gold.py`
against ground truth a human read by hand, and the work log records what went
wrong at each step — including a routing bug that was silently discarding a
fifth of the archive, found because somebody looked at one document and said
that doesn't sound right.

What the six weeks buys is not the tooling. It is the reading, the vocabulary,
and the parts of this that cannot be done on one laptop.

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
moved it to 96.8%. Publishing the first number would have narrowed the project
for no reason at all. Everything in this proposal is built to catch that class of
error, because it is the one that looks like success.

It keeps happening, which is why I keep building the checks. An adversarial
audit of this repo, run days before submitting, found nine confirmed defects
and six of them were serious. The value check accepted any round number against
any sentence containing its first digit — 3,000,000 verified against a sentence
about the year 1913 — so the headline safeguard had a hole shaped exactly like
the numbers this corpus is full of. One genuine reading could carry five
hundred fabrications into the library through a public endpoint. And the
shipped town page captioned twelve of its thirteen numbers with a sentence that
does not contain them, under a heading promising every number is linked to its
scan, because the number and its citation were chosen by two different pieces of
code.

All of that is fixed, tested against the attacks that found it, and written up
in the commit history rather than quietly repaired. I am including it here
because a project whose entire claim is "check my work" should say what happened
when someone did.

---

## Open source

MIT. Public repository, zero required dependencies in the core — clone it and
verify a measurement in five minutes with no install and no API key. The map
portal and the agent are a separate optional layer, so nobody has to stand up a
web stack to check whether 104 mg/L is what the page says.
