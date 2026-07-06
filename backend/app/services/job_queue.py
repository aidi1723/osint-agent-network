from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Condition, Thread
from time import monotonic
from typing import Any, Callable

from app.services.worker import run_investigation_jobs


WorkerFunc = Callable[[Any, str], dict]
RECENT_HISTORY_LIMIT = 20
ERROR_EXCERPT_LIMIT = 500


@dataclass
class QueueRequest:
    store: Any
    investigation_id: str
    max_jobs: int | None
    enqueued_at: str


class BackgroundJobQueue:
    def __init__(self, worker_func: Callable[..., dict] = run_investigation_jobs):
        self._worker_func = worker_func
        self._condition = Condition()
        self._pending: deque[QueueRequest] = deque()
        self._running: QueueRequest | None = None
        self._thread: Thread | None = None
        self._recent_runs: deque[dict] = deque(maxlen=RECENT_HISTORY_LIMIT)
        self._recent_errors: deque[dict] = deque(maxlen=RECENT_HISTORY_LIMIT)

    def enqueue(self, store: Any, investigation_id: str, max_jobs: int | None = None) -> dict:
        request = QueueRequest(
            store=store,
            investigation_id=investigation_id,
            max_jobs=max_jobs,
            enqueued_at=_now(),
        )
        with self._condition:
            duplicate_status = self._duplicate_status(investigation_id)
            if duplicate_status:
                return self._response(False, duplicate_status, investigation_id, max_jobs)
            self._pending.append(request)
            self._ensure_thread_locked()
            self._condition.notify_all()
            return self._response(True, "QUEUED", investigation_id, max_jobs)

    def snapshot(self) -> dict:
        with self._condition:
            return self._snapshot_locked()

    def wait_until_idle(self, timeout: float = 5.0) -> bool:
        deadline = monotonic() + timeout
        with self._condition:
            while self._pending or self._running is not None:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(timeout=remaining)
            return True

    def _ensure_thread_locked(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = Thread(target=self._run_loop, name="osint-background-job-queue", daemon=True)
        self._thread.start()

    def _run_loop(self) -> None:
        while True:
            with self._condition:
                if not self._pending:
                    self._thread = None
                    self._condition.notify_all()
                    return
                request = self._pending.popleft()
                self._running = request
                self._condition.notify_all()
            started_at = _now()
            try:
                summary = self._worker_func(request.store, request.investigation_id, max_jobs=request.max_jobs)
                self._record_run(request, started_at, summary)
            except Exception as exc:  # pragma: no cover - exercised by queue error tests
                self._record_error(request, started_at, exc)
            finally:
                with self._condition:
                    self._running = None
                    self._condition.notify_all()

    def _record_run(self, request: QueueRequest, started_at: str, summary: dict) -> None:
        record = {
            "investigation_id": request.investigation_id,
            "max_jobs": request.max_jobs,
            "enqueued_at": request.enqueued_at,
            "started_at": started_at,
            "finished_at": _now(),
            "started": int(summary.get("started") or 0),
            "completed": int(summary.get("completed") or 0),
            "failed": int(summary.get("failed") or 0),
            "blocked": int(summary.get("blocked") or 0),
            "queued_followups": int(summary.get("queued_followups") or 0),
        }
        with self._condition:
            self._recent_runs.appendleft(record)

    def _record_error(self, request: QueueRequest, started_at: str, exc: Exception) -> None:
        error = {
            "investigation_id": request.investigation_id,
            "max_jobs": request.max_jobs,
            "enqueued_at": request.enqueued_at,
            "started_at": started_at,
            "finished_at": _now(),
            "error": _excerpt(str(exc)),
        }
        add_event = getattr(request.store, "add_event", None)
        if callable(add_event):
            try:
                add_event(
                    request.investigation_id,
                    "worker-queue",
                    "error",
                    "后台任务队列执行失败",
                    {"error": error["error"]},
                )
            except Exception:
                pass
        with self._condition:
            self._recent_errors.appendleft(error)

    def _duplicate_status(self, investigation_id: str) -> str:
        if self._running is not None and self._running.investigation_id == investigation_id:
            return "ALREADY_RUNNING"
        if any(item.investigation_id == investigation_id for item in self._pending):
            return "ALREADY_QUEUED"
        return ""

    def _response(self, accepted: bool, status: str, investigation_id: str, max_jobs: int | None) -> dict:
        snapshot = self._snapshot_locked()
        return {
            "accepted": accepted,
            "mode": "background",
            "status": status,
            "investigation_id": investigation_id,
            "max_jobs": max_jobs,
            "queue_depth": snapshot["queue_depth"],
            "running": snapshot["running"],
        }

    def _snapshot_locked(self) -> dict:
        return {
            "mode": "in_process",
            "queue_depth": len(self._pending),
            "running": self._running.investigation_id if self._running is not None else None,
            "pending": [
                {
                    "investigation_id": item.investigation_id,
                    "max_jobs": item.max_jobs,
                    "enqueued_at": item.enqueued_at,
                }
                for item in self._pending
            ],
            "recent_runs": list(self._recent_runs),
            "recent_errors": list(self._recent_errors),
        }


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _excerpt(value: str) -> str:
    if len(value) <= ERROR_EXCERPT_LIMIT:
        return value
    return f"{value[:ERROR_EXCERPT_LIMIT]}...[truncated]"


job_queue = BackgroundJobQueue()
