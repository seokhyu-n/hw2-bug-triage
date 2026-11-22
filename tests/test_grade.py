import pytest

from eval import grade


def test_classification_metrics_known_values():
    m = grade.classification_metrics(["bug", "bug", "question"], ["bug", "question", "question"])
    assert m["accuracy"] == pytest.approx(2 / 3)
    assert m["confusion"]["bug"]["question"] == 1
    assert list(m["confusion"]) == ["bug", "question", "feature_request"]
    # bug: P=1 R=.5 F1=2/3 ; question: P=.5 R=1 F1=2/3 ; feature: 0
    assert m["macro_f1"] == pytest.approx((2 / 3 + 2 / 3 + 0) / 3)


def test_classification_error_prediction_is_wrong():
    m = grade.classification_metrics(["bug", "bug"], ["bug", "오류"])
    assert m["accuracy"] == 0.5
    assert sum(sum(r.values()) for r in m["confusion"].values()) == 1


def test_extraction_counts_hallucination_and_miss():
    exp = [{"app_version": None, "device_model": "Pixel 8"}]
    m = grade.extraction_metrics(exp, [{"app_version": "1.0", "device_model": None}])
    assert m["fields"]["app_version"]["hallucination_rate"] == 1.0
    assert m["fields"]["device_model"]["miss_rate"] == 1.0
    assert m["fields"]["app_version"]["accuracy"] == 0.0


def test_extraction_version_normalized():
    exp = [{"app_version": "1.0.1", "android_version": "14", "device_model": "Galaxy S21  FE"}]
    pred = [{"app_version": "v1.0.1", "android_version": "14.0", "device_model": "galaxy s21 fe"}]
    m = grade.extraction_metrics(exp, pred)
    for f in ("app_version", "android_version", "device_model"):
        assert m["fields"][f]["accuracy"] == 1.0


def test_extraction_failed_case_is_wrong_and_presence():
    exp = [{"app_version": "1.0.1", "symptom": "x", "repro_steps": []}] * 2
    m = grade.extraction_metrics(exp, [None, {"app_version": "1.0.1", "symptom": "다르게 씀", "repro_steps": ["a"]}])
    assert m["fields"]["app_version"]["accuracy"] == 0.5
    assert m["presence"]["symptom"] == 0.5
    assert m["presence"]["repro_steps"] == 0.0


def test_completeness_mae_only_numeric_pairs():
    assert grade.completeness_mae([2, None, 0, 1], [1, None, 2, None]) == pytest.approx(1.5)
    assert grade.completeness_mae([None], [None]) is None


def test_priority_metrics():
    m = grade.priority_metrics(["P1", "P2", "P4"], ["P1", "P3", "P1"])
    assert m["exact"] == pytest.approx(1 / 3)
    assert m["within_1"] == pytest.approx(2 / 3)


def test_link_accuracy_none_matches_none():
    assert grade.link_accuracy([None, "I-1", None], [None, "I-2", "I-3"]) == pytest.approx(1 / 3)
    assert grade.link_accuracy([None], [None]) == 1.0
