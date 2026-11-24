"""Ideas taken from running apps' support: public known-issues page, device self-check guides,
and a run record attached to a report."""
import json

import pytest
from fastapi.testclient import TestClient

import app.intake as intake
import app.main as main
from app.activity import Activity, block, facts, parse
from app.intake import IntakeWorker
from app.issues import IssueRegistry
from app.self_help import family, match
from app.store import Store
from tests.test_store import make_log, make_result


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = Store(tmp_path)
    main.app.state.store = s
    main.app.state.worker = IntakeWorker(s, sync=True, retry_delays=())
    calls = []

    def fake(text, **kw):
        calls.append(text)
        return make_result(), [make_log()]
    monkeypatch.setattr(intake, "analyze", fake)
    monkeypatch.setattr(intake, "assign_developer", lambda area: "dev2")
    s.calls = calls
    return s


def login_as(dev_id):
    c = TestClient(main.app)
    assert c.post("/api/login", json={"dev_id": dev_id}).status_code == 200
    return c


# ---------- public known-issues page ----------

def test_public_issues_show_only_public_fields_open_first(store):
    IssueRegistry(store.base).add(title="지도 확대 시 멈춤", feature_area="map", symptoms=["멈춤"],
                                  affected_android=[], affected_app_versions=[], workaround="두 번 탭",
                                  created_by="dev2")
    c = TestClient(main.app)
    assert c.get("/known-issues").status_code == 200
    data = c.get("/api/public/issues").json()
    issues = data["issues"]
    assert data["open"] == sum(i["status"] == "open" for i in issues) and data["open"] >= 1
    assert [i["status"] for i in issues] == sorted((i["status"] for i in issues), key=lambda s: s != "open")
    team = next(i for i in issues if i["id"] == "ISSUE-13")
    assert team["platform"] == "all" and team["workaround"] == "두 번 탭"
    assert set(team) == {"id", "title", "feature_area", "status", "fixed_in", "workaround", "reports", "platform"}
    assert "created_by" not in json.dumps(issues) and "symptoms" not in json.dumps(issues)
    fixed = next(i for i in issues if i["id"] == "ISSUE-02")
    assert fixed["status"] == "fixed" and fixed["fixed_in"] == "1.2.0" and fixed["platform"] == "android"


def test_report_page_has_banner_and_known_issues_link(store):
    page = TestClient(main.app).get("/report").text
    assert 'id="known-banner"' in page and "/known-issues" in page


# ---------- self-check guides ----------

@pytest.mark.parametrize("text,device,platform,ids", [
    ("화면 끄고 뛰면 중간에 기록이 끊겨요", "갤럭시 S23", None, ["SH-GALAXY-SLEEP"]),
    ("화면 끄고 뛰면 중간에 기록이 끊겨요", "아이폰 15", None, ["SH-IPHONE-BACKGROUND"]),
    ("화면 끄고 뛰면 중간에 기록이 끊겨요", None, "ios", ["SH-IPHONE-BACKGROUND"]),
    ("GPS가 튀어서 거리가 길게 나와요", "갤럭시 S23", None, ["SH-GPS-START"]),
    ("러닝 시작 누르면 앱이 꺼져요", "갤럭시 S23", None, []),  # a crash is an app bug, not a setting
    ("화면 끄면 기록이 끊겨요", None, None, []),  # phone unknown: no phone-specific steps
])
def test_self_help_match(text, device, platform, ids):
    assert [g["id"] for g in match(text, device, platform)] == ids


def test_family():
    assert family("갤럭시 Z 플립6") == "galaxy" and family("Galaxy S23") == "galaxy"
    assert family("아이폰 SE (3세대)") == "iphone" and family(None, "ios") == "iphone"
    assert family("픽셀 7") is None


