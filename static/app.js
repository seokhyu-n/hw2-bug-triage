// All report/chat text is untrusted: it is only ever inserted with textContent / text nodes.
let selectedId = null;

function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined && text !== null) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}
const val = v => (v === null || v === undefined || v === "" ? "(없음)" : v);
const $ = id => document.getElementById(id);

async function api(path, method = "GET", body) {
  const opts = {method, headers: {}};
  if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const r = await fetch(path, opts);
  if (r.status === 401) { location.href = "/"; throw new Error("로그인이 필요합니다"); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    let d = data.detail;
    if (Array.isArray(d)) d = d.map(x => x.msg).join("; ");
    throw new Error(d || "요청에 실패했습니다");
  }
  return data;
}

function line(parent, label, value) {
  const p = el("div");
  p.appendChild(el("strong", label + " "));
  p.appendChild(document.createTextNode(value));
  parent.appendChild(p);
}

async function loadList() {
  const rows = await api("/api/reports");
  const ul = $("report-list");
  ul.replaceChildren();
  for (const r of rows) {
    const li = el("li", null, r.request_id === selectedId ? "sel" : "");
    if (r.result) {
      li.appendChild(el("span", r.result.score.priority, "badge " + r.result.score.priority));
      li.appendChild(el("span", r.request_id));
      li.appendChild(el("span", r.result.classification.category));
    } else {
      li.appendChild(el("span", STATUS_LABEL[r.status], "badge " + r.status));
      li.appendChild(el("span", r.request_id));
      li.appendChild(el("span", "미분석"));
    }
    li.appendChild(el("span", (r.text || "").slice(0, 40)));
    li.onclick = () => { selectedId = r.request_id; showDetail(r); loadList(); };
    ul.appendChild(li);
  }
  if (!rows.length) ul.appendChild(el("li", "아직 제보가 없습니다"));
}

const STATUS_LABEL = {pending: "분석 중", failed: "분석 실패"};

// A report saved by the intake whose background analysis is running or failed.
function showQueued(r) {
  const d = $("detail");
  d.replaceChildren();
  const head = el("h2", r.request_id + " ");
  head.appendChild(el("span", STATUS_LABEL[r.status], "badge " + r.status));
  d.appendChild(head);
  if (r.status === "pending") {
    line(d, "상태:", "분석 중입니다. 끝나면 담당 개발자 목록으로 옮겨집니다. \"새로 고침\"으로 확인하세요.");
  } else {
    line(d, "상태:", "자동 분석이 " + r.attempts + "번 실패했습니다. 제보는 저장되어 있습니다.");
    line(d, "마지막 오류:", val(r.last_error));
  }
  d.appendChild(el("h3", "제보 원문"));
  d.appendChild(el("div", r.text, "box raw"));
  if (r.status !== "failed") return;
  const btn = el("button", "다시 분석 시도");
  const err = el("div", "", "error");
  btn.onclick = async () => {
    err.textContent = ""; btn.disabled = true;
    try {
      await api("/api/reports/" + r.request_id + "/retry", "POST");
      showQueued({...r, status: "pending"}); loadList();
    } catch (e) { err.textContent = e.message; btn.disabled = false; }
  };
  const p = el("p"); p.appendChild(btn); d.appendChild(p);
  d.appendChild(err);
}

function showDetail(r) {
  if (!r.result) return showQueued(r);
  const d = $("detail");
  d.replaceChildren();
  const x = r.result.extraction, s = r.result.score, c = r.result.classification, l = r.result.link;
  const head = el("h2", r.request_id + " ");
  head.appendChild(el("span", s.priority, "badge " + s.priority));
  d.appendChild(head);
  line(d, "분류:", c.category + (c.labels.length > 1 ? " (복합: " + c.labels.join(", ") + ")" : ""));
  line(d, "완성도:", s.completeness === null ? "해당 없음" : s.completeness + "/2");
  line(d, "답변 상태:", r.result.answer_status);

  d.appendChild(el("h3", "제보 원문"));
  d.appendChild(el("div", r.text, "box raw"));
  if (r.added_info && r.added_info.length) {
    d.appendChild(el("h3", "추가로 받은 정보"));
    d.appendChild(el("div", r.added_info.join("\n"), "box raw"));
  }

  d.appendChild(el("h3", "추출"));
  const ex = el("div", null, "box");
  line(ex, "기기:", val(x.device_model)); line(ex, "Android:", val(x.android_version));
  line(ex, "앱 버전:", val(x.app_version)); line(ex, "기능:", val(x.feature_area));
  line(ex, "증상:", val(x.symptom)); line(ex, "기대 동작:", val(x.expected));
  line(ex, "실제 동작:", val(x.actual)); line(ex, "빈도:", val(x.frequency));
  line(ex, "재현:", x.repro_steps.length ? x.repro_steps.map((t, i) => (i + 1) + ") " + t).join(" ") : "(없음)");
  d.appendChild(ex);

  d.appendChild(el("h3", "도구로 조회한 사실"));
  const facts = el("div", null, "box facts");
  if (l && l.linked_issue_id) {
    line(facts, "관련 이슈:", l.linked_issue_id);
    line(facts, "일치 이유:", val(l.match_reason));
    line(facts, "수정 버전(fixed_in):", val(l.fixed_in));
    line(facts, "업데이트 안내:", l.user_should_update === null ? "(해당 없음)" : (l.user_should_update ? "필요" : "불필요"));
  } else {
    facts.textContent = "연결된 알려진 이슈 없음";
  }
  d.appendChild(facts);

  d.appendChild(el("h3", "판단 근거"));
  d.appendChild(el("div", s.reasoning, "box"));

  d.appendChild(el("h3", "부족한 정보"));
  d.appendChild(el("div", x.missing_fields.length ? x.missing_fields.join(", ") : "없음", "box"));
  if (s.questions_to_reporter.length) d.appendChild(el("div", s.questions_to_reporter.map(q => "→ " + q).join("\n"), "box"));

  const inp = el("input"); inp.type = "text"; inp.placeholder = "제보자에게 받은 추가 정보 입력";
  const btn = el("button", "다시 분석");
  const err = el("div", "", "error");
  btn.onclick = async () => {
    err.textContent = ""; btn.disabled = true; btn.textContent = "분석 중...";
    try {
      const updated = await api("/api/reports/" + r.request_id + "/reanalyze", "POST", {added_info: inp.value});
      showDetail(updated); loadList();
    } catch (e) { err.textContent = e.message; btn.disabled = false; btn.textContent = "다시 분석"; }
  };
  d.appendChild(inp);
  const p = el("p"); p.appendChild(btn); d.appendChild(p);
  d.appendChild(err);

  const ls = r.logs_summary;
  d.appendChild(el("div", "처리 시간 " + ls.latency_s.toFixed(1) + "s · 비용 $" + ls.cost_usd.toFixed(4) +
    " · 캐시 적중 " + ls.cache_read.toLocaleString() + " 토큰", "meta"));
}

