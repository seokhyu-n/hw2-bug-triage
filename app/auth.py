"""Developer-ID login (in-memory sessions) and feature-area based assignment."""
import json
import secrets

from fastapi import HTTPException, Request

from app.config import DATA_DIR

DEFAULT_DEV = "dev3"
_sessions: dict[str, str] = {}


def load_developers() -> dict[str, list[str]]:
    """Return {dev_id: [feature areas]} from data/developers.json."""
    raw = json.loads((DATA_DIR / "developers.json").read_text(encoding="utf-8"))
    return {dev_id: list(info["areas"]) for dev_id, info in raw.items()}


def assign_developer(feature_area: str | None) -> str:
    if feature_area:
        for dev_id, areas in load_developers().items():
            if feature_area in areas:
                return dev_id
    return DEFAULT_DEV


def login(dev_id: str) -> str:
    if dev_id not in load_developers():
        raise ValueError(f"unknown developer id: {dev_id}")
    token = secrets.token_urlsafe(24)
    _sessions[token] = dev_id
    return token


def logout(token: str | None) -> None:
    if token:
        _sessions.pop(token, None)


def current_dev(request: Request) -> str:
    dev_id = _sessions.get(request.cookies.get("session", ""))
    if dev_id is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    return dev_id
