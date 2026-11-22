import csv
import json
from types import SimpleNamespace

import openpyxl
import pytest

from app.llm import LLMError, Usage
from app.pipeline import StepLog, TriageResult
from eval import run_eval

CASES = [
    {"id": "E-001", "text": "질문", "hard": False, "tags": [], "expected": {
        "category": "question", "labels": ["question"],
        "extraction": {"device_model": None, "android_version": None, "app_version": None, "feature_area": "tracking",
                       "symptom": "s", "expected": None, "actual": None, "frequency": None, "repro_steps": []},
        "completeness": None, "priority": "P4", "linked_issue_id": None}},
    {"id": "E-002", "text": "버그 v1.0.1", "hard": True, "tags": [], "expected": {
        "category": "bug", "labels": ["bug"],
        "extraction": {"device_model": "Pixel 8", "android_version": "14", "app_version": "1.0.1",
                       "feature_area": "tracking", "symptom": "s", "expected": "e", "actual": "a",
                       "frequency": "always", "repro_steps": ["x"]},
        "completeness": 2, "priority": "P2", "linked_issue_id": "I-1"}},
]


def _result(cat, ext, comp, prio, link):
    return TriageResult.model_validate({
        "extraction": {**ext, "missing_fields": []},
        "classification": {"category": cat, "labels": [cat], "reason": "r"},
        "link": None if link is None else {"linked_issue_id": link, "match_reason": "m", "fixed_in": None,
                                          "user_should_update": None},
        "score": {"reasoning": "r", "completeness": comp, "priority": prio, "questions_to_reporter": []},
        "answer_status": "ready"})


def _logs():
    return [StepLog("extract", "m", 1.0, 0.01, Usage(10, 5, 7, 0)), StepLog("score", "m", 2.0, 0.02, Usage(10, 5, 3, 0))]


