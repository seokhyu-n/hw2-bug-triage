"""Merge the four analysis pages into one tabbed page (docs/artifacts/assignment2.html).

Run after editing any of the source pages:
    venv\\Scripts\\python.exe docs\\artifacts\\build_combined.py
"""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (hash id, tab label, source file) in reading order: what was built -> how it works -> how well it works
TABS = [
    ("service", "서비스 구조", "service_workflow.html"),
    ("chain", "분석 체인", "chaining.html"),
    ("tools", "Function calling", "function_calling.html"),
    ("evaluation", "평가 결과", "evaluation.html"),
]

SUMMARY = """
<section class="summary" aria-label="과제 요약">
  <h1>RunBuddy 버그 제보 트리아지</h1>
  <p class="lead">러닝 앱 RunBuddy의 사용자가 문제 신고 페이지에 남긴 제보를 Claude가 <b>추출 → 분류 → 알려진 이슈 연결 → 우선순위·완성도 채점</b> 순서로 처리해 담당 개발자에게 배정한다. 개발자는 ID로 로그인해 자기 담당 제보를 보고, 멀티턴 챗봇으로 조회·재분석을 요청한다.</p>
  <div class="kpis">
    <div class="kpi"><span class="k">분류 정확도</span><span class="v">0.98</span></div>
    <div class="kpi"><span class="k">추출 정확도</span><span class="v">0.972</span></div>
    <div class="kpi"><span class="k">우선순위 exact</span><span class="v">0.88</span><span class="s">기준선 0.76</span></div>
    <div class="kpi"><span class="k">완성도 MAE</span><span class="v">0.109</span><span class="s">기준선 0.411</span></div>
    <div class="kpi"><span class="k">이슈 연결</span><span class="v">0.96</span></div>
    <div class="kpi"><span class="k">100건 비용</span><span class="v">$0.087</span><span class="s">건당 약 8.1초</span></div>
  </div>
  <p class="legend">위 수치는 Run-07 (Claude Haiku 5.5, Few-shot + Rubric + Context 선별 + 프롬프트 개선 2건), 평가셋 100건 기준. Run-01~07 전체 실험 비용 약 $2.11. 이후 경계 사례 20건을 더한 120건에서 프롬프트를 3번 더 고치고, 아이폰 지원(3회 반복 평균 분류 0.975, 우선순위 0.928)과 수정 버전 링크 규칙을 더한 V2-Run-12(120건에서 분류 0.983, 우선순위 0.925)를 거쳐, 250건을 보고 고친 <b>V3-Run-12가 현재 설정</b>이다(새 사례 100건에서 확실히 좋아진 것은 분류뿐: 0.950 &rarr; 0.993, 평가 결과 11번). 원본 수치는 <code>eval/runs.csv</code>.</p>
  <details class="reqs">
    <summary>사용한 기법과 위치</summary>
    <div class="scroll"><table class="wide">
      <tr><th>기법</th><th>어디에서 보나</th></tr>
      <tr><td>LLM API 호출, System·User 분리, 주요 파라미터(스트리밍 포함)</td><td>분석 체인 3번, Function calling 4번</td></tr>
      <tr><td>Markdown 템플릿, Few-shot, CoT, Rubric, 정보 부족 시 답변 불가</td><td>분석 체인 3·4번</td></tr>
      <tr><td>Decomposition, Prompt Chaining</td><td>분석 체인 1번</td></tr>
      <tr><td>Structured Outputs, Function calling</td><td>분석 체인 3번, Function calling 1~3번</td></tr>
      <tr><td>Context 선별·위치 배치·상태 관리, Prefix cache, 여러 태스크 조합</td><td>서비스 구조 3·4·6번, 분석 체인 2번</td></tr>
      <tr><td>평가셋·지표, 자동 채점, CSV·Excel, 품질·응답시간·비용, Baseline 후 한 변수씩</td><td>평가 결과 1~7번</td></tr>
      <tr><td>반복 실행으로 흔들림 측정, 사람의 정답 검토, 경계 사례를 더한 dataset_v2</td><td>평가 결과 8번</td></tr>
      <tr><td>약점을 한 변수씩 개선(Run-08~10), 부작용 발견과 수정</td><td>평가 결과 9번</td></tr>
      <tr><td>추가 기능(신고 전 안내, 스크린샷 추출, 제보자 답변 재분석) 평가</td><td>평가 결과 10번</td></tr>
      <tr><td>기법을 하나씩 끈 비교(250건), 튜닝에 쓰지 않은 새 사례 검증</td><td>평가 결과 11번</td></tr>
    </table></div>
    <p class="legend">파일·함수 단위 대응표는 저장소 README에 있다.</p>
  </details>
</section>
"""

