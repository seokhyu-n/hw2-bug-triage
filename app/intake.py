"""Background analysis of queued reports.

The public intake saves a report first and answers with a receipt number at once; this worker
then runs the 4-step analysis, assigns a developer and moves the report into that developer's
list. Temporary failures (API down, timeouts) are retried with a delay; a report that still
fails stays in the queue as `failed`, visible to the fallback developer, who can retry it.
"""
import logging
import queue
import threading
import time

from app.auth import DEFAULT_DEV, assign_developer
from app.llm import LLMError, LLMRefusal, LLMTruncated
from app.pipeline import analyze
from app.store import Store

log = logging.getLogger(__name__)

# Seconds to wait before the 2nd and 3rd attempt (the SDK already retries single requests).
RETRY_DELAYS = (5, 30)
# Developer who sees reports that could not be analyzed (same fallback as unassignable reports).
FAILED_OWNER = DEFAULT_DEV


def _error_message(exc: Exception) -> str:
    if isinstance(exc, (LLMRefusal, LLMTruncated)):
        return "모델이 이 제보를 처리하지 못했습니다."
    if isinstance(exc, LLMError):
        return "분석 서비스 오류 (API 연결 실패 또는 응답 오류)"
    return "분석 중 예기치 않은 오류"


def _retryable(exc: Exception) -> bool:
    # A refusal or truncation repeats with the same input; only transient errors are retried.
    return not isinstance(exc, (LLMRefusal, LLMTruncated))


class IntakeWorker:
    """One background thread processing queued report IDs in order.

    With `sync=True` (tests), `submit` runs the analysis inline and `retry_delays` are not slept.
    """

    def __init__(self, store: Store, sync: bool = False, retry_delays=RETRY_DELAYS):
        self.store = store
        self.sync = sync
        self.retry_delays = tuple(retry_delays)
        self._jobs: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the thread and resume reports left `pending` (e.g. the server stopped mid-analysis)."""
        if self.sync or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="intake-worker", daemon=True)
        self._thread.start()
        for r in self.store.queued(status="pending"):
            self._jobs.put(r["request_id"])

    def submit(self, request_id: str) -> None:
        if self.sync:
            self.process(request_id)
        else:
            self._jobs.put(request_id)

    def _run(self) -> None:
        while True:
            rid = self._jobs.get()
            try:
                self.process(rid)
            except Exception:  # noqa: BLE001 - keep the worker alive for the next report
                log.exception("intake worker crashed on %s", rid)

    def process(self, request_id: str) -> bool:
        """Analyze one queued report. Returns True when it reached a developer's list."""
        entry = self.store.get_queued(request_id)
        if entry is None:  # already processed
            return True
        self.store.set_queue_status(request_id, "pending")
        attempts = len(self.retry_delays) + 1
        for attempt in range(attempts):
            try:
                result, logs = analyze(entry["text"], images=self.store.images(entry))
            except Exception as exc:  # noqa: BLE001 - every failure is recorded on the report
                last = attempt == attempts - 1 or not _retryable(exc)
                self.store.set_queue_status(request_id, "failed" if last else "pending",
                                            _error_message(exc), count_attempt=True)
                log.warning("analysis failed for %s (attempt %d): %s", request_id, attempt + 1,
                            type(exc).__name__)
                if last:
                    return False
                if not self.sync:
                    time.sleep(self.retry_delays[attempt])
                continue
            self.store.complete(request_id, assign_developer(result.extraction.feature_area), result, logs)
            return True
        return False
