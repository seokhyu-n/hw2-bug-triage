"""Report form fields, log files, pre-submit suggestions, the reporter status page and replies,
and the developer's processing state."""
import json

import pytest
from fastapi.testclient import TestClient

import app.intake as intake
import app.main as main
from app.intake import IntakeWorker
from app.llm import LLMUnavailable
from app.pipeline import LOG_RULES, analyze
from app.report_form import FormError, ReportForm, log_tail, validate_log
from app.store import Store
from app.suggest import suggest
from tests.test_pipeline import classification, extraction, jr, link, score
from tests.test_store import make_log, make_result


def need_info_result(priority="P2"):
    r = make_result(priority=priority)
    r.answer_status = "need_info"
    r.score.questions_to_reporter = ["앱 버전을 알려 주세요"]
    return r


# ---------- form ----------

def test_compose_keeps_description_and_adds_only_filled_fields():
    form = ReportForm.parse({"category": "bug", "app_version": " 1.1.1 ", "steps": "1. 실행\n2. 시작",
                             "frequency": "always", "expected": "   "})
    text = form.compose("러닝 시작하면 꺼져요")
    assert text.startswith("러닝 시작하면 꺼져요\n\n[신고 양식에 입력한 내용]\n")
    assert "- 제보자가 고른 유형(참고용): 오류/버그" in text
    assert "- 앱 버전: 1.1.1" in text and "- 발생 빈도: 매번" in text
    assert "- 재현 순서: \n  1. 실행\n  2. 시작" in text
    assert "기대한 결과" not in text  # blank fields are left out
    assert form.as_dict() == {"category": "bug", "frequency": "always", "app_version": "1.1.1",
                              "steps": "1. 실행\n2. 시작"}
    # nothing filled in: the text is exactly the description (as in the evaluation set)
    assert ReportForm.parse({}).compose("문의") == "문의"


@pytest.mark.parametrize("raw,msg", [({"category": "urgent"}, "유형"), ({"frequency": "daily"}, "빈도"),
                                     ({"app_version": "1" * 21}, "앱 버전")])
def test_form_rejects_unknown_choices_and_long_values(raw, msg):
    with pytest.raises(FormError, match=msg):
        ReportForm.parse(raw)


def test_validate_log():
    assert validate_log("app.log", b"E/RunBuddy: crash") == ("app.log", b"E/RunBuddy: crash")
    assert validate_log("x.txt", b"") is None
    with pytest.raises(FormError, match=".txt 또는 .log"):
        validate_log("dump.bin", b"abc")
    with pytest.raises(FormError, match="텍스트"):
        validate_log("a.log", b"\x00\x01\x02")
    with pytest.raises(FormError, match="1MB"):
        validate_log("a.log", b"a" * (1024 * 1024 + 1))
    assert log_tail("a" * 5000 + "END") == ("a" * 5000 + "END")[-4000:]
    assert log_tail("   ") is None


# ---------- pipeline: log goes to extract only, as data ----------

def test_log_tail_goes_to_extract_only(fake_llm):
    fake_llm.queue(jr(extraction()), jr(classification()), jr(link()), jr(score()))
    analyze("앱이 꺼져요", log="FATAL EXCEPTION: main java.lang.SecurityException")
    first = fake_llm.calls[0]["messages"][0]["content"]
    assert "<app_log>\nFATAL EXCEPTION" in first and LOG_RULES in first
    assert all("<app_log>" not in json.dumps(c["messages"], ensure_ascii=False) for c in fake_llm.calls[1:])


# ---------- suggestions ----------

def test_suggest_known_issue_with_update_advice():
    out = suggest("러닝 시작 버튼 누르면 앱이 바로 꺼져요", android_version="14", app_version="1.1.1")
    assert out["issues"][0]["id"] == "ISSUE-02"
    assert "1.2.0 이상으로 업데이트" in out["issues"][0]["advice"]


def test_suggest_skips_issue_already_fixed_in_reporters_version():
    # 1.2.0 already has the fix: this is a regression and must be reported, not deflected
    out = suggest("러닝 시작 버튼 누르면 앱이 바로 꺼져요 안드로이드 14 앱 1.2.0")
    assert "ISSUE-02" not in [i["id"] for i in out["issues"]]


