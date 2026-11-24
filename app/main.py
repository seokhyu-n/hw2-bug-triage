"""FastAPI service: public report intake, developer login, triage view, reanalysis, chatbot, static UI."""
import json
import queue
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator
from starlette.datastructures import UploadFile as StarletteUpload

from app import auth
from app.attachments import MAX_BYTES, MAX_FILES, AttachmentError, Upload
from app.attachments import validate as validate_attachments
from app.report_form import LOG_MAX_BYTES, FormError, ReportForm, validate_log
from app.issues import IssueRegistry
from app.ratelimit import RateLimiter
from app.similar import groups as similar_groups
from app.store import tracked_issue
from app.suggest import suggest
from app.tools import set_extra_issues
from app.auth import current_dev
from app.chat import chat_turn
from app.config import ROOT, RUNTIME_DIR
from app.intake import FAILED_OWNER, IntakeWorker
from app.llm import LLMError, LLMRefusal, LLMTruncated, LLMUnavailable
from app.pipeline import analyze
from app.schemas import TriageResult
from app.store import Store

STATIC_DIR = ROOT / "static"
MAX_REPORT_CHARS = 5000

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background analysis and resume reports that were still pending when the server stopped.
    app.state.worker.start()
    yield


app = FastAPI(title="RunBuddy Bug Triage", lifespan=lifespan)
app.state.store = Store(RUNTIME_DIR)
app.state.worker = IntakeWorker(app.state.store)
app.state.limiter = RateLimiter()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
# issues the team registers join the issue search of the live service (never the evaluation)
set_extra_issues(lambda: IssueRegistry(app.state.store.base).extra())


def _store(request: Request) -> Store:
    return request.app.state.store


def _issues(request: Request) -> IssueRegistry:
    return IssueRegistry(_store(request).base)


def _limit(request: Request, endpoint: str) -> None:
    request.app.state.limiter.check(request, endpoint)


def _worker(request: Request) -> IntakeWorker:
    return request.app.state.worker


def _nonblank(v: str) -> str:
    if not v.strip():
        raise ValueError("내용을 입력해 주세요")
    return v


class LoginIn(BaseModel):
    dev_id: str


