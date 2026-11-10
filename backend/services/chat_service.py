"""데이터 기반 AI 채팅 (컨텍스트 주입 + Function Calling).

흐름
1. 데이터 요약 조회 (GET /api/data/summary 와 같은 로직)
2. 요약을 시스템 프롬프트에 삽입 (컨텍스트 주입)
3. GPT 호출 — 요약만으로 부족하면 GPT가 도구(get_records 등)를 호출, 결과를 받아 다시 호출
4. 질문/답변을 conversations 컬렉션에 자동 저장
"""

import json
import logging
import os
from typing import Any, Optional

from openai import APIError, AuthenticationError, OpenAI, RateLimitError

from backend.core.config import today
from backend.core.exceptions import ExternalServiceError
from backend.models.conversation import Message
from backend.services import analytics_service, conversation_service, data_service
from backend.services.tools import TOOL_SCHEMAS, execute_tool


logger = logging.getLogger("time_black_market")

HISTORY_LIMIT = 10  # GPT에 보낼 이전 메시지 수 (비용 제한)
MAX_TOOL_ROUNDS = 3


def _model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-5-mini")


def _max_tokens() -> int:
    # gpt-5 계열(추론 모델)은 내부 추론 토큰도 이 한도에 포함되므로 넉넉히 둔다.
    return int(os.getenv("OPENAI_MAX_TOKENS", "2000"))


def _reasoning_effort() -> Optional[str]:
    """추론 모델의 생각 강도(minimal/low/medium/high). 비우면 보내지 않음."""
    return os.getenv("OPENAI_REASONING_EFFORT", "low").strip() or None


def _client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ExternalServiceError("OPENAI_API_KEY가 설정되지 않았습니다.")
    # OPENAI_BASE_URL: OpenAI 호환 게이트웨이(예: Codyssey 공개 API) 사용 시 지정. 비우면 OpenAI 공식 API.
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    return OpenAI(api_key=api_key, base_url=base_url, timeout=60, max_retries=1)


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return "-"
    minutes = int(round(value))
    hours, rest = divmod(minutes, 60)
    return f"{minutes}분({hours}시간 {rest}분)" if hours else f"{minutes}분"


def build_system_prompt(summary: dict[str, Any]) -> str:
    if not summary.get("count"):
        data_block = "- 아직 기록된 데이터가 없습니다. 데이터 관리 화면에서 기록을 추가하도록 안내하세요."
    else:
        m = summary["metrics"]
        rec = summary["recommendation"]
        payoff = summary["payoff_forecast"]
        credit = summary["credit"]
        recent = "\n".join(
            f"  - {r['date']}: {_fmt(r['value'])} / {r['memo'] or '메모 없음'}" for r in summary["recent_records"]
        )
        data_block = f"""- 데이터 기간: {summary['period']['label']} ({summary['period']['days']}일)
- 총 레코드: {summary['count']}개
- 주요 지표: 현재 부채 {_fmt(m['current'])} ({m['current_date']}), 평균 {_fmt(m['average'])}, 중앙값 {_fmt(m['median'])}, 최대 {_fmt(m['max'])} ({m['max_date']}), 최소 {_fmt(m['min'])} ({m['min_date']})
- 누적 차입 {_fmt(m['total_borrowed'])} ({m['borrow_days']}일) / 누적 상환 {_fmt(m['total_repaid'])} ({m['repay_days']}일)
- 최근 트렌드: {summary['trend']['description']}
- 추천 상환일: {rec.get('weekday')}요일 — {rec.get('reason')}
- 완납 예상: {payoff.get('status')} {payoff.get('description', '')}
- 시간 신용등급: {credit['grade']} ({credit['label']})
- 최근 7일 기록:
{recent}"""

    return f"""당신은 'Time Black Market(시간 암시장)'의 데이터 분석 비서입니다.
사용자는 오늘 처리하지 못하고 미래로 미룬 업무 시간을 '시간 부채(Time Debt)'로 기록합니다.
value는 그날 마감 시점의 총 시간 부채(분)이고, 전날보다 늘면 '차입', 줄면 '상환'입니다.
오늘 날짜: {today().isoformat()}

[사용자 데이터 요약]
{data_block}

위 데이터를 기반으로 맞춤형 답변을 제공하세요.
- 숫자는 위 요약이나 도구 결과에 있는 값만 사용하고, 없는 수치를 지어내지 마세요.
- 요약에 없는 특정 날짜/기간의 세부 내용이 필요하면 get_records, 요일/월별 비교가 필요하면 get_statistics,
  이전 대화를 언급하면 list_conversations/get_conversation 도구를 호출하세요.
- 시간은 '2시간 30분'처럼 읽기 쉽게 표현하고, 답변은 한국어로 3~6문장 이내로 간결하게.
- 필요하면 구체적인 상환 행동(언제, 무엇을, 얼마나)을 1~2개 제안하세요."""


