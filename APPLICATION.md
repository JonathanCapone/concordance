# Concordance

**A free website where anyone can look up what was measured where they live —
the pollution readings, the water quality, the air — going back to the 1800s,
with every number linked to the exact government page it was read from. Plus an
open, source-linked seed dataset designed to grow beyond the pilot communities.**

*AI Builders Fellowship application. Core benchmark figures are tied to named
snapshots or artifacts; live-source estimates are labelled separately.*

---

## 1. The project

My August 11 catalogue snapshot holds **104,241 scanned Canadian government
publications** and 22.1 million pages; this project scopes its historical run
from 1841 to 2013. Inside are measurements of the physical condition of the
country, town by town, year by year: how much sewage a town discharged into its
river, what was in the drinking water, what came out of the smelter.

The fellowship brief describes the collection as roughly 48 TB, mostly page
imagery. The prose path fetches the separate OCR text layer and requests page
images only where the text layer is insufficient.

The median document in that collection has been downloaded **90 times**. I found
no usable national database of the numbers inside. To find out what your town's
sewage plant was discharging in 1969 you would have to know the report exists,
find it, and read it.

Taken together, those measurements can be treated as nodes in a monitoring
network that ran for over a century and covered the country. I have not found
evidence that this collection has been analyzed as one connected historical
record; each contributor published to paper and the paper went into a box.

I want to spend six weeks reading it back out, and putting the result somewhere
a person can use it.

### How it works, in one paragraph

The site and the reader already work, but the bridge between them is the
fellowship build. Today, the reader runs locally and can send prose results to
a Concordance instance, where each cited sentence and complete
numeric token are checked again. Table locators are preserved, but the current
public verifier abstains unless the number can be localized to the exact cell.
The browser can show existing results, but it does not yet hand a requested
place to a visitor's local reader. I will build and test that handoff so a
volunteer can contribute without an account, an API key, or a process left running.

That is the path to growth without a permanent central compute bill. It is a
deliverable, not something I am claiming is already deployed.

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

Nothing survives that. But many narrative paragraphs remain legible — and in
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

That is a complete set of readings in ordinary English. So the tractable first
problem is **reading prose**, where the current four-page benchmark measures
96.8% precision. Degraded tables remain the harder, unproven path.

Then, while I was building this, a plausible second path arrived. A local vision
model can read some table images even when OCR has destroyed their structure.
On one Brantford page it returned 27 records and recovered **10 of 12 values** I
had identified in the OCR beforehand. Across 24 table pages from 11 collections,
it returned 535 records from documents as unlike as Statistics Canada salt
production in 2003 and the Georgian Bay Ship Canal Survey of 1909.

The stored trial checked 461 of those 535 records for a matching digit sequence
in page OCR and found 411 (89%). That is a useful consistency check, not an
accuracy score: short numbers can match by chance, 50 did not match, and the
artifact does not preserve why 74 records were excluded. Their status is
unknown, not evidence from OCR-free pages; all 24 pages had some OCR text.

**The page images survived even where the OCR table structure did not.** The
question for the fellowship is how much can be recovered accurately and on
hardware a contributor might own.

### It already works

Not a proposal — a running artifact. Every figure carries the size of the sample
it came from, because a percentage without a denominator is not a measurement:

| | |
|---|---|
| Extraction precision / recall | **96.8% / 88.2%** — on 4 pages hand-read by a person, 68 values |
| ...of which, the one page annotated *before* any run | **94% / 94%** — 17 values |
| Telling a measurement from a design spec from a legal limit | **98.3%** — 60 matched values |
| Telling water going in from water coming out | **88.9%** — 18 judged pairs |
| Source-sentence mismatches in a 286-record audit | **0** |
| Vision-table trial output | **535 records** from 24 pages across 11 collections, 1879–2003; no hand-read accuracy score yet |
| Deterministic OCR date recovery | **142/145** non-bound held-out guesses agreed with catalogue years; **111/300** yearless residual items received date proposals |
| Frozen application checkpoint (`f8fbca2`) | **5,147 source-linked records** across 14 municipalities, including 2,384 observations |

*Precision* is how much of what it produced was correct; *recall* is how much of
what was there it found. Both are measured against a set of pages a human read
by hand first. Four pages is a small sample and I would not defend it as more
than an early signal — widening it is the first thing in the work plan.

