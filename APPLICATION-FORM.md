# Concordance — answers for the BC + AI application form

Each answer is written to stand alone, because they are read as separate fields
in a review database and a reviewer may not read them in order. Character counts
are checked by `scripts/check_form.py`; the limits are the form's own.

---

## Project title

Concordance: Canada's Municipal Water Record, Page by Page

---

## Project summary — *What do you want to build or create?* (2000)

In 1969, the sewage plant in Owen Sound, Ontario measured what it discharged into the river, wrote it down, and filed the report with the government. The report was scanned decades later. Almost nobody has ever read it.

Concordance is a free, open-source website that turns reports like that into a searchable public memory. Type in a town and see what officials measured there: effluent, drinking water, flows, and related municipal conditions across decades. Every value carries the sentence it came from and a link to the scanned page. Measurements made in incompatible ways remain separate instead of becoming a clean but fictional trend.

This is not a chatbot over an archive. A model running locally proposes structured readings; the evidence determines what can be published. The collection contains roughly 22 million pages, but I found no national, machine-readable database that brings these municipal measurements together with page-level provenance.

The live site holds 6,554 records across 24 towns, all downloadable; the repository carries the pipeline, the benchmark, and the 6,510 committed extraction records. A visitor picks an unread town and their own browser reads it, with no install, account, API key, or project-operated inference server. The site re-verifies every quoted sentence against the archive before publishing anything. A volunteer took Ear Falls through the loop before I submitted; Ingersoll was read entirely in a browser tab.

Six fellowship weeks would turn a working prototype into a defensible public tool: replace the four-page smoke test with a frozen benchmark across eras and document types, develop the existing British Columbia read into a community-tested pilot, and make both contribution paths work for a first-time user. Reading damaged tables is a bounded experiment, not a dependency.

Live: concordance.jonathancapone.com
Code: github.com/JonathanCapone/concordance

---

## Public benefit — *Who could use, question, or learn from this work?* (2000)

Concordance is designed first for a resident who wants to know what was measured in the water where they live. The archive is public but not practically searchable at the level of a local measurement. A resident can use a search box, chart, and source link.

Journalists and local historians can use the gaps as leads rather than conclusions. A title survey identifies 107 recurring municipal report series, and 72 end in 1974. That disappearance may reflect a policy change, a renamed series, missing records, administrative reorganization, or incomplete catalogue coverage. Concordance makes the pattern visible while refusing to claim which explanation is correct.

Researchers gain machine-readable historical series with a source page for every value and no silent joining of incompatible measurements. Design capacities, legal limits, observed measurements, and authors' conclusions remain distinct. Contextual records such as population served or sewer connections may be included, but are clearly labelled and never substituted for environmental observations.

A first British Columbia read already exists: 366 verified records from seven Lower Mainland documents. The fellowship pilot is therefore about community testing and reuse conditions, not about whether the method travels across provinces. The pilot community will be selected for a useful multi-year record, documented reuse conditions, and access to at least one local person who can test whether the result is understandable and relevant.

Anyone can challenge a reading. A challenge must cite evidence to alter the record; unsupported objections may remain visible but do not replace the original. The linked scan lets the public inspect both the extraction and the source.

A measurement pulled by a model from a sixty-year-old scan has no authority on its own. Concordance is useful because it makes that measurement easy to inspect, question, and correct.

---

## Proposed approach — *core method, tools, and a scope you can finish* (2000)

OCR often destroys historical table structure while preserving the prose around it. In these reports, prose sentences frequently contain complete readings: quantity, unit, place, date, and context. A four-page smoke test yields 96.8% precision, which is promising but not yet a defensible accuracy claim.

The pipeline first uses a low-cost local filter to classify pages as prose, table, figure, or skip. A language model running on the contributor's computer reads selected prose pages into structured records. It must label each statement as an observed measurement, design specification, legal limit, or author's conclusion. That distinction prevents a plant's rated capacity from being misread as what actually flowed through it.

Every proposed record must include supporting text. The verifier checks that the quotation and number occur in the page's OCR text layer; the public link lets a person compare that evidence with the scanned page image. This blocks a large class of fabrications, while the benchmark measures what still gets through. In current tests, the browser reader finds roughly half of what a page states and invents nothing that survives the checks.

The fellowship work will freeze an approximately 200-page, hand-labelled benchmark before tuning, stratified across eras, agencies, document types, and measurement classes. I will report precision and recall by category. Only classes reaching 95% precision will enter the dataset; the rest will remain clearly labelled finding aids.

The core verification path is plain Python with no package dependencies. Contributors do not need an API key or local copies of the collection's scans. A bounded table-reading experiment will test newer small vision models on a stated consumer-hardware baseline. Success would expand coverage; failure will produce a measured limit without blocking the public release.

---

## Dataset interest — *Why does this idea need the Canadian civics and open-government collection?* (2000)

Concordance needs the Canadian civics and open-government collection because the measurements appear to survive nowhere else in usable national form. They were published in annual reports, deposited with government, and eventually scanned by Internet Archive Canada. I found no machine-readable national database that brings the values together with links to the pages where they were reported.

The collection is valuable because it repeats. A title search finds more than five hundred dated reports resolving into 107 recurring municipal series. The same places filed related reports year after year, making it possible to build historical series rather than isolated anecdotes.

It is also deep enough to reveal gaps. Seventy-two of the identified series end in 1974. That is not proof that reporting stopped. It may reflect policy, cataloguing, administrative change, missing records, or incomplete collection coverage. Concordance can make the disappearance visible and direct a journalist, historian, or resident to the right question without pretending the archive already contains the answer.

