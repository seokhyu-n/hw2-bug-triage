import pytest
from fastapi.testclient import TestClient

import app.intake as intake
import app.main as main
from app.chat import ChatReply
from app.intake import IntakeWorker
from app.llm import LLMRefusal, LLMUnavailable
from app.store import Store
from tests.test_store import make_log, make_result


@pytest.fixture
def store(tmp_path, monkeypatch):
    main.app.state.store = Store(tmp_path)
    # analysis runs inline in tests (the real worker is a background thread)
    main.app.state.worker = IntakeWorker(main.app.state.store, sync=True)
    fake = lambda text, **kw: (make_result(), [make_log()])  # noqa: E731
    monkeypatch.setattr(main, "analyze", fake)    # reanalyze endpoint
    monkeypatch.setattr(intake, "analyze", fake)  # background intake analysis
    return main.app.state.store


@pytest.fixture
def reporter(store):
    """Anonymous client: the public intake needs no login."""
    return TestClient(main.app)


@pytest.fixture
def client(store):
    c = TestClient(main.app)
    assert c.post("/api/login", json={"dev_id": "dev1"}).status_code == 200
    return c


def login_as(dev_id):
    c = TestClient(main.app)
    assert c.post("/api/login", json={"dev_id": dev_id}).status_code == 200
    return c


def test_login_sets_cookie_and_unknown_401():
    c = TestClient(main.app)
    r = c.post("/api/login", json={"dev_id": "dev1"})
    assert r.status_code == 200 and "session" in r.cookies
    assert "httponly" in r.headers["set-cookie"].lower()
    assert TestClient(main.app).post("/api/login", json={"dev_id": "nobody"}).status_code == 401


def test_developer_endpoints_require_login():
    c = TestClient(main.app)
    assert c.get("/api/reports").status_code == 401
    assert c.get("/api/reports/R-0001").status_code == 401
    assert c.post("/api/reports/R-0001/reanalyze", json={"added_info": "x"}).status_code == 401
    assert c.post("/api/chat", json={"message": "x"}).status_code == 401


def test_developers_cannot_submit_through_old_endpoint(client):
    # Submission moved to the public intake; the developer API is read/triage only.
    assert client.post("/api/reports", json={"text": "제보"}).status_code == 405


def test_logout_invalidates_session(client):
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/reports").status_code == 401


