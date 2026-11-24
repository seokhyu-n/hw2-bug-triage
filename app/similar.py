"""'Same symptom' groups among bug reports.

Two reports are grouped when they are tracked under the same issue, or when both are bugs of the
same feature area and their text + extracted symptom are similar (character-bigram cosine).
Bigram weights come from the fixed issue/FAQ corpus (app/suggest.py), so a pair's score does not
change as more reports arrive.

Threshold from eval/dataset_v2.jsonl (bug pairs linked to the same known issue vs different ones):
at 0.2, 16 of 20 same-issue pairs are found; of the 67 different-issue pairs in the same feature
area, 4 are joined. Groups are advice for the developer, never an automatic change.
"""
from app.store import tracked_issue
from app.suggest import _bigrams, _corpus, _cosine, _weight

THRESHOLD = 0.2


def _is_bug(r: dict) -> bool:
    return bool(r.get("result")) and "bug" in r["result"]["classification"]["labels"]


def _text(r: dict) -> str:
    ex = r["result"]["extraction"]
    desc = r["text"].split("\n\n[신고 양식")[0]
    return " ".join(filter(None, [desc, ex.get("symptom"), ex.get("actual")]))


def groups(reports: list[dict]) -> dict[str, list[str]]:
    """request_id -> IDs of the other reports with the same symptom (bugs only)."""
    bugs = [r for r in reports if _is_bug(r)]
    _, idf = _corpus()
    vecs = {r["request_id"]: _weight(_bigrams(_text(r)), idf) for r in bugs}
    out: dict[str, list[str]] = {r["request_id"]: [] for r in bugs}
    for i, a in enumerate(bugs):
        for b in bugs[i + 1:]:
            ia, ib = tracked_issue(a), tracked_issue(b)
            if ia or ib:
                same = ia is not None and ia == ib
            else:
                fa = a["result"]["extraction"].get("feature_area")
                fb = b["result"]["extraction"].get("feature_area")
                same = fa == fb and _cosine(vecs[a["request_id"]], vecs[b["request_id"]]) >= THRESHOLD
            if same:
                out[a["request_id"]].append(b["request_id"])
                out[b["request_id"]].append(a["request_id"])
    return out
