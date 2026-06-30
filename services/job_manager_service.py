"""
job_manager_service.py
----------------------
Async Job Manager Service – manages background asyncio tasks.

Features
--------
- submit()        : schedule a coroutine in the background, returns job_id
- job_key lock    : prevents two concurrent jobs sharing the same context key
- TTL / timeout   : auto-releases the job_key and marks the job TIMED_OUT when
                    the coroutine exceeds the configured TTL (seconds)
- get_status()    : poll a running / finished job's metadata by job_id
- get_result()    : retrieve the final result then evict the job from memory
- report_progress : lightweight progress-reporter injected into every coroutine

Usage example
-------------
    from services.job_manager_service import job_manager, ProgressReporter

    # The coroutine you want to run in the background must accept
    # a single positional argument: a ProgressReporter callable.
    async def deploy_lab(progress: ProgressReporter):
        await progress(10, "Uploading topology …")
        # … heavy work …
        await progress(90, "Starting nodes …")
        return {"lab_id": "abc123"}

    job_id = await job_manager.submit(
        deploy_lab,
        job_key="deploy:lab:my-lab",   # duplicate guard key
        ttl=300,                        # 5-minute timeout
    )

    # Poll status …
    status = job_manager.get_status(job_id)
    print(status.status, status.progress)

    # When done, retrieve result (evicts from memory automatically)
    if status.is_done:
        result = job_manager.get_result(job_id)
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional

_logger = logging.getLogger("eve_mcp")

# ---------------------------------------------------------------------------
# Public type aliases
# ---------------------------------------------------------------------------

#: Signature of the progress-reporter callable injected into every coroutine.
#: ``await reporter(percent, message)``
ProgressReporter = Callable[[int, str], Awaitable[None]]

#: Signature of the user-supplied coroutine factory.
#: ``async def my_task(progress: ProgressReporter) -> Any: …``
JobCoroutine = Callable[[ProgressReporter], Awaitable[Any]]


# ---------------------------------------------------------------------------
# Enums & data-classes
# ---------------------------------------------------------------------------


class JobStatus(str, Enum):
    """Lifecycle states of a managed job."""

    PENDING   = "pending"    # submitted, not yet started by the event loop
    RUNNING   = "running"    # coroutine is executing
    COMPLETED = "completed"  # coroutine returned a value
    FAILED    = "failed"     # coroutine raised an exception
    TIMED_OUT = "timed_out" # exceeded TTL
    CANCELLED = "cancelled" # cancelled gracefully via cancel()


@dataclass
class ProgressSnapshot:
    """Immutable snapshot of a single progress report."""

    percent: int   # 0-100
    message: str
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class JobInfo:
    """All metadata and runtime state of a single job."""

    job_id: str
    job_key: str
    status: JobStatus = JobStatus.PENDING
    ttl: float = 300.0

    # Timing (monotonic clock)
    created_at: float = field(default_factory=time.monotonic)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    # Latest progress snapshot (None until the first report_progress call)
    progress: Optional[ProgressSnapshot] = None

    # Outcome (set when status is COMPLETED or FAILED)
    result: Any = None
    error: Optional[str] = None

    # Internal asyncio task handle – not exposed to callers
    _task: Optional[asyncio.Task] = field(default=None, repr=False)
    # Set to True by cancel() so _run() knows to use CANCELLED instead of FAILED
    _cancel_requested: bool = field(default=False, repr=False)

    # ------------------------------------------------------------------
    @property
    def is_done(self) -> bool:
        """True once the job has reached a terminal state."""
        return self.status in (
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.TIMED_OUT,
            JobStatus.CANCELLED,
        )

    @property
    def elapsed(self) -> float:
        """Seconds elapsed since the job was created (monotonic)."""
        return time.monotonic() - self.created_at

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-safe dict (safe to return to MCP callers)."""
        return {
            "job_id": self.job_id,
            "job_key": self.job_key,
            "status": self.status.value,
            "ttl": self.ttl,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": round(self.elapsed, 2),
            "progress": (
                {
                    "percent": self.progress.percent,
                    "message": self.progress.message,
                    "timestamp": self.progress.timestamp,
                }
                if self.progress
                else None
            ),
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# JobManager
# ---------------------------------------------------------------------------


class JobManager:
    """
    Async job manager built on :mod:`asyncio`.

    Thread / event-loop safety
    --------------------------
    All public methods are safe to call from within a **single asyncio event
    loop**.  ``submit()`` is a coroutine and must be awaited.  All other
    read/query methods are synchronous and non-blocking.

    Memory management
    -----------------
    Finished jobs stay in memory until ``get_result()`` or ``evict()`` is
    called.  On error / timeout the ``job_key`` slot is released automatically
    so a retry can be submitted without manual cleanup.
    """

    def __init__(self) -> None:
        # job_id  → JobInfo
        self._jobs: Dict[str, JobInfo] = {}
        # job_key → job_id  (only active / in-flight jobs)
        self._key_index: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def submit(
        self,
        coro_factory: JobCoroutine,
        *,
        job_key: str,
        ttl: float = 300.0,
    ) -> str:
        """
        Schedule *coro_factory* as a background asyncio task.

        Parameters
        ----------
        coro_factory:
            An ``async def`` callable that accepts exactly one positional
            argument – a :data:`ProgressReporter` coroutine-function – and
            returns any value.
        job_key:
            Opaque string that uniquely identifies the *context* of the job
            (e.g. ``"deploy:lab:my-lab"``).  Submitting a second job with the
            same key while the first is still active raises
            :exc:`DuplicateJobError`.
        ttl:
            Maximum seconds the coroutine may run before it is cancelled and
            the job is marked :attr:`JobStatus.TIMED_OUT`.

        Returns
        -------
        str
            The ``job_id`` of the newly created job.

        Raises
        ------
        DuplicateJobError
            An active job already holds *job_key*.
        """
        if job_key in self._key_index:
            existing_id = self._key_index[job_key]
            raise DuplicateJobError(
                f"A job with key '{job_key}' is already active "
                f"(job_id={existing_id!r})."
            )

        job_id = str(uuid.uuid4())
        info = JobInfo(job_id=job_id, job_key=job_key, ttl=ttl)
        self._jobs[job_id] = info
        self._key_index[job_key] = job_id

        # Fire-and-forget asyncio Task
        task = asyncio.create_task(
            self._run(job_id, coro_factory),
            name=f"job:{job_key}:{job_id[:8]}",
        )
        info._task = task

        _logger.info(
            "Job submitted  job_id=%s  job_key=%r  ttl=%.0fs",
            job_id,
            job_key,
            ttl,
        )
        return job_id

    # ------------------------------------------------------------------

    def get_status(self, job_id: str) -> JobInfo:
        """
        Return the live :class:`JobInfo` for *job_id*.

        Raises
        ------
        JobNotFoundError
            Unknown or already-evicted job id.
        """
        info = self._jobs.get(job_id)
        if info is None:
            raise JobNotFoundError(f"Job '{job_id}' not found.")
        return info

    # ------------------------------------------------------------------

    def get_result(self, job_id: str) -> Any:
        """
        Retrieve the final result of a **completed** job and evict it.

        Calling this method on a finished job releases all memory associated
        with it.  If you only want to inspect the outcome without eviction use
        ``get_status()`` and read ``info.result`` directly.

        Raises
        ------
        JobNotFoundError
            Unknown or already-evicted job id.
        JobNotDoneError
            The job is still running or pending.
        JobFailedError
            The job finished with an unhandled exception.
        JobTimedOutError
            The job exceeded its TTL.
        """
        info = self.get_status(job_id)

        if not info.is_done:
            raise JobNotDoneError(
                f"Job '{job_id}' is still {info.status.value}."
            )
        if info.status == JobStatus.TIMED_OUT:
            self.evict(job_id)
            raise JobTimedOutError(
                f"Job '{job_id}' timed out after {info.ttl:.0f}s."
            )
        if info.status == JobStatus.FAILED:
            self.evict(job_id)
            raise JobFailedError(
                f"Job '{job_id}' failed: {info.error}"
            )
        if info.status == JobStatus.CANCELLED:
            self.evict(job_id)
            raise JobCancelledError(
                f"Job '{job_id}' was cancelled."
            )

        result = info.result
        self.evict(job_id)
        return result

    # ------------------------------------------------------------------

    def evict(self, job_id: str) -> None:
        """
        Remove *job_id* from the registry unconditionally.

        If the underlying asyncio task is still running it is cancelled first.
        The ``job_key`` slot is also freed so a new job can reuse the same key.
        """
        info = self._jobs.pop(job_id, None)
        if info is None:
            return
        self._key_index.pop(info.job_key, None)
        if info._task and not info._task.done():
            info._task.cancel()
        _logger.debug(
            "Job evicted  job_id=%s  job_key=%r", job_id, info.job_key
        )

    # ------------------------------------------------------------------

    def list_jobs(self) -> Dict[str, Dict[str, Any]]:
        """Return a serialisable summary of every tracked job."""
        return {jid: info.to_dict() for jid, info in self._jobs.items()}

    # ------------------------------------------------------------------

    def cancel(self, job_id: str) -> bool:
        """
        Request graceful cancellation of a job.

        Unlike :meth:`evict`, ``cancel()`` **keeps the job in the registry**
        so callers can still read its final status via :meth:`get_status`
        after the cancellation has been processed.  The ``job_key`` is
        released immediately so a new job with the same key can be submitted
        right away.

        Parameters
        ----------
        job_id:
            ID of the job to cancel.

        Returns
        -------
        bool
            ``True``  – cancellation signal sent (job was PENDING or RUNNING).
            ``False`` – job was already in a terminal state; no action taken.

        Raises
        ------
        JobNotFoundError
            Unknown job id.
        """
        info = self.get_status(job_id)
        if info.is_done:
            return False
        info._cancel_requested = True
        # Release key immediately so a retry can be submitted right away
        self._key_index.pop(info.job_key, None)
        if info._task and not info._task.done():
            info._task.cancel()
        _logger.info(
            "Job cancel requested  job_id=%s  job_key=%r",
            job_id,
            info.job_key,
        )
        return True

    # ------------------------------------------------------------------
    # Internal async runner
    # ------------------------------------------------------------------

    async def _run(self, job_id: str, coro_factory: JobCoroutine) -> None:
        """
        Wrap the user coroutine with timeout enforcement and status bookkeeping.

        The ``job_key`` is removed from the active-key index whenever the job
        reaches a terminal state due to error or timeout so that a retry can
        be submitted immediately.
        """
        info = self._jobs[job_id]
        info.status = JobStatus.RUNNING
        info.started_at = time.monotonic()

        # -------------------------------------------------------------------
        # Progress reporter – closed over `info` so it writes directly into
        # the live JobInfo object tracked by the registry.
        # -------------------------------------------------------------------
        async def _reporter(percent: int, message: str = "") -> None:
            snap = ProgressSnapshot(
                percent=max(0, min(100, percent)),
                message=message,
            )
            info.progress = snap
            _logger.debug(
                "Job progress  job_id=%s  %d%%  %s",
                job_id,
                snap.percent,
                message,
            )

        # -------------------------------------------------------------------
        try:
            result = await asyncio.wait_for(
                coro_factory(_reporter),
                timeout=info.ttl,
            )
            info.result = result
            info.status = JobStatus.COMPLETED
            _logger.info(
                "Job completed  job_id=%s  elapsed=%.2fs",
                job_id,
                info.elapsed,
            )

        except asyncio.TimeoutError:
            info.status = JobStatus.TIMED_OUT
            info.error = f"Timed out after {info.ttl:.0f}s"
            _logger.warning(
                "Job timed out  job_id=%s  ttl=%.0fs", job_id, info.ttl
            )
            # Release key → retry is now possible
            self._key_index.pop(info.job_key, None)

        except asyncio.CancelledError:
            if info._cancel_requested:
                # Graceful cancel via cancel() – keep job in registry as CANCELLED
                info.status = JobStatus.CANCELLED
                _logger.info("Job cancelled  job_id=%s", job_id)
            else:
                # Hard evict() while running – job already removed from registry
                info.status = JobStatus.FAILED
                info.error = "Job was force-evicted while running."
                _logger.warning("Job force-evicted  job_id=%s", job_id)
            self._key_index.pop(info.job_key, None)  # safe double-pop
            raise  # must re-raise so asyncio cleans up the Task properly

        except Exception as exc:  # noqa: BLE001
            info.status = JobStatus.FAILED
            info.error = f"{type(exc).__name__}: {exc}"
            _logger.exception("Job failed  job_id=%s", job_id)
            # Release key → retry is now possible
            self._key_index.pop(info.job_key, None)

        finally:
            info.completed_at = time.monotonic()


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class JobManagerError(Exception):
    """Base class for all job-manager errors."""


class DuplicateJobError(JobManagerError):
    """Raised when a second job is submitted with an already-active job_key."""


class JobNotFoundError(JobManagerError):
    """Raised when a job_id is not present in the registry."""


class JobNotDoneError(JobManagerError):
    """Raised by get_result() when the job is still running or pending."""


class JobFailedError(JobManagerError):
    """Raised by get_result() when the job finished with an unhandled exception."""


class JobTimedOutError(JobManagerError):
    """Raised by get_result() when the job exceeded its TTL."""


class JobCancelledError(JobManagerError):
    """Raised by get_result() when the job was cancelled via cancel()."""


# ---------------------------------------------------------------------------
# Module-level singleton  (import and use directly)
# ---------------------------------------------------------------------------

#: Shared default instance – import this in service / controller modules.
job_manager: JobManager = JobManager()
