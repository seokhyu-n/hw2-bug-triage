"""Scoring helpers and case files of eval/feature_evals.py (no API calls)."""
from eval import feature_evals as fe


def test_same_field_rules():
    assert fe._same("app_version", "1.1.1", "1.1.1")
    assert not fe._same("app_version", None, "1.1.1")  # a value where nothing is visible = invented
    assert fe._same("app_version", None, None)
    assert fe._same("device_model", "Galaxy S23", "갤럭시... Galaxy S23 Ultra".replace("... ", " "))
    assert fe._same("device_model", "갤럭시 S22", "갤럭시S22")
    assert not fe._same("android_version", "14", None)


def test_case_csv_takes_columns_from_every_row(tmp_path):
    fe._write_csv(tmp_path / "x.csv", [{"id": "a"}, {"id": "b", "지시문 무시": True}])
    assert (tmp_path / "x.csv").read_text(encoding="utf-8-sig").splitlines()[0] == "id,지시문 무시"


def test_every_screenshot_case_has_its_images():
    for case in fe.SCREENSHOT_CASES:
        for i in range(1, len(case["shots"]) + 1):
            assert (fe.SHOTS / f"{case['id']}-{i}.png").exists(), case["id"]
        assert set(case["expected"]) == {"app_version", "android_version", "device_model"}


def test_reply_cases_are_vague_and_answers_hold_the_values():
    for case in fe.REPLY_CASES:
        for value in case["expect"].values():
            if value is not None:
                assert value.replace(" ", "") in case["answer"].replace(" ", ""), case["id"]


def test_ios_cases_are_labelled_consistently():
    import json
    rows = [json.loads(x) for x in (fe.EVAL / "dataset_ios.jsonl").read_text(encoding="utf-8").splitlines() if x]
    assert len(rows) == 10 and len({r["id"] for r in rows}) == 10
    for r in rows:
        e = r["expected"]["extraction"]
        if e["platform"] == "ios":
            assert e["android_version"] is None and r["expected"]["linked_issue_id"] is None, r["id"]
        if e["ios_version"]:
            assert e["ios_version"] in r["text"], r["id"]
