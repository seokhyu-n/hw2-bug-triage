"""Pure grading functions for the triage eval (no I/O, no LLM)."""
from __future__ import annotations

import re

from app.tools import parse_version

LABELS = ("bug", "question", "feature_request")
# Graded for exact accuracy (structured values).
STRUCT_FIELDS = ("device_model", "android_version", "app_version", "feature_area", "frequency")
# Free text / lists: paraphrases are fine, so only null-vs-non-null agreement is reported.
PRESENCE_FIELDS = ("symptom", "expected", "actual", "repro_steps")


def _norm_text(v) -> str | None:
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip().casefold()
    return s or None


def _norm_field(field: str, v) -> object:
    s = _norm_text(v)
    if s is None:
        return None
    if field == "app_version":
        return parse_version(s) or s
    if field == "android_version":
        m = re.search(r"\d+", s)
        return int(m.group()) if m else s
    return s


def _present(v) -> bool:
    if v is None:
        return False
    if isinstance(v, (list, tuple)):
        return any(_norm_text(x) for x in v)
    return _norm_text(v) is not None


def _div(a: float, b: float) -> float | None:
    return a / b if b else None


def classification_metrics(expected: list[str], predicted: list[str]) -> dict:
    """Accuracy, macro-F1 over the 3 fixed labels, and confusion[expected][predicted].
    Predictions outside LABELS (e.g. errors) count as wrong and stay out of the matrix."""
    confusion = {e: {p: 0 for p in LABELS} for e in LABELS}
    for e, p in zip(expected, predicted):
        if e in confusion and p in confusion[e]:
            confusion[e][p] += 1
    correct = sum(e == p for e, p in zip(expected, predicted))
    f1s = []
    for lab in LABELS:
        tp = sum(1 for e, p in zip(expected, predicted) if e == lab and p == lab)
        fp = sum(1 for e, p in zip(expected, predicted) if e != lab and p == lab)
        fn = sum(1 for e, p in zip(expected, predicted) if e == lab and p != lab)
        denom = 2 * tp + fp + fn
        f1s.append(2 * tp / denom if denom else 0.0)
    return {"accuracy": _div(correct, len(expected)) or 0.0, "macro_f1": sum(f1s) / len(LABELS),
            "confusion": confusion}


def extraction_metrics(expected: list[dict], predicted: list[dict | None]) -> dict:
    """Per-field accuracy / hallucination_rate (expected null, predicted a value) / miss_rate
    (expected a value, predicted null). A None prediction (failed case) is wrong and excluded
    from hallucination/miss. Top level has pooled accuracy and hallucination_rate over STRUCT_FIELDS,
    `fields` has the per-field breakdown, `presence` the null-vs-non-null agreement of free-text fields."""
    fields: dict[str, dict] = {}
    tot = {"n": 0, "ok": 0, "h": 0, "h_den": 0, "m": 0, "m_den": 0}
    for f in STRUCT_FIELDS:
        n = ok = h = h_den = m = m_den = 0
        for e, p in zip(expected, predicted):
            n += 1
            if p is None:
                continue
            en, pn = _norm_field(f, e.get(f)), _norm_field(f, p.get(f))
            ok += en == pn
            if en is None:
                h_den += 1
                h += pn is not None
            else:
                m_den += 1
                m += pn is None
        fields[f] = {"accuracy": _div(ok, n), "hallucination_rate": _div(h, h_den), "miss_rate": _div(m, m_den)}
        for k, v in zip(("n", "ok", "h", "h_den", "m", "m_den"), (n, ok, h, h_den, m, m_den)):
            tot[k] += v
    presence = {}
    for f in PRESENCE_FIELDS:
        n = sum(1 for _ in expected)
        ok = sum(1 for e, p in zip(expected, predicted) if p is not None and _present(e.get(f)) == _present(p.get(f)))
        presence[f] = _div(ok, n)
    return {"accuracy": _div(tot["ok"], tot["n"]), "hallucination_rate": _div(tot["h"], tot["h_den"]),
            "miss_rate": _div(tot["m"], tot["m_den"]), "fields": fields, "presence": presence}


def completeness_mae(expected: list, predicted: list) -> float | None:
    pairs = [(e, p) for e, p in zip(expected, predicted)
             if isinstance(e, (int, float)) and isinstance(p, (int, float))]
    return sum(abs(e - p) for e, p in pairs) / len(pairs) if pairs else None


def _prio(v) -> int | None:
    m = re.fullmatch(r"P([1-4])", v) if isinstance(v, str) else None
    return int(m.group(1)) if m else None


def priority_metrics(expected: list[str], predicted: list[str | None]) -> dict:
    n = len(expected)
    exact = within = 0
    for e, p in zip(expected, predicted):
        ei, pi = _prio(e), _prio(p)
        if ei is None or pi is None:
            continue
        exact += ei == pi
        within += abs(ei - pi) <= 1
    return {"exact": _div(exact, n), "within_1": _div(within, n)}


def link_accuracy(expected: list, predicted: list) -> float | None:
    """None == None counts as correct."""
    return _div(sum(e == p for e, p in zip(expected, predicted)), len(expected))
