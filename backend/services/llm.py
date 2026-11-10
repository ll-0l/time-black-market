"""OpenAI 호환 LLM 클라이언트 공통 설정 (OpenAI 공식 / Codyssey 게이트웨이)."""

import os
from typing import Any, Optional

from openai import OpenAI

from backend.core.exceptions import ExternalServiceError


def model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-5-mini")


def max_tokens() -> int:
    # gpt-5 계열(추론 모델)은 내부 추론 토큰도 이 한도에 포함되므로 넉넉히 둔다.
    return int(os.getenv("OPENAI_MAX_TOKENS", "2000"))


def reasoning_options() -> dict[str, Any]:
    """추론 강도(minimal/low/medium/high). 비우면 보내지 않음 (Codyssey 게이트웨이는 미지원)."""
    effort: Optional[str] = os.getenv("OPENAI_REASONING_EFFORT", "").strip() or None
    if effort and model().startswith(("gpt-5", "o")):
        return {"reasoning_effort": effort}
    return {}


def client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ExternalServiceError("OPENAI_API_KEY가 설정되지 않았습니다.")
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    return OpenAI(api_key=api_key, base_url=base_url, timeout=60, max_retries=1)