def test_suggest_faq_for_question_but_not_for_bug_with_generic_words():
    assert suggest("헬스장 러닝머신에서 뛰면 경로가 안 그려지나요?")["faq"][0]["id"] == "FAQ-01"
    assert suggest("픽셀8 안드14인데 러닝 시작하자마자 튕김 ㅠ 위치 권한 다 허용했어요")["faq"] == []
    assert suggest("짧음") == {"issues": [], "faq": []}


def test_suggest_quality_on_eval_set():
    """The numbers quoted in app/suggest.py and the README."""
    rows = [json.loads(line) for line in open("eval/dataset_v2.jsonl", encoding="utf-8")]
    linked = [r for r in rows if r["expected"].get("linked_issue_id")]
    hits = wrong = 0
    for r in linked:
        ids = [i["id"] for i in suggest(r["text"])["issues"]]
        hits += r["expected"]["linked_issue_id"] in ids
        wrong += bool(ids) and r["expected"]["linked_issue_id"] not in ids
    assert (len(linked), hits, wrong) == (26, 25, 0)  # 25 since FAQ-10..12 (11-26) changed the IDF
    pure_bugs = [r for r in rows if r["expected"]["labels"] == ["bug"]]
    assert sum(bool(suggest(r["text"])["faq"]) for r in pure_bugs) == 0


# ---------- API: intake, status page, replies, workflow ----------

@pytest.fixture
def store(tmp_path, monkeypatch):
    main.app.state.store = Store(tmp_path)
    main.app.state.worker = IntakeWorker(main.app.state.store, sync=True, retry_delays=())
    calls = []

    def fake(text, prior=None, added_info=None, images=None, log=None, **kw):
        calls.append({"text": text, "prior": prior, "added_info": added_info, "log": log})
        return (make_result(priority="P1") if added_info else need_info_result()), [make_log()]
    monkeypatch.setattr(intake, "analyze", fake)
    monkeypatch.setattr(intake, "assign_developer", lambda area: "dev2")
    main.app.state.store.calls = calls
    return main.app.state.store


def login_as(dev_id):
    c = TestClient(main.app)
    assert c.post("/api/login", json={"dev_id": dev_id}).status_code == 200
    return c


def submit(**fields):
    data = {"text": "러닝 시작하면 꺼져요", **fields}
    files = []
    if "log" in data:
        files = [("log", ("app.log", data.pop("log"), "text/plain"))]
    return TestClient(main.app).post("/api/intake", data=data, files=files or None)


def test_intake_form_fields_and_log_reach_the_analysis(store):
    r = submit(category="bug", app_version="1.1.1", frequency="always", log=b"E/RunBuddy: NPE at Tracker")
    assert r.status_code == 200 and r.json()["status_url"].startswith("/status/")
    call = store.calls[0]
    assert "- 앱 버전: 1.1.1" in call["text"] and call["log"] == "E/RunBuddy: NPE at Tracker"
    rec = store.get_report("dev2", r.json()["request_id"])
    assert rec["form"]["app_version"] == "1.1.1" and rec["log"]["name"] == "app.log"
    dev2 = login_as("dev2")
    assert dev2.get(f"/api/reports/{rec['request_id']}/log").text == "E/RunBuddy: NPE at Tracker"
    assert login_as("dev1").get(f"/api/reports/{rec['request_id']}/log").status_code == 404
    # JSON clients (the app) send the same fields
    r = TestClient(main.app).post("/api/intake", json={"text": "문의", "category": "question"})
    assert r.status_code == 200
    assert submit(category="nope").status_code == 422
    assert submit(log=b"\x00binary").status_code == 422


def test_status_token_is_never_shown_to_developers(store):
    rid = submit().json()["request_id"]
    dev2 = login_as("dev2")
    assert "status_token" not in dev2.get(f"/api/reports/{rid}").json()
    assert all("status_token" not in r for r in dev2.get("/api/reports").json())


def test_status_page_shows_only_reporter_facing_fields(store):
    url = submit().json()["status_url"]
    token = url.rsplit("/", 1)[1]
    c = TestClient(main.app)
    assert c.get(url).status_code == 200
    s = c.get(f"/api/status/{token}").json()
    assert s["stage"] == "new" and s["stage_label"] == "접수됨"
    assert s["questions"] == ["앱 버전을 알려 주세요"] and s["can_reply"] is True
    assert not {"result", "priority", "dev_id", "assigned_to", "status_token"} & set(s)
    assert c.get("/api/status/wrong-token").status_code == 404


