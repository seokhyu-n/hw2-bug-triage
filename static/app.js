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

let knownIds = null;  // report IDs seen so far (null until the first load): new P1s raise an alert
const baseTitle = document.title;

function alertNewP1(rows) {
  const ids = new Set(rows.map(r => r.request_id));
  if (knownIds !== null) {
    const fresh = rows.filter(r => !knownIds.has(r.request_id) && r.result && r.result.score.priority === "P1");
    if (fresh.length) {
      const text = "새 P1 제보 " + fresh.length + "건: " + fresh.map(r => r.request_id).join(", ");
      $("p1-alert").textContent = text; $("p1-alert").hidden = false;
      document.title = "(" + fresh.length + ") " + baseTitle;
      if ("Notification" in window && Notification.permission === "granted")
        new Notification("RunBuddy 트리아지", {body: text});
    }
  }
  knownIds = ids;
}
$("p1-alert").onclick = () => { $("p1-alert").hidden = true; document.title = baseTitle; };

async function loadList() {
  const rows = await api("/api/reports");
  alertNewP1(rows);
  const ul = $("report-list");
  ul.replaceChildren();
  for (const r of rows) {
    const li = el("li", null, r.request_id === selectedId ? "sel" : "");
    if (r.result) {
      li.appendChild(el("span", r.result.score.priority, "badge " + r.result.score.priority));
      li.appendChild(el("span", r.request_id));
      li.appendChild(el("span", r.result.classification.category));
      const wf = (r.workflow || {state: "new"}).state;
      if (wf !== "new") li.appendChild(el("span", WF_LABEL[wf], "wf " + wf));
      if ((r.replies || []).some(x => x.state !== "failed")) li.appendChild(el("span", "답변 옴", "wf in_progress"));
      const same = (r.similar || []).length + (r.similar_elsewhere || 0);
      if (same) li.appendChild(el("span", "같은 증상 " + (same + 1) + "건", "wf group"));
      if (r.issue_id) li.appendChild(el("span", r.issue_id, "wf issue"));
    } else {
      li.appendChild(el("span", STATUS_LABEL[r.status], "badge " + r.status));
      li.appendChild(el("span", r.request_id));
      li.appendChild(el("span", "미분석"));
    }
    li.appendChild(el("span", (r.text || "").split("\n\n[신고 양식")[0].slice(0, 40) +((r.attachments || []).length ? " 📎" + r.attachments.length : "")));
    li.onclick = () => { selectedId = r.request_id; showDetail(r); loadList(); };
    ul.appendChild(li);
  }
  if (!rows.length) ul.appendChild(el("li", "아직 제보가 없습니다"));
}

const STATUS_LABEL = {pending: "분석 중", failed: "분석 실패"};

const WF_LABEL = {new: "접수됨", in_progress: "확인 중", resolved: "수정 완료", wont_fix: "처리 종료"};

// ---- same-symptom group, known issue (register / link / resolve), reassignment ----
let issuesCache = null, devsCache = null;
async function issues(force) { if (force || !issuesCache) issuesCache = await api("/api/issues"); return issuesCache; }

