"""아주 단순한 IP별 분당 요청 제한 (OpenAI 비용 보호용, 단일 인스턴스 기준)."""

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


_lock = threading.Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)
WINDOW_SECONDS = 60


def _limit() -> int:
    return int(os.getenv("CHAT_RATE_LIMIT_PER_MINUTE", "10"))


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")  # Render 등 프록시 뒤
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def chat_rate_limit(request: Request) -> None:
    key = _client_ip(request)
    now = time.monotonic()
    with _lock:
        hits = _hits[key]
        while hits and now - hits[0] > WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= _limit():
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="질문이 너무 잦아요. 1분 후 다시 시도하세요.",
            )
        hits.append(now)
