"""The volunteer loop: ask on the site, read on your machine, publish for all.

This is the sentence the project is built on, made executable end to end:
nobody pre-processes the archive -- somebody asks about a place, the machine in
front of them reads the documents, and everyone who asks afterward gets the
answer. Everything else in this repository exists to make that loop honest.

Three pieces, each tested here:
  * the shared site HANDS OFF an unread town: the refusal to read carries the
    exact per-town command pointed back at the site itself
  * one command on a volunteer's machine reads the town and publishes it
  * asking for a town is counted, once per visitor, and shown to the next one
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import concordance.server as server


def _load_share():
    spec = importlib.util.spec_from_file_location(
        "share", Path(__file__).resolve().parents[1] / "scripts" / "share.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _handler(path, payload, host="concordance.example"):
    handler = object.__new__(server.Handler)
    handler.path = path
    handler.client_address = ("192.0.2.44", 4567)
    handler.headers = {"Host": host, "X-Forwarded-Proto": "https"}
    sent = {}
    handler._send_json = lambda body, status=200, headers=None: sent.update(
        body=body, status=status)
    return handler, sent


# -- the site hands off an unread town ---------------------------------------

def test_the_refusal_to_read_carries_the_handoff_recipe(monkeypatch) -> None:
    """A shared instance will not read for a visitor -- but the refusal now
    hands them everything needed to BE the machine that reads: the one-time
    setup and the exact command for this exact town, pointed back at this
    exact site. Before this, the refusal was a dead end and the project's
    entire loop was unreachable from its own website."""
    monkeypatch.setenv("CONCORDANCE_PUBLIC_HOSTS", "concordance.example")
    handler, sent = _handler("/api/read", {"place": "Fergus", "raw": "Fergus"})
    handler._post_read({"place": "Fergus", "raw": "Fergus"})

    assert sent["status"] == 501
    recipe = sent["body"]["recipe"]
    assert 'share.py read --place "Fergus"' in recipe["command"]
    assert "--to https://concordance.example" in recipe["command"]
    assert any("git clone" in s for s in recipe["setup"])
    assert any("ollama pull" in s for s in recipe["setup"])
    assert "asked" in sent["body"]


# -- one command reads and publishes -----------------------------------------

def test_share_read_reads_then_pushes_to_the_instance(monkeypatch, tmp_path) -> None:
    """python scripts/share.py read --place X --to SITE must do the whole
    volunteer job: read (via library.ask, which verifies and keeps the local
    copy), bundle, and push to the instance -- which re-checks everything on
    arrival. One command, because a volunteer given three commands does one."""
    share = _load_share()

    read_calls = []

    def fake_ask(place, **kw):
        read_calls.append(place)
        # place=None on purpose: the record whose sentence named no town.
        # The bundle must stamp it before it travels, or it arrives at the
        # instance nameless -- how 151 of Ear Falls' 190 records vanished.
        return SimpleNamespace(
            records=[{"kind": "observation", "parameter": "BOD", "value": 1.0,
                      "place": None}],
            source="read now", published=1, contributed=True, note="")

    pushed = {}

    def fake_push(bundle, to, timeout=600.0):
        pushed.update(bundle=bundle, to=to)
        return 0

    import concordance.library as lib
    monkeypatch.setattr(lib, "ask", fake_ask)
    monkeypatch.setattr(share, "push_bundle", fake_push)

    args = SimpleNamespace(place="Fergus", to="https://concordance.example",
                           model="gemma4:12b", who="tester", timeout=600.0)
    assert share.do_read(args) == 0
    assert read_calls == ["Fergus"]
    assert pushed["to"] == "https://concordance.example"
    assert pushed["bundle"]["n_records"] == 1
    assert "Fergus" in pushed["bundle"]["note"]
    assert pushed["bundle"]["records"][0]["place"] == "Fergus", (
        "a nameless record travelled nameless")


def test_share_read_sends_nothing_when_nothing_survived(monkeypatch) -> None:
    """A read whose records all failed their own evidence check must not
    push -- the instance would refuse them anyway, but the volunteer deserves
    the truth from their own machine first."""
    share = _load_share()

    def fake_ask(place, **kw):
        return SimpleNamespace(records=[{"kind": "observation"}],
                               source="read now", published=0,
                               contributed=False, note="")

    def must_not_push(*a, **kw):
        raise AssertionError("pushed records that survived nothing")

    import concordance.library as lib
    monkeypatch.setattr(lib, "ask", fake_ask)
    monkeypatch.setattr(share, "push_bundle", must_not_push)

    args = SimpleNamespace(place="Nowhere", to="https://x.example",
                           model="m", who="t", timeout=1.0)
    assert share.do_read(args) == 1


def test_share_read_without_a_destination_stays_local(monkeypatch) -> None:
    share = _load_share()

    def fake_ask(place, **kw):
        return SimpleNamespace(records=[{"k": 1}], source="read now",
                               published=1, contributed=True, note="")

    import concordance.library as lib
    monkeypatch.setattr(lib, "ask", fake_ask)
    monkeypatch.setattr(share, "push_bundle",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError()))
    args = SimpleNamespace(place="Fergus", to="", model="m", who="t", timeout=1.0)
    assert share.do_read(args) == 0


# -- asking is counted, once per visitor -------------------------------------

def test_a_towns_asks_are_counted_once_per_visitor(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(server, "REQUESTS_FILE", tmp_path / "requests.jsonl")

    assert server._record_request("Fergus", "203.0.113.5") == 1
    assert server._record_request("Fergus", "203.0.113.5") == 1, \
        "one visitor counted twice"
    assert server._record_request("Fergus", "203.0.113.9") == 2
    assert server._record_request("fergus", "203.0.113.9") == 2, \
        "case split one town into two counts"
    assert server._request_count("FERGUS") == 2

    # Nothing about the visitor is stored beyond a non-reversible tag.
    stored = (tmp_path / "requests.jsonl").read_text(encoding="utf-8")
    assert "203.0.113" not in stored


def test_the_request_endpoint_counts_and_reports(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(server, "REQUESTS_FILE", tmp_path / "requests.jsonl")

    class _Allow:
        def check(self, peer):
            return True, 0

    monkeypatch.setattr(server, "MUTATION_RATE_LIMITER", _Allow())
    handler, sent = _handler("/api/request", {"place": "Fergus"})
    handler._post_request({"place": "Fergus"})
    assert sent["body"]["asked"] == 1

    handler2, sent2 = _handler("/api/request", {"place": ""})
    handler2._post_request({"place": ""})
    assert sent2["status"] == 400


# -- the page draws the handoff ----------------------------------------------

def test_the_unread_town_page_renders_the_handoff() -> None:
    page = server.State().html()
    assert "handoffHtml" in page
    assert "I want this town read" in page
    assert "/api/request" in page
    assert 'share.py read' in page or "handoff-cmd" in page


def test_the_library_answers_for_records_that_inherit_their_files_place(
        tmp_path, monkeypatch) -> None:
    """A record with no place of its own belongs to the place its file was
    read for -- every loader applies that rule, and the library query did
    not. The first live re-share of Ear Falls found 35 of its own 190
    records; the 155 spec lines with no place field were invisible to the
    very query that wrote them."""
    import concordance.library as lib

    monkeypatch.setattr(lib, "LIBRARY", tmp_path)
    (tmp_path / "ear-falls.json").write_text(json.dumps({
        "place": "Ear Falls",
        "records": [
            {"kind": "observation", "parameter": "BOD", "value": 1.0,
             "place": "Ear Falls"},
            {"kind": "design", "parameter": "capacity", "value": 2.0,
             "place": None},
        ]}), encoding="utf-8")

    answer = lib.ask("Ear Falls", read_if_missing=False)
    assert len(answer.records) == 2, \
        f"the placeless record is invisible again ({len(answer.records)})"
