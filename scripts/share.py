"""Move readings between machines, and re-check them on arrival.

This is the part the distributed model was missing. Supported prose evidence can
be checked against the page it cites without asking who is speaking, but a
contribution written to `data/contributions` on one laptop reached nobody.

The base mechanism is a file.

    python scripts/share.py export --out fergus.bundle.json
    python scripts/share.py import fergus.bundle.json

A bundle can travel by email, USB stick, or a link in a forum post, none of
which need a server anybody has to run, pay for, or be trusted to keep honest.
Whoever wants to publish a set of readings publishes a file.

Handing files to people does not scale, so there is also a shared instance:

    python scripts/share.py push fergus.bundle.json --to https://example.org
    python scripts/share.py pull --frm https://example.org

The instance changes nothing about what is true. It evaluates the cited evidence,
keeps only the supported records, hands back everything it holds, and can be
replaced by anyone who does not like how it is run -- `pull` then
`import --verified-only` reconstructs its supported library locally. A server
that cannot be audited by copying it is a different kind of object than this one.

**Trust does not travel with it.** Nothing about the sender is checked: an
imported bundle's prose evidence is checked against archive.org on the importing
machine. Locator-only table claims abstain without localized cell proof. A bundle
from a stranger and one from the author are treated identically. A signature
would prove who sent it; it would not prove what the cited page supports.

What arrives unverifiable stays out, and is reported rather than dropped
quietly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import urllib.error
import urllib.request

from concordance.archive import Archive
from concordance.contribute import make_bundle, merge_bundle, verify_bundle
from concordance.disputes import CONTRIBUTIONS, load_claims, load_contributions


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
    print("\nWhoever imports this will evaluate each record against the pages "
          "it cites; unsupported evidence stays out.\nNothing about you travels "
          "with it, and nothing needs to.")
    return 0


def do_import(args: argparse.Namespace) -> int:
    """Take somebody else's readings, after asking the archive about them."""
    bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    print(f"bundle {bundle.get('bundle_id','?')} from "
          f"{bundle.get('contributor','anonymous')!r}: "
          f"{bundle.get('n_records', 0)} readings")
    if bundle.get("note"):
        print(f"  note: {bundle['note'][:160]}")

    print("\nchecking each record against the pages it cites...")
    verdict = verify_bundle(bundle, archive=Archive())
    print(f"  verified   {verdict.verified}")
    print(f"  failed     {len(verdict.failed)}")
    print(f"  unchecked  {len(verdict.unchecked)}")
    print(f"  unsupported {len(verdict.unsupported)}")
    for f in (verdict.failed + verdict.unsupported)[:6]:
        print(f"    {f.get('why','')[:70]}: {str(f.get('quote',''))[:56]!r}")

    if not verdict.accepted and not args.verified_only:
        print("\nNot merged. Some records are not supported by the pages they cite.")
        print("Re-run with --verified-only to take the ones that are; the rest stay")
        print("out, listed above, which is a visible gap rather than a silent one.")
        return 1

    if not verdict.accepted:
        # The verifier owns the positive set. Reconstructing it as "everything
        # not failed" once let unsupported records ride in with one genuine
        # record. Preserve only what the archive actually supported.
        keep = list(verdict.supported or [])
        refused = len(verdict.failed) + len(verdict.unsupported)
        bundle = make_bundle(
            keep,
            contributor=str(bundle.get("contributor") or "anonymous"),
            note=str(bundle.get("note") or ""),
        )
        print(f"\ntaking {len(keep)} supported readings; {refused} left out and "
              "listed above")

        # Re-verify what is actually about to be merged, rather than handing
        # merge_bundle the verdict for the bundle this one was cut down from.
        # Passing the old verdict tripped its own gate -- it still carried the
        # failures -- so `import --verified-only` raised ValueError on any
        # bundle with a single unverifiable record, which is every realistic
        # one. The command is documented verbatim in the README.
        #
        # Re-checking rather than hand-building a clean Verdict is the point: it
        # proves the trimmed set passes instead of asserting it, and the pages
        # are cached by now so it costs nothing.
        verdict = verify_bundle(bundle, archive=Archive())
        if not verdict.accepted:
            print("The trimmed bundle still does not verify, which should not "
                  "happen.\nNothing merged.")
            return 1

    if args.dry_run:
        print("\nWould merge. Re-run without --dry-run.")
        return 0

    out = merge_bundle(bundle, into=args.into, verdict=verdict)
    # merge_bundle returns `accepted` and `duplicates_dropped`. There is no
    # `added`, so the old message fell through to verdict.verified and reported
    # "merged 115 readings" for an import that merged none of them -- every one
    # already present under the same record key. A number that counts what was
    # checked and calls it what was stored is exactly the kind of plausible
    # wrong answer this project exists to catch.
    added = out.get("accepted", 0)
    dupes = out.get("duplicates_dropped", 0)
    print(f"\nmerged {added} new reading{'' if added == 1 else 's'} into {args.into}")
    if dupes:
        print(f"{dupes} were already here under the same record key and were not "
              "duplicated.")
    if added:
        print("They are now on the same footing as everything read locally.")
    return 0


