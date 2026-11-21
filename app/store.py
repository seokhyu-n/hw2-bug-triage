"""Per-developer JSONL store: reports (rewritten atomically), chat history, shared step log."""
import dataclasses
import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path

from app.config import RUNTIME_DIR
from app.pipeline import StepLog
from app.schemas import TriageResult

# One process-wide re-entrant lock: FastAPI runs sync endpoints in a thread pool.
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _dump(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


class Store:
    def __init__(self, base_dir: Path = RUNTIME_DIR):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    # ---- helpers ----
    def _dev_dir(self, dev_id: str) -> Path:
        d = self.base / dev_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _load(self, dev_id: str) -> list[dict]:
        return _read_jsonl(self._dev_dir(dev_id) / "reports.jsonl")

    def _save(self, dev_id: str, reports: list[dict]) -> None:
        path = self._dev_dir(dev_id) / "reports.jsonl"
        tmp = path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            f.writelines(_dump(r) for r in reports)
        os.replace(tmp, path)

    def _next_id(self) -> str:
        highest = 0
        for sub in self.base.iterdir():
            if sub.is_dir():
                for r in _read_jsonl(sub / "reports.jsonl"):
                    m = re.fullmatch(r"R-(\d+)", r.get("request_id", ""))
                    if m:
                        highest = max(highest, int(m.group(1)))
        return f"R-{highest + 1:04d}"

    def _log(self, request_id: str, dev_id: str, logs: list[StepLog]) -> None:
        if not logs:
            return
        with (self.base / "logs.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            for log in logs:
                u = dataclasses.asdict(log.usage)
                f.write(_dump({
                    "request_id": request_id, "dev_id": dev_id, "step": log.step,
                    "model": log.model, "input_tokens": u["input_tokens"],
                    "output_tokens": u["output_tokens"], "cache_read": u["cache_read"],
                    "cache_write": u["cache_write"], "latency_s": log.latency_s,
                    "cost_usd": log.cost_usd, "at": _now(),
                }))

    # ---- reports ----
    def create_report(self, dev_id: str, text: str, result: TriageResult,
                      logs: list[StepLog]) -> str:
        with _LOCK:
            request_id = self._next_id()
            now = _now()
            reports = self._load(dev_id)
            reports.append({
                "request_id": request_id, "dev_id": dev_id, "text": text,
                "result": result.model_dump(mode="json"), "added_info": [],
                "created_at": now, "updated_at": now,
            })
            self._save(dev_id, reports)
            self._log(request_id, dev_id, logs)
        return request_id

    def get_report(self, dev_id: str, request_id: str) -> dict | None:
        for r in self._load(dev_id):
            if r["request_id"] == request_id:
                return r
        return None

    def list_reports(self, dev_id: str, priority: str | None = None,
                     category: str | None = None) -> list[dict]:
        rows = self._load(dev_id)
        if priority:
            rows = [r for r in rows if r["result"]["score"]["priority"] == priority]
        if category:
            rows = [r for r in rows if r["result"]["classification"]["category"] == category]
        # newest first (IDs only grow), then stable sort by priority P1 -> P4
        rows.sort(key=lambda r: r["request_id"], reverse=True)
        rows.sort(key=lambda r: r["result"]["score"]["priority"])
        return rows

    def update_report(self, dev_id: str, request_id: str, result: TriageResult,
                      logs: list[StepLog], added_info: str) -> None:
        with _LOCK:
            reports = self._load(dev_id)
            for r in reports:
                if r["request_id"] == request_id:
                    r["result"] = result.model_dump(mode="json")
                    r["added_info"].append(added_info)
                    r["updated_at"] = _now()
                    break
            else:
                raise KeyError(request_id)
            self._save(dev_id, reports)
            self._log(request_id, dev_id, logs)

    # ---- chat ----
    def append_chat(self, dev_id: str, role: str, content: str) -> None:
        with (self._dev_dir(dev_id) / "chat.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(_dump({"role": role, "content": content, "at": _now()}))

    def get_chat(self, dev_id: str) -> list[dict]:
        return _read_jsonl(self._dev_dir(dev_id) / "chat.jsonl")