def test_intake_works_without_login_and_returns_receipt_only(reporter, monkeypatch):
    monkeypatch.setattr(intake, "assign_developer", lambda area: "dev2")
    r = reporter.post("/api/intake", json={"text": "지도가 안 열려요"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"request_id", "message"}  # no triage result, no assignee
    assert body["request_id"] == "R-0001"
    assert "R-0001" in body["message"]


def test_intake_rejects_empty_and_too_long(reporter):
    assert reporter.post("/api/intake", json={"text": "   "}).status_code == 422
    assert reporter.post("/api/intake", json={"text": "가" * 5001}).status_code == 422
    assert reporter.post("/api/intake", json={"text": "가" * 5000}).status_code == 200


def test_intake_assigns_developer_and_only_assignee_sees_it(reporter, monkeypatch):
    monkeypatch.setattr(intake, "assign_developer", lambda area: "dev2")
    rid = reporter.post("/api/intake", json={"text": "지도가 안 열려요"}).json()["request_id"]
    dev2 = login_as("dev2")
    body = dev2.get(f"/api/reports/{rid}").json()
    assert body["assigned_to"] == "dev2"
    assert set(body["logs_summary"]) == {"latency_s", "cost_usd", "cache_read"}
    assert body["result"]["score"]["priority"] == "P3"
    assert [x["request_id"] for x in dev2.get("/api/reports").json()] == [rid]
    dev1 = login_as("dev1")
    assert dev1.get(f"/api/reports/{rid}").status_code == 404
    assert dev1.get("/api/reports").json() == []
    assert dev1.post(f"/api/reports/{rid}/reanalyze", json={"added_info": "x"}).status_code == 404


@pytest.mark.parametrize("exc,attempts", [(LLMRefusal("x"), 1), (LLMUnavailable("x"), 3)])
def test_intake_llm_error_keeps_report_as_failed(reporter, store, monkeypatch, exc, attempts):
    calls = []

    def boom(text, **kw):
        calls.append(text)
        raise exc
    monkeypatch.setattr(intake, "analyze", boom)
    r = reporter.post("/api/intake", json={"text": "제보"})
    # the reporter still gets a receipt: the report is saved before the analysis
    assert r.status_code == 200 and r.json()["request_id"] == "R-0001"
    entry = store.get_queued("R-0001")
    assert entry["status"] == "failed" and entry["text"] == "제보"
    # transient errors are retried, a refusal is not
    assert len(calls) == attempts and entry["attempts"] == attempts
    assert any("가" <= ch <= "힣" for ch in entry["last_error"])


def test_failed_report_visible_to_fallback_dev_and_retry_assigns_it(reporter, store, monkeypatch):
    def boom(text, **kw):
        raise LLMUnavailable("x")
    monkeypatch.setattr(intake, "analyze", boom)
    rid = reporter.post("/api/intake", json={"text": "지도가 안 열려요"}).json()["request_id"]

    dev3 = login_as(intake.FAILED_OWNER)
    rows = dev3.get("/api/reports").json()
    assert [(x["request_id"], x["status"], x["result"]) for x in rows] == [(rid, "failed", None)]
    assert dev3.get(f"/api/reports/{rid}").json()["status"] == "failed"
    # other developers do not see unassigned reports and cannot retry them
    dev1 = login_as("dev1")
    assert dev1.get("/api/reports").json() == []
    assert dev1.post(f"/api/reports/{rid}/retry").status_code == 404

    monkeypatch.setattr(intake, "analyze", lambda text, **kw: (make_result(), [make_log()]))
    monkeypatch.setattr(intake, "assign_developer", lambda area: "dev2")
    r = dev3.post(f"/api/reports/{rid}/retry")
    assert r.status_code == 200
    assert store.get_queued(rid) is None
    assert dev3.get("/api/reports").json() == []
    assert login_as("dev2").get(f"/api/reports/{rid}").json()["status"] == "done"
    assert dev3.post(f"/api/reports/{rid}/retry").status_code == 404


def test_retry_rejects_report_still_pending(reporter, store):
    rid = store.enqueue("분석 대기")
    assert login_as(intake.FAILED_OWNER).post(f"/api/reports/{rid}/retry").status_code == 409


def test_list_and_reanalyze(client, reporter, monkeypatch):
    monkeypatch.setattr(intake, "assign_developer", lambda area: "dev1")
    rid = reporter.post("/api/intake", json={"text": "제보"}).json()["request_id"]
    seen = {}

    def fake(text, prior=None, added_info=None, **kw):
        seen.update(text=text, prior=prior, added_info=added_info)
        return make_result(priority="P1"), [make_log()]
    monkeypatch.setattr(main, "analyze", fake)
    r = client.post(f"/api/reports/{rid}/reanalyze", json={"added_info": "앱 버전 1.0"})
    assert r.status_code == 200
    assert r.json()["result"]["score"]["priority"] == "P1"
    assert r.json()["added_info"] == ["앱 버전 1.0"]
    assert seen["text"] == "제보" and seen["prior"] is not None and seen["added_info"] == "앱 버전 1.0"
    assert client.post(f"/api/reports/{rid}/reanalyze", json={"added_info": "  "}).status_code == 422
    assert [x["request_id"] for x in client.get("/api/reports").json()] == [rid]


def test_chat_endpoint_returns_reply(client, monkeypatch):
    def fake(dev_id, message, store, **kw):
        store.append_chat(dev_id, "user", message)
        store.append_chat(dev_id, "assistant", "답변")
        return ChatReply(text="답변", tool_calls=["list_my_reports"], cost_usd=0.001,
                         latency_s=1.0, cache_read=5)
    monkeypatch.setattr(main, "chat_turn", fake)
    r = client.post("/api/chat", json={"message": "P1만 보여줘"})
    assert r.status_code == 200
    assert r.json()["text"] == "답변" and r.json()["tool_calls"] == ["list_my_reports"]
    assert client.post("/api/chat", json={"message": " "}).status_code == 422
    hist = client.get("/api/chat/history").json()
    assert [h["role"] for h in hist] == ["user", "assistant"]


def test_static_pages(client):
    assert "로그인" in client.get("/").text
    assert "/report" in client.get("/").text
    report_page = client.get("/report")
    assert report_page.status_code == 200 and "/api/intake" in report_page.text
    app_page = client.get("/app").text
    assert 'id="report-text"' not in app_page  # developers no longer type reports
    assert client.get("/static/app.js").status_code == 200


def test_missing_api_key_saves_report_as_failed(reporter, store, monkeypatch):
    from app import llm
    from app.pipeline import analyze

    def no_key():
        raise RuntimeError("CLAUDE_API_KEY가 .env에 없습니다")
    monkeypatch.setattr(intake, "analyze", analyze)  # undo the fixture stub: go through the real call_llm
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm, "get_api_key", no_key)
    r = reporter.post("/api/intake", json={"text": "제보"})
    assert r.status_code == 200
    entry = store.get_queued(r.json()["request_id"])
    assert entry["status"] == "failed" and "CLAUDE_API_KEY" not in entry["last_error"]


def test_reanalyze_llm_error_returns_message(client, reporter, monkeypatch):
    monkeypatch.setattr(intake, "assign_developer", lambda area: "dev1")
    rid = reporter.post("/api/intake", json={"text": "제보"}).json()["request_id"]

    def boom(text, **kw):
        raise LLMUnavailable("x")
    monkeypatch.setattr(main, "analyze", boom)
    r = client.post(f"/api/reports/{rid}/reanalyze", json={"added_info": "앱 버전 1.0"})
    assert r.status_code == 502
    assert any("가" <= ch <= "힣" for ch in r.json()["detail"])


def _ndjson(resp):
    import json
    return [json.loads(x) for x in resp.text.splitlines() if x.strip()]


def test_chat_stream_sends_text_tool_and_done(client, monkeypatch):
    def fake(dev_id, message, store, on_text=None, on_tool=None, **kw):
        on_tool("list_my_reports")
        on_text("담당 ")
        on_text("제보 없음")
        return ChatReply(text="담당 제보 없음", tool_calls=["list_my_reports"], cost_usd=0.001,
                         latency_s=1.0, cache_read=5)
    monkeypatch.setattr(main, "chat_turn", fake)
    r = client.post("/api/chat/stream", json={"message": "내 제보"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    events = _ndjson(r)
    assert [e["type"] for e in events] == ["tool", "text", "text", "done"]
    assert events[-1]["text"] == "담당 제보 없음" and events[-1]["tool_calls"] == ["list_my_reports"]


def test_chat_stream_error_event_and_login(client, monkeypatch):
    def boom(*a, **kw):
        raise LLMUnavailable("x")
    monkeypatch.setattr(main, "chat_turn", boom)
    events = _ndjson(client.post("/api/chat/stream", json={"message": "x"}))
    assert events == [{"type": "error", "detail": events[0]["detail"]}]
    assert any("가" <= ch <= "힣" for ch in events[0]["detail"])
    assert TestClient(main.app).post("/api/chat/stream", json={"message": "x"}).status_code == 401
    assert client.post("/api/chat/stream", json={"message": " "}).status_code == 422
