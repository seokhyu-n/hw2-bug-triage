"""Known issues the team registers while triaging (on top of the fixed dummy data in data/).

Registered issues and status overrides live in the runtime folder (`_issues.json`). The service
plugs them into the issue search used by the link step, the chatbot and the pre-submit suggestions;
the evaluation runner never does, so eval results stay comparable.
"""
import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path

from app.tools import _load, parse_version

_LOCK = threading.RLock()
FEATURE_AREAS = ("tracking", "map", "record", "card_image", "voice", "login", "ai_chat", "other")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class IssueRegistry:
    def __init__(self, base_dir: Path):
        self.path = Path(base_dir) / "_issues.json"

    def _read(self) -> dict:
        if not self.path.exists():
            return {"issues": [], "overrides": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def extra(self) -> list[dict]:
        """Registered issues plus status overrides of the dummy ones (used by tools.search)."""
        data = self._read()
        base_over = [{**i, **data["overrides"][i["id"]]} for i in _load("known_issues.json")
                     if i["id"] in data["overrides"]]
        return data["issues"] + base_over

    def all(self) -> list[dict]:
        data = self._read()
        base = [{**i, **data["overrides"].get(i["id"], {}), "source": "data"} for i in _load("known_issues.json")]
        return base + data["issues"]

    def get(self, issue_id: str) -> dict | None:
        return next((i for i in self.all() if i["id"] == issue_id), None)

    def add(self, *, title: str, feature_area: str | None, symptoms: list[str], affected_android: list[str],
            affected_app_versions: list[str], workaround: str | None, created_by: str) -> dict:
        with _LOCK:
            data = self._read()
            nums = [int(m.group(1)) for i in self.all() if (m := re.fullmatch(r"ISSUE-(\d+)", i["id"]))]
            issue = {"id": f"ISSUE-{max(nums, default=0) + 1:02d}", "title": title,
                     "feature_area": feature_area if feature_area in FEATURE_AREAS else "other",
                     "symptoms": symptoms, "affected_android": affected_android,
                     "affected_app_versions": affected_app_versions, "status": "open", "fixed_in": None,
                     "workaround": workaround, "source": "team", "created_by": created_by,
                     "created_at": _now()}
            data["issues"].append(issue)
            self._write(data)
            return issue

    def mark_fixed(self, issue_id: str, fixed_in: str) -> dict:
        if parse_version(fixed_in) is None:
            raise ValueError("수정 버전 형식이 올바르지 않습니다 (예: 1.2.1)")
        with _LOCK:
            data = self._read()
            for i in data["issues"]:
                if i["id"] == issue_id:
                    i.update(status="fixed", fixed_in=fixed_in, fixed_at=_now())
                    self._write(data)
                    return i
            if any(i["id"] == issue_id for i in _load("known_issues.json")):
                data["overrides"][issue_id] = {"status": "fixed", "fixed_in": fixed_in, "fixed_at": _now()}
                self._write(data)
                return self.get(issue_id)
        raise KeyError(issue_id)
