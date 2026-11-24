"""Per-developer JSONL store: reports (rewritten atomically), chat history, shared step log."""
import dataclasses
import hmac
import json
import os
import re
import secrets
import threading
from datetime import datetime
from pathlib import Path

from app.attachments import extension
from app.config import RUNTIME_DIR
from app.pipeline import StepLog
from app.schemas import TriageResult

# One process-wide re-entrant lock: FastAPI runs sync endpoints in a thread pool.
_LOCK = threading.RLock()
# Reports waiting for (or failed) analysis. Not a developer ID, so nobody can log in as it.
INTAKE_DIR = "_intake"
# Screenshots: _attachments/<request_id>/<n>.<ext> (the ID never changes, so files never move).
ATTACH_DIR = "_attachments"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _dump(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


def tracked_issue(record: dict) -> str | None:
    """A developer's explicit choice wins; otherwise the issue the AI linked (verified by tools)."""
    if "issue_id" in record:
        return record["issue_id"]
    link = (record.get("result") or {}).get("link") or {}
    return link.get("linked_issue_id")


def _summary(logs: list[StepLog]) -> dict:
    return {"latency_s": round(sum(l.latency_s for l in logs), 3),
            "cost_usd": round(sum(l.cost_usd for l in logs), 6),
            "cache_read": sum(l.usage.cache_read for l in logs)}


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

    # ---- intake queue (saved before analysis, so a failed analysis never loses a report) ----
    def enqueue(self, text: str, files: list[tuple[str, str, bytes]] | None = None,
                form: dict | None = None, log: tuple[str, bytes] | None = None,
                activity: dict | None = None) -> tuple[str, str]:
        """Save a new report as `pending` in the intake queue. Returns (request_id, status token).

        `files` are validated screenshots (display name, media type, bytes) and `log` a validated
        log file (display name, bytes); both are stored under server-made names in
        `_attachments/<request_id>/`. `form` keeps the structured fields the reporter filled in.
        The status token is the reporter's private link to the report (unguessable, unlike the ID).
        """
        with _LOCK:
            request_id = self._next_id()
            token = secrets.token_urlsafe(18)
            now = _now()
            attachments = self._save_files(request_id, files or [])
            entry = {"request_id": request_id, "text": text, "status": "pending",
                     "attempts": 0, "last_error": None, "attachments": attachments,
                     "form": form or {}, "log": self._save_log(request_id, log), "activity": activity,
                     "status_token": token, "created_at": now, "updated_at": now}
            queued = self._load(INTAKE_DIR)
            queued.append(entry)
            self._save(INTAKE_DIR, queued)
        return request_id, token

    def _save_log(self, request_id: str, log: tuple[str, bytes] | None) -> dict | None:
        if not log:
            return None
        name, data = log
        folder = self.base / ATTACH_DIR / request_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "log.txt").write_bytes(data)
        return {"name": name, "size": len(data), "file": "log.txt"}

    def log_text(self, record: dict) -> str | None:
        meta = record.get("log")
        if not meta:
            return None
        return self.attachment(record["request_id"], meta).decode("utf-8", errors="replace")

    def find_by_token(self, token: str) -> tuple[str | None, dict] | None:
        """(dev_id or None when still queued, record) for a reporter's status token."""
        if not token:
            return None
        for r in self._load(INTAKE_DIR):
            if hmac.compare_digest(r.get("status_token", ""), token):
                return None, r
        for sub in self.base.iterdir():
            if sub.is_dir() and not sub.name.startswith("_"):
                for r in _read_jsonl(sub / "reports.jsonl"):
                    if hmac.compare_digest(r.get("status_token", ""), token):
                        return sub.name, r
        return None

    # ---- attachments ----
    def _save_files(self, request_id: str, files: list[tuple[str, str, bytes]]) -> list[dict]:
        if not files:
            return []
        folder = self.base / ATTACH_DIR / request_id
        folder.mkdir(parents=True, exist_ok=True)
        meta = []
        for i, (name, media_type, data) in enumerate(files, start=1):
            stored = f"{i}.{extension(media_type)}"
            (folder / stored).write_bytes(data)
            meta.append({"name": name, "media_type": media_type, "size": len(data), "file": stored})
        return meta

    def attachment(self, request_id: str, meta: dict) -> bytes:
        return (self.base / ATTACH_DIR / request_id / meta["file"]).read_bytes()

    def images(self, record: dict) -> list[tuple[str, bytes]]:
        """(media type, bytes) of a report's screenshots, in upload order, for the analysis."""
        return [(m["media_type"], self.attachment(record["request_id"], m))
                for m in record.get("attachments", [])]

    def queued(self, status: str | None = None) -> list[dict]:
        rows = self._load(INTAKE_DIR)
        return [r for r in rows if status is None or r["status"] == status]

    def get_queued(self, request_id: str) -> dict | None:
        return next((r for r in self._load(INTAKE_DIR) if r["request_id"] == request_id), None)

    def set_queue_status(self, request_id: str, status: str, error: str | None = None,
                         count_attempt: bool = False) -> None:
        with _LOCK:
            queued = self._load(INTAKE_DIR)
            for r in queued:
                if r["request_id"] == request_id:
                    r["status"] = status
                    r["last_error"] = error
                    r["attempts"] += 1 if count_attempt else 0
                    r["updated_at"] = _now()
                    break
            else:
                raise KeyError(request_id)
            self._save(INTAKE_DIR, queued)

    def complete(self, request_id: str, dev_id: str, result: TriageResult,
                 logs: list[StepLog]) -> None:
        """Move an analyzed report out of the queue into its developer's list, keeping its ID."""
        with _LOCK:
            queued = self._load(INTAKE_DIR)
            entry = next((r for r in queued if r["request_id"] == request_id), None)
            if entry is None:
                raise KeyError(request_id)
            carried = {k: entry[k] for k in ("attachments", "form", "log", "status_token", "activity") if k in entry}
            self._append_report(dev_id, request_id, entry["text"], result, logs, entry["created_at"], carried)
            self._save(INTAKE_DIR, [r for r in queued if r["request_id"] != request_id])

    # ---- reports ----
    def _append_report(self, dev_id: str, request_id: str, text: str, result: TriageResult,
                       logs: list[StepLog], created_at: str, extra: dict | None = None) -> None:
        reports = self._load(dev_id)
        now = _now()
        reports.append({
            "request_id": request_id, "dev_id": dev_id, "text": text,
            "attachments": [], "form": {}, "log": None,
            **(extra or {}),
            "result": result.model_dump(mode="json"), "added_info": [],
            "workflow": {"state": "new", "message": None, "updated_at": now},
            "logs_summary": _summary(logs),
            "created_at": created_at, "updated_at": now,
        })
        self._save(dev_id, reports)
        self._log(request_id, dev_id, logs)

    def set_workflow(self, dev_id: str, request_id: str, state: str, message: str | None) -> dict:
        """Developer-side processing state and an optional message shown to the reporter."""
        with _LOCK:
            reports = self._load(dev_id)
            for r in reports:
                if r["request_id"] == request_id:
                    r["workflow"] = {"state": state, "message": message, "updated_at": _now()}
                    r["updated_at"] = _now()
                    break
            else:
                raise KeyError(request_id)
            self._save(dev_id, reports)
            return r

    # ---- team-level operations (issues, reassignment) ----
    def dev_ids(self) -> list[str]:
        return sorted(sub.name for sub in self.base.iterdir() if sub.is_dir() and not sub.name.startswith("_"))

    def all_reports(self) -> list[dict]:
        """Every assigned report of every developer (each record carries its dev_id)."""
        return [r for dev in self.dev_ids() for r in self._load(dev)]

    def move_report(self, from_dev: str, to_dev: str, request_id: str, note: str) -> dict:
        """Reassign a report to another developer, keeping its ID, history and status link."""
        with _LOCK:
            src = self._load(from_dev)
            rec = next((r for r in src if r["request_id"] == request_id), None)
            if rec is None:
                raise KeyError(request_id)
            rec["dev_id"] = to_dev
            rec.setdefault("history", []).append({"at": _now(), "event": "reassigned",
                                                  "from": from_dev, "to": to_dev, "note": note})
            rec["updated_at"] = _now()
            dst = self._load(to_dev)
            dst.append(rec)
            self._save(to_dev, dst)  # write the copy first: a crash in between never loses the report
            self._save(from_dev, [r for r in src if r["request_id"] != request_id])
            return rec

    def set_issue(self, dev_id: str, request_id: str, issue_id: str | None) -> dict:
        """The known issue a developer filed this report under (overrides the AI link for tracking)."""
        def change(r):
            r["issue_id"] = issue_id
            return r
        return self._edit(dev_id, request_id, change)

    def resolve_issue_reports(self, issue_id: str, message: str) -> list[str]:
        """Mark every open report tracked under issue_id as resolved, with a message for its reporter."""
        done = []
        with _LOCK:
            for dev in self.dev_ids():
                reports = self._load(dev)
                changed = False
                for r in reports:
                    wf = r.get("workflow") or {"state": "new"}
                    if tracked_issue(r) == issue_id and wf["state"] in ("new", "in_progress"):
                        r["workflow"] = {"state": "resolved", "message": message, "updated_at": _now()}
                        r["updated_at"] = _now()
                        done.append(r["request_id"])
                        changed = True
                if changed:
                    self._save(dev, reports)
        return done

    # ---- reporter replies (answers to the questions shown on the status page) ----
    def _edit(self, dev_id: str, request_id: str, change) -> dict:
        with _LOCK:
            reports = self._load(dev_id)
            for r in reports:
                if r["request_id"] == request_id:
                    out = change(r)
                    r["updated_at"] = _now()
                    self._save(dev_id, reports)
                    return out
            raise KeyError(request_id)

    def add_reply(self, dev_id: str, request_id: str, text: str) -> int:
        """Save the reporter's answer first (state `pending` until the re-analysis is done)."""
        def change(r):
            r.setdefault("replies", []).append({"text": text, "at": _now(), "state": "pending"})
            return len(r["replies"]) - 1
        return self._edit(dev_id, request_id, change)

    def set_reply_state(self, dev_id: str, request_id: str, index: int, state: str) -> None:
        self._edit(dev_id, request_id, lambda r: r["replies"][index].update(state=state))

    def apply_reply(self, dev_id: str, request_id: str, index: int, result: TriageResult,
                    logs: list[StepLog]) -> None:
        def change(r):
            r["result"] = result.model_dump(mode="json")
            r["logs_summary"] = _summary(logs)
            r["replies"][index]["state"] = "applied"
        self._edit(dev_id, request_id, change)
        with _LOCK:
            self._log(request_id, dev_id, logs)

    def pending_replies(self) -> list[tuple[str, str, int]]:
        out = []
        for sub in self.base.iterdir():
            if sub.is_dir() and not sub.name.startswith("_"):
                for r in _read_jsonl(sub / "reports.jsonl"):
                    for i, reply in enumerate(r.get("replies", [])):
                        if reply["state"] == "pending":
                            out.append((sub.name, r["request_id"], i))
        return out

    def create_report(self, dev_id: str, text: str, result: TriageResult,
                      logs: list[StepLog]) -> str:
        with _LOCK:
            request_id = self._next_id()
            self._append_report(dev_id, request_id, text, result, logs, _now())
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
                    r["logs_summary"] = _summary(logs)
                    r["updated_at"] = _now()
                    break
            else:
                raise KeyError(request_id)
            self._save(dev_id, reports)
            self._log(request_id, dev_id, logs)

    # ---- chat ----
    def append_chat(self, dev_id: str, role: str, content: str) -> None:
        with _LOCK, (self._dev_dir(dev_id) / "chat.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(_dump({"role": role, "content": content, "at": _now()}))

    def get_chat(self, dev_id: str) -> list[dict]:
        return _read_jsonl(self._dev_dir(dev_id) / "chat.jsonl")
