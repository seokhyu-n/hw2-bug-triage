import json

from app.llm import Usage
from app.pipeline import StepLog
from app.schemas import (Classification, Extraction, Link, Score, TriageResult)
from app.store import Store


def make_result(priority="P3", category="bug") -> TriageResult:
    return TriageResult(
        extraction=Extraction(device_model=None, android_version=None, app_version=None,
                              feature_area="map", symptom="앱 종료", expected=None, actual=None,
                              frequency=None, repro_steps=[], missing_fields=[]),
        classification=Classification(category=category, labels=[category], reason="r"),
        link=Link(linked_issue_id=None, match_reason=None, fixed_in=None, user_should_update=None),
        score=Score(reasoning="r", completeness=1, priority=priority, questions_to_reporter=[]),
        answer_status="ready",
    )


def make_log(step="extract") -> StepLog:
    return StepLog(step=step, model="claude-haiku-5-5", latency_s=0.5, cost_usd=0.001,
                   usage=Usage(input_tokens=10, output_tokens=5, cache_read=3, cache_write=0))


def test_ids_increment(tmp_path):
    store = Store(tmp_path)
    assert store.create_report("dev1", "a", make_result(), []) == "R-0001"
    assert store.create_report("dev2", "b", make_result(), []) == "R-0002"
    assert Store(tmp_path).create_report("dev1", "c", make_result(), []) == "R-0003"


def test_get_report_other_dev_404(tmp_path):
    store = Store(tmp_path)
    rid = store.create_report("dev1", "한글 본문", make_result(), [])
    assert store.get_report("dev2", rid) is None
    rec = store.get_report("dev1", rid)
    assert rec["text"] == "한글 본문" and rec["added_info"] == []
    assert rec["result"]["score"]["priority"] == "P3"
    assert store.get_report("dev1", "R-9999") is None


def test_list_sorted_by_priority(tmp_path):
    store = Store(tmp_path)
    a = store.create_report("dev1", "a", make_result("P3"), [])
    b = store.create_report("dev1", "b", make_result("P1"), [])
    c = store.create_report("dev1", "c", make_result("P3", "question"), [])
    store.create_report("dev2", "x", make_result("P1"), [])
    ids = [r["request_id"] for r in store.list_reports("dev1")]
    assert ids == [b, c, a]
    assert [r["request_id"] for r in store.list_reports("dev1", priority="P3")] == [c, a]
    assert [r["request_id"] for r in store.list_reports("dev1", category="question")] == [c]


def test_update_report(tmp_path):
    store = Store(tmp_path)
    rid = store.create_report("dev1", "a", make_result("P3"), [])
    store.update_report("dev1", rid, make_result("P1"), [make_log("score")], "앱 버전 1.2")
    rec = store.get_report("dev1", rid)
    assert rec["result"]["score"]["priority"] == "P1"
    assert rec["added_info"] == ["앱 버전 1.2"]
    store.update_report("dev1", rid, make_result("P2"), [], "두번째")
    assert store.get_report("dev1", rid)["added_info"] == ["앱 버전 1.2", "두번째"]


def test_logs_linked_to_request(tmp_path):
    store = Store(tmp_path)
    rid = store.create_report("dev1", "a", make_result(), [make_log("extract"), make_log("score")])
    lines = (tmp_path / "logs.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines]
    assert [r["step"] for r in rows] == ["extract", "score"]
    r = rows[0]
    assert r["request_id"] == rid and r["dev_id"] == "dev1" and r["cache_read"] == 3
    assert r["input_tokens"] == 10 and r["output_tokens"] == 5
    assert r["latency_s"] == 0.5 and r["cost_usd"] == 0.001 and r["model"] and r["at"]


def test_chat_roundtrip_per_dev(tmp_path):
    store = Store(tmp_path)
    assert store.get_chat("dev1") == []
    store.append_chat("dev1", "user", "안녕")
    store.append_chat("dev1", "assistant", "네")
    store.append_chat("dev2", "user", "other")
    chat = store.get_chat("dev1")
    assert [(m["role"], m["content"]) for m in chat] == [("user", "안녕"), ("assistant", "네")]