EXTRA_CSS = """
.summary{padding-bottom:8px}
.kpis{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(min(100%,140px),1fr));margin:14px 0 8px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 12px;display:flex;flex-direction:column;gap:2px}
.kpi .k{font-size:.8rem;color:var(--muted)}
.kpi .v{font-size:1.35rem;font-weight:700;font-variant-numeric:tabular-nums}
.kpi .s{font-size:.75rem;color:var(--muted)}
.reqs{margin:10px 0 0;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:8px 14px}
.reqs summary{cursor:pointer;font-weight:600}
.tabs{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--bg);display:flex;gap:6px;flex-wrap:wrap;padding:10px 0;margin-top:18px;border-bottom:1px solid var(--line)}
.tabs a{display:inline-block;padding:7px 14px;border-radius:99px;border:1px solid var(--line);color:var(--ink);text-decoration:none;font-size:.92rem;background:var(--surface)}
.tabs a:hover{border-color:var(--accent)}
.tabs a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tabs a[aria-selected="true"]{background:var(--accent);border-color:var(--accent);color:var(--bg);font-weight:600}
.panel>h1{font-size:1.35rem;margin-top:20px}
"""

SCRIPT = """
<script>
(function () {
  var ids = %s;
  function show(id) {
    if (ids.indexOf(id) < 0) id = ids[0];
    ids.forEach(function (x) {
      document.getElementById("panel-" + x).hidden = x !== id;
      document.getElementById("tab-" + x).setAttribute("aria-selected", x === id ? "true" : "false");
    });
  }
  window.addEventListener("hashchange", function () { show(location.hash.slice(1)); });
  show(location.hash.slice(1));
})();
</script>
"""


def _part(html: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", html, re.S)
    if not m:
        raise ValueError(f"<{tag}> not found")
    return m.group(1).strip()


def build() -> tuple[str, str]:
    """Returns (standalone page with document wrapper, body for publishing without the wrapper)."""
    sources = {fname: (HERE / fname).read_text(encoding="utf-8") for _, _, fname in TABS}
    css = _part(sources[TABS[0][2]], "style")  # the four pages share one stylesheet
    tabs = "".join(
        f'<a id="tab-{tid}" href="#{tid}" role="tab" aria-controls="panel-{tid}" '
        f'aria-selected="{"true" if i == 0 else "false"}">{label}</a>'
        for i, (tid, label, _) in enumerate(TABS))
    panels = "\n".join(
        f'<section class="panel" id="panel-{tid}" role="tabpanel" aria-labelledby="tab-{tid}"'
        f'{"" if i == 0 else " hidden"}>\n{_part(sources[fname], "main")}\n</section>'
        for i, (tid, _, fname) in enumerate(TABS))
    ids = "[" + ",".join(f'"{tid}"' for tid, _, _ in TABS) + "]"
    body = (f"<title>RunBuddy 트리아지 분석</title>\n<style>\n{css}\n{EXTRA_CSS}</style>\n"
            f"<main>\n{SUMMARY}\n<nav class=\"tabs\" role=\"tablist\" aria-label=\"분석 섹션\">{tabs}</nav>\n"
            f"{panels}\n</main>\n{SCRIPT % ids}")
    page = ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"</head>\n<body>\n{body}</body>\n</html>\n")
    return page, body


if __name__ == "__main__":
    page, body = build()
    (HERE / "assignment2.html").write_text(page, encoding="utf-8", newline="\n")
    print(f"wrote {HERE / 'assignment2.html'} ({len(page):,} bytes)")
