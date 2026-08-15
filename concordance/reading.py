"""Reading a place, on demand, on this machine.

This is the loop the whole project is built around and the one the portal did
not have. Nobody pre-processes the archive: somebody asks about a place, the
machine in front of them reads the documents, and the answer accumulates as a
by-product. That is why there is no compute bill, and it is why "we have not
read your town" is the normal state rather than an error.

**Why this refuses to run on a public host.** Reading a town is hours of local
model time. A public instance that started one from a web request would be
handing every visitor a lever on somebody else's GPU, so the endpoint says no
and points at the local reader instead. On your own machine the reader *is*
your machine, and the button works. The distinction is the deployment, not the
code.

One job at a time, because there is one graphics card. A second request is
refused with the state of the first rather than queued, since a queue implies a
promise about when it drains and nothing here can honestly make one.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ReadJob:
    """One place being read, and what it has said so far."""

    place: str
    raw: str = ""
    state: str = "running"          # running | done | error | nothing
    started: float = field(default_factory=time.time)
    finished: float | None = None
    #: The progress lines `library.ask` emits, newest last. Bounded, because a
    #: long read is chatty and nobody reads the middle of it.
    log: list[str] = field(default_factory=list)
    records: int = 0
    documents: int = 0
    note: str = ""
    error: str = ""

    MAX_LOG = 40

    def say(self, message: str) -> None:
        line = str(message).strip()
        if not line:
            return
        self.log.append(line)
        if len(self.log) > self.MAX_LOG:
            # Keep the first line -- it says what was found to read -- and the
            # most recent, which is where the work actually is.
            self.log[:] = self.log[:1] + self.log[-(self.MAX_LOG - 1):]

    @property
    def seconds(self) -> float:
        return (self.finished or time.time()) - self.started

    def to_dict(self) -> dict[str, Any]:
        return {
            "place": self.place, "state": self.state,
            "seconds": round(self.seconds, 1),
            "log": list(self.log), "records": self.records,
            "documents": self.documents, "note": self.note, "error": self.error,
        }


class Reader:
    """The one reading job this machine will run at a time."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._job: ReadJob | None = None
        self._thread: threading.Thread | None = None

    @property
    def current(self) -> ReadJob | None:
        with self._lock:
            return self._job

    def busy(self) -> bool:
        job = self.current
        return bool(job and job.state == "running")

    def start(
        self,
        place: str,
        raw: str = "",
        *,
        ask: Callable[..., Any],
        after: Callable[[], None] | None = None,
        model: str = "gemma4:12b",
    ) -> tuple[bool, ReadJob]:
        """Begin reading, unless something is already being read.

        Returns (started, job). When `started` is False the job returned is the
        one already running, so a caller can show its progress instead of a
        refusal with nothing in it.
        """
        with self._lock:
            if self._job and self._job.state == "running":
                return False, self._job
            job = ReadJob(place=place, raw=raw)
            self._job = job

        def run() -> None:
            try:
                answer = ask(place, read_if_missing=True, model=model,
                             on_progress=job.say)
                # What the LIBRARY now holds, not what the extractor produced.
                # These differed silently: a read that recovered 40 readings
                # and published none (verification failed, nothing written)
                # reported "done -- read 40 measurements", and the publication
                # callback fired for a library that had not changed.
                published = int(getattr(answer, "published", 0) or 0)
                contributed = bool(getattr(answer, "contributed", False))
                job.records = published if contributed else 0
                job.documents = int(getattr(answer, "documents", 0) or 0)
                job.note = str(getattr(answer, "note", "") or "")
                extracted = len(getattr(answer, "records", []) or [])
                if extracted and not contributed:
                    job.note = (job.note + " " if job.note else "") + (
                        f"{extracted} readings were recovered but none survived "
                        "the evidence check; the library is unchanged.")
                # "Read it and found nothing" is a real outcome and must not be
                # dressed as success: it means the documents exist and hold no
                # measurement this reader could recover, which is worth knowing
                # and worth showing.
                job.state = "done" if job.records else "nothing"
                if after and job.records:
                    after()
            except Exception as exc:  # noqa: BLE001
                job.state = "error"
                job.error = f"{type(exc).__name__}: {str(exc)[:200]}"
            finally:
                job.finished = time.time()

        thread = threading.Thread(target=run, name=f"read:{place}", daemon=True)
        with self._lock:
            self._thread = thread
        thread.start()
        return True, job


#: Process-wide, because the constraint is the machine's one graphics card
#: rather than anything about a request.
READER = Reader()
