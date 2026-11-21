"""FastAPI service: login, report intake/triage, reanalysis, chatbot, static UI."""
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from app import auth
from app.auth import assign_developer, current_dev
from app.chat import chat_turn
from app.config import ROOT, RUNTIME_DIR
from app.llm import LLMError, LLMRefusal, LLMTruncated, LLMUnavailable
from app.pipeline import analyze
from app.schemas import TriageResult
from app.store import Store

STATIC_DIR = ROOT / "static"
MAX_REPORT_CHARS = 5000

app = FastAPI(title="RunBuddy Bug Triage")
app.state.store = Store(RUNTIME_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _store(request: Request) -> Store:
    return request.app.state.store


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


@app.post("/api/reports")
def create_report(body: ReportIn, request: Request, _dev: str = Depends(current_dev)):
    store = _store(request)
    try:
        result, logs = analyze(body.text)
    except LLMError as exc:
        raise _llm_http_error(exc)
    owner = assign_developer(result.extraction.feature_area)
    rid = store.create_report(owner, body.text, result, logs)
    return _view(store.get_report(owner, rid))


@app.get("/api/reports")
def list_reports(request: Request, priority: str | None = None, category: str | None = None,
                 dev_id: str = Depends(current_dev)):
    return [_view(r) for r in _store(request).list_reports(dev_id, priority, category)]


def _own_report(request: Request, dev_id: str, request_id: str) -> dict:
    record = _store(request).get_report(dev_id, request_id)
    if record is None:
        raise HTTPException(404, "제보를 찾을 수 없습니다")
    return record


@app.get("/api/reports/{request_id}")
def get_report(request_id: str, request: Request, dev_id: str = Depends(current_dev)):
    return _view(_own_report(request, dev_id, request_id))


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


@app.get("/api/chat/history")
def chat_history(request: Request, dev_id: str = Depends(current_dev)):
    return _store(request).get_chat(dev_id)
