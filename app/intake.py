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
from app.report_form import log_tail
from app.schemas import TriageResult
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
            self._jobs.put(("intake", r["request_id"]))
        for dev_id, rid, index in self.store.pending_replies():
            self._jobs.put(("reply", dev_id, rid, index))

    def submit(self, request_id: str) -> None:
        self._enqueue(("intake", request_id))

    def submit_reply(self, dev_id: str, request_id: str, index: int) -> None:
        """Re-analyze an assigned report with the reporter's answer (reply `index`)."""
        self._enqueue(("reply", dev_id, request_id, index))

    def _enqueue(self, job: tuple) -> None:
        if self.sync:
            self._dispatch(job)
        else:
            self._jobs.put(job)

    def _dispatch(self, job: tuple) -> bool:
        if job[0] == "reply":
            return self.process_reply(*job[1:])
        return self.process(job[1])

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            try:
                self._dispatch(job)
            except Exception:  # noqa: BLE001 - keep the worker alive for the next report
                log.exception("intake worker crashed on %s", job[:3])

    def _with_retries(self, request_id: str, run, on_error) -> tuple | None:
        """Call run() up to len(retry_delays)+1 times; on_error(exc, is_last) after each failure."""
        attempts = len(self.retry_delays) + 1
        for attempt in range(attempts):
            try:
                return run()
            except Exception as exc:  # noqa: BLE001 - every failure is recorded on the report
                last = attempt == attempts - 1 or not _retryable(exc)
                on_error(exc, last)
                log.warning("analysis failed for %s (attempt %d): %s", request_id, attempt + 1,
                            type(exc).__name__)
                if last:
                    return None
                if not self.sync:
                    time.sleep(self.retry_delays[attempt])
        return None

    def process(self, request_id: str) -> bool:
        """Analyze one queued report. Returns True when it reached a developer's list."""
        entry = self.store.get_queued(request_id)
        if entry is None:  # already processed
            return True
        self.store.set_queue_status(request_id, "pending")
        out = self._with_retries(
            request_id,
            lambda: analyze(entry["text"], images=self.store.images(entry),
                            log=log_tail(self.store.log_text(entry))),
            lambda exc, last: self.store.set_queue_status(request_id, "failed" if last else "pending",
                                                          _error_message(exc), count_attempt=True))
        if out is None:
            return False
        result, logs = out
        self.store.complete(request_id, assign_developer(result.extraction.feature_area), result, logs)
        return True

    def process_reply(self, dev_id: str, request_id: str, index: int) -> bool:
        """Re-analysis with the reporter's answer: confirmed fields + only the new text (like a
        developer's re-analysis). The answer itself is already saved, so a failure loses nothing."""
        record = self.store.get_report(dev_id, request_id)
        if record is None:
            return False
        reply = record["replies"][index]["text"]
        out = self._with_retries(
            request_id,
            lambda: analyze(record["text"], prior=TriageResult.model_validate(record["result"]),
                            added_info=reply),
            lambda exc, last: last and self.store.set_reply_state(dev_id, request_id, index, "failed"))
        if out is None:
            return False
        result, logs = out
        self.store.apply_reply(dev_id, request_id, index, result, logs)
        return True
