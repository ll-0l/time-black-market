"""AI가 호출할 수 있는 내부 기능(도구) 정의.

- TOOL_SCHEMAS: OpenAI Function Calling 스키마
- execute_tool: 이름/인자로 실제 내부 서비스를 실행해 JSON 직렬화 가능한 결과를 돌려준다.
같은 도구 목록을 MCP 서버(mcp_server/)에서도 노출한다.
"""

import datetime as dt
import json
from typing import Any, Callable

from backend.core.config import today
from backend.core.exceptions import AppError
from backend.services import analytics_service, conversation_service, data_service, task_service


MAX_RECORDS = 62
MAX_CONVERSATION_MESSAGES = 20


def _get_data_summary() -> dict[str, Any]:
    return analytics_service.build_summary(data_service.get_all_data(), today())


def _get_statistics(section: str = "all") -> dict[str, Any]:
    stats = analytics_service.build_statistics(data_service.get_all_data())
    stats.pop("series", None)  # 일별 시계열은 get_records로 조회 (토큰 절약)
    if section in ("weekday", "monthly"):
        return {"count": stats["count"], section: stats[section]}
    return stats


def _get_records(start: str, end: str) -> dict[str, Any]:
    start_date, end_date = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    records = data_service.get_all_data(start_date.isoformat(), end_date.isoformat())
    truncated = len(records) > MAX_RECORDS
    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "count": len(records),
        "truncated": truncated,
        "records": [
            {"date": r["date"], "value": r["value"], "memo": r["memo"]} for r in records[:MAX_RECORDS]
        ],
    }


def _list_conversations(limit: int = 10) -> dict[str, Any]:
    items = conversation_service.list_conversations(max(1, min(int(limit), 30)))
    return {
        "conversations": [
            {
                "id": c["id"],
                "title": c["title"],
                "updated_at": c["updated_at"].isoformat() if hasattr(c["updated_at"], "isoformat") else c["updated_at"],
                "message_count": c["message_count"],
            }
            for c in items
        ]
    }


def _get_conversation(conversation_id: str) -> dict[str, Any]:
    conversation = conversation_service.get_conversation(conversation_id)
    return {
        "id": conversation["id"],
        "title": conversation["title"],
        "messages": [
            {"role": m["role"], "content": m["content"]}
            for m in conversation["messages"][-MAX_CONVERSATION_MESSAGES:]
        ],
    }


def _list_tasks(status: str = "open") -> dict[str, Any]:
    tasks = task_service.list_tasks(status if status in ("open", "done") else "open", 20)
    return {
        "status": status,
        "count": len(tasks),
        "total_estimated_minutes": sum(t["estimated_minutes"] for t in tasks),
        "tasks": [
            {k: t[k] for k in ("title", "estimated_minutes", "created_date", "done_date", "actual_minutes")} for t in tasks
        ],
    }


TOOL_FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_data_summary": _get_data_summary,
    "get_statistics": _get_statistics,
    "get_records": _get_records,
    "list_conversations": _list_conversations,
    "get_conversation": _get_conversation,
    "list_tasks": _list_tasks,
}

TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_data_summary": "시간 부채 전체 요약(기간, 개수, 현재/평균/최대/최소, 추세, 추천 상환일, 완납 예상일, 신용등급)을 최신 상태로 다시 조회한다. 사용자가 방금 데이터를 수정했다고 하거나 최신 수치가 필요할 때 사용.",
    "get_statistics": "요일별(평균 부채, 평균 증감) 또는 월별(평균, 최대, 최소, 순증감) 통계를 조회한다. '무슨 요일에', '몇 월에', '월별 비교' 같은 질문에 사용.",
    "get_records": "특정 기간의 일별 원본 기록(date, value=그날 마감 시점 총 시간 부채(분), memo=미룬/처리한 업무)을 조회한다. 특정 날짜·주·월에 무슨 일이 있었는지, 왜 늘었는지 등 세부 질문에 사용. 최대 62일.",
    "list_conversations": "저장된 이전 대화 목록(제목, 최근 수정 시각)을 조회한다. 사용자가 '전에 물어본 것', '지난 대화'를 언급할 때 사용.",
    "get_conversation": "특정 이전 대화의 메시지를 조회한다. list_conversations로 id를 먼저 확인한 뒤 사용.",
    "list_tasks": "현재 남은 업무(open, 오늘 부채의 구성) 또는 최근 완료 업무(done, 예상 vs 실제 시간)를 조회한다. '뭐부터 할까', '예상보다 오래 걸린 일' 같은 질문에 사용.",
}

TOOL_PARAMETERS: dict[str, dict[str, Any]] = {
    "get_data_summary": {"type": "object", "properties": {}, "additionalProperties": False},
    "get_statistics": {
        "type": "object",
        "properties": {
            "section": {"type": "string", "enum": ["weekday", "monthly", "all"], "description": "조회할 통계 종류"}
        },
        "required": ["section"],
        "additionalProperties": False,
    },
    "get_records": {
        "type": "object",
        "properties": {
            "start": {"type": "string", "description": "시작일 YYYY-MM-DD"},
            "end": {"type": "string", "description": "종료일 YYYY-MM-DD"},
        },
        "required": ["start", "end"],
        "additionalProperties": False,
    },
    "list_conversations": {
        "type": "object",
        "properties": {"limit": {"type": "integer", "description": "가져올 개수 (1~30)"}},
        "required": ["limit"],
        "additionalProperties": False,
    },
    "get_conversation": {
        "type": "object",
        "properties": {"conversation_id": {"type": "string", "description": "대화 id"}},
        "required": ["conversation_id"],
        "additionalProperties": False,
    },
    "list_tasks": {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": ["open", "done"], "description": "open=남은 일, done=완료한 일"}},
        "required": ["status"],
        "additionalProperties": False,
    },
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {"name": name, "description": TOOL_DESCRIPTIONS[name], "parameters": TOOL_PARAMETERS[name]},
    }
    for name in TOOL_FUNCTIONS
]


def execute_tool(name: str, arguments: dict[str, Any] | str | None) -> dict[str, Any]:
    """도구 실행. 실패해도 예외 대신 {'error': ...}를 돌려줘 GPT가 상황을 설명할 수 있게 한다."""
    if name not in TOOL_FUNCTIONS:
        return {"error": f"알 수 없는 도구: {name}"}
    try:
        args = json.loads(arguments) if isinstance(arguments, str) and arguments else (arguments or {})
        return TOOL_FUNCTIONS[name](**args)
    except AppError as exc:
        return {"error": exc.detail}
    except (TypeError, ValueError) as exc:
        return {"error": f"잘못된 인자: {exc}"}
