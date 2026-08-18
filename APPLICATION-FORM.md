# Concordance — answers for the BC + AI application form

Each answer is written to stand alone, because they are read as separate fields
in a review database and a reviewer may not read them in order. Character counts
are checked by `scripts/check_form.py`; the limits are the form's own.

---

## Project title

Concordance: Canada's Municipal Water Record, Page by Page

---

## Project summary — *What do you want to build or create?* (2000)

In 1969, the sewage plant in Owen Sound, Ontario measured what it discharged into the river, recorded the results, and filed a report with the government. The report was scanned decades later, but almost nobody has read it.

Concordance is a free, open-source website that makes reports like this searchable. Enter the name of a town and see what local officials measured over time, including effluent, drinking water, and municipal flows. Every value appears with the sentence it came from and a link to the scanned page. Measurements collected in incompatible ways remain separate instead of becoming a clean but fictional trend.

This is not a chatbot over an archive. A model running locally proposes structured readings, but only records supported by verifiable evidence can be published. The collection contains roughly 22 million pages, and I found no national, machine-readable database that brings these municipal measurements together with page-level provenance.

The live site contains 6,554 records from 24 towns, all downloadable. The repository includes the extraction pipeline, benchmark, and 6,510 committed extraction records. Visitors can also choose a town that has not yet been processed and have their own browser read it, with no installation, account, API key, or project-hosted model. Before publication, the site checks every quotation against the archive. A volunteer completed the process for Ear Falls, and Ingersoll was read entirely in a browser tab.

During the fellowship, I would make the prototype more rigorous by creating a frozen benchmark across eras and document types, developing the British Columbia material already processed into a community-tested pilot, and improving both contribution paths for first-time users. Reading damaged tables would remain a bounded experiment rather than a requirement for success.

Live: concordance.jonathancapone.com
Code: github.com/JonathanCapone/concordance

---

## Public benefit — *Who could use, question, or learn from this work?* (2000)

The first audience for Concordance is a resident who wants to know what has been measured in the water where they live. The archive is public, but finding a single local measurement in it is difficult. Concordance gives residents a search box, charts, and direct links to source pages.

Journalists and local historians can use gaps in the record as leads rather than conclusions. A survey identified 107 recurring municipal report series, 72 of which end in 1974. That could reflect a policy change, a renamed series, missing records, administrative reorganization, or incomplete catalogue coverage. Concordance makes the disappearance visible without claiming to know its cause.

Researchers gain machine-readable historical records with a source page attached to every value. The project does not merge measurements collected in incompatible ways. Design capacities, legal limits, observed measurements, and authors' conclusions remain separate. Context such as population served or sewer connections may be included, but it is clearly labelled and never presented as an environmental observation.

Seven Lower Mainland documents have already produced 366 verified records. The fellowship pilot would therefore focus on community testing and responsible reuse, not on proving that the method works outside Ontario. The pilot community would be chosen for its multi-year record, documented reuse conditions, and access to a local person who can assess whether the results are understandable and relevant.

Any published reading can be challenged. Evidence is required to change a record; unsupported objections may remain visible, but they do not replace the original. Because every entry links to the scanned page, the public can inspect both the extraction and its source.

A measurement extracted by a model from a sixty-year-old scan should not be trusted on its own. Concordance makes it useful by making it easy to inspect, question, and correct.

---

## Proposed approach — *core method, tools, and a scope you can finish* (2000)

Historical OCR often preserves prose more reliably than tables. In these reports, prose sentences frequently contain complete readings: quantity, unit, place, date, and context. A four-page smoke test currently produces 96.8% precision. Promising, but too small for a broad accuracy claim.

The pipeline begins with a low-cost local classifier that sorts pages into prose, table, figure, or skip. A language model running on the contributor's computer converts selected prose pages into structured records. Each statement must be classified as an observed measurement, design specification, legal limit, or author's conclusion. This prevents a plant's rated capacity, for example, from being mistaken for the amount that actually flowed through it.

Every proposed record must include supporting text. The verifier confirms that the quotation and number appear in the page's OCR layer, and the page link lets a person compare that evidence with the scan. These checks prevent a large class of fabricated records, while the benchmark measures the errors that remain. In current tests, the browser reader finds roughly half of the relevant statements on a page, and no invented statement has survived verification.

The fellowship would begin by freezing an approximately 200-page, hand-labelled benchmark before further tuning. It would cover different eras, agencies, document types, and measurement classes, with precision and recall reported for each category. Only classes reaching 95% precision would enter the dataset; lower-performing classes would remain labelled finding aids.

The verification process is plain Python with no package dependencies. Contributors do not need an API key or local copies of the archive's scans. A limited experiment would test newer small vision models on damaged tables using a stated consumer-hardware baseline. Success would expand coverage; failure would establish a documented limit without preventing the public release.

---

## Dataset interest — *Why does this idea need the Canadian civics and open-government collection?* (2000)

Concordance needs the Canadian civics and open-government collection because these measurements do not appear to exist elsewhere in a usable national form. They were published in annual reports, deposited with government, and later scanned by Internet Archive Canada. I found no machine-readable national database that brings the values together while preserving links to their source pages.

Many reports recur. A title search identified more than five hundred dated reports that resolve into 107 municipal series. The same communities submitted related reports year after year, making it possible to build historical series rather than collect isolated examples.

The collection is also extensive enough to make absences visible. Seventy-two of the identified series end in 1974. This does not prove that reporting stopped. The change could reflect policy, cataloguing, administrative restructuring, missing records, or incomplete collection coverage. Concordance can show where the record changes and help a journalist, historian, or resident ask a more precise question without claiming the archive already contains the answer.