def _history_messages(conversation: Optional[dict[str, Any]]) -> list[dict[str, str]]:
    if not conversation:
        return []
    return [{"role": m["role"], "content": m["content"]} for m in conversation["messages"][-HISTORY_LIMIT:]]


def _call_gpt(client: OpenAI, messages: list[dict[str, Any]]):
    options: dict[str, Any] = {}
    if _reasoning_effort() and _model().startswith(("gpt-5", "o")):
        options["reasoning_effort"] = _reasoning_effort()
    try:
        return client.chat.completions.create(
            model=_model(),
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            max_completion_tokens=_max_tokens(),
            **options,
        )
    except RateLimitError as exc:
        logger.warning("OpenAI rate limit: %s", exc)
        raise ExternalServiceError("AI 요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.") from exc
    except AuthenticationError as exc:
        logger.warning("OpenAI auth error: %s", exc)
        raise ExternalServiceError("AI API 키가 올바르지 않습니다. OPENAI_API_KEY / OPENAI_BASE_URL을 확인하세요.") from exc
    except APIError as exc:
        logger.exception("OpenAI error: %s", exc)
        raise ExternalServiceError("AI 응답을 받지 못했습니다. 잠시 후 다시 시도하세요.") from exc


def chat(message: str, conversation_id: Optional[str] = None) -> dict[str, Any]:
    client = _client()
    conversation = conversation_service.get_conversation(conversation_id) if conversation_id else None

    # 1~2. 요약 조회 → 시스템 프롬프트 주입
    summary = analytics_service.build_summary(data_service.get_all_data())
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": build_system_prompt(summary)},
        *_history_messages(conversation),
        {"role": "user", "content": message},
    ]

    # 3. GPT 호출 (+ 도구 호출 루프)
    tool_calls_log: list[dict[str, Any]] = []
    reply = ""
    for _ in range(MAX_TOOL_ROUNDS + 1):
        response = _call_gpt(client, messages)
        choice = response.choices[0].message
        if not choice.tool_calls:
            reply = (choice.content or "").strip()
            break

        messages.append(choice.model_dump(exclude_none=True))
        for call in choice.tool_calls:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            result = execute_tool(call.function.name, arguments)
            tool_calls_log.append({"name": call.function.name, "arguments": arguments})
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False, default=str)}
            )
    if not reply:
        reply = "죄송해요, 답변을 정리하지 못했어요. 질문을 조금 더 구체적으로 해주세요."

    # 4. 대화 자동 저장
    tools_used = sorted({c["name"] for c in tool_calls_log})
    new_messages = [
        Message(role="user", content=message),
        Message(role="assistant", content=reply, tools_used=tools_used),
    ]
    if conversation:
        saved = conversation_service.append_messages(conversation["id"], new_messages)
    else:
        saved = conversation_service.create_conversation(new_messages)

    return {
        "conversation_id": saved["id"],
        "title": saved["title"],
        "reply": reply,
        "tool_calls": tool_calls_log,
        "summary": summary,
        "model": _model(),
    }
