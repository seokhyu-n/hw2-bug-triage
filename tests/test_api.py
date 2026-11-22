import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.chat import ChatReply
from app.llm import LLMRefusal, LLMUnavailable
from app.store import Store
from tests.test_store import make_log, make_result


@pytest.fixture
def store(tmp_path, monkeypatch):
    main.app.state.store = Store(tmp_path)
    monkeypatch.setattr(main, "analyze", lambda text, **kw: (make_result(), [make_log()]))
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
    monkeypatch.setattr(main, "assign_developer", lambda area: "dev2")
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
    monkeypatch.setattr(main, "assign_developer", lambda area: "dev2")
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


@pytest.mark.parametrize("exc,status", [(LLMRefusal("x"), 422), (LLMUnavailable("x"), 502)])
def test_intake_llm_error_returns_message(reporter, monkeypatch, exc, status):
    def boom(text, **kw):
        raise exc
    monkeypatch.setattr(main, "analyze", boom)
    r = reporter.post("/api/intake", json={"text": "제보"})
    assert r.status_code == status
    assert any("가" <= ch <= "힣" for ch in r.json()["detail"])


def test_list_and_reanalyze(client, reporter, monkeypatch):
    monkeypatch.setattr(main, "assign_developer", lambda area: "dev1")
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


def test_missing_api_key_returns_502_with_korean_detail(reporter, monkeypatch):
    from app import llm
    from app.pipeline import analyze

    def no_key():
        raise RuntimeError("CLAUDE_API_KEY가 .env에 없습니다")
    monkeypatch.setattr(main, "analyze", analyze)  # undo the fixture stub: go through the real call_llm
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm, "get_api_key", no_key)
    r = reporter.post("/api/intake", json={"text": "제보"})
    assert r.status_code == 502
    assert any("가" <= ch <= "힣" for ch in r.json()["detail"])