async function teamPanel(d, r) {
  const box = el("div", null, "team");
  d.appendChild(el("h3", "같은 증상 · 이슈"));
  d.appendChild(box);
  const isBug = r.result.classification.labels.includes("bug");
  const same = r.similar || [], elsewhere = r.similar_elsewhere || 0;
  if (same.length || elsewhere) {
    const p = el("p");
    p.appendChild(document.createTextNode("같은 증상 신고 " + (same.length + elsewhere + 1) + "건: 이 신고"));
    for (const id of same) {
      p.appendChild(document.createTextNode(", "));
      const a = el("a", id); a.href = "#"; a.onclick = async e => { e.preventDefault(); selectedId = id; showDetail(await api("/api/reports/" + id)); loadList(); };
      p.appendChild(a);
    }
    if (elsewhere) p.appendChild(document.createTextNode(" + 다른 담당자 목록에 " + elsewhere + "건"));
    box.appendChild(p);
    const total = same.length + elsewhere + 1;
    if (total >= 3 && ["P3", "P4"].includes(r.result.score.priority))
      box.appendChild(el("p", "같은 증상이 " + total + "건 들어왔어요. 영향 사용자가 많을 수 있으니 우선순위를 올릴지 검토하세요.", "hint-warn"));
  } else if (isBug) {
    box.appendChild(el("p", "같은 증상으로 들어온 다른 신고는 아직 없어요.", "meta"));
  }

  const err = el("div", "", "error");
  if (r.issue_id) {
    const all = await issues();
    const issue = all.find(i => i.id === r.issue_id);
    const line1 = el("p");
    line1.appendChild(el("b", r.issue_id + " "));
    line1.appendChild(document.createTextNode(issue ? issue.title : ""));
    box.appendChild(line1);
    if (issue) {
      box.appendChild(el("p", (issue.status === "fixed" ? "수정됨 (" + issue.fixed_in + ")" : "수정 전") +
        " · 이 이슈로 묶인 신고 " + issue.reports + "건, 처리 중 " + issue.open_reports + "건" +
        (issue.source === "team" ? " · 팀에서 등록" : ""), "meta"));
      if (issue.status !== "fixed" || issue.open_reports) {
        const row = el("div", null, "workflow");
        const ver = el("input"); ver.type = "text"; ver.placeholder = "수정 버전 (예: 1.2.1)"; ver.maxLength = 20;
        ver.setAttribute("aria-label", "수정 버전");
        const btn = el("button", "수정 완료 → 신고자 " + issue.open_reports + "명에게 안내");
        btn.onclick = async () => {
          err.textContent = ""; btn.disabled = true;
          try {
            const out = await api("/api/issues/" + r.issue_id + "/resolve", "POST", {fixed_in: ver.value});
            box.appendChild(el("p", "안내 완료: " + out.resolved_reports.length + "건을 수정 완료로 바꾸고 신고자에게 '" + out.message + "'를 보냈어요.", "meta"));
            await issues(true); loadList();
          } catch (e) { err.textContent = e.message; }
          btn.disabled = false;
        };
        row.append(ver, btn);
        box.appendChild(row);
      }
    }
  } else if (isBug) {
    // link to an existing issue
    const all = await issues();
    const row = el("div", null, "workflow");
    const sel = el("select"); sel.setAttribute("aria-label", "기존 이슈");
    sel.appendChild(Object.assign(el("option", "기존 이슈에 묶기…"), {value: ""}));
    for (const i of all.filter(i => i.status !== "fixed")) sel.appendChild(Object.assign(el("option", i.id + " " + i.title), {value: i.id}));
    const link = el("button", "묶기", "secondary");
    link.onclick = async () => {
      if (!sel.value) return;
      try { showDetail(await api("/api/reports/" + r.request_id + "/issue", "POST", {issue_id: sel.value})); loadList(); }
      catch (e) { err.textContent = e.message; }
    };
    row.append(sel, link);
    box.appendChild(row);
    // register a new issue from this report (+ its same-symptom group)
    const reg = el("details");
    reg.appendChild(el("summary", "새 알려진 이슈로 등록" + (same.length ? " (같은 증상 " + (same.length + 1) + "건 함께)" : "")));
    const title = el("input"); title.type = "text"; title.maxLength = 120; title.value = r.result.extraction.symptom || "";
    title.setAttribute("aria-label", "이슈 제목");
    const work = el("input"); work.type = "text"; work.maxLength = 500; work.placeholder = "임시 해결 방법 (선택)";
    work.setAttribute("aria-label", "임시 해결 방법");
    const go = el("button", "등록");
    go.onclick = async () => {
      err.textContent = ""; go.disabled = true;
      try {
        const issue = await api("/api/issues", "POST", {title: title.value, workaround: work.value || null,
          report_ids: [r.request_id, ...same]});
        await issues(true);
        showDetail(await api("/api/reports/" + r.request_id)); loadList();
        $("list-err").textContent = issue.id + " 등록: 같은 증상으로 신고하는 사람에게 신고 전에 안내돼요.";
      } catch (e) { err.textContent = e.message; go.disabled = false; }
    };
    reg.append(el("p", "같은 증상 신고들의 기기·버전으로 영향 범위를 채워요. 등록하면 이후 신고자에게 신고 전 안내로 보여요.", "meta"), title, work, go);
    box.appendChild(reg);
  }
  box.appendChild(err);
}

async function assignPanel(d, r) {
  if (!devsCache) devsCache = await api("/api/developers");
  const me = $("who").dataset.dev;
  const row = el("div", null, "workflow");
  const sel = el("select"); sel.setAttribute("aria-label", "넘길 개발자");
  for (const x of devsCache.filter(x => x.dev_id !== me))
    sel.appendChild(Object.assign(el("option", x.dev_id + " (" + x.areas.join(", ") + ")"), {value: x.dev_id}));
  const note = el("input"); note.type = "text"; note.maxLength = 300; note.placeholder = "넘기는 이유 (선택)";
  note.setAttribute("aria-label", "넘기는 이유");
  const btn = el("button", "담당자 변경", "secondary");
  const msg = el("span", "", "meta");
  btn.onclick = async () => {
    btn.disabled = true;
    try {
      await api("/api/reports/" + r.request_id + "/assign", "POST", {dev_id: sel.value, note: note.value || null});
      selectedId = null; $("detail").replaceChildren(el("p", r.request_id + "을(를) " + sel.value + "에게 넘겼어요.", "meta"));
      loadList();
    } catch (e) { msg.textContent = e.message; btn.disabled = false; }
  };
  row.append(sel, note, btn, msg);
  d.appendChild(el("h3", "담당자 변경"));
  d.appendChild(row);
}
const REPLY_STATE = {pending: "재분석 중", applied: "재분석 반영", failed: "재분석 실패(내용은 저장됨)"};