def test_reporter_reply_is_saved_and_reanalyzed(store):
    body = submit().json()
    token, rid = body["status_url"].rsplit("/", 1)[1], body["request_id"]
    c = TestClient(main.app)
    s = c.post(f"/api/status/{token}/reply", json={"text": "앱 버전은 1.1.1이에요"}).json()
    assert s["replies"][0]["state"] == "applied"
    call = store.calls[-1]
    assert call["added_info"] == "앱 버전은 1.1.1이에요" and call["prior"] is not None
    rec = store.get_report("dev2", rid)
    assert rec["result"]["score"]["priority"] == "P1"  # re-analysis applied
    assert s["questions"] == []  # no longer need_info
    assert c.post(f"/api/status/{token}/reply", json={"text": "  "}).status_code == 422


def test_reply_kept_when_reanalysis_fails(store, monkeypatch):
    body = submit().json()
    token, rid = body["status_url"].rsplit("/", 1)[1], body["request_id"]

    def boom(*a, **kw):
        raise LLMUnavailable("x")
    monkeypatch.setattr(intake, "analyze", boom)
    s = TestClient(main.app).post(f"/api/status/{token}/reply", json={"text": "갤럭시 S23"}).json()
    assert s["replies"][0] == {"text": "갤럭시 S23", "at": s["replies"][0]["at"], "state": "failed"}
    assert login_as("dev2").get(f"/api/reports/{rid}").json()["replies"][0]["text"] == "갤럭시 S23"


def test_reply_limits(store, monkeypatch):
    monkeypatch.setattr(intake, "analyze", lambda *a, **kw: (need_info_result(), [make_log()]))
    token = submit().json()["status_url"].rsplit("/", 1)[1]
    c = TestClient(main.app)
    for i in range(main.MAX_REPLIES):
        assert c.post(f"/api/status/{token}/reply", json={"text": f"답 {i}"}).status_code == 200
    assert c.post(f"/api/status/{token}/reply", json={"text": "또"}).status_code == 409


def test_no_reply_while_still_queued(store, monkeypatch):
    def boom(*a, **kw):
        raise LLMUnavailable("x")
    monkeypatch.setattr(intake, "analyze", boom)
    token = submit().json()["status_url"].rsplit("/", 1)[1]
    c = TestClient(main.app)
    s = c.get(f"/api/status/{token}").json()
    assert s["stage"] == "checking" and s["can_reply"] is False
    assert c.post(f"/api/status/{token}/reply", json={"text": "x"}).status_code == 409


def test_developer_workflow_and_message_reach_the_reporter(store):
    body = submit().json()
    token, rid = body["status_url"].rsplit("/", 1)[1], body["request_id"]
    dev2 = login_as("dev2")
    r = dev2.post(f"/api/reports/{rid}/workflow", json={"state": "resolved", "message": " 1.2.1에서 고쳤어요 "})
    assert r.status_code == 200 and r.json()["workflow"]["state"] == "resolved"
    s = TestClient(main.app).get(f"/api/status/{token}").json()
    assert (s["stage_label"], s["developer_message"]) == ("수정 완료", "1.2.1에서 고쳤어요")
    assert s["questions"] == [] and s["can_reply"] is False  # closed reports take no more answers
    assert dev2.post(f"/api/reports/{rid}/workflow", json={"state": "done"}).status_code == 422
    assert login_as("dev1").post(f"/api/reports/{rid}/workflow", json={"state": "resolved"}).status_code == 404


def test_suggest_endpoint(store):
    r = TestClient(main.app).post("/api/intake/suggest", json={"text": "러닝머신에서 뛰면 경로가 원래 안 나오나요?",
                                                                "category": "question"})
    assert r.status_code == 200 and r.json()["faq"][0]["id"] == "FAQ-01"


def test_pending_replies_resume_on_start(tmp_path, monkeypatch):
    store = Store(tmp_path)
    rid, _ = store.enqueue("x")
    store.complete(rid, "dev2", need_info_result(), [])
    store.add_reply("dev2", rid, "앱 버전 1.1.1")
    assert store.pending_replies() == [("dev2", rid, 0)]
    monkeypatch.setattr(intake, "analyze", lambda *a, **kw: (make_result(), [make_log()]))
    w = IntakeWorker(store, sync=True)
    w.process_reply("dev2", rid, 0)
    assert store.pending_replies() == []