def test_suggest_returns_self_help_but_not_for_questions(store):
    c = TestClient(main.app)
    body = {"text": "화면 끄고 뛰면 중간에 기록이 끊겨요", "device_model": "갤럭시 S23", "platform": "android"}
    out = c.post("/api/intake/suggest", json={**body, "category": "bug"}).json()
    assert [g["id"] for g in out["self_help"]] == ["SH-GALAXY-SLEEP"] and out["self_help"][0]["steps"]
    assert c.post("/api/intake/suggest", json={**body, "category": "question"}).json()["self_help"] == []


def test_developer_sees_device_setting_hint(store):
    rid = TestClient(main.app).post("/api/intake", json={
        "text": "화면 끄고 뛰면 중간에 기록이 끊겨요", "device_model": "갤럭시 S23"}).json()["request_id"]
    view = login_as("dev2").get(f"/api/reports/{rid}").json()
    assert [g["id"] for g in view["self_help"]] == ["SH-GALAXY-SLEEP"]


# ---------- run record ----------

A1002 = {"activity_id": "A-1002", "started_at": "2026-11-23T19:40:00", "distance_km": 3.21, "duration_s": 1805,
         "gps_points": 640, "gaps": [{"start_s": 760, "end_s": 1315}], "max_jump_m": 9}


def test_facts_and_block():
    a = Activity.model_validate(A1002)
    f = facts(a)
    assert f[0] == "기록 ID: A-1002 (2026-11-23 19:40 시작)"
    assert "거리 3.21km, 시간 30분 5초, GPS 위치 640개" in f[1]
    assert f[2] == "GPS 끊김 1번, 합계 9분 15초 동안 위치 없음 (12분 40초~21분 55초)"
    assert block(a).startswith("[연결된 러닝 기록]\n- 기록 ID: A-1002")
    jump = facts(Activity.model_validate({**A1002, "gaps": [], "max_jump_m": 410}))
    assert "GPS 끊김 없음" in jump and "한 번에 410m 튄 위치가 있음" in jump


@pytest.mark.parametrize("bad", [
    {**A1002, "gaps": [{"start_s": 900, "end_s": 100}]},       # end before start
    {**A1002, "distance_km": -1},
    {**A1002, "activity_id": "A-1<script>"},
    "{not json",
])
def test_bad_activity_rejected(bad):
    with pytest.raises((ValueError, TypeError)):
        parse(bad)


def test_intake_with_activity_json_and_form(store):
    c = TestClient(main.app)
    r = c.post("/api/intake", json={"text": "기록이 중간에 끊겼어요", "activity": A1002})
    assert r.status_code == 200
    assert "[연결된 러닝 기록]" in store.calls[-1] and "9분 15초 동안 위치 없음" in store.calls[-1]
    view = login_as("dev2").get(f"/api/reports/{r.json()['request_id']}").json()
    assert view["activity"]["activity_id"] == "A-1002" and len(view["activity_facts"]) == 3
    # the report page sends it as a form field (JSON string)
    r = c.post("/api/intake", data={"text": "기록이 이상해요", "activity": json.dumps(A1002)})
    assert r.status_code == 200
    assert c.post("/api/intake", data={"text": "x 문제", "activity": "{bad"}).status_code == 422
    assert c.post("/api/intake", json={"text": "x 문제", "activity": {**A1002, "duration_s": -5}}).status_code == 422


def test_activity_summary_is_not_read_as_symptoms_for_self_help(store):
    # "GPS 끊김" in the attached summary must not trigger the GPS guide by itself
    rid = TestClient(main.app).post("/api/intake", json={"text": "기록 확인 부탁드려요", "activity": A1002}).json()["request_id"]
    assert login_as("dev2").get(f"/api/reports/{rid}").json()["self_help"] == []


def test_demo_activities(store):
    c = TestClient(main.app)
    a = c.get("/api/demo/activities/A-1003").json()
    assert a["activity_id"] == "A-1003" and "한 번에 410m 튄 위치가 있음" in a["facts"]
    assert c.get("/api/demo/activities/A-9999").status_code == 404
