# Work log

A running record of what was built, what was measured, and — mostly — what turned
out to be wrong. Kept because the mistakes are the useful part: every serious one
in this project has been **plausible-wrong rather than crash-wrong**, and that
pattern is worth more to the application than a feature list.

Reverse chronological. Every figure here is reproducible from the repository.

---

## Where it stands

| | |
|---|---|
| Commits | 36 |
| Tests | 331 |
| Python | ~14,000 lines, zero required dependencies in the core |
| Documents read | 22 of 104,241 (**0.02%**) |
| Extraction precision / recall | **88.7% / 82.5%** on hand-checked ground truth |
| Blind page | **88% / 88%** |
| Quotes failing verification | **0 of 286** |
| Licence | MIT |

---

## The findings, each with its control

**72 of 107 Ontario municipalities stop filing water pollution control plant
reports in 1975.** A series vanishing at once usually means the scanning stopped,
so it was checked: Ministry of the Environment publications in the same
collection run 1,449 before 1975 and 3,800 after, steady at 83–141 items a year
straight through. The archive kept growing; this series died.

**539 of 1,119 Ontario river gauges are discontinued** — 48%, live ECCC data. The
same winding-down, still happening.

**Owen Sound, 1963–1972.** BOD removal 46.4% → 64%. 120 readings from 10 scanned
reports, each linked to its page.

**Whose effluent reached whom.** Fergus → Brantford → Cayuga on the Grand;
Orangeville → Streetsville → Clarkson on the Credit — recovered from gauge
catchment areas, and correct.

**90.8% of documents in the collection carry measurements** (95% CI 84.3–94.8%),
from a random sample of 120 items and 23,729 pages.

**13,429 metadata corrections** proposed for the collection itself.

---

## What went wrong, and what it cost

### The ruler, not the thing being measured
First scored run: **49% precision.** Auditing the records it called wrong showed
nearly all were right. The scorer could not convert "3.0 million gallons" to
"3000000 gallons", and the hand-written ground truth was incomplete. Fixing the
*measurement*, with no change to the extractor, moved it to **88.7%**.

Publishing 49% would have narrowed the project for no reason. This is the single
most important thing that happened.

### A chart that was quietly plotting the wrong quantity
Parameters were matched by substring, so `"suspended solids"` matched
`"suspended solids removal"` and the effluent-**concentration** chart was
plotting removal **percentages**. Both are small numbers that fall when a plant
improves, so it looked entirely reasonable.

### A threshold set by guess
Ontario has two Sydenham Rivers in unconnected watersheds — one draining to
Georgian Bay, one to Lake St. Clair. A 300 km guard linked them and produced a
confident, wrong claim about whose sewage reached whose water. Recalibrated
against real spreads: legitimate rivers reach 127 km (the Thames), the Sydenham
pair spans 244, so 150 separates them.

### A measurement defined away by its own measurement
The silence detector derived its horizon from the same data it was testing. Every
town's last report was 1974, so the horizon became 1974 and no town could register
as having gone silent. It reported **9** municipalities instead of **72**.

### Provenance that was wrong rather than missing
Every row in the town panel quoted the same sentence, because source records were
matched on year alone. Wrong provenance is worse than none: the entire trust model
is "this sentence is where this number came from".

### A regex that could never match
Four attempts to separate exceedance from removal failed because writing the
pattern through a shell heredoc collapsed every `\b` into a literal backspace
byte. It printed identically to a correct pattern and matched nothing. The repo is
now checked for control bytes rather than assumed clean.

### A vocabulary gap mistaken for extraction failure
An audit of 281 records found **36.7%** carried a parameter the table had never
seen — hardness, retention time, trihalomethanes. Extracted correctly, then
dropped from every series in silence. Adding them took unresolved records to
15.0% and clean records from 36% to 69%.

### A thousandfold error that looked ordinary
Drinking-water reports give trace contaminants in `ug/L`. Reading 8 ug/L as
8 mg/L overstates it a thousand times, and both numbers look perfectly normal on
a page.

### Two facilities, one town
The extraction walked from sewage annual reports into a 1992 Drinking Water
Surveillance report, because both are titled "annual report" and both say Owen
Sound. One measures what the town discharged, the other what residents drank.
Merged, the chart is not merely wrong but backwards.

---

## Things that worked first time

Rare enough to record.

**The hallucination guard.** The model must return the verbatim sentence, and it
is checked against the page. Zero failures in 286 records.

**Refusing to answer.** The first trend the project produced was a refusal —
Owen Sound's flow rises 175,000 gal/day/yr, and the same line reports p=0.71, an
interval spanning zero, 62% direction stability, and two of six points flagged as
probable scan damage. A naive pipeline publishes the slope.

**Reading is the sensing act.** OCR preserved prose and destroyed tables, and the
measurements are in the prose. That finding — made before applying — is why six
weeks is credible.

---

## Design decisions worth defending

**Zero dependencies in the core.** A stranger can clone it and verify a
measurement in five minutes with no install and no key. The claim is "88.7%
precision"; a claim like that is worth nothing if checking it is hard.

**The serving layer is separate.** Map, portal and agent live outside the core,
so nobody has to stand up a web stack to check whether 104 mg/L is what the page
says.

**Every number is falsifiable in under a minute.** Verbatim sentence, verified
against the page, deep link to the scan. A measurement recovered by a model from
a sixty-year-old scan has no authority on its own; it earns authority by being
trivially easy to disprove.

**Refusals are features.** The units layer declines to compare a concentration
with a load. The changepoint test is documented as useless at these sample sizes.
The watershed refuses two rivers sharing a name. Silence about a limit is worse
than the limit.

---

## Reading the whole archive

| | |
|---|---|
| Pages worth reading | 11,735,100 |
| Total tokens | 13.9B |
| On this machine | 56 machine-years — not a plan |
| Rented A100 (spot) | ~$1,500–3,100 · 54–107 days |
| Rented H100 | ~$1,400–2,700 · 20–40 days |
| Hosted API, list price | $26,000 — no |

Reading the entire Canadian public record fits inside a $5,000 fellowship, and
it is a one-time cost. Afterwards the dataset costs everyone else nothing.

Caveats travel with the number: rented throughput is estimated rather than
measured, tables and figures are 26% of pages and need a dearer vision pass, and
any prompt change means paying again — so the extraction prompt must be settled
before the money is spent.

---

## Distribution: reading as a side effect of asking

There is no volunteer mode and nothing is asked of anyone. You ask for a place's
record. If the library has it, you get it in milliseconds. If you are the first
to want it, your machine reads it — and it is in the library for everyone from
then on.

The cost falls on whoever cares first, who is also the person most willing to
wait. The archive gets read in the order people actually want to know things.

This works because **verification is domain-independent**. Every record carries
its sentence and page, so the check asks the archive rather than the submitter:
is that sentence there, and is that number in it. You can accept a contribution
about school examinations while knowing nothing about school examinations.

Both attacks are covered — a fabricated sentence fails, and changing a number
while keeping its true sentence fails too. What it cannot catch is misreading:
"104 mg/1" really being on the page says nothing about whether it is influent or
effluent.

---

## The frontier

The archive can nearly answer things. "Did what Fergus discharged show up in
Brantford's intake?" needs both towns; Brantford is read, so it is one document
away — and has been waiting since 1961.

That gives eleven million pages an ordering nobody otherwise has: not
alphabetical, not chronological, but **by what reading it would unlock**. Against
the real data the top of the list is Fergus, which opens three questions at once.

It replaces a badge with something true. "You processed 40 documents" is a fact
about you. "You made the Grand River answerable for everyone" is a fact about the
world.
