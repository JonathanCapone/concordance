"""Move readings between machines, and re-check them on arrival.

This is the part the distributed model was missing. Everything else was in
place -- a reading is verified against the scan it cites, and the check never
asks who is speaking -- but a contribution written to `data/contributions` on
one laptop reached nobody, so "read it once and it is there for everyone" was
true of the reading and false of the everyone.

The mechanism is deliberately a file.

    python scripts/share.py export --out fergus.bundle.json
    python scripts/share.py import fergus.bundle.json

A bundle can travel by pull request, email, USB stick, or a link in a forum
post, and none of those need a server anybody has to run, pay for, or be
trusted to keep honest. The project has no infrastructure and this way it needs
none: whoever wants to publish a set of readings publishes a file.

**Trust does not travel with it.** Nothing about the sender is checked, because
nothing about the sender is relevant -- an imported bundle is re-verified
against archive.org on the importing machine, record by record, exactly as the
machine's own output is. A bundle from a stranger and a bundle from the author
are treated identically, which is the property that makes this safe to accept
from anyone and the reason there is no signature scheme here. A signature would
prove who sent it; the archive proves whether it is true, which is the question
that matters.

What arrives unverifiable stays out, and is reported rather than dropped
quietly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from groundtruth.archive import Archive
from groundtruth.contribute import make_bundle, merge_bundle, verify_bundle
from groundtruth.disputes import CONTRIBUTIONS, load_claims, load_contributions


def do_export(args: argparse.Namespace) -> int:
    """Package local readings for somebody else."""
    claims = load_contributions() if args.mine_only else (
        load_claims() + load_contributions())
    if args.place:
        want = args.place.lower()
        claims = [c for c in claims
                  if want in str(c.record.get("place") or "").lower()]
    records = [c.record for c in claims]
    if not records:
        print("nothing to export")
        return 1

    bundle = make_bundle(records, contributor=args.who, note=args.note)
    Path(args.out).write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(records)} readings from {len(bundle['identifiers'])} documents "
          f"-> {args.out}")
    print(f"bundle id {bundle['bundle_id']}")
    print("\nWhoever imports this will re-check every record against the scans "
          "it cites.\nNothing about you travels with it, and nothing needs to.")
    return 0


def do_import(args: argparse.Namespace) -> int:
    """Take somebody else's readings, after asking the archive about them."""
    bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    print(f"bundle {bundle.get('bundle_id','?')} from "
          f"{bundle.get('contributor','anonymous')!r}: "
          f"{bundle.get('n_records', 0)} readings")
    if bundle.get("note"):
        print(f"  note: {bundle['note'][:160]}")

    print("\nchecking every record against the pages it cites...")
    verdict = verify_bundle(bundle, archive=Archive())
    print(f"  verified   {verdict.verified}")
    print(f"  failed     {len(verdict.failed)}")
    print(f"  unchecked  {len(verdict.unchecked)}")
    for f in verdict.failed[:6]:
        print(f"    {f.get('why','')[:70]}: {str(f.get('quote',''))[:56]!r}")

    if not verdict.accepted and not args.verified_only:
        print("\nNot merged. Some records are not supported by the pages they cite.")
        print("Re-run with --verified-only to take the ones that are; the rest stay")
        print("out, listed above, which is a visible gap rather than a silent one.")
        return 1

    if not verdict.accepted:
        # Taking the verified subset is safe HERE and would not be in a system
        # that hid the difference. Every record's standing is individually known,
        # and the dispute ledger has a state for "unsupported", so what is left
        # behind is a reported absence rather than a quiet loss. Discarding 115
        # good readings to punish 4 unverifiable ones is the worse trade -- and
        # one of those four is "Just over three million gallons", a real number
        # written in words, which is a limit of the check rather than a fault in
        # the reading.
        failed = {(f.get("identifier"), f.get("page"), f.get("quote"),
                   repr(f.get("value"))) for f in verdict.failed}
        keep = []
        for r in bundle.get("records") or []:
            prov = r.get("provenance") or {}
            key = (prov.get("identifier"), prov.get("page"),
                   (prov.get("source_text") or "")[:120], repr(r.get("value")))
            if key not in failed:
                keep.append(r)
        bundle = dict(bundle, records=keep, n_records=len(keep))
        print(f"\ntaking {len(keep)} verified readings; {len(verdict.failed)} left "
              "out and listed above")

    if args.dry_run:
        print("\nWould merge. Re-run without --dry-run.")
        return 0

    out = merge_bundle(bundle, into=args.into, verdict=verdict)
    print(f"\nmerged {out.get('added', verdict.verified)} readings into {args.into}")
    print("They are now on the same footing as everything read locally.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("export", help="package readings as a file")
    ex.add_argument("--out", default="readings.bundle.json")
    ex.add_argument("--place", default="", help="only this place")
    ex.add_argument("--who", default="anonymous", help="a label, not a credential")
    ex.add_argument("--note", default="")
    ex.add_argument("--mine-only", action="store_true",
                    help="only readings submitted here, not the machine's own")
    ex.set_defaults(func=do_export)

    im = sub.add_parser("import", help="check and merge somebody else's file")
    im.add_argument("bundle")
    im.add_argument("--into", default="data/results")
    im.add_argument("--dry-run", action="store_true")
    im.add_argument("--verified-only", action="store_true",
                    help="merge the records the archive supports, leave the rest")
    im.set_defaults(func=do_import)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
