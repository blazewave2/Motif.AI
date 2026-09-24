"""Compositions as jobs the panel can watch and stop.

Composing with care takes minutes, not seconds, so a request is accepted at
once and worked on in the background: the panel polls for what is
happening — which stage, which bar, what the composer is thinking about —
and can cancel. One job runs at a time; the rest wait their turn.
"""
from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field

KEEP_FINISHED = 30


@dataclass
class Job:
    id: str
    kind: str = "compose"
    state: str = "queued"               # queued | running | done | error | cancelled
    progress: dict = field(default_factory=lambda: {
        "stage": "queued", "label": "Waiting to start", "detail": "", "fraction": 0.0})
    created: float = field(default_factory=time.time)
    started: float = 0.0
    finished: float = 0.0
    payload: dict | None = None
    error: str = ""
    cancel: threading.Event = field(default_factory=threading.Event)

    def view(self) -> dict:
        now = time.time()
        out = {"ok": True, "job_id": self.id, "state": self.state,
               "progress": dict(self.progress),
               "elapsed": round((self.finished or now) - (self.started or now), 1),
               "queued_for": round((self.started or now) - self.created, 1)}
        if self.state == "done" and self.payload is not None:
            out["result"] = self.payload
        if self.state in ("error", "cancelled"):
            out["error"] = self.error
        return out


class JobManager:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._queue: "queue.Queue[tuple[Job, object]]" = queue.Queue()
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._run, name="motif-composer", daemon=True)
        self._worker.start()

    def submit(self, work, kind: str = "compose") -> Job:
        """``work(job)`` runs on the worker thread and returns the result payload."""
        job = Job(id=uuid.uuid4().hex[:16], kind=kind)
        with self._lock:
            self._jobs[job.id] = job
            self._prune()
        self._queue.put((job, work))
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> Job | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.cancel.set()
        if job.state == "queued":
            job.state = "cancelled"
            job.error = "Stopped before it started."
            job.finished = time.time()
        return job

    def wait(self, job: Job, timeout: float | None = None) -> Job:
        end = None if timeout is None else time.time() + timeout
        while job.state in ("queued", "running"):
            if end is not None and time.time() > end:
                break
            time.sleep(0.05)
        return job

    # ------------------------------------------------------------------
    def _run(self) -> None:
        while True:
            job, work = self._queue.get()
            if job.state == "cancelled":
                continue
            job.state = "running"
            job.started = time.time()
            try:
                payload = work(job)
                if job.cancel.is_set():
                    job.state = "cancelled"
                    job.error = "Stopped."
                elif isinstance(payload, dict) and payload.get("ok") is False:
                    job.state = "error"
                    job.error = payload.get("error") or payload.get("message") or "failed"
                    job.payload = payload
                else:
                    job.payload = payload
                    job.state = "done"
            except Exception as exc:                 # never let the worker die
                job.state = "error"
                job.error = f"{type(exc).__name__}: {exc}"
            finally:
                job.finished = time.time()
                job.progress = dict(job.progress, fraction=1.0 if job.state == "done"
                                    else job.progress.get("fraction", 0.0))

    def _prune(self) -> None:
        finished = [j for j in self._jobs.values()
                    if j.state not in ("queued", "running")]
        finished.sort(key=lambda j: j.finished or j.created)
        for j in finished[:-KEEP_FINISHED]:
            self._jobs.pop(j.id, None)
