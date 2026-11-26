"""Lookup tools over the dummy issue data and a dispatcher for tool_use blocks."""
import json
import re
from functools import lru_cache

from app.config import DATA_DIR

_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def parse_version(text: str | None) -> tuple[int, int, int] | None:
    """'v1.0.1' / '1.0.1 버전' -> (1, 0, 1). Returns None when no version is found."""
    if not text:
        return None
    m = _VERSION_RE.search(text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def version_lt(a: str | None, b: str | None) -> bool | None:
    pa, pb = parse_version(a), parse_version(b)
    if pa is None or pb is None:
        return None
    return pa < pb


@lru_cache(maxsize=None)
def _load(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def _android_major(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"\d+", text)
    return int(m.group(0)) if m else None


def _norm_version(text: str | None) -> tuple[int, int, int] | None:
    return parse_version(text)


# The running service plugs in issues registered by the team (app/issues.py). Nothing else does,
# so the evaluation always searches the fixed dummy data only.
_extra_issues = None  # callable returning a list of issues (registered + status overrides)


def set_extra_issues(provider) -> None:
    global _extra_issues
    _extra_issues = provider


def known_issues() -> list[dict]:
    base = _load("known_issues.json")
    if _extra_issues is None:
        return base
    extra = _extra_issues()
    override = {i["id"]: i for i in extra}
    return [override.get(i["id"], i) for i in base] + [i for i in extra if i["id"] not in {b["id"] for b in base}]


def search_known_issues(keywords: list[str], feature_area: str | None = None,
                        android_version: str | None = None,
                        app_version: str | None = None) -> dict:
    kws = [k.strip().lower() for k in (keywords or []) if k and k.strip()]
    want_major = _android_major(android_version)
    want_app = _norm_version(app_version)
    scored = []
    for issue in known_issues():
        haystack = (issue["title"] + " " + " ".join(issue["symptoms"])).lower()
        hits = sum(1 for k in kws if k in haystack)
        if kws and hits == 0:
            continue  # metadata filters only reorder keyword hits
        score = hits
        if feature_area and issue["feature_area"] == feature_area:
            score += 1
        if want_major is not None and any(_android_major(v) == want_major for v in issue["affected_android"]):
            score += 1
        if want_app is not None and any(_norm_version(v) == want_app for v in issue["affected_app_versions"]):
            score += 1
        if score > 0:
            scored.append((score, issue))
    if not scored:
        return {"status": "not_found"}
    scored.sort(key=lambda s: -s[0])  # stable: ties keep file order
    return {"status": "ok", "issues": [_for_model(i) for _, i in scored[:5]]}


# Fields the code uses after the model's answer; the model never sees them, so adding them does not
# change what the link and score steps are given.
_CODE_ONLY_FIELDS = ("limited_scope",)


def _for_model(issue: dict) -> dict:
    return {k: v for k, v in issue.items() if k not in _CODE_ONLY_FIELDS}


def get_release_info(version: str) -> dict:
    target = parse_version(version)
    for rel in _load("releases.json"):
        if target is not None and parse_version(rel["version"]) == target:
            return {"status": "ok", "version": rel["version"], "date": rel["date"],
                    "fixed_issues": rel["fixed_issues"]}
    return {"status": "not_found"}


def _nullable_str(desc: str) -> dict:
    return {"type": ["string", "null"], "description": desc}


ISSUE_TOOL_DEFS: list[dict] = [
    {
        "name": "search_known_issues",
        "description": "RunBuddy 알려진 이슈 DB를 키워드, 기능 영역, 안드로이드/앱 버전으로 검색한다. 최대 5건 반환.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "keywords": {"type": "array", "items": {"type": "string"},
                             "description": "제목/증상에서 찾을 한국어 키워드 목록"},
                "feature_area": {  # anyOf: the API rejects enum combined with a type list
                    "anyOf": [
                        {"type": "string",
                         "enum": ["tracking", "map", "record", "card_image", "voice", "login", "ai_chat", "other"]},
                        {"type": "null"},
                    ],
                    "description": "기능 영역. 모르면 null",
                },
                "android_version": _nullable_str("안드로이드 버전(예: '14'). 모르면 null"),
                "app_version": _nullable_str("앱 버전(예: '1.0.1'). 모르면 null"),
            },
            "required": ["keywords", "feature_area", "android_version", "app_version"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_release_info",
        "description": "특정 앱 버전의 릴리스 날짜와 해당 버전에서 수정된 이슈 ID 목록을 조회한다.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"version": {"type": "string", "description": "앱 버전(예: '1.1.0')"}},
            "required": ["version"],
            "additionalProperties": False,
        },
    },
]

_TOOLS = {"search_known_issues": search_known_issues, "get_release_info": get_release_info}


def run_tool(name: str, tool_input: dict) -> tuple[str, bool]:
    """Execute a tool; returns (JSON string, is_error)."""
    fn = _TOOLS.get(name)
    if fn is None:
        return json.dumps({"error": f"알 수 없는 도구: {name}"}, ensure_ascii=False), True
    try:
        return json.dumps(fn(**tool_input), ensure_ascii=False), False
    except Exception as e:  # noqa: BLE001 - report any failure to the model as a tool error
        return json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False), True