The dating check is also deliberately narrower than “accuracy”: catalogue year
is a noisy surrogate. Every proposal carries verbatim OCR evidence; all 145
non-bound guesses were within one year of that catalogue value, and lower-bound
dates are reported separately rather than presented as publication dates.

Every prose number carries its source sentence; a table number carries its cell
locator. Both carry the exact page, and prose sentences and complete numeric
tokens are checked locally. Current table locators do not independently bind a
number to a cell, so those claims abstain from public verification. A measurement
pulled by a model out of a sixty-year-old scan has no authority on its own. It
earns authority by being easy to check.

### What it has already found

Each with the check that makes it a finding rather than an artefact:

**All 107 title-derived Ontario municipal report series end by 1974 — 72 of
them in that exact year.** Broader Ministry of the Environment publishing in the same collection
continues: 1,449 indexed items before 1975 and 3,800 afterward. That argues
against a collection-wide scanning cutoff. It does **not** distinguish municipal
non-reporting from missing holdings for any individual place, so this is a
finding about the indexed record and not yet one about the rivers.

A live ECCC query during development suggested that about 48% of returned
Ontario gauge records were marked discontinued. It is a live operational signal,
not a frozen application metric; its exact response has not been preserved.

**Whose sewage was in whose drinking water.** Plants matched to river gauges and
ordered by catchment: Fergus → Brantford → Cayuga on the Grand; Orangeville →
Streetsville → Clarkson on the Credit.

**13,429 catalogue-field proposals** for the collection itself, to be offered
back for review: 11,151 deterministic language-code normalizations and 2,278
year proposals. In my snapshot, 57% of items have no subject tag and 32% have no
parsed year; the subject gap remains separate work.

**My router was throwing away narrow-column prose.** My code counted a page
as prose only if its lines held eight or more words. That is a fact about
typography, not about content, and it was quietly deciding which parts of the
public record exist. A 1983 city magazine set in narrow columns — 149 lines of
unbroken prose, median four words to the line — scored zero, and every page went
in the bin, including one recording how many schools Hamilton had. On a later
8,372-page convenience sample, fixing that rule raised the candidate-page rate
to 69.5%. That sample cannot be extrapolated as the collection-wide rate, but it
located a real blind spot: Acts of the Parliament of Canada went from 265 usable
pages to 861.

I did not find that. Someone looked at a document and said *that doesn't sound
right*. It is in the work log with the rest of my mistakes, and it is the best
argument I have for building this in the open.

**How many kinds of measurement are in there? About 700, and I am nowhere near
them.** I ran a stratified sample across 25 collections overnight — 1,416
readings, twelve hours on one machine — to find out where the archive's
measurement vocabulary saturates. It does not. Coverage of the archive's own
terms reached **44%**, and Good–Turing/Chao1 puts the number of distinct
measurement types at **727, with a 95% interval of 557 to 987**. The discovery
curve is still climbing: the last round found more new terms than any round
before it.

The useful part is the contrast. The same estimator run over water reports alone
had said 90% coverage and about 200 terms — it looked finished because it was
only looking at the one domain the extractor was built for. Widening the sample
to 25 collections cut coverage in half and tripled the estimate.

And the control that matters most: **76% of readings outside the water reports
used a parameter name the model chose rather than one the archive uses**, against
32% inside them. That is the honest size of the gap between "this works on
municipal sewage reports" and "this works on the Canadian public record", and it
is the first thing weeks 1–3 are for. It is also exactly the class of error this
project keeps finding in itself: a number that looked good because it was
measured on the easy case.

**The archive also preserves who debated what.** Roughly 13,600 titles match
minutes, agendas or hearings. A deterministic parser can find motions and recorded
votes without a model, but its people and division counts have not passed the
same evidence benchmark as the measurements. For now that is an adjacent civic
opportunity, not a headline result.

### How big the job actually is

The frozen routing census sampled 120 documents and 23,729 pages:

- **90.8%** had at least one page routed to prose or table (95% confidence
  interval 84.3–94.8%)
- **53.1%** of pages were flagged for some reading path (95% confidence interval
  52.5–53.8%), extrapolating to 11.6–11.9 million pages under that router