$("refresh-btn").onclick = async () => {
  $("list-err").textContent = "";
  try { await loadList(); } catch (e) { $("list-err").textContent = e.message; }
};

function addMsg(role, text, tools) {
  const m = el("div", null, "msg " + role);
  const body = document.createTextNode(text);
  m.appendChild(body);
  const toolLine = el("div", tools && tools.length ? "사용한 도구: " + tools.join(", ") : "", "tools");
  m.appendChild(toolLine);
  $("chat-log").appendChild(m);
  $("chat-log").scrollTop = $("chat-log").scrollHeight;
  return {body, toolLine};
}

// Reads the NDJSON stream from /api/chat/stream and calls onEvent per line.
async function streamChat(message, onEvent) {
  const r = await fetch("/api/chat/stream", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({message})});
  if (r.status === 401) { location.href = "/"; throw new Error("로그인이 필요합니다"); }
  if (!r.ok) {
    const data = await r.json().catch(() => ({}));
    let d = data.detail;
    if (Array.isArray(d)) d = d.map(x => (x.msg || "").replace(/^Value error, /, "")).join("; ");
    throw new Error(d || "요청에 실패했습니다");
  }
  const reader = r.body.getReader(), dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const {value, done} = await reader.read();
    if (done) break;
    buf += dec.decode(value, {stream: true});
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const lineText = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (lineText) onEvent(JSON.parse(lineText));
    }
  }
}

async function sendChat() {
  const input = $("chat-input"), err = $("chat-err"), msg = input.value;
  if (!msg.trim()) return;
  err.textContent = ""; $("chat-btn").disabled = true;
  addMsg("user", msg); input.value = "";
  const reply = addMsg("assistant", "…");
  let streamed = "", tools = [], final = null;
  try {
    await streamChat(msg, ev => {
      if (ev.type === "text") { streamed += ev.text; reply.body.textContent = streamed; }
      else if (ev.type === "tool") { tools.push(ev.name); reply.toolLine.textContent = "사용 중인 도구: " + tools.join(", "); }
      else if (ev.type === "done") final = ev;
      else if (ev.type === "error") throw new Error(ev.detail);
      $("chat-log").scrollTop = $("chat-log").scrollHeight;
    });
    if (!final) throw new Error("답변이 중간에 끊겼습니다. 다시 시도해 주세요.");
    // the saved reply is the final round's text (earlier rounds may hold short notes before tool calls)
    reply.body.textContent = final.text;
    reply.toolLine.textContent = final.tool_calls.length ? "사용한 도구: " + final.tool_calls.join(", ") : "";
    loadList();
    if (selectedId && final.tool_calls.includes("reanalyze_report")) {
      try { showDetail(await api("/api/reports/" + selectedId)); } catch (e2) { /* list reload still shows the change */ }
    }
  } catch (e) {
    err.textContent = e.message;
    if (!streamed) reply.body.textContent = "(답변 실패)";
  }
  $("chat-btn").disabled = false;
}
$("chat-btn").onclick = sendChat;

$("logout-btn").onclick = async () => { await fetch("/api/logout", {method: "POST"}); location.href = "/"; };

(async function init() {
  const me = await api("/api/me");
  $("who").textContent = me.dev_id; $("who").dataset.dev = me.dev_id;
  for (const h of await api("/api/chat/history")) addMsg(h.role, h.content);
  loadList();
})();
