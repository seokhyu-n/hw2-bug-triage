"""Intake queue: save first, analyze in the background, retry, never lose a report."""
import threading

import app.intake as intake
from app.intake import IntakeWorker
from app.llm import LLMTruncated, LLMUnavailable
from app.store import INTAKE_DIR, Store
from tests.test_store import make_log, make_result


def ok(text, **kw):
    return make_result(), [make_log()]


def test_enqueue_saves_pending_and_shares_id_sequence(tmp_path):
    store = Store(tmp_path)
    assert store.create_report("dev1", "a", make_result(), []) == "R-0001"
    assert store.enqueue("b")[0] == "R-0002"
    assert store.create_report("dev1", "c", make_result(), []) == "R-0003"
    entry = store.get_queued("R-0002")
    assert entry["status"] == "pending" and entry["attempts"] == 0 and entry["text"] == "b"
    # the queue is on disk, so it survives a restart
    assert Store(tmp_path).get_queued("R-0002")["text"] == "b"


def test_complete_moves_report_keeping_id_and_created_at(tmp_path):
    store = Store(tmp_path)
    rid = store.enqueue("지도 오류")[0]
    created = store.get_queued(rid)["created_at"]
    store.complete(rid, "dev2", make_result(), [make_log()])
    assert store.queued() == []
    rec = store.get_report("dev2", rid)
    assert rec["text"] == "지도 오류" and rec["created_at"] == created
    assert rec["logs_summary"]["cost_usd"] == 0.001
    assert (tmp_path / "logs.jsonl").read_text(encoding="utf-8").count(rid) == 1


def test_worker_assigns_by_feature_area(tmp_path, monkeypatch):
    store = Store(tmp_path)
    monkeypatch.setattr(intake, "analyze", ok)
    rid = store.enqueue("지도가 안 열려요")[0]
    assert IntakeWorker(store, sync=True).process(rid) is True
    # make_result() has feature_area "map" -> dev2 in data/developers.json
    assert store.get_report("dev2", rid) is not None


def test_worker_retries_transient_error_then_succeeds(tmp_path, monkeypatch):
    store = Store(tmp_path)
    results = [LLMUnavailable("down"), ok("x")]

    def flaky(text, **kw):
        item = results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    monkeypatch.setattr(intake, "analyze", flaky)
    rid = store.enqueue("제보")[0]
    assert IntakeWorker(store, sync=True).process(rid) is True
    assert store.queued() == [] and results == []


def test_worker_does_not_retry_truncation(tmp_path, monkeypatch):
    store = Store(tmp_path)
    calls = []

    def truncated(text, **kw):
        calls.append(1)
        raise LLMTruncated("x")
    monkeypatch.setattr(intake, "analyze", truncated)
    rid = store.enqueue("제보")[0]
    assert IntakeWorker(store, sync=True).process(rid) is False
    assert len(calls) == 1 and store.get_queued(rid)["status"] == "failed"


def test_unexpected_exception_is_recorded_not_raised(tmp_path, monkeypatch):
    store = Store(tmp_path)

    def bug(text, **kw):
        raise ValueError("secret detail")
    monkeypatch.setattr(intake, "analyze", bug)
    rid = store.enqueue("제보")[0]
    assert IntakeWorker(store, sync=True, retry_delays=()).process(rid) is False
    entry = store.get_queued(rid)
    assert entry["status"] == "failed" and "secret" not in entry["last_error"]


def test_background_worker_resumes_pending_on_start(tmp_path, monkeypatch):
    store = Store(tmp_path)
    pending = store.enqueue("서버가 멈춘 사이 남은 제보")[0]
    failed = store.enqueue("이미 실패한 제보")[0]
    store.set_queue_status(failed, "failed", "x", count_attempt=True)
    done = threading.Event()

    def analyzed(text, **kw):
        done.set()
        return ok(text)
    monkeypatch.setattr(intake, "analyze", analyzed)
    IntakeWorker(store, retry_delays=()).start()
    assert done.wait(5)
    for _ in range(100):  # complete() runs right after analyze() returns
        if store.get_queued(pending) is None:
            break
        threading.Event().wait(0.05)
    assert store.get_queued(pending) is None
    # failed reports wait for a developer's retry instead of being retried forever
    assert store.get_queued(failed)["status"] == "failed"


def test_queue_dir_is_not_a_developer(tmp_path):
    from app.auth import load_developers
    assert INTAKE_DIR not in load_developers()