Those are classifier outputs, not proof that a page contains measurements. A
later 8,372-page convenience sample produced 69.5% after a router fix, but it is
not a replacement for the random census. The router has changed again, so the
coverage and path split must be re-measured before they drive a budget.

### What the money is for

The fellowship is $5,000. **All of it is six weeks of my time.** There is no
compute line, and that is a deliberate design choice rather than an omission.

The obvious thing to do with money and an archive this size is rent GPUs and
read the whole thing. The current cost model is not reliable enough to quote in
an application, and even its corrected planning range exceeds this fellowship.
More importantly, a corpus bought in one batch is finished the day the money
runs out; the next person who wants an unread document has no way to get one.

**So the planned reading loop starts because somebody wanted to know
something.** You ask for a place. If it has been read, you get it instantly. If
you are first, the site will make an explicit handoff to the local reader, let
you preview what it found, and offer the evidence-checked result back. The
reader, bundle format and receiving endpoint work today; the safe one-click
handoff does not, and building it is in scope for the fellowship.

Results already move between machines and their cited page evidence is rechecked
on arrival, so no central instance has to be trusted as the authority. If
the handoff and user test succeed, **the archive can fill in as people ask for
it without a permanent central inference bill** — in the order people actually
want to know things, which is a better order than any I would impose.

### The hole in that, named

The model has one major unresolved weakness: degraded tables. Their current
corpus-wide share is not measured reliably, and the promising vision model does
not fit on an ordinary computer. On my own graphics card a trial page takes
about eight minutes because only 18% of the model's layers fit in memory.

I am not asking for money to brute-force past that, because that would buy a
fixed corpus and abandon the model that outlives the grant. Two things get tried
first, and both are measurable:

- **A smaller vision model may be adequate.** That is a question, not a hope,
  and I have not measured it yet.
- **Tables might be read once and shared.** One person with a good graphics card
  can read a document's tables, but the current page/row/column locator does not
  prove which number occupies the cited cell. Localized cell proof — and the
  image-only case where OCR supplies no referee — remain fellowship work.

If both fail, the honest answer is a re-measured fraction of this archive that
needs hardware most people do not own. That is worth knowing too, and it is a
better outcome than a number that hides it.

---

## 2. Work plan

**What the six weeks buys, in priority order.** The money is for evidence and a
complete public contribution loop, not for pretending the whole corpus fits.

**Week 1 — Freeze the test.** Design and hand-label a benchmark spanning eras,
agencies and document types, and select a British Columbia pilot before tuning.

**Week 2 — Comparability.** Apply the source-attested vocabulary and test units,
methods and reporting changes. Publish refusal rules for comparisons the
evidence cannot support.

**Week 3 — Measure prose.** Run the benchmark and publish precision and recall
per era and parameter, including where the system is bad.

**Week 4 — The tables.** Owen Sound's 1973 and 1974 reports contain *zero*
readable prose pages between them, so those years are unreachable without an
image path. The first vision model invented structure; the current 24-page trial
is promising but has no hand-read accuracy score. So the questions are
throughput, validation and whether a smaller model is good enough. *Ends with:*
either tables distribute, or the limit is named with a number.

**Week 5 — Complete the contribution loop.** Build the browser-to-local handoff
and test request, preview, source-check and sharing with first-time users.

**Week 6 — Publish.** The dataset released openly with its methodology and its
failures; the metadata proposals offered to Internet Archive Canada; the
write-up; and, if the work is ready, the conditional October 28 showcase.

### What happens after, and is not being funded here

I would rather name these as intentions than pad six weeks with them: running
the silence detector nationally, cross-referencing agencies whose records have
never been in the same room, and pointing the pipeline at other scanned
archives. All three are things this design makes possible and none of them are
promises for October.

### Comparability, which is the real scientific risk

A number from 1961 and one from 2001 are not automatically comparable. "BOD"
was measured by different methods, laboratories, detection limits and reporting
rules. Some dimension and unit guards exist, but MGD and Imperial-gallon
normalization remains unresolved; affected series are not yet defensible as
comparable. A plant that changes what it reports can look like a plant that
changes what it discharges.

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
their town, and nobody has been asked to. The contribution primitives — local
reading, bundle export, server-side evidence checks and merge — are built. The
safe browser-to-local handoff is not. I believe people will contribute for the
town they grew up in, but I have no evidence; building and testing that complete
loop is fellowship work.

