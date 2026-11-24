"""Structured report form: optional fields next to the free description.

The fields are folded into the report text under a labelled block, so the analysis still reads one
report text (and the evaluation, which uses plain text, is unaffected). Values the reporter typed
are explicit text, so the extract step can use them without guessing; empty fields are left out.
"""
from dataclasses import dataclass

CATEGORIES = {"bug": "오류/버그", "question": "사용 문의", "feature_request": "기능 제안"}
FREQUENCIES = {"always": "매번", "sometimes": "가끔", "once": "한 번"}

# (form key, label in the report text, max length)
_TEXT_FIELDS = [
    ("device_model", "기기", 60),
    ("android_version", "안드로이드 버전", 20),
    ("ios_version", "iOS 버전", 20),  # 아이폰 reporters: kept apart so it never reads as an Android version
    ("app_version", "앱 버전", 20),
    ("steps", "재현 순서", 1000),
    ("expected", "기대한 결과", 500),
    ("actual", "실제 결과", 500),
]

LOG_MAX_BYTES = 1024 * 1024
LOG_TAIL_CHARS = 4000  # only the end of a log goes to the model: errors are usually last


class FormError(ValueError):
    """Shown to the reporter as is (Korean)."""


@dataclass
class ReportForm:
    category: str | None = None
    frequency: str | None = None
    device_model: str | None = None
    android_version: str | None = None
    ios_version: str | None = None
    app_version: str | None = None
    steps: str | None = None
    expected: str | None = None
    actual: str | None = None

    @classmethod
    def parse(cls, raw: dict) -> "ReportForm":
        def clean(key: str, limit: int) -> str | None:
            value = raw.get(key)
            if not isinstance(value, str) or not value.strip():
                return None
            value = value.strip()
            if len(value) > limit:
                raise FormError(f"{dict((k, l) for k, l, _ in _TEXT_FIELDS).get(key, key)}은(는) "
                                f"{limit:,}자 이하여야 합니다")
            return value

        category = clean("category", 30)
        if category is not None and category not in CATEGORIES:
            raise FormError("문의 유형이 올바르지 않습니다")
        frequency = clean("frequency", 30)
        if frequency is not None and frequency not in FREQUENCIES:
            raise FormError("발생 빈도 값이 올바르지 않습니다")
        return cls(category=category, frequency=frequency,
                   **{key: clean(key, limit) for key, _, limit in _TEXT_FIELDS})

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    def compose(self, description: str) -> str:
        """Description first, then a labelled block with only the fields that were filled in."""
        lines = []
        if self.category:
            lines.append(f"- 제보자가 고른 유형(참고용): {CATEGORIES[self.category]}")
        for key, label, _ in _TEXT_FIELDS:
            value = getattr(self, key)
            if value:
                if "\n" in value:
                    value = "\n  " + value.replace("\n", "\n  ")
                lines.append(f"- {label}: {value}")
        if self.frequency:
            lines.append(f"- 발생 빈도: {FREQUENCIES[self.frequency]}")
        if not lines:
            return description
        return description.rstrip() + "\n\n[신고 양식에 입력한 내용]\n" + "\n".join(lines)


def validate_log(filename: str, data: bytes) -> tuple[str, bytes] | None:
    """A plain-text log file (.txt/.log). Returns (display name, bytes) or None if nothing sent."""
    from app.attachments import safe_name

    if not data:
        return None
    name = safe_name(filename or "log.txt")
    if len(data) > LOG_MAX_BYTES:
        raise FormError(f"{name}: 로그 파일은 1MB 이하여야 합니다")
    if not name.lower().endswith((".txt", ".log")):
        raise FormError(f"{name}: 로그는 .txt 또는 .log 파일만 첨부할 수 있습니다")
    if b"\x00" in data[:8192]:
        raise FormError(f"{name}: 텍스트 로그 파일만 첨부할 수 있습니다")
    return name, data


def log_tail(text: str | None) -> str | None:
    if not text or not text.strip():
        return None
    return text[-LOG_TAIL_CHARS:]
