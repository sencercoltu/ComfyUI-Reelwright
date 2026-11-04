"""Per-project locks and the jobs running for a project (added 2026-11-03 v0.6.0).

ComfyUI runs the node (renders, the merge after a render) on its execution thread while the HTTP routes (autosave,
star, delete, merge, Files) run on the event loop or in worker threads. Every read-modify-write of a project's files
(index.json, project.json, cut numbering) holds the project's lock, and long jobs register themselves so the Files tab
can refuse to delete what a render or merge is using, and so a merge can be cancelled.

Pure Python, no ComfyUI imports.
"""

import contextlib
import itertools
import threading
import time

_guard = threading.Lock()
_locks = {}      # slug -> RLock
_running = {}    # job id -> Job
_ids = itertools.count(1)


def lock(slug):
    """The project's re-entrant lock. Hold it around any read-modify-write of the project's files."""
    with _guard:
        lk = _locks.get(slug)
        if lk is None:
            lk = _locks[slug] = threading.RLock()
        return lk


class Cancelled(RuntimeError):
    """Raised inside a job after cancel(); the job stops and cleans up."""


class Job:
    def __init__(self, slug, kind, job_id=None):
        self.id = job_id or "{}-{}".format(kind, next(_ids))
        self.slug = slug
        self.kind = kind            # "render" | "merge" | anything else
        self.started = time.time()
        self.progress = 0.0
        self.cancelled = threading.Event()

    def check(self):
        """Raise Cancelled when the job was cancelled."""
        if self.cancelled.is_set():
            raise Cancelled("{} cancelled".format(self.kind))


@contextlib.contextmanager
def running(slug, kind, job_id=None):
    """Register a job for the duration of the block: `with jobs.running(slug, "merge") as job: ...`."""
    job = Job(slug, kind, job_id)
    with _guard:
        _running[job.id] = job
    try:
        yield job
    finally:
        with _guard:
            _running.pop(job.id, None)


class Busy(RuntimeError):
    """added 2026-11-03 v0.6.0: exclusive() found a job of the same kind already running for the project."""

    def __init__(self, job):
        super().__init__("a {} of this project is already running".format(job.kind))
        self.job = job


@contextlib.contextmanager
def exclusive(slug, kind, job_id=None):
    """added 2026-11-03 v0.6.0: like running(), but only one job of this kind per project: raises Busy when one is
    running already. The check and the registration happen in one step."""
    with _guard:
        other = next((j for j in _running.values() if j.slug == slug and j.kind == kind), None)
        if other is None and job_id and job_id in _running:
            other = _running[job_id]
        if other is not None:
            raise Busy(other)
        job = Job(slug, kind, job_id)
        _running[job.id] = job
    try:
        yield job
    finally:
        with _guard:
            if _running.get(job.id) is job:
                _running.pop(job.id, None)


def busy(slug, kind=None):
    """Jobs of this project that are running now (of one kind, or all)."""
    with _guard:
        return [j for j in _running.values() if j.slug == slug and (kind is None or j.kind == kind)]


def is_busy(slug, kind=None):
    return bool(busy(slug, kind))


def get(job_id):
    with _guard:
        return _running.get(job_id)


def cancel(job_id):
    """Ask a running job to stop. False when no such job is running."""
    job = get(job_id)
    if not job:
        return False
    job.cancelled.set()
    return True