If they do not come, the project does not fail: it becomes a smaller dataset
plus a very good finding aid, because every reading published still carries its
scan and the machinery still works for whoever runs it. That is the fallback and
it is worth saying out loud rather than discovering in week five.

**No institution has agreed to anything.** The 13,429 metadata proposals are
offered to Internet Archive Canada, not accepted by them — I have not asked yet,
because offering a diff is more useful than offering a promise. Same for the
municipalities whose records these are.

**The validated evidence is Ontario water.** Every worked extraction example
above — Owen Sound, Brantford, Burlington — comes from Ontario sewage reports,
because that is where the deepest comparable run survives. The collection does
contain British Columbia material, including provincial Water Management
publications, but I have not published a BC extraction benchmark. A named BC
pilot is therefore a week-one deliverable, not something this application
pretends has already happened.

### Who actually does what

Four kinds of person, and only one of them is asked to do anything.

**Most people just read.** They look up a covered town and see published readings
and documented collection gaps, with caveats visible. They install nothing and
contribute nothing, and they are the point of the whole exercise. If this works
they are 99% of the users.

**Someone wants a place nobody has read yet.** The intended experience is one
explicit handoff from the site to a local reader, followed by a preview and an
evidence-checked contribution. Today those pieces exist separately; joining
them safely and testing whether anyone will use them is part of the build.

**Someone disagrees with a number.** They cite a page and quote evidence. The
source check settles whether that evidence exists, not whether its interpretation
is correct. During a running instance, an unevidenced flag is counted and shown
but cannot change data; supported disagreements remain beside the original.

When two readings both survive the check, neither wins. Both link to the exact
archive page and, when the image service permits, show a cropped photograph of
the cited sentence; otherwise the unavailable crop is named plainly. The reader
settles it from the evidence rather than from the model.

**And someone has a good graphics card.** They can test the tables the rest of
us cannot. Making those results safely reusable still requires localized cell
proof; the current public verifier deliberately abstains without it.

### What is built, and what is not

| | |
|---|---|
| Look up a covered town and see selected series and source records | **built** |
| Ask for a place nobody has read; your machine reads it | **not yet end-to-end** — fellowship work |
| Submit a correction, checked for cited page evidence, no moderator | **built** |
| Send readings to a shared instance, page evidence rechecked on arrival | **built** |
| Ask a question in plain English and get an answer that cites its pages | **built** — over two towns, needs the data |
| Read the tables on ordinary hardware | **not built** — weeks 3–5 |
| The dataset, published, at scale | **not built** — this is the fellowship |

An instance rechecks cited page evidence and reports what it refused. It can
export its merged dataset so another instance can recheck and rehost it. That
makes it replaceable as a data source; it is not by itself proof that a public
deployment is operationally safe.

---

## 3. Success metric

> **A resident in every published pilot community — the existing 14 plus at
> least one British Columbia pilot — can ask what was measured, get a straight
> answer, and click every published record through to its scanned page.**

Checkable, in four parts:

1. **The dataset exists and is open** — measurements with place, time,
   parameter, unit and a page link, published with the accuracy methodology
   beside it. No uncertainty column unless there is a real method behind it, per
   the commitment above.
2. **Accuracy is published including its failures**, per era and per parameter,
   on a benchmark anyone can re-score themselves.
3. **Every number resolves to its scan.** Not a sample — every one. This is the
   one I will not trade away, because it is what makes the rest checkable.
4. **The browser-to-local contribution loop passes a first-time-user test.** An
   archival gap is labelled with what its controls rule out and what remains
   unknown; it is never presented as an environmental trend by itself. National
   coverage and the national silence map are stretch goals, not pass/fail claims.

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

It keeps happening, which is why I keep building checks. An adversarial audit
found nine defects, six rated serious — including a verifier that accepted a
number against a sentence containing only its first digit. The fixes have
targeted regression tests, and the full test suite passes. A project whose
claim is *check my work* should say what happened when somebody did.

---

## Open source

MIT licence; the fellowship deliverable is a public repository. The core has
**zero package dependencies** —
someone with Python can clone it and verify a stored measurement without an API
key. New extraction also needs Ollama and a local model. The map and assistant
are a separate optional layer, so checking whether 104 mg/L is really what the
page says does not require a web stack.
