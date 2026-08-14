"""Asking for a place nobody has read.

This is the loop the project is built around: nobody pre-processes the archive,
somebody asks, the machine in front of them reads, and the answer is there for
everyone afterwards. The portal did not have it -- it browsed a corpus built by
a batch script, which is why an unread town looked like an empty state instead
of the normal one.

The endpoint shipped broken once with 792 tests passing, because nothing here
called it. These tests call it.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from concordance.reading import ReadJob, Reader


class _Answer(SimpleNamespace):
    pass


def _ask_ok(place, **kw):
    say = kw.get("on_progress") or (lambda _m: None)
    say(f"Nobody has read {place} yet. 3 documents to work through.")
    say("[1/3] 1969: 4 pages worth reading")
    return _Answer(records=[{"v": 1}, {"v": 2}], documents=3, note="")


def _ask_empty(place, **kw):
    return _Answer(records=[], documents=2, note="No measurements in them.")


def _ask_boom(place, **kw):
    raise RuntimeError("ollama is not running")


def _settle(reader: Reader, timeout: float = 5.0) -> ReadJob:
    end = time.time() + timeout
    while time.time() < end:
        job = reader.current
        if job and job.state != "running":
            return job
        time.sleep(0.01)
    raise AssertionError("job never finished")


def test_a_read_reports_what_it_found() -> None:
    reader = Reader()
    started, _job = reader.start("Orillia", ask=_ask_ok)
    assert started
    job = _settle(reader)
    assert job.state == "done"
    assert job.records == 2 and job.documents == 3
    assert any("Nobody has read Orillia" in line for line in job.log)


def test_reading_and_finding_nothing_is_not_success() -> None:
    """"We read the documents and there were no measurements in them" is a
    real answer and must not be dressed as a successful read."""
    reader = Reader()
    reader.start("Nowhere", ask=_ask_empty)
    job = _settle(reader)
    assert job.state == "nothing"
    assert job.records == 0
    assert "No measurements" in job.note


def test_a_failed_read_says_so_instead_of_hanging() -> None:
    reader = Reader()
    reader.start("Anywhere", ask=_ask_boom)
    job = _settle(reader)
    assert job.state == "error"
    assert "ollama" in job.error


def test_one_job_at_a_time_because_there_is_one_graphics_card() -> None:
    """A second request is refused WITH the running job, so the caller can show
    its progress rather than a bare rejection."""
    reader = Reader()
    slow = lambda place, **kw: (time.sleep(0.3), _Answer(records=[1], documents=1))[1]
    started, first = reader.start("First", ask=slow)
    assert started
    started2, running = reader.start("Second", ask=_ask_ok)
    assert not started2
    assert running is first and running.place == "First"
    _settle(reader)


def test_the_log_is_bounded(monkeypatch) -> None:
    """A long read is chatty; the first line says what was found to read and the
    last lines are where the work is."""
    job = ReadJob(place="X")
    job.say("first line")
    for i in range(200):
        job.say(f"page {i}")
    assert len(job.log) <= ReadJob.MAX_LOG
    assert job.log[0] == "first line"
    assert "page 199" in job.log[-1]


def test_only_the_local_instance_will_read(monkeypatch) -> None:
    """Reading is hours of local model time. A shared instance must refuse, and
    it refuses server-side rather than by hiding a button."""
    import concordance.server as server

    handler = server.Handler.__new__(server.Handler)
    handler._direct_peer = lambda: "203.0.113.7"
    monkeypatch.delenv("CONCORDANCE_PUBLIC_HOSTS", raising=False)
    assert not handler._is_local_instance()

    handler._direct_peer = lambda: "127.0.0.1"
    assert handler._is_local_instance()

    # A proxied public deployment must not be talked into enabling it.
    monkeypatch.setenv("CONCORDANCE_PUBLIC_HOSTS", "concordance.example.org")
    assert not handler._is_local_instance()


def test_the_read_endpoints_are_post_only() -> None:
    import concordance.server as server

    assert "/api/read" in server.POST_ONLY_ENDPOINTS
    assert "/api/read/status" in server.POST_ONLY_ENDPOINTS