// Processing state + a message the reporter sees on their status page.
function workflow(d, r) {
  const wf = r.workflow || {state: "new", message: null};
  d.appendChild(el("h3", "처리 상태 (제보자에게 보임)"));
  const row = el("div", null, "workflow");
  const sel = el("select");
  sel.setAttribute("aria-label", "처리 상태");
  for (const [k, v] of Object.entries(WF_LABEL)) {
    const o = el("option", v); o.value = k; if (k === wf.state) o.selected = true; sel.appendChild(o);
  }
  const msg = el("input"); msg.type = "text"; msg.maxLength = 1000; msg.value = wf.message || "";
  msg.placeholder = "제보자에게 남길 말 (예: 1.2.1에서 수정 예정입니다)";
  msg.setAttribute("aria-label", "제보자에게 남길 말");
  const save = el("button", "저장");
  const note = el("span", "", "meta");
  save.onclick = async () => {
    save.disabled = true; note.textContent = "";
    try {
      const updated = await api("/api/reports/" + r.request_id + "/workflow", "POST", {state: sel.value, message: msg.value});
      note.textContent = "저장했어요"; loadList(); Object.assign(r, updated);
    } catch (e) { note.textContent = e.message; }
    save.disabled = false;
  };
  row.append(sel, msg, save, note);
  d.appendChild(row);
}

function replies(d, r) {
  const list = r.replies || [];
  if (!list.length) return;
  d.appendChild(el("h3", "제보자 답변 (상태 확인 페이지에서 보냄)"));
  for (const x of list) d.appendChild(el("div", x.text + "\n— " + x.at.replace("T", " ") + " · " + (REPLY_STATE[x.state] || x.state), "box raw"));
}

function logLink(d, r) {
  if (!r.log) return;
  const p = el("p");
  const a = el("a", "첨부 로그 보기: " + r.log.name + " (" + Math.ceil(r.log.size / 1024) + "KB)");
  a.href = "/api/reports/" + encodeURIComponent(r.request_id) + "/log"; a.target = "_blank"; a.rel = "noopener";
  p.appendChild(a); d.appendChild(p);
}

// Screenshots the reporter attached; served only to the developer who can see the report.
function shots(d, r) {
  logLink(d, r);
  const list = r.attachments || [];
  if (!list.length) return;
  d.appendChild(el("h3", "첨부 스크린샷 (" + list.length + ")"));
  const box = el("div", null, "shots");
  list.forEach((m, i) => {
    const url = "/api/reports/" + encodeURIComponent(r.request_id) + "/attachments/" + (i + 1);
    const a = el("a"); a.href = url; a.target = "_blank"; a.rel = "noopener"; a.title = m.name;
    const img = el("img"); img.src = url; img.alt = m.name; img.loading = "lazy";
    a.appendChild(img);
    box.appendChild(a);
  });
  d.appendChild(box);
}

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
  shots(d, r);
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
  workflow(d, r);
  const teamSlot = el("div"); d.appendChild(teamSlot);
  teamPanel(teamSlot, r).catch(e => teamSlot.appendChild(el("div", e.message, "error")));

  d.appendChild(el("h3", "제보 원문"));
  d.appendChild(el("div", r.text, "box raw"));
  shots(d, r);
  replies(d, r);
  if (r.added_info && r.added_info.length) {
    d.appendChild(el("h3", "추가로 받은 정보"));
    d.appendChild(el("div", r.added_info.join("\n"), "box raw"));
  }

  d.appendChild(el("h3", "추출"));
  const ex = el("div", null, "box");
  line(ex, "기기:", val(x.device_model));
  if (x.platform === "ios") line(ex, "iOS:", val(x.ios_version));
  else line(ex, "Android:", val(x.android_version));
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

  const assignSlot = el("div"); d.appendChild(assignSlot);
  assignPanel(assignSlot, r).catch(e => assignSlot.appendChild(el("div", e.message, "error")));

  const ls = r.logs_summary;
  d.appendChild(el("div", "처리 시간 " + ls.latency_s.toFixed(1) + "s · 비용 $" + ls.cost_usd.toFixed(4) +
    " · 캐시 적중 " + ls.cache_read.toLocaleString() + " 토큰", "meta"));
}

$("refresh-btn").onclick = async () => {
  $("list-err").textContent = "";
  // browsers only allow the permission prompt after a click: ask once, for P1 desktop notifications
  if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
  try { await loadList(); } catch (e) { $("list-err").textContent = e.message; }
};
// background refresh; a failure here is silent (the next tick or the button shows errors)
setInterval(() => { if (!document.hidden || "Notification" in window) loadList().catch(() => {}); }, 20000);

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
