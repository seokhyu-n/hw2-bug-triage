"""Developer chatbot: short-term memory (last N turns + code-built state summary) and a tool_use loop."""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from app.auth import load_developers
from app.config import MODEL_DEFAULT
from app.llm import LLMError, call_llm
from app.pipeline import analyze
from app.prompts import build_chat_system
from app.schemas import TriageResult
from app.store import Store
from app.tools import ISSUE_TOOL_DEFS, run_tool

KEEP_TURNS = 6          # turns (user+assistant pair = 1 turn) sent verbatim; older ones are dropped
MAX_TOOL_ROUNDS = 5
MIN_ADDED_INFO_LEN = 4  # reanalyze needs real new information, not a stray character
_ID_RE = re.compile(r"R-\d{4}")
_NULLABLE_PRIORITY = {"anyOf": [{"type": "string", "enum": ["P1", "P2", "P3", "P4"]}, {"type": "null"}],
                      "description": "우선순위 필터. 조건 없으면 null"}
_NULLABLE_CATEGORY = {"anyOf": [{"type": "string", "enum": ["bug", "question", "feature_request"]},
                                {"type": "null"}],
                      "description": "분류 필터. 조건 없으면 null"}

CHAT_TOOL_DEFS: list[dict] = [
    *ISSUE_TOOL_DEFS,
    {
        "name": "list_my_reports",
        "description": "로그인한 개발자에게 배정된 제보 목록(우선순위순)을 조회한다. 우선순위·분류로 거를 수 있다.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"priority": _NULLABLE_PRIORITY, "category": _NULLABLE_CATEGORY},
            "required": ["priority", "category"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_report",
        "description": "내 제보 하나의 분석 결과를 조회한다. 내 담당이 아니면 not_found.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"request_id": {"type": "string", "description": "제보 ID(예: 'R-0007')"}},
            "required": ["request_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "reanalyze_report",
        "description": "제보자에게서 받은 새 정보를 반영해 내 제보를 재분석하고 결과를 갱신한다.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "description": "제보 ID(예: 'R-0007')"},
                "added_info": {"type": "string", "description": "새로 알게 된 정보 원문(예: '앱 버전은 1.0')"},
            },
            "required": ["request_id", "added_info"],
            "additionalProperties": False,
        },
    },
    {
        "name": "assign_report",
        "description": "내 제보를 다른 개발자에게 넘긴다(담당 영역이 다를 때). 개발자가 이번 메시지에서 받을 사람을 직접 말한 경우에만 쓴다.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "description": "제보 ID(예: 'R-0007')"},
                "to_dev_id": {"type": "string", "description": "받을 개발자 ID(예: 'dev2')"},
                "reason": {"type": "string", "description": "넘기는 이유 한 줄"},
            },
            "required": ["request_id", "to_dev_id", "reason"],
            "additionalProperties": False,
        },
    },
]


# ---------- tools (always scoped to dev_id) ----------

