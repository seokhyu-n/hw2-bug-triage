"""Per-client request limits for the public (no-login) endpoints.

Every report and every reporter reply starts paid Claude calls, so a script hammering the public
form would run up the bill. A sliding window per client address and endpoint is enough for one
process (the store is single-process too); behind a proxy the key would be the forwarded address.
"""
import threading
import time
from collections import deque

from fastapi import HTTPException, Request

# endpoint -> (max requests, window seconds)
LIMITS = {
    "intake": (10, 600),      # new reports: 10 per 10 minutes
    "suggest": (60, 600),     # pre-submit suggestions (no LLM): generous
    "reply": (10, 600),       # reporter answers (each one re-analyzes)
    "status": (120, 600),     # status page reads
}


class RateLimiter:
    def __init__(self, limits: dict | None = None):
        self.limits = dict(limits or LIMITS)
        self._hits: dict[tuple[str, str], deque] = {}
        self._lock = threading.Lock()

    def check(self, request: Request, endpoint: str) -> None:
        limit, window = self.limits[endpoint]
        key = (endpoint, request.client.host if request.client else "unknown")
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > window:
                hits.popleft()
            if len(hits) >= limit:
                retry = int(window - (now - hits[0])) + 1
                raise HTTPException(429, f"요청이 너무 많아요. {max(1, retry // 60)}분 뒤에 다시 시도해 주세요.",
                                    headers={"Retry-After": str(retry)})
            hits.append(now)
