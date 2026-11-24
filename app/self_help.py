"""Device self-check guides (data/self_help.json): settings a reporter can try before reporting.

Running apps document the same causes of "the run stopped recording": Samsung's app sleeping
(Runkeeper, MapMyRun, Samsung support), iPhone Low Power Mode and location permission, and starting
before GPS has a fix (Nike Run Club). The match is by phone family + symptom keywords, no LLM.
The same match is shown to the developer as "기기 설정 원인 가능성", never as a verdict.
"""
import json
from functools import lru_cache

from app.config import DATA_DIR


@lru_cache(maxsize=1)
def guides() -> list[dict]:
    return json.loads((DATA_DIR / "self_help.json").read_text(encoding="utf-8"))


def family(device_model: str | None, platform: str | None = None) -> str | None:
    """galaxy / iphone / None from the picked model name or the extracted platform."""
    name = (device_model or "").lower()
    if "갤럭시" in name or "galaxy" in name:
        return "galaxy"
    if "아이폰" in name or "iphone" in name or platform == "ios":
        return "iphone"
    return None


def match(text: str, device_model: str | None = None, platform: str | None = None) -> list[dict]:
    fam = family(device_model, platform)
    out = []
    for g in guides():
        want = g["when"]["family"]
        if want != "any" and want != fam:
            continue
        if any(k in (text or "") for k in g["when"]["keywords"]):
            out.append({k: g[k] for k in ("id", "title", "steps", "note", "source")})
    return out


def match_record(record: dict) -> list[dict]:
    """For a saved report: its text + the device/platform the analysis extracted (or the form)."""
    ex = (record.get("result") or {}).get("extraction") or {}
    device = (record.get("form") or {}).get("device_model") or ex.get("device_model")
    text = record.get("text", "").split("\n\n[연결된 러닝 기록]")[0]  # the record summary is data, not symptoms
    return match(text, device, ex.get("platform"))