class ReportIn(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def _check(cls, v: str) -> str:
        _nonblank(v)
        if len(v) > MAX_REPORT_CHARS:
            raise ValueError(f"제보는 {MAX_REPORT_CHARS:,}자 이하여야 합니다")
        return v


class SuggestIn(BaseModel):
    text: str = Field(max_length=MAX_REPORT_CHARS)
    category: str | None = None
    app_version: str | None = Field(default=None, max_length=20)
    android_version: str | None = Field(default=None, max_length=20)


class WorkflowIn(BaseModel):
    state: Literal["new", "in_progress", "resolved", "wont_fix"]
    message: str | None = Field(default=None, max_length=1000)

    @field_validator("message")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() or None if v else None


class ReplyIn(BaseModel):
    text: str = Field(max_length=2000)

    @field_validator("text")
    @classmethod
    def _check(cls, v: str) -> str:
        return _nonblank(v).strip()


class ReanalyzeIn(BaseModel):
    added_info: str

    @field_validator("added_info")
    @classmethod
    def _check(cls, v: str) -> str:
        return _nonblank(v)


class ChatIn(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def _check(cls, v: str) -> str:
        return _nonblank(v)


def _llm_http_error(exc: LLMError) -> HTTPException:
    if isinstance(exc, (LLMRefusal, LLMTruncated)):
        return HTTPException(422, "모델이 이 제보를 처리하지 못했습니다. 내용을 확인하고 다시 시도해 주세요.")
    if isinstance(exc, LLMUnavailable):
        return HTTPException(502, "분석 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.")
    return HTTPException(502, "분석 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")


def _view(record: dict) -> dict:
    out = dict(record)
    out.pop("status_token", None)  # the reporter's link stays with the reporter
    out["status"] = "done"
    out.setdefault("logs_summary", {"latency_s": 0.0, "cost_usd": 0.0, "cache_read": 0})
    out["assigned_to"] = record["dev_id"]
    return out


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/app")
def app_page():
    return FileResponse(STATIC_DIR / "app.html")


@app.post("/api/login")
def login(body: LoginIn, response: Response):
    dev_id = body.dev_id.strip()
    try:
        token = auth.login(dev_id)
    except ValueError:
        raise HTTPException(401, "등록되지 않은 개발자 ID입니다")
    response.set_cookie("session", token, httponly=True, samesite="lax")
    return {"dev_id": dev_id}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    auth.logout(request.cookies.get("session"))
    response.delete_cookie("session")
    return {"ok": True}


@app.get("/api/me")
def me(dev_id: str = Depends(current_dev)):
    return {"dev_id": dev_id}


@app.get("/report")
def report_page():
    return FileResponse(STATIC_DIR / "report.html")


FORM_KEYS = ("text", "category", "frequency", "device_model", "android_version", "app_version",
             "steps", "expected", "actual")


async def _read_intake(request: Request) -> tuple[dict, list[Upload], Upload | None]:
    """JSON (app/API clients: the same keys, no files) or a multipart form (report page) with
    up to 3 `files` screenshots and one `log` text file."""
    ctype = request.headers.get("content-type", "")
    if ctype.startswith(("multipart/form-data", "application/x-www-form-urlencoded")):
        form = await request.form(max_files=MAX_FILES + 3, max_fields=len(FORM_KEYS) + 2)
        fields = {k: v for k in FORM_KEYS if isinstance(v := form.get(k), str)}
        uploads = []
        for f in form.getlist("files"):
            if isinstance(f, StarletteUpload):
                data = await f.read(MAX_BYTES + 1)  # one byte over is enough to reject
                uploads.append(Upload(f.filename or "", data))
        log_file = form.get("log")
        log = None
        if isinstance(log_file, StarletteUpload):
            log = Upload(log_file.filename or "", await log_file.read(LOG_MAX_BYTES + 1))
        return fields, uploads, log
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(422, "요청 형식이 올바르지 않습니다")
    if not isinstance(body, dict):
        raise HTTPException(422, "요청 형식이 올바르지 않습니다")
    return {k: v for k in FORM_KEYS if isinstance(v := body.get(k), str)}, [], None


@app.post("/api/intake")
async def intake(request: Request):
    """Public intake for reporters (app users, QA, support). No login.

    The report (screenshots, log) is saved first and the receipt number returned at once; the
    analysis and the assignment run in the background (`app/intake.py`), so an API failure never
    loses a report. The reporter gets the receipt number and a private status link; the triage
    result and the assignee stay on the developer side.
    """
    _limit(request, "intake")
    fields, uploads, log_upload = await _read_intake(request)
    try:
        body = ReportIn(text=fields.get("text", ""))
    except ValidationError as e:
        raise RequestValidationError(e.errors(include_url=False))
    try:
        form = ReportForm.parse(fields)
        files = validate_attachments(uploads)
        log = validate_log(log_upload.filename, log_upload.data) if log_upload else None
    except (AttachmentError, FormError) as e:
        raise HTTPException(422, str(e))
    rid, token = await run_in_threadpool(_store(request).enqueue, form.compose(body.text), files,
                                         form.as_dict(), log)
    _worker(request).submit(rid)
    return {"request_id": rid, "status_url": f"/status/{token}",
            "message": f"제보가 접수되었습니다. 접수 번호는 {rid}입니다. 담당 개발자가 확인할 예정입니다."}


@app.post("/api/intake/suggest")
def intake_suggest(body: SuggestIn, request: Request):
    """Before submitting: known issues and FAQ entries that look like this report (no LLM call)."""
    _limit(request, "suggest")
    return suggest(body.text, category=body.category, app_version=body.app_version,
                   android_version=body.android_version)


def _queue_view(entry: dict) -> dict:
    """A report still waiting for (or failed) analysis: no result yet."""
    out = {**entry, "result": None, "added_info": [], "assigned_to": None,
           "logs_summary": {"latency_s": 0.0, "cost_usd": 0.0, "cache_read": 0}}
    out.pop("status_token", None)  # the reporter's link stays with the reporter
    return out


def _sees_queue(dev_id: str) -> bool:
    return dev_id == FAILED_OWNER


@app.get("/api/reports")
def list_reports(request: Request, priority: str | None = None, category: str | None = None,
                 dev_id: str = Depends(current_dev)):
    store = _store(request)
    sim = _similar(store)
    rows = [_with_team_info(_view(r), dev_id, sim, store) for r in store.list_reports(dev_id, priority, category)]
    if _sees_queue(dev_id) and not (priority or category):
        # failed first (they need action), then reports still being analyzed; newest first
        queued = sorted(store.queued(), key=lambda r: r["request_id"], reverse=True)
        queued.sort(key=lambda r: r["status"] != "failed")
        rows = [_queue_view(r) for r in queued] + rows
    return rows


def _own_report(request: Request, dev_id: str, request_id: str) -> dict:
    record = _store(request).get_report(dev_id, request_id)
    if record is None:
        raise HTTPException(404, "제보를 찾을 수 없습니다")
    return record


@app.get("/api/reports/{request_id}")
def get_report(request_id: str, request: Request, dev_id: str = Depends(current_dev)):
    store = _store(request)
    if _sees_queue(dev_id) and (entry := store.get_queued(request_id)) is not None:
        return _queue_view(entry)
    return _with_team_info(_view(_own_report(request, dev_id, request_id)), dev_id, _similar(store), store)


# ---------- same-symptom groups, known issues, reassignment ----------

def _similar(store: Store) -> tuple[dict[str, list[str]], dict[str, str]]:
    """(request_id -> similar report IDs, request_id -> owner) across the whole team."""
    reports = store.all_reports()
    return similar_groups(reports), {r["request_id"]: r["dev_id"] for r in reports}


def _with_team_info(view: dict, dev_id: str, sim: tuple, store: Store) -> dict:
    """Similar reports: own ones by ID, other developers' only as a count (each sees their own list)."""
    groups, owner = sim
    others = groups.get(view["request_id"], [])
    view["similar"] = sorted(r for r in others if owner.get(r) == dev_id)
    view["similar_elsewhere"] = sum(owner.get(r) != dev_id for r in others)
    view["issue_id"] = tracked_issue(view)
    return view


class IssueIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    symptoms: list[str] = Field(default_factory=list, max_length=10)
    workaround: str | None = Field(default=None, max_length=500)
    report_ids: list[str] = Field(min_length=1, max_length=50)


class ResolveIn(BaseModel):
    fixed_in: str = Field(max_length=20)
    message: str | None = Field(default=None, max_length=1000)


class TrackIn(BaseModel):
    issue_id: str | None = Field(default=None, max_length=20)


class AssignIn(BaseModel):
    dev_id: str
    note: str | None = Field(default=None, max_length=300)


@app.get("/api/developers")
def developers(dev_id: str = Depends(current_dev)):
    return [{"dev_id": d, "areas": areas} for d, areas in auth.load_developers().items()]


@app.get("/api/issues")
def list_issues(request: Request, dev_id: str = Depends(current_dev)):
    """Known issues (dummy data + registered by the team) with how many open reports track each."""
    reports = _store(request).all_reports()
    out = []
    for issue in _issues(request).all():
        tracked = [r for r in reports if tracked_issue(r) == issue["id"]]
        out.append({**issue, "reports": len(tracked),
                    "open_reports": sum((r.get("workflow") or {"state": "new"})["state"] in ("new", "in_progress")
                                        for r in tracked),
                    "my_reports": sorted(r["request_id"] for r in tracked if r["dev_id"] == dev_id)})
    return out


@app.post("/api/issues")
def register_issue(body: IssueIn, request: Request, dev_id: str = Depends(current_dev)):
    """Register a new known issue from own reports; they are filed under it, and later reporters
    with the same symptom see it before submitting."""
    store = _store(request)
    reports = [_own_report(request, dev_id, rid) for rid in dict.fromkeys(body.report_ids)]
    ex = [r["result"]["extraction"] for r in reports if r.get("result")]
    issue = _issues(request).add(
        title=body.title.strip(),
        feature_area=next((e["feature_area"] for e in ex if e.get("feature_area")), None),
        symptoms=[s.strip() for s in body.symptoms if s.strip()]
        or list(dict.fromkeys(e["symptom"] for e in ex if e.get("symptom")))[:5],
        affected_android=sorted({e["android_version"] for e in ex if e.get("android_version")}),
        affected_app_versions=sorted({e["app_version"] for e in ex if e.get("app_version")}),
        workaround=(body.workaround or "").strip() or None, created_by=dev_id)
    for r in reports:
        store.set_issue(dev_id, r["request_id"], issue["id"])
    return issue


@app.post("/api/issues/{issue_id}/resolve")
def resolve_issue(issue_id: str, body: ResolveIn, request: Request, dev_id: str = Depends(current_dev)):
    """Mark an issue fixed in a version and tell every open report's reporter at once."""
    try:
        issue = _issues(request).mark_fixed(issue_id, body.fixed_in.strip())
    except KeyError:
        raise HTTPException(404, "이슈를 찾을 수 없습니다")
    except ValueError as e:
        raise HTTPException(422, str(e))
    message = (body.message or "").strip() or (
        f"{issue['fixed_in']} 버전에서 수정됐어요. 앱을 {issue['fixed_in']} 이상으로 업데이트해 주세요. 알려 주셔서 감사합니다.")
    resolved = _store(request).resolve_issue_reports(issue_id, message)
    return {"issue": issue, "resolved_reports": resolved, "message": message}


@app.post("/api/reports/{request_id}/issue")
def track_issue(request_id: str, body: TrackIn, request: Request, dev_id: str = Depends(current_dev)):
    """File a report under an existing issue (or clear it with null)."""
    _own_report(request, dev_id, request_id)
    if body.issue_id is not None and _issues(request).get(body.issue_id) is None:
        raise HTTPException(404, "이슈를 찾을 수 없습니다")
    store = _store(request)
    store.set_issue(dev_id, request_id, body.issue_id)
    return _with_team_info(_view(store.get_report(dev_id, request_id)), dev_id, _similar(store), store)


@app.post("/api/reports/{request_id}/assign")
def assign_report(request_id: str, body: AssignIn, request: Request, dev_id: str = Depends(current_dev)):
    """Hand a report to another developer (e.g. the AI picked the wrong feature area)."""
    _own_report(request, dev_id, request_id)
    if body.dev_id not in auth.load_developers() or body.dev_id == dev_id:
        raise HTTPException(422, "넘길 수 없는 개발자 ID입니다")
    _store(request).move_report(dev_id, body.dev_id, request_id, (body.note or "").strip())
    return {"request_id": request_id, "assigned_to": body.dev_id}


@app.get("/api/reports/{request_id}/attachments/{index}")
def get_attachment(request_id: str, index: int, request: Request, dev_id: str = Depends(current_dev)):
    """A report's screenshot, only for the developer who can see that report."""
    store = _store(request)
    record = store.get_queued(request_id) if _sees_queue(dev_id) else None
    if record is None:
        record = _own_report(request, dev_id, request_id)
    files = record.get("attachments", [])
    if not 1 <= index <= len(files):
        raise HTTPException(404, "첨부 파일을 찾을 수 없습니다")
    meta = files[index - 1]
    return Response(store.attachment(request_id, meta), media_type=meta["media_type"],
                    headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600",
                             "Content-Security-Policy": "default-src 'none'"})


@app.get("/api/reports/{request_id}/log")
def get_log(request_id: str, request: Request, dev_id: str = Depends(current_dev)):
    """The attached log as plain text, only for the developer who can see the report."""
    store = _store(request)
    record = store.get_queued(request_id) if _sees_queue(dev_id) else None
    if record is None:
        record = _own_report(request, dev_id, request_id)
    if not record.get("log"):
        raise HTTPException(404, "첨부된 로그가 없습니다")
    return Response(store.log_text(record), media_type="text/plain; charset=utf-8",
                    headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'"})


@app.post("/api/reports/{request_id}/workflow")
def set_workflow(request_id: str, body: WorkflowIn, request: Request, dev_id: str = Depends(current_dev)):
    """Processing state (new / in progress / resolved / won't fix) and a message for the reporter."""
    _own_report(request, dev_id, request_id)
    return _view(_store(request).set_workflow(dev_id, request_id, body.state, body.message))


# ---------- reporter status page (private link, no login) ----------

WORKFLOW_LABEL = {"new": "접수됨", "in_progress": "개발자 확인 중", "resolved": "수정 완료", "wont_fix": "처리 종료"}
MAX_REPLIES = 5


def _status_view(dev_id: str | None, record: dict) -> dict:
    """What the reporter may see: never priority, classification, assignee or internal notes."""
    out = {"request_id": record["request_id"], "created_at": record["created_at"],
           "text": record["text"], "screenshots": len(record.get("attachments", [])),
           "questions": [], "replies": [{"text": r["text"], "at": r["at"], "state": r["state"]}
                                        for r in record.get("replies", [])],
           "developer_message": None, "can_reply": False}
    if dev_id is None:  # still in the intake queue
        out["stage"] = "analyzing" if record["status"] == "pending" else "checking"
        out["stage_label"] = "접수 확인 중" if record["status"] == "pending" else "담당자 확인 중"
        return out
    wf = record.get("workflow") or {"state": "new", "message": None}
    out["stage"] = wf["state"]
    out["stage_label"] = WORKFLOW_LABEL[wf["state"]]
    out["developer_message"] = wf.get("message")
    open_ = wf["state"] in ("new", "in_progress")
    result = record["result"]
    if open_ and result["answer_status"] == "need_info":
        out["questions"] = result["score"]["questions_to_reporter"]
    out["can_reply"] = open_ and len(out["replies"]) < MAX_REPLIES
    return out


def _by_token(request: Request, token: str) -> tuple[str | None, dict]:
    found = _store(request).find_by_token(token)
    if found is None:
        raise HTTPException(404, "신고를 찾을 수 없습니다. 링크를 다시 확인해 주세요.")
    return found


@app.get("/status/{token}")
def status_page(token: str):
    return FileResponse(STATIC_DIR / "status.html", headers={"Referrer-Policy": "no-referrer"})


@app.get("/api/status/{token}")
def get_status(token: str, request: Request):
    _limit(request, "status")
    return _status_view(*_by_token(request, token))


@app.post("/api/status/{token}/reply")
def reporter_reply(token: str, body: ReplyIn, request: Request):
    """The reporter answers the questions; saved first, then the report is re-analyzed with it."""
    _limit(request, "reply")
    dev_id, record = _by_token(request, token)
    view = _status_view(dev_id, record)
    if dev_id is None:
        raise HTTPException(409, "아직 접수를 확인하고 있어요. 잠시 후 다시 시도해 주세요.")
    if not view["can_reply"]:
        raise HTTPException(409, "이 신고에는 더 답변할 수 없어요.")
    index = _store(request).add_reply(dev_id, record["request_id"], body.text)
    _worker(request).submit_reply(dev_id, record["request_id"], index)
    dev_id, record = _by_token(request, token)
    return _status_view(dev_id, record)


@app.post("/api/reports/{request_id}/retry")
def retry_analysis(request_id: str, request: Request, dev_id: str = Depends(current_dev)):
    """Run the analysis again for a report whose background analysis failed."""
    store = _store(request)
    entry = store.get_queued(request_id) if _sees_queue(dev_id) else None
    if entry is None:
        raise HTTPException(404, "제보를 찾을 수 없습니다")
    if entry["status"] != "failed":
        raise HTTPException(409, "이미 분석 중인 제보입니다")
    store.set_queue_status(request_id, "pending", entry["last_error"])
    _worker(request).submit(request_id)
    return {"request_id": request_id, "status": "pending"}


@app.post("/api/reports/{request_id}/reanalyze")
def reanalyze(request_id: str, body: ReanalyzeIn, request: Request, dev_id: str = Depends(current_dev)):
    record = _own_report(request, dev_id, request_id)
    try:
        result, logs = analyze(record["text"], prior=TriageResult.model_validate(record["result"]),
                               added_info=body.added_info)
    except LLMError as exc:
        raise _llm_http_error(exc)
    store = _store(request)
    store.update_report(dev_id, request_id, result, logs, body.added_info)
    return _view(store.get_report(dev_id, request_id))


@app.post("/api/chat")
def chat(body: ChatIn, request: Request, dev_id: str = Depends(current_dev)):
    try:
        reply = chat_turn(dev_id, body.message, _store(request))
    except LLMError as exc:
        raise _llm_http_error(exc)
    return {"text": reply.text, "tool_calls": reply.tool_calls, "cost_usd": reply.cost_usd,
            "latency_s": reply.latency_s, "cache_read": reply.cache_read}


@app.post("/api/chat/stream")
def chat_stream(body: ChatIn, request: Request, dev_id: str = Depends(current_dev)):
    """Streamed chat turn as NDJSON lines:
    {"type":"text","text":...} per text delta, {"type":"tool","name":...} per tool call,
    then {"type":"done", ...reply} or {"type":"error","detail":...}."""
    store = _store(request)
    events: queue.Queue = queue.Queue()

    def worker():
        try:
            reply = chat_turn(dev_id, body.message, store,
                              on_text=lambda t: events.put({"type": "text", "text": t}),
                              on_tool=lambda n: events.put({"type": "tool", "name": n}))
            events.put({"type": "done", "text": reply.text, "tool_calls": reply.tool_calls,
                        "cost_usd": reply.cost_usd, "latency_s": reply.latency_s,
                        "cache_read": reply.cache_read})
        except LLMError as exc:
            events.put({"type": "error", "detail": _llm_http_error(exc).detail})
        except Exception:  # noqa: BLE001 - the stream has started; report instead of a broken connection
            events.put({"type": "error", "detail": "답변 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."})
        finally:
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def lines():
        while (ev := events.get()) is not None:
            yield json.dumps(ev, ensure_ascii=False) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson")


@app.get("/api/chat/history")
def chat_history(request: Request, dev_id: str = Depends(current_dev)):
    return _store(request).get_chat(dev_id)
