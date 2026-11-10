"""AI 업무 소요 시간 예측.

사용자의 과거 완료 기록(예상 vs 실제)을 함께 보내 개인화된 예측을 받는다.
응답은 JSON으로 요청하고, 형식이 어긋나면 안전하게 보정한다.
"""

import json
import logging
import re
from typing import Any

from openai import APIError

from backend.core.exceptions import ExternalServiceError
from backend.services import llm, task_service


logger = logging.getLogger("time_black_market")

SYSTEM_PROMPT = """당신은 시간 암시장에서 미래의 시간을 외상으로 빌려주는 두더지 대부업자 '몰래 사장'입니다.
손님이 미루려는 업무에 시간을 얼마나 빌려줘야 할지(=소요 시간) 감정합니다.
사용자가 할 일 하나를 주면, 한국 직장인/학생 기준으로 그 일을 끝내는 데 필요한 시간을 분 단위로 추정하세요.
사용자의 과거 기록(예상 vs 실제)이 주어지면 그 사람이 평소 과소/과대 추정하는 경향을 반영하세요.
반드시 아래 JSON 한 개만 출력하세요. 설명 문장이나 코드블록 없이.
{"fast": 분, "normal": 분, "safe": 분, "reason": "몰래 사장 말투(친근한 반말)의 한 문장 근거, 40자 이내"}
- fast < normal < safe, 모두 5분 단위 정수, 5~1440 범위
- normal이 가장 현실적인 값"""


def _round5(value: Any) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    return int(max(5, min(1440, round(number / 5) * 5)))


def _parse(content: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", content or "", re.S)
    if not match:
        raise ValueError("JSON 없음")
    data = json.loads(match.group(0))
    fast, normal, safe = (_round5(data.get(k)) for k in ("fast", "normal", "safe"))
    if not normal:
        raise ValueError("normal 값 없음")
    fast = fast or _round5(normal * 0.7)
    safe = safe or _round5(normal * 1.5)
    # 순서가 뒤바뀌었거나 같은 값이면 보통값 기준으로 벌려준다
    fast = min(fast, normal)
    safe = max(safe, normal)
    if fast == normal and normal > 5:
        fast = _round5(normal * 0.75) if _round5(normal * 0.75) < normal else normal - 5
    if safe == normal:
        safe = min(1440, max(normal + 10, _round5(normal * 1.4)))
    return {"fast": fast, "normal": normal, "safe": safe, "reason": str(data.get("reason", ""))[:120]}


def estimate(title: str) -> dict[str, Any]:
    history = task_service.completed_history()
    user_lines = [f"할 일: {title}"]
    if history:
        user_lines.append("내 과거 기록 (업무 / 예상 → 실제, 분):")
        user_lines += [f"- {h['title']} / {h['estimated']} → {h['actual']}" for h in history]

    try:
        response = llm.client().chat.completions.create(
            model=llm.model(),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "\n".join(user_lines)},
            ],
            max_completion_tokens=llm.max_tokens(),
            **llm.reasoning_options(),
        )
        parsed = _parse(response.choices[0].message.content or "")
    except APIError as exc:
        logger.exception("Estimate API error: %s", exc)
        raise ExternalServiceError("AI 예상 시간을 받지 못했어요. 직접 입력해 주세요.") from exc
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Estimate parse error: %s", exc)
        raise ExternalServiceError("AI 응답을 해석하지 못했어요. 다시 시도하거나 직접 입력해 주세요.") from exc

    return {
        "title": title,
        "options": [
            {"label": "빠르게", "minutes": parsed["fast"]},
            {"label": "보통", "minutes": parsed["normal"]},
            {"label": "넉넉히", "minutes": parsed["safe"]},
        ],
        "recommended": parsed["normal"],
        "reason": parsed["reason"],
        "history_used": len(history),
    }
