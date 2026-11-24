"""Screenshot attachments: validation, upload API, access control, and what the extract step sees."""
import base64

import pytest
from fastapi.testclient import TestClient

import app.intake as intake
import app.main as main
from app.attachments import MAX_BYTES, AttachmentError, Upload, safe_name, sniff, validate
from app.intake import IntakeWorker
from app.llm import LLMUnavailable
from app.pipeline import SCREENSHOT_RULES, analyze
from app.store import Store
from tests.test_pipeline import classification, extraction, jr, link, score
from tests.test_store import make_log, make_result

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
GIF = b"GIF89a" + b"\x00" * 32
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 32


# ---------- validation ----------

@pytest.mark.parametrize("data,media", [(PNG, "image/png"), (JPG, "image/jpeg"),
                                        (GIF, "image/gif"), (WEBP, "image/webp"),
                                        (b"%PDF-1.7", None), (b"<svg></svg>", None), (b"MZ\x90\x00", None)])
def test_sniff_by_magic_bytes(data, media):
    assert sniff(data) == media


def test_validate_rejects_renamed_non_image_and_limits():
    with pytest.raises(AttachmentError, match="이미지 파일"):
        validate([Upload("shot.png", b"<html>not an image</html>")])
    with pytest.raises(AttachmentError, match="3장"):
        validate([Upload(f"{i}.png", PNG) for i in range(4)])
    with pytest.raises(AttachmentError, match="5MB"):
        validate([Upload("big.png", PNG + b"\x00" * MAX_BYTES)])
    # an empty file input sends one empty part: ignored, not an error
    assert validate([Upload("", b"")]) == []
    assert validate([Upload("a.jpg", JPG)]) == [("a.jpg", "image/jpeg", JPG)]


def test_safe_name_strips_paths_and_control_chars():
    assert safe_name("C:\\Users\\me\\..\\shot.png") == "shot.png"
    assert safe_name("../../etc/passwd") == "passwd"
    assert safe_name("a\x00b\nc.png") == "abc.png"
    assert safe_name("") == "screenshot"


# ---------- API ----------

@pytest.fixture
def store(tmp_path, monkeypatch):
    main.app.state.store = Store(tmp_path)
    main.app.state.worker = IntakeWorker(main.app.state.store, sync=True)
    seen = {}

    def fake(text, images=None, **kw):
        seen["images"] = images
        return make_result(), [make_log()]
    monkeypatch.setattr(intake, "analyze", fake)
    monkeypatch.setattr(intake, "assign_developer", lambda area: "dev2")
    main.app.state.store.seen = seen
    return main.app.state.store


def login_as(dev_id):
    c = TestClient(main.app)
    assert c.post("/api/login", json={"dev_id": dev_id}).status_code == 200
    return c


def post_report(text="지도가 안 열려요", files=()):
    return TestClient(main.app).post("/api/intake", data={"text": text},
                                     files=[("files", (name, data, ctype)) for name, data, ctype in files])


def test_multipart_intake_stores_screenshots_and_passes_them_to_analysis(store):
    r = post_report(files=[("오류 화면.png", PNG, "image/png"), ("앱정보.jpg", JPG, "image/jpeg")])
    assert r.status_code == 200 and set(r.json()) == {"request_id", "message"}
    rid = r.json()["request_id"]
    assert store.seen["images"] == [("image/png", PNG), ("image/jpeg", JPG)]

    rec = store.get_report("dev2", rid)
    assert [(a["name"], a["media_type"], a["file"]) for a in rec["attachments"]] == [
        ("오류 화면.png", "image/png", "1.png"), ("앱정보.jpg", "image/jpeg", "2.jpg")]
    dev2 = login_as("dev2")
    img = dev2.get(f"/api/reports/{rid}/attachments/1")
    assert img.status_code == 200 and img.content == PNG
    assert img.headers["content-type"] == "image/png"
    assert img.headers["x-content-type-options"] == "nosniff"
    assert dev2.get(f"/api/reports/{rid}").json()["attachments"][1]["name"] == "앱정보.jpg"


