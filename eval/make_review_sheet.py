"""Build the human label-review workbook eval/review/review_sheet.xlsx.

Sheet "기존 30건": 30 cases sampled from dataset_v1 (stratified by category, hard cases favoured; the 6
cases the user already checked are excluded). Sheet "새 사례 20건": eval/dataset_v2_new.jsonl.
The reviewer fills "판정" (O = label correct, X = wrong) and, for X, writes the fix in "고칠 내용".
    venv\\Scripts\\python.exe -m eval.make_review_sheet
"""
import json
import random
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

EVAL = Path(__file__).resolve().parent
OUT = EVAL / "review" / "review_sheet.xlsx"
ALREADY_REVIEWED = {"E-023", "E-034", "E-047", "E-049", "E-057", "E-090"}
QUOTA = {"bug": 15, "question": 8, "feature_request": 7}
HARD_SHARE = 0.4  # about 40% of each category's picks are hard cases
SEED = 20261122

# reviewer columns first (B, C) so they are visible without scrolling right
COLUMNS = [("ID", 8), ("판정 (O/X)", 10), ("고칠 내용", 28), ("제보 원문", 55), ("분류(주)", 14), ("라벨 전체", 22),
           ("우선순위", 9), ("완성도", 8), ("연결 이슈", 11), ("기능 영역", 11), ("기기", 14), ("안드로이드", 10),
           ("앱 버전", 9), ("재현 절차", 34)]


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sample_v1(cases: list[dict]) -> list[dict]:
    rng = random.Random(SEED)
    picked = []
    for cat, n in QUOTA.items():
        pool = [c for c in cases if c["expected"]["category"] == cat and c["id"] not in ALREADY_REVIEWED]
        hard = [c for c in pool if c.get("hard")]
        easy = [c for c in pool if not c.get("hard")]
        n_hard = min(len(hard), round(n * HARD_SHARE))
        picked += rng.sample(hard, n_hard) + rng.sample(easy, n - n_hard)
    return sorted(picked, key=lambda c: c["id"])


def row(c: dict) -> list:
    e, x = c["expected"], c["expected"]["extraction"]
    return [c["id"], "", "", c["text"], e["category"], ", ".join(e["labels"]), e["priority"],
            "-" if e["completeness"] is None else e["completeness"], e["linked_issue_id"] or "-",
            x["feature_area"] or "-", x["device_model"] or "-", x["android_version"] or "-", x["app_version"] or "-",
            " → ".join(x["repro_steps"]) or "-"]


def sheet(wb, title: str, cases: list[dict]) -> None:
    ws = wb.create_sheet(title)
    ws.append([name for name, _ in COLUMNS])
    for i, (_, width) in enumerate(COLUMNS, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = width
    for c in cases:
        ws.append(row(c))
    head = PatternFill("solid", fgColor="DDE7F5")
    todo = PatternFill("solid", fgColor="FFF4CC")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = head
    for r in ws.iter_rows(min_row=2):
        for cell in r:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        r[1].fill = todo
        r[2].fill = todo
    dv = DataValidation(type="list", formula1='"O,X"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"B2:B{len(cases) + 1}")
    ws.freeze_panes = "D2"  # ID, 판정, 고칠 내용 stay visible while scrolling


def main() -> None:
    v1 = sample_v1(load(EVAL / "dataset_v1.jsonl"))
    new = load(EVAL / "dataset_v2_new.jsonl")
    wb = openpyxl.Workbook()
    guide = wb.active
    guide.title = "읽어 주세요"
    for line in [
        "정답 검토표",
        "",
        "아래쪽 시트 탭 '기존 30건', '새 사례 20건'을 눌러 이동하세요.",
        "각 시트에서 행마다 정답(분류·라벨·우선순위·완성도·연결 이슈 등)이 맞는지 보고, ID 바로 옆 노란 '판정' 칸(B열)에서 O 또는 X를 고르세요.",
        "X라면 '고칠 내용'에 무엇을 어떻게 바꿀지 적어 주세요. 예: 우선순위 P2로 / 분류 question으로 / 완성도 1로",
        "",
        "판단 기준",
        "- bug: 지금 있는 기능이 고장났다는 주장이 있다(질문형·요청형 문장이어도 고장이면 bug).",
        "- question: 고장 주장 없이 기능·사용법·정책을 묻는다.",
        "- feature_request: 없는 기능 추가나 설계대로 동작하는 것을 바꿔 달라는 요청.",
        "- 우선순위: P1 크래시·기록 유실·로그인 불가 / P2 핵심 기능 오동작 / P3 우회 가능·일부 / P4 사소·문의·요청.",
        "- 완성도(버그만): 0 증상 불명확 / 1 증상은 명확, 환경(안드로이드·앱 버전) 또는 재현 절차 누락 / 2 모두 있음.",
        "- 원문에 없는 값은 비워 둔다('-'). 기기 이름으로 안드로이드 버전을 추측하지 않는다.",
        "",
        f"기존 30건: 기존 평가셋 100건에서 분류별로 골고루 뽑음(이미 검토한 6건 제외). 새 사례 20건: 이번에 추가한 헷갈리는 분류 사례.",
        "다 했으면 저장하고 알려 주세요.",
    ]:
        guide.append([line])
    guide.column_dimensions["A"].width = 110
    guide["A1"].font = Font(bold=True, size=14)
    sheet(wb, "기존 30건", v1)
    sheet(wb, "새 사례 20건", new)
    OUT.parent.mkdir(exist_ok=True)
    wb.save(OUT)
    print(f"wrote {OUT}: {len(v1)} existing + {len(new)} new")


if __name__ == "__main__":
    main()