These are civic records as well as scientific ones. Council minutes, agendas, hearings, budgets, and planning documents appear alongside technical reports. Together, they preserve both measurements and decisions about the systems being measured. Concordance will not infer causal relationships the evidence does not support, but the collection makes future research connecting measurements and public decisions possible.

The archive also gives each published value page-level accountability. Rather than becoming an unattributed number in a new database, every record can point back to its public source.

Access to a scan does not automatically establish permission for every form of reuse. The software will remain MIT-licensed, while derived data will be released only when source rights support it, with those conditions documented.

---

## Work plan — *phases, and where you expect to learn or change course* (2000)

Concordance enters the fellowship as a working prototype with a reproducible dataset and benchmark. The six-week plan turns that prototype into a measured public release.

Week 1: Freeze the test. Finalize an approximately 200-page benchmark, answer key, consumer-hardware baseline, and 95% class-level precision rule before tuning. Select the British Columbia pilot community and document reuse conditions, building on the seven Lower Mainland documents already processed.

Week 2: Keep unlike things unlike. Process and review the pilot documents, then refine the rules separating observed measurements, specifications, legal limits, conclusions, units, methods, and contextual civic records.

Week 3: Measure. Run the frozen benchmark and publish precision and recall by era, document type, and measurement class. Classes below 95% precision remain finding aids rather than entering the public dataset.

Week 4: Build the public experience. Complete the pilot's search, charts, page links, uncertainty labels, and clear "not comparable" states. Then run a bounded experiment on damaged tables using the stated hardware baseline.

Week 5: Make the contribution loop survive strangers. Test both paths with first-time users: the in-browser reader, which requires one click and no installation, and the installed reader for larger machines. Require at least one person to finish without live help; preserve a share-by-file fallback and document every failure.

Week 6: Publish. Release the website, seed dataset, reusable pipeline, benchmark, accuracy report, known limitations, and methods. Submit the proposed catalogue corrections to Internet Archive Canada for review.

The project will narrow rather than bluff: weak extraction classes become finding aids, incompatible methods remain separate, and unsuccessful table reading is published as a measured limit.

---

## Expected deliverable — *What working artifact will exist at the end?* (2000)

By the end of six weeks, Concordance would produce four public deliverables.

The first is a website anyone can use. Visitors will be able to search every place already published on the live site—24 at the time of writing—as well as a community-tested British Columbia pilot. They will be able to see what was measured, recognize when values are unknown or not comparable, and open the scanned source page for every published value.

The second is a downloadable seed dataset. Each record will include place, time, quantity, unit, record class, supporting text, source document, and page link. Observed measurements will remain separate from specifications, limits, conclusions, and contextual civic records. Only measurement classes that reach 95% precision on the frozen benchmark will be included. The dataset will not claim national completeness; it will be designed to grow one requested place at a time.

The third is a frozen benchmark and public accuracy report. It will include the approximately 200-page answer key, scoring code, precision and recall by era and measurement class, failed examples, and the classes withheld from the dataset. Anyone will be able to rerun the evaluation.

The fourth is a documented, reusable pipeline. The code will show how to classify pages, extract prose readings locally, verify evidence, review results, and prepare a contribution for publication. The software will be MIT-licensed, while derived data will be released only when source rights support reuse.

The project will also offer Internet Archive Canada 13,429 proposed catalogue corrections for review: 11,151 language-code normalizations and 2,278 proposed publication years, each supported by evidence.

The project will not attempt to read all 22 million pages. Its final form will be a defensible seed dataset, a public method, and a contribution system that can expand without a project-hosted model.

---

## Success metric (600)

I will consider the fellowship successful if every place published at submission remains searchable and the Lower Mainland documents become a community-tested British Columbia pilot with documented reuse conditions. Every record must include supporting text and a page link. The benchmark must report precision and recall by era and measurement class, and classes below the required precision threshold must remain finding aids rather than enter the dataset. One British Columbia tester must verify a local reading without help, and one new contributor must complete the full contribution process.

---

## Relevant experience — *What prepares you to do this work* (2000)

The live site contains 6,554 records from 24 towns, all downloadable. The repository includes the pipeline, benchmark, and 6,510 committed extraction records. The core system is already built and open to inspection. Every push runs the test suite on fresh Ubuntu and Windows machines; the build fails if the accuracy score cannot be reproduced. The fellowship would begin with a functioning system, not an empty repository.

My strongest preparation is the habit of treating my own results as provisional. In this kind of project, the dangerous errors do not crash — they look like findings.

Concordance's first accuracy result was 49% precision. The extraction was not the main problem: the scorer did not recognize that "3.0 million gallons" and "3000000 gallons" represented the same quantity. Correcting it raised the result to 88.7%, and later extraction work produced the current 96.8% four-page smoke test. That experience is why the fellowship plan freezes a broader benchmark before further tuning.

A human tester later found that the page router was rejecting narrow-column prose because I had required eight words per line. A typographic shortcut was silently determining which parts of the public record the system could see. I corrected the rule and added regression tests.

Days before submitting, I conducted an adversarial audit of the repository. It identified seven defects, six serious, including a verifier that accepted a number when only its first digit was present. Each correction now has a regression test.

My work as an artist and educator is also relevant. Concordance must make provenance, uncertainty, incompatible methods, and technical failure understandable to people who are not data specialists. Its central promise is that the work can be checked. My experience has taught me to build that check into the system, invite challenges, and explain clearly what happened when it was wrong.

---