@pytest.fixture
def env(tmp_path, monkeypatch):
    ds = tmp_path / "ds.jsonl"
    ds.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in CASES), encoding="utf-8")
    monkeypatch.setattr(run_eval, "DATASET", ds)
    monkeypatch.setattr(run_eval, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(run_eval, "RUNS_CSV", tmp_path / "runs.csv")
    monkeypatch.setattr(run_eval, "RUNS_XLSX", tmp_path / "runs.xlsx")
    return tmp_path


def _rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_run_eval_appends_row(env, monkeypatch):
    def fake(text, cfg):
        if "버그" in text:
            return _result("bug", CASES[1]["expected"]["extraction"], 1, "P2", "I-1"), _logs()
        return _result("question", CASES[0]["expected"]["extraction"], None, "P4", None), _logs()
    monkeypatch.setattr(run_eval, "analyze", fake)
    run_eval.main(["--run-id", "Run-T1", "--baseline", "--change", "베이스라인", "--workers", "2"])
    rows = _rows(env / "runs.csv")
    assert len(rows) == 1
    r = rows[0]
    assert r["Run ID"] == "Run-T1" and r["변경사항"] == "베이스라인"
    assert float(r["분류 정확도"]) == 1.0
    assert float(r["완성도 MAE"]) == 1.0
    assert float(r["링크 정확도"]) == 1.0
    assert float(r["총비용(USD)"]) == pytest.approx(0.06)
    assert int(r["캐시 적중 토큰"]) == 20
    assert float(r["평균 응답시간(s)"]) == pytest.approx(3.0)
    per = _rows(env / "results" / "Run-T1.csv")
    assert [p["id"] for p in per] == ["E-001", "E-002"]
    assert (env / "results" / "Run-T1_confusion.csv").exists()
    assert (env / "results" / "Run-T1.jsonl").exists()
    wb = openpyxl.load_workbook(env / "runs.xlsx")
    assert wb.sheetnames == ["전체 Run", "분류", "추출", "스코어링", "이슈 연결", "속도·비용", "혼동행렬 Run-T1"]
    # appends on second run
    run_eval.main(["--run-id", "Run-T2", "--no-rubric"])
    assert [r["Run ID"] for r in _rows(env / "runs.csv")] == ["Run-T1", "Run-T2"]
    assert openpyxl.load_workbook(env / "runs.xlsx").sheetnames == [
        "전체 Run", "분류", "추출", "스코어링", "이슈 연결", "속도·비용", "혼동행렬 Run-T1", "혼동행렬 Run-T2"]


def test_run_eval_records_errors(env, monkeypatch):
    def fake(text, cfg):
        if "버그" in text:
            raise LLMError("boom")
        return _result("question", CASES[0]["expected"]["extraction"], None, "P4", None), _logs()
    monkeypatch.setattr(run_eval, "analyze", fake)
    run_eval.main(["--run-id", "Run-E"])
    per = _rows(env / "results" / "Run-E.csv")
    assert per[1]["error"] == "boom" and per[1]["category_ok"] == "오류"
    r = _rows(env / "runs.csv")[0]
    assert float(r["분류 정확도"]) == 0.5
    assert int(r["오류 건수"]) == 1
    assert float(r["링크 정확도"]) == 0.5


def test_limit_and_only_hard(env, monkeypatch):
    seen = []
    monkeypatch.setattr(run_eval, "analyze", lambda t, c: (seen.append(t), (_ for _ in ()).throw(LLMError("x")))[1])
    run_eval.main(["--run-id", "Run-H", "--only-hard"])
    assert seen == ["버그 v1.0.1"]
    seen.clear()
    run_eval.main(["--run-id", "Run-L", "--limit", "1"])
    assert seen == ["질문"]


def test_unexpected_exception_recorded_and_latency_uses_successes(env, monkeypatch):
    def fake(text, cfg):
        if "버그" in text:
            raise KeyError("oops")
        return _result("question", CASES[0]["expected"]["extraction"], None, "P4", None), _logs()
    monkeypatch.setattr(run_eval, "analyze", fake)
    run_eval.main(["--run-id", "Run-K"])
    per = _rows(env / "results" / "Run-K.csv")
    assert per[1]["category_ok"] == "오류" and per[1]["error_type"] == "KeyError"
    r = _rows(env / "runs.csv")[0]
    assert float(r["평균 응답시간(s)"]) == pytest.approx(3.0)  # 1 success, not 2 cases
    assert int(r["오류 건수"]) == 1


def test_xlsx_numeric_columns_are_numbers(env, monkeypatch):
    monkeypatch.setattr(run_eval, "analyze", lambda t, c: (_result(
        "question", CASES[0]["expected"]["extraction"], None, "P4", None), _logs()))
    run_eval.main(["--run-id", "Run-N"])
    ws = openpyxl.load_workbook(env / "runs.xlsx")["전체 Run"]
    hdr = [c.value for c in ws[1]]
    row = [c.value for c in ws[2]]
    d = dict(zip(hdr, row))
    assert isinstance(d["분류 정확도"], float) and isinstance(d["캐시 적중 토큰"], int)
    assert isinstance(d["Run ID"], str)


def test_failed_case_keeps_cost_of_paid_steps(env, monkeypatch):
    def fake(text, cfg):
        if "버그" in text:
            err = LLMError("late failure")
            err.partial_logs = _logs()[:1]  # one paid step before the failure
            raise err
        return _result("question", CASES[0]["expected"]["extraction"], None, "P4", None), _logs()
    monkeypatch.setattr(run_eval, "analyze", fake)
    run_eval.main(["--run-id", "Run-P"])
    per = _rows(env / "results" / "Run-P.csv")
    assert float(per[1]["cost_usd"]) == pytest.approx(0.01) and per[1]["category_ok"] == "오류"
    r = _rows(env / "runs.csv")[0]
    assert float(r["총비용(USD)"]) == pytest.approx(0.04)  # 0.03 success + 0.01 failed
    assert float(r["평균 응답시간(s)"]) == pytest.approx(3.0)  # error latency excluded


def test_analyze_attaches_partial_logs_on_failure(fake_llm):
    import pytest

    from app.pipeline import analyze
    from tests.test_pipeline import extraction, jr
    fake_llm.queue(jr(extraction()), LLMError("classify down"))
    with pytest.raises(LLMError) as ei:
        analyze("제보")
    assert [s.step for s in ei.value.partial_logs] == ["extract"]


def test_task_sheets_show_history_and_skip_smoke_runs(env, monkeypatch):
    monkeypatch.setattr(run_eval, "analyze", lambda t, c: (_result(
        "question", CASES[0]["expected"]["extraction"], None, "P4", None), _logs()))
    run_eval.main(["--run-id", "Run-00-smoke", "--limit", "1"])
    run_eval.main(["--run-id", "Run-A", "--change", "기준"])
    run_eval.main(["--run-id", "Run-B", "--change", "다음"])
    wb = openpyxl.load_workbook(env / "runs.xlsx")
    assert "혼동행렬 Run-00-smoke" not in wb.sheetnames
    ws = wb["분류"]
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    assert rows[0][:3] == ["Run ID", "모델", "분류 정확도"] and rows[0][-1] == "변경사항"
    assert [r[0] for r in rows[1:]] == ["Run-A", "Run-B"]  # smoke run left out
    assert rows[1][-2] == "" or rows[1][-2] is None      # no previous run for the first row
    assert rows[2][-2] == 0 and rows[2][-1] == "다음"
    assert len(ws._charts) == 1
    assert [r["Run ID"] for r in _rows(env / "runs.csv")][0] == "Run-00-smoke"  # still recorded in CSV