def test_browser_content_type_is_ignored(store):
    # the browser says png, the bytes are HTML: rejected
    r = post_report(files=[("x.png", b"<script>alert(1)</script>", "image/png")])
    assert r.status_code == 422 and "이미지 파일" in r.json()["detail"]
    assert store.queued() == []


def test_too_many_or_too_big_files_rejected_and_nothing_saved(store):
    r = post_report(files=[(f"{i}.png", PNG, "image/png") for i in range(4)])
    assert r.status_code == 422 and "3장" in r.json()["detail"]
    r = post_report(files=[("big.png", PNG + b"\x00" * MAX_BYTES, "image/png")])
    assert r.status_code == 422 and "5MB" in r.json()["detail"]
    assert store.queued() == [] and not (store.base / "_attachments").exists()


def test_multipart_without_files_and_json_both_work(store):
    assert post_report().status_code == 200
    assert TestClient(main.app).post("/api/intake", json={"text": "제보"}).status_code == 200
    assert store.seen["images"] == []
    # text rules still apply to the form
    assert post_report(text="   ").status_code == 422


def test_attachment_only_for_the_developer_who_sees_the_report(store):
    rid = post_report(files=[("a.png", PNG, "image/png")]).json()["request_id"]
    assert TestClient(main.app).get(f"/api/reports/{rid}/attachments/1").status_code == 401
    assert login_as("dev1").get(f"/api/reports/{rid}/attachments/1").status_code == 404
    dev2 = login_as("dev2")
    assert dev2.get(f"/api/reports/{rid}/attachments/2").status_code == 404
    assert dev2.get(f"/api/reports/{rid}/attachments/0").status_code == 404


def test_failed_report_keeps_screenshots_for_fallback_dev(store, monkeypatch):
    def boom(text, **kw):
        raise LLMUnavailable("x")
    monkeypatch.setattr(intake, "analyze", boom)
    main.app.state.worker.retry_delays = ()
    rid = post_report(files=[("a.png", PNG, "image/png")]).json()["request_id"]
    dev3 = login_as(intake.FAILED_OWNER)
    assert dev3.get(f"/api/reports/{rid}").json()["attachments"][0]["name"] == "a.png"
    assert dev3.get(f"/api/reports/{rid}/attachments/1").content == PNG
    assert login_as("dev2").get(f"/api/reports/{rid}/attachments/1").status_code == 404


# ---------- pipeline ----------

def test_images_go_to_extract_only_before_the_text(fake_llm):
    fake_llm.queue(jr(extraction()), jr(classification()), jr(link()), jr(score()))
    analyze("러닝 시작하면 꺼져요", images=[("image/png", PNG)])
    first = fake_llm.calls[0]["messages"][0]["content"]
    assert [b["type"] for b in first] == ["image", "text"]
    assert first[0]["source"] == {"type": "base64", "media_type": "image/png",
                                  "data": base64.b64encode(PNG).decode()}
    assert "첨부 스크린샷" in first[1]["text"] and "<report>" in first[1]["text"]
    # later steps get no images (they use what extract read from them)
    for call in fake_llm.calls[1:]:
        for m in call["messages"]:
            if isinstance(m["content"], list):
                assert all(b.get("type") != "image" for b in m["content"])


def test_text_only_report_message_is_unchanged(fake_llm):
    fake_llm.queue(jr(extraction()), jr(classification()), jr(link()), jr(score()))
    analyze("러닝 시작하면 꺼져요")
    first = fake_llm.calls[0]["messages"][0]["content"]
    assert isinstance(first, str) and "첨부 스크린샷" not in first
    # screenshot rules never touch the cached system prompt
    assert all(SCREENSHOT_RULES[:10] not in b["text"] for b in fake_llm.calls[0]["system"])