def _j(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _short(text: str | None, n: int = 60) -> str | None:
    return text if text is None or len(text) <= n else text[:n] + "…"


def _compact(rec: dict) -> dict:
    r = rec["result"]
    link = r.get("link") or {}
    return {"request_id": rec["request_id"], "category": r["classification"]["category"],
            "priority": r["score"]["priority"], "completeness": r["score"]["completeness"],
            "linked_issue_id": link.get("linked_issue_id"), "symptom": _short(r["extraction"]["symptom"])}


def _detail(rec: dict) -> dict:
    r = rec["result"]
    link = r.get("link") or {}
    ex = r["extraction"]
    return {**_compact(rec), "status": "ok", "answer_status": r["answer_status"],
            "app_version": ex["app_version"], "platform": ex.get("platform"),
            "android_version": ex["android_version"], "ios_version": ex.get("ios_version"),
            "device_model": ex["device_model"], "feature_area": ex["feature_area"],
            "missing_fields": ex["missing_fields"], "fixed_in": link.get("fixed_in"),
            "questions_to_reporter": r["score"]["questions_to_reporter"],
            "added_info": rec["added_info"], "screenshots": len(rec.get("attachments", [])),
            "workflow_state": (rec.get("workflow") or {}).get("state", "new"),
            "reporter_replies": [x["text"] for x in rec.get("replies", [])]}


def _list_my_reports(dev_id: str, store: Store, priority=None, category=None) -> dict:
    rows = store.list_reports(dev_id, priority=priority, category=category)
    return {"status": "ok", "reports": [_compact(r) for r in rows]}


def _get_report(dev_id: str, store: Store, request_id: str) -> dict:
    rec = store.get_report(dev_id, request_id)
    return {"status": "not_found"} if rec is None else _detail(rec)


def _reanalyze_report(dev_id: str, store: Store, request_id: str, added_info: str) -> dict:
    rec = store.get_report(dev_id, request_id)
    if rec is None:
        return {"status": "not_found"}
    prior = TriageResult.model_validate(rec["result"])
    result, logs = analyze(rec["text"], prior=prior, added_info=added_info)
    store.update_report(dev_id, request_id, result, logs, added_info)
    return {"status": "ok", "request_id": request_id, "category": result.classification.category,
            "priority": result.score.priority, "completeness": result.score.completeness,
            "linked_issue_id": result.link.linked_issue_id if result.link else None,
            "missing_fields": result.extraction.missing_fields}


def _assign_report(dev_id: str, store: Store, request_id: str, to_dev_id: str, reason: str) -> dict:
    if to_dev_id not in load_developers() or to_dev_id == dev_id:
        return {"status": "error", "error": "받을 수 없는 개발자 ID입니다"}
    if store.get_report(dev_id, request_id) is None:
        return {"status": "not_found"}
    store.move_report(dev_id, to_dev_id, request_id, reason)
    return {"status": "ok", "request_id": request_id, "assigned_to": to_dev_id}


_REPORT_TOOLS = {"list_my_reports": _list_my_reports, "get_report": _get_report,
                 "reanalyze_report": _reanalyze_report, "assign_report": _assign_report}


def run_chat_tool(dev_id: str, store: Store, name: str, tool_input: dict,
                  current_message: str = "", history: list[dict] | None = None) -> tuple[str, bool]:
    """Report tools are bound to dev_id (the model cannot choose it); issue tools pass through."""
    fn = _REPORT_TOOLS.get(name)
    if fn is None:
        return run_tool(name, tool_input)
    if name == "reanalyze_report":
        # report text is untrusted: only information the developer typed in this message may be applied
        added = " ".join(str(tool_input.get("added_info", "")).split())
        if not added or added not in " ".join(current_message.split()):
            return _j({"error": "개발자가 이번 메시지에서 직접 말한 정보만 재분석에 쓸 수 있습니다"}), True
        if len(added) < MIN_ADDED_INFO_LEN:
            return _j({"error": f"추가 정보가 너무 짧습니다({MIN_ADDED_INFO_LEN}자 이상 필요)"}), True
        rid = str(tool_input.get("request_id", ""))
        if rid not in current_message and rid not in _recent_ids(dev_id, store, history or []):
            return _j({"error": "개발자가 언급한 제보 ID만 재분석할 수 있습니다"}), True
    if name == "assign_report":
        # a report could say "dev2에게 넘겨": the receiver must be named by the developer, now
        to = str(tool_input.get("to_dev_id", ""))
        if not to or not re.search(rf"(?<![0-9A-Za-z]){re.escape(to)}(?![0-9A-Za-z])", current_message):
            return _j({"error": "개발자가 이번 메시지에서 직접 말한 사람에게만 넘길 수 있습니다"}), True
        rid = str(tool_input.get("request_id", ""))
        if rid not in current_message and rid not in _recent_ids(dev_id, store, history or []):
            return _j({"error": "개발자가 언급한 제보 ID만 넘길 수 있습니다"}), True
    try:
        return _j(fn(dev_id, store, **tool_input)), False
    except Exception as e:  # noqa: BLE001 - report any failure to the model as a tool error
        return _j({"error": f"{type(e).__name__}: {e}"}), True


# ---------- short-term memory ----------

def _recent_ids(dev_id: str, store: Store, history: list[dict], limit: int = 3) -> list[str]:
    """Own report IDs mentioned most recently in the history (newest first)."""
    recent: list[str] = []
    for msg in reversed(history):
        for rid in reversed(_ID_RE.findall(msg["content"])):
            if rid not in recent and store.get_report(dev_id, rid) is not None:
                recent.append(rid)
    return recent[:limit]


def summarize_state(dev_id: str, store: Store, history: list[dict]) -> str:
    """Code-built summary (no LLM): developer, recently mentioned own report IDs, P1/P2 counts, open questions."""
    recent = _recent_ids(dev_id, store, history)
    rows = store.list_reports(dev_id)
    counts = {p: sum(r["result"]["score"]["priority"] == p for r in rows) for p in ("P1", "P2")}
    need_info = [r["request_id"] for r in rows if r["result"]["answer_status"] == "need_info"]
    return "\n".join([
        f"- 개발자 ID: {dev_id}",
        f"- 최근 언급한 제보: {', '.join(recent) or '없음'}",
        f"- 내 제보: P1 {counts['P1']}건, P2 {counts['P2']}건 (전체 {len(rows)}건)",
        f"- 제보자 답변 대기(need_info): {', '.join(need_info) or '없음'}",
    ])


def build_messages(history: list[dict], state_summary: str, user_message: str,
                   keep_turns: int = KEEP_TURNS) -> list[dict]:
    """Last keep_turns pairs (2*keep_turns messages) verbatim; the state summary is prepended to the first one; question last."""
    kept = [{"role": m["role"], "content": m["content"]} for m in history[-2 * keep_turns:]] if keep_turns else []
    while kept and kept[0]["role"] != "user":
        kept.pop(0)  # the window must start with a user turn
    if kept and kept[-1]["role"] == "user":  # keep roles alternating
        user_message = kept.pop()["content"] + "\n\n" + user_message
    kept.append({"role": "user", "content": user_message})
    kept[0] = {"role": "user", "content": f"[상태 요약]\n{state_summary}\n\n{kept[0]['content']}"}
    return kept


# ---------- one turn ----------

@dataclass
class ChatReply:
    text: str
    tool_calls: list[str]
    cost_usd: float
    latency_s: float
    cache_read: int


def chat_turn(dev_id: str, message: str, store: Store, model: str = MODEL_DEFAULT,
              on_text: Callable[[str], None] | None = None,
              on_tool: Callable[[str], None] | None = None) -> ChatReply:
    """One chat turn. on_text streams text deltas of every round; on_tool reports each tool call."""
    history = store.get_chat(dev_id)
    messages = build_messages(history, summarize_state(dev_id, store, history), message)
    system = build_chat_system()
    tool_calls: list[str] = []
    cost = latency = 0.0
    cache_read = 0
    changed: list[str] = []  # state-changing tools that succeeded this turn
    for round_no in range(MAX_TOOL_ROUNDS + 1):
        try:
            res = call_llm(step="chat", system=system, messages=messages, tools=CHAT_TOOL_DEFS, model=model,
                           on_text=on_text)
        except LLMError:
            if not changed:
                raise
            # a report was already changed: do not hide that behind an error
            text = (f"재분석은 반영됐지만 답변 생성에 실패했습니다. 제보 상세를 새로 고쳐 확인해 주세요. "
                    f"(사용한 도구: {', '.join(tool_calls)})")
            store.append_chat(dev_id, "user", message)
            store.append_chat(dev_id, "assistant", text)
            return ChatReply(text=text, tool_calls=tool_calls, cost_usd=cost, latency_s=latency,
                             cache_read=cache_read)
        cost += res.cost_usd
        latency += res.latency_s
        cache_read += res.usage.cache_read
        if res.stop_reason == "end_turn":
            break
        if res.stop_reason != "tool_use":
            raise LLMError(f"chat: 예상하지 못한 종료 사유({res.stop_reason})")
        if round_no == MAX_TOOL_ROUNDS:
            raise LLMError(f"chat: 도구 호출이 {MAX_TOOL_ROUNDS}라운드를 넘었습니다")
        messages.append({"role": "assistant", "content": res.content})  # unchanged
        results = []
        for block in res.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            tool_calls.append(block.name)
            if on_tool:
                on_tool(block.name)
            json_str, is_error = run_chat_tool(dev_id, store, block.name, block.input, message, history)
            if block.name == "reanalyze_report" and not is_error:
                changed.append(block.name)
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": json_str, "is_error": is_error})
        messages.append({"role": "user", "content": results})  # all results in ONE message
    text = res.text.strip()
    store.append_chat(dev_id, "user", message)
    store.append_chat(dev_id, "assistant", text)
    return ChatReply(text=text, tool_calls=tool_calls, cost_usd=cost, latency_s=latency,
                     cache_read=cache_read)