def do_push(args: argparse.Namespace) -> int:
    """Send readings to an instance that evaluates each record's evidence.

    The instance is a convenience and not an authority. It holds no key anyone
    else lacks; it simply saves each person from being handed a file. Anything
    it accepts has supporting archive evidence under the current rules; semantic
    interpretation remains open to challenge.
    """
    bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    url = args.to.rstrip("/") + "/api/bundle"
    body = json.dumps(bundle).encode()
    print(f"sending {bundle.get('n_records', 0)} readings to {url}")

    request = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json",
                 "User-Agent": "concordance/0.1"},
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            out = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        print(f"the instance refused it: HTTP {exc.code} {exc.read()[:200]!r}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"could not reach {url}: {type(exc).__name__}: {str(exc)[:120]}")
        print("The bundle is unharmed. Send it to somebody, or try another "
              "instance -- nothing here depends on one server existing.")
        return 1

    print(f"  re-verified there : {out.get('verified', 0)}")
    print(f"  merged            : {out.get('merged', 0)}")
    print(f"  already had       : {out.get('already_here', 0)}")
    print(f"  refused           : {out.get('refused', 0)}")
    for why in out.get("why_refused") or []:
        print(f"      {why}")
    print()
    print(out.get("note", ""))
    return 0 if out.get("accepted") or out.get("already_here") else 1


def do_pull(args: argparse.Namespace) -> int:
    """Take a shared instance's readings, and check them here anyway."""
    url = args.frm.rstrip("/") + "/api/library.json"
    print(f"fetching {url}")
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "concordance/0.1"})
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            bundle = json.loads(response.read().decode())
    except Exception as exc:  # noqa: BLE001
        print(f"could not reach {url}: {type(exc).__name__}: {str(exc)[:120]}")
        return 1

    out = Path(args.out)
    out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{bundle.get('n_records', 0)} readings -> {out}")
    print("Nothing has been trusted yet. Run:")
    print(f"  python scripts/share.py import {out} --verified-only")
    print("which evaluates each record against its cited page here, on your machine.")
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

    ps = sub.add_parser("push", help="send a bundle to a shared instance")
    ps.add_argument("bundle")
    ps.add_argument("--to", default="http://localhost:8765",
                    help="instance URL; it checks supported cited evidence")
    ps.add_argument("--timeout", type=float, default=600.0)
    ps.set_defaults(func=do_push)

    pl = sub.add_parser("pull", help="fetch a shared instance's readings")
    pl.add_argument("--frm", default="http://localhost:8765", metavar="URL")
    pl.add_argument("--out", default="pulled.bundle.json")
    pl.add_argument("--timeout", type=float, default=600.0)
    pl.set_defaults(func=do_pull)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
