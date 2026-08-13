"""Read a stratified sample of the whole archive until the vocabulary saturates.

The question this answers: **how many distinct kinds of measurement does the
Canadian public record contain?** Nobody knows. It is not in any catalogue, and
you cannot find out by thinking about it — you have to read until you stop
finding new ones.

Why it has to be stratified rather than random. `governmentpublications` is
51,137 items and `sessionalpaperscanada` is three, so a random sample is a
sample of Ontario water reports with a rounding error of everything else. The
vocabulary that is missing is exactly the vocabulary of the corners: fisheries
tonnage, mine ventilation, hospital bed-days, grain grades. So every collection
is its own stratum, each item lands in the RAREST collection it belongs to, and
the stopping rule is a minimum across strata rather than a pooled total. A total
can read 97% while an entire agency is untouched.

Coverage is Good–Turing: the share of readings whose term has been seen more
than once. If a tenth of what you read is still a term you have never seen, you
are not finished. `vocab_sample` also reports Chao1, an estimate of how many
terms exist including the ones never sampled, with an interval.

    python scripts/run_vocab.py --budget 4000 --out data/results/vocab_coverage.json

Nothing here decides what a term MEANS. That is judgement and it stays with a
person — `vocab_builder` produces the proposals and someone confirms them. This
script only finds out what the archive says, and when it has said enough of it.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concordance.archive import Archive
from concordance.extract import default_client, extract_prose
from concordance.router import Path as RoutePath, route
from concordance.vocab_sample import Reading, Survey, stratify


def _family(title: str) -> str:
    """The title family, not the item.

    Brantford 1962 and Brantford 1963 are two documents and one vocabulary.
    Counting families is what stops a stratum looking well sampled because one
    annual report was read twelve times.
    """
    t = "".join(c if c.isalnum() or c.isspace() else " " for c in str(title).lower())
    words = [w for w in t.split() if not w.isdigit()]
    return " ".join(words[:6])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=4000,
                    help="maximum readings to collect before stopping")
    ap.add_argument("--per-stratum", type=int, default=3,
                    help="documents to sample from each stratum per round")
    ap.add_argument("--pages-per-doc", type=int, default=4)
    ap.add_argument("--model", default="gemma4:12b")
    ap.add_argument("--out", default="data/results/vocab_coverage.json")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--max-strata", type=int, default=40,
                    help="cap the strata sampled; the tail is thousands of "
                         "collections holding one item each")
    args = ap.parse_args()

    random.seed(args.seed)
    archive = Archive()
    client = default_client()

    print("loading the index…", flush=True)
    index = list(archive.iter_items())
    strata = stratify(index)
    print(f"{len(index):,} items in {len(strata):,} collections")

    # Biggest strata first, but every one of them sampled: the plan is what the
    # stopping rule is measured against, so a stratum that is never planned can
    # never quietly excuse itself.
    chosen = sorted(strata.items(), key=lambda kv: -len(kv[1]))[: args.max_strata]
    survey = Survey()
    survey.strata_planned = {name: len(items) for name, items in chosen}
    print(f"sampling {len(chosen)} strata\n")

    seen_docs: set[str] = set()
    started = time.time()
    round_no = 0

    while survey.readings < args.budget:
        round_no += 1
        batch: list[Reading] = []
        pages_read = 0
        docs_read: set[str] = set()

        for name, items in chosen:
            pool = [it for it in items if it.get("identifier") not in seen_docs]
            if not pool:
                continue
            for item in random.sample(pool, min(args.per_stratum, len(pool))):
                ident = str(item.get("identifier") or "")
                seen_docs.add(ident)
                try:
                    pages = archive.pages(ident)
                except Exception as exc:  # noqa: BLE001
                    print(f"    {ident[:34]:<36} unreachable: {str(exc)[:40]}")
                    continue

                readable = [p for p in pages
                            if RoutePath.PROSE in route(p).paths]
                if not readable:
                    continue
                docs_read.add(ident)
                for page in random.sample(
                        readable, min(args.pages_per_doc, len(readable))):
                    try:
                        result = extract_prose(
                            page, client=client, title=str(item.get("title") or ""),
                            publisher=str(item.get("publisher") or ""),
                            year=str(item.get("year") or ""))
                    except Exception as exc:  # noqa: BLE001
                        print(f"    {ident[:34]:<36} extract failed: "
                              f"{str(exc)[:40]}")
                        continue
                    pages_read += 1
                    for rec in result.records:
                        batch.append(Reading(
                            parameter=rec.parameter, unit=rec.unit,
                            source_text=(rec.provenance.source_text
                                         if rec.provenance else ""),
                            stratum=name, identifier=ident,
                            family=_family(item.get("title") or ""),
                            page=page.page,
                            ocr_confidence=getattr(page, "confidence", None)))

        if not batch:
            print("no further readings available; stopping early")
            break

        # Survey.observe counts readings and terms; effort in PAGES and
        # DOCUMENTS is the runner's to record, and the first run reported
        # "1,416 readings, 0 documents" because nothing here was setting it.
        # Effort is half of a saturation result -- coverage means nothing
        # without how much reading bought it.
        survey.pages += pages_read
        survey.documents.update(docs_read)

        fresh = survey.observe(batch)
        cov = survey.coverage()
        weakest = survey.weakest_strata(1)
        w = weakest[0] if weakest else {}
        print(f"round {round_no:>2}  +{len(batch):>4} readings  "
              f"total {survey.readings:>5}  new terms {fresh:>3}  "
              f"min coverage {cov.coverage:.1%}  "
              f"weakest {str(w.get('stratum',''))[:24]}", flush=True)

        # Checkpoint every round. This run is measured in hours, and a survey
        # that only writes at the end is a survey that loses everything to a
        # closed laptop. The report is valid at any round: it is a curve, and a
        # shorter curve is a smaller result rather than a broken one.
        Path(args.out).write_text(
            json.dumps(survey.report(), indent=2, ensure_ascii=False),
            encoding="utf-8")

        if survey.done():
            print("\nstopping rule met: every planned stratum is above target")
            break

    report = survey.report()
    out = Path(args.out)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    mins = (time.time() - started) / 60
    print(f"\n{survey.readings:,} readings, {len(survey.documents):,} documents, "
          f"{mins:.0f} min")
    print(f"terms found: {len(survey.archive_terms())}")
    print(f"-> {out}")
    if not survey.done():
        print("\nThe stopping rule was NOT met. That is a result, not a failure: "
              "it says\nhow much of the vocabulary this much reading reaches, and "
              "the estimate of\nwhat remains is in the report.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
