"""'Is it one of these?' suggestions shown before a report is submitted (no LLM call).

Matches the typed text against the known issues and the FAQ with character-bigram TF-IDF cosine
similarity (works for Korean without a morphological analyzer), then applies the version rules
the link step uses: an issue fixed in a version the reporter already has is not suggested (that is
a new bug or a regression and should be reported).
"""
import json
import math
import re
from collections import Counter
from functools import lru_cache

from app.config import DATA_DIR
from app.tools import _android_major, _load, parse_version

# Tuned on eval/dataset_v2.jsonl (120 reports): at 0.16 the expected known issue is suggested for
# 24 of 26 linked reports and never a wrong one; 30 of the 94 unlinked reports see a similar issue
# (mostly near misses such as a crash on a version that already has the fix). Suggestions never
# block a report. See tests/test_report_flow.py::test_suggest_quality_on_eval_set.
MIN_SCORE = 0.16
VERSION_BONUS = 0.05  # the reporter's Android / app version is in the issue's affected list
FAQ_KEYWORD_MIN = 0.05
FAQ_MIN_SCORE = 0.3
MAX_ISSUES = 2
MAX_FAQ = 2

_ANDROID_RE = re.compile(r"(?:안드로이드|안드|android)\s*(\d{1,2})", re.I)
_APP_RE = re.compile(r"(?:앱|버전|ver|v)\s*\.?\s*(\d+\.\d+(?:\.\d+)?)", re.I)


def _bigrams(text: str) -> Counter:
    s = re.sub(r"[^0-9a-z가-힣]+", " ", text.lower())
    grams = Counter()
    for word in s.split():
        if len(word) == 1:
            continue
        grams.update(word[i:i + 2] for i in range(len(word) - 1))
    return grams


@lru_cache(maxsize=1)
def _corpus():
    issues = _load("known_issues.json")
    faq = json.loads((DATA_DIR / "faq.json").read_text(encoding="utf-8"))
    docs = [("issue", i, _bigrams(i["title"] + " " + " ".join(i["symptoms"]))) for i in issues]
    docs += [("faq", f, _bigrams(f["question"] + " " + " ".join(f["keywords"]))) for f in faq]
    df = Counter(g for _, _, grams in docs for g in grams)
    n = len(docs)
    idf = {g: math.log((n + 1) / (c + 0.5)) for g, c in df.items()}
    vecs = [(kind, item, _weight(grams, idf)) for kind, item, grams in docs]
    return vecs, idf


def _weight(grams: Counter, idf: dict) -> dict:
    default = max(idf.values()) if idf else 1.0  # unseen bigram: rare
    return {g: c * idf.get(g, default) for g, c in grams.items()}


def _cosine(a: dict, b: dict) -> float:
    dot = sum(v * b[g] for g, v in a.items() if g in b)
    if not dot:
        return 0.0
    return dot / (math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values())))


def _versions(text: str, app_version: str | None, android_version: str | None):
    app = app_version or (m.group(1) if (m := _APP_RE.search(text)) else None)
    android = android_version or (m.group(1) if (m := _ANDROID_RE.search(text)) else None)
    return parse_version(app), _android_major(android)


def _issue_view(issue: dict, app) -> dict:
    fixed = issue.get("fixed_in")
    if fixed and app is not None:
        advice = f"앱을 {fixed} 이상으로 업데이트하면 해결되는 문제예요."
    elif fixed:
        advice = f"{fixed} 버전에서 수정된 문제예요. 앱 버전이 그보다 낮다면 업데이트해 주세요."
    else:
        advice = "개발팀이 알고 있고 수정 중인 문제예요. 신고하시면 같은 문제로 함께 처리돼요."
    return {"id": issue["id"], "title": issue["title"], "fixed_in": fixed,
            "advice": advice, "workaround": issue.get("workaround")}


def suggest(text: str, category: str | None = None, app_version: str | None = None,
            android_version: str | None = None) -> dict:
    text = text or ""
    if len(text.strip()) < 6:
        return {"issues": [], "faq": []}
    vecs, idf = _corpus()
    query = _weight(_bigrams(text), idf)
    app, android = _versions(text, app_version, android_version)
    issues, faq = [], []
    for kind, item, vec in vecs:
        score = _cosine(query, vec)
        if kind == "faq":
            # an FAQ needs one of its specific phrases (or a very close text): generic words such as
            # "위치 권한" also appear in real bug reports
            keyword = any(k.lower() in text.lower() for k in item["keywords"])
            if (keyword and score >= FAQ_KEYWORD_MIN) or score >= FAQ_MIN_SCORE:
                faq.append((score + keyword, {"id": item["id"], "question": item["question"],
                                              "answer": item["answer"]}))
            continue
        affected = item.get("affected_android") or []
        if android is not None and affected:
            if all(_android_major(v) != android for v in affected):
                continue  # a different Android version: not this issue
            score += VERSION_BONUS
        fixed = parse_version(item.get("fixed_in"))
        if app is not None and fixed is not None and app >= fixed:
            continue  # already on the fixed version: a new bug or a regression, so report it
        if app is not None and any(parse_version(v) == app for v in item.get("affected_app_versions", [])):
            score += VERSION_BONUS
        if score < MIN_SCORE:
            continue
        issues.append((score, _issue_view(item, app)))
    issues.sort(key=lambda s: -s[0])
    faq.sort(key=lambda s: -s[0])
    return {"issues": [i for _, i in issues[:MAX_ISSUES]], "faq": [f for _, f in faq[:MAX_FAQ]]}
