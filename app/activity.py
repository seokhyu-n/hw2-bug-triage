"""A run record attached to a report ("이 기록 신고하기" in a running app, as Strava support asks
for the activity link). The app sends a small summary; it becomes a labelled block after the report
text so the analysis can use the facts (e.g. "GPS 없음 9분") without guessing, and the developer
sees it as a card. It is reporter-side data like the report text: shown as sent, never trusted as
an instruction.
"""
import json
from functools import lru_cache

from pydantic import BaseModel, Field, field_validator

from app.config import DATA_DIR

MAX_GAPS = 20
LONG_JUMP_M = 100  # a single GPS jump this long is reported as a jump


class Gap(BaseModel):
    start_s: int = Field(ge=0, le=86_400)
    end_s: int = Field(ge=0, le=86_400)


class Activity(BaseModel):
    activity_id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    started_at: str | None = Field(default=None, max_length=25)
    distance_km: float = Field(ge=0, le=500)
    duration_s: int = Field(ge=0, le=86_400)
    gps_points: int = Field(ge=0, le=1_000_000)
    gaps: list[Gap] = Field(default_factory=list, max_length=MAX_GAPS)
    max_jump_m: float | None = Field(default=None, ge=0, le=100_000)

    @field_validator("gaps")
    @classmethod
    def _ordered(cls, gaps: list[Gap]) -> list[Gap]:
        if any(g.end_s <= g.start_s for g in gaps):
            raise ValueError("GPS 끊김 구간의 끝이 시작보다 앞설 수 없습니다")
        return gaps


def _mmss(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}분 {s}초" if s else f"{m}분"


def facts(a: Activity) -> list[str]:
    """Plain facts computed from the summary (shared by the report text and the developer card)."""
    pace = a.duration_s / a.distance_km / 60 if a.distance_km else None
    out = [f"기록 ID: {a.activity_id}" + (f" ({a.started_at.replace('T', ' ')[:16]} 시작)" if a.started_at else ""),
           f"거리 {a.distance_km:.2f}km, 시간 {_mmss(a.duration_s)}, GPS 위치 {a.gps_points}개"
           + (f", 평균 페이스 {int(pace)}분 {round((pace % 1) * 60):02d}초/km" if pace else "")]
    if a.gaps:
        total = sum(g.end_s - g.start_s for g in a.gaps)
        spans = ", ".join(f"{_mmss(g.start_s)}~{_mmss(g.end_s)}" for g in a.gaps)
        out.append(f"GPS 끊김 {len(a.gaps)}번, 합계 {_mmss(total)} 동안 위치 없음 ({spans})")
    else:
        out.append("GPS 끊김 없음")
    if a.max_jump_m is not None and a.max_jump_m >= LONG_JUMP_M:
        out.append(f"한 번에 {a.max_jump_m:.0f}m 튄 위치가 있음")
    return out


def block(a: Activity) -> str:
    return "[연결된 러닝 기록]\n" + "\n".join(f"- {f}" for f in facts(a))


def parse(raw) -> Activity | None:
    """From the JSON body (dict) or a form field (JSON string)."""
    if raw in (None, ""):
        return None
    data = json.loads(raw) if isinstance(raw, str) else raw
    return Activity.model_validate(data)


@lru_cache(maxsize=1)
def samples() -> dict[str, dict]:
    data = json.loads((DATA_DIR / "sample_activities.json").read_text(encoding="utf-8"))
    return {a["activity_id"]: a for a in data["activities"]}