The collection is civic as well as scientific. Alongside technical reports are council minutes, agendas, hearings, budgets, and planning documents: the record of who debated and decided the systems being measured. Concordance will not claim causal links it has not demonstrated, but the collection makes future connections between measurements and public decisions possible.

Finally, this archive supports page-level accountability. Each published value can point back to the public record rather than becoming an unattributed entry in a new database.

Public access to a scan is not a blanket licence for every use. The code will remain MIT-licensed, while derived data will be published only where reuse is supportable, with source rights documented and preserved.

---

## Work plan — *phases, and where you expect to learn or change course* (2000)

Concordance enters the fellowship as a working prototype with a reproducible corpus and benchmark. The six-week plan is designed to turn that prototype into a measured public release.

Week 1: Freeze the test. Finalize an approximately 200-page benchmark, answer key, consumer-hardware baseline, and the 95% class-level precision rule before tuning. Select the British Columbia pilot community and document reuse conditions, building from the existing Lower Mainland read.

Week 2: Read the pilot and keep unlike things unlike. Process and review the BC documents, then extend the rules separating observed measurements, specifications, legal limits, conclusions, units, methods, and contextual civic records.

Week 3: Measure. Run the frozen benchmark and publish precision and recall by era, document type, and measurement class. Classes below 95% precision remain finding aids rather than entering the public dataset.

Week 4: Build the public experience. Complete the BC search, charts, page links, uncertainty labels, and "not comparable" states. Once the prose path works, run a bounded experiment on damaged tables using the stated hardware baseline.

Week 5: Make the contribution loop survive strangers. Test both contribution paths with first-time users: the in-browser reader, which requires one click and no installation, and the installed reader for larger machines. Require at least one person to finish without live help; preserve a share-by-file fallback and document every failure.

Week 6: Publish. Release the website, seed dataset, reusable pipeline, benchmark, accuracy report, known limitations, and methods. Offer the catalogue corrections to Internet Archive Canada for review.

The project will narrow rather than bluff: weak extraction classes become finding aids, incompatible methods remain separate, and unsuccessful table reading is published as a measured limit.

---

## Expected deliverable — *What working artifact will exist at the end?* (2000)

At the end of six weeks, Concordance will produce four public deliverables.

First, a website anyone can use. A visitor can look up every place already published on the live site, 24 at time of writing, plus a community-tested British Columbia pilot. They can see what was measured, understand when values are unknown or not comparable, and open every published value's scanned source page.

Second, a downloadable seed dataset. Each record will include place, time, quantity, unit, record class, supporting text, source document, and page link. Observed measurements will remain distinct from specifications, limits, conclusions, and contextual civic records. Only measurement classes reaching 95% precision on the frozen benchmark will enter the dataset. It will not claim national completeness; it will be built to grow one requested place at a time.

Third, a frozen benchmark and accuracy report. The public report will include the approximately 200-page answer key, scoring code, precision and recall by era and measurement class, failed examples, and the classes withheld from the dataset. Anyone will be able to rerun the evaluation.

Fourth, a documented, reusable pipeline. The code will show how to classify pages, extract prose readings locally, verify evidence, review results, and prepare a contribution for publication. Code will be MIT-licensed; derived data will be released only where source rights support reuse.

A separate partner contribution will offer Internet Archive Canada 13,429 proposed catalogue corrections: 11,151 language-code normalizations and 2,278 publication-year proposals, with evidence for review.

The whole 22-million-page collection will not be read. The finished artifact will be a defensible seed corpus, a public method, and a contribution system that can expand without a project-operated inference server.

---

## Success metric (600)

Pass if every place published at submission remains searchable and the existing Lower Mainland read becomes a community-tested British Columbia pilot with documented reuse conditions. Every published record must carry supporting text and a page link; the frozen benchmark must report precision and recall by era and measurement class; and classes below the stated precision threshold must remain finding aids, not data. One BC tester must verify a local reading without help, and one new contributor must complete the full contribution path.

---

## Relevant experience — *What prepares you to do this work* (2000)

The live site holds 6,554 records across 24 towns, all downloadable; the repository carries the pipeline, the benchmark, and the 6,510 committed extraction records. The hardest half of Concordance is already built and can be checked rather than taken on trust. Every push runs the test suite on fresh Ubuntu and Windows machines. The accuracy score must reproduce exactly or the build fails. The fellowship would begin with a working system, not a blank repository.

My strongest qualification is a habit: I treat my own numbers as suspects, because in this kind of project the dangerous errors do not crash; they look like findings.

The first accuracy figure Concordance produced was 49% precision. The extraction was not the problem; the scorer failed to recognize that "3.0 million gallons" and "3000000 gallons" represent the same quantity. Correcting the ruler moved the result to 88.7%, and later extraction work produced the current 96.8% four-page smoke test. That experience is why the fellowship plan freezes a broader benchmark before tuning.

A human tester then found that the page router was discarding narrow-column prose because I had required eight words per line. A typographic shortcut was silently deciding which parts of the public record existed. The rule was corrected and covered by regression tests.

Days before submitting, I ran an adversarial audit of the repository. It found nine defects, six serious, including a verifier that accepted a number when only its first digit was present. Every fix now has a regression test.

My work as an artist and educator matters here too. Concordance must make provenance, uncertainty, incompatible methods, and technical failure understandable to people who are not data specialists. The project's claim is "check my work"; my experience has taught me to build the check, invite the challenge, and explain what happened when the system was wrong.
