"""Time Black Market MCP 서버 — 몰래 사장의 외상 장부를 외부 AI 클라이언트에서 쓰기.

배포된 백엔드 REST API(Render)를 호출하는 얇은 어댑터라서 Firebase 키가 필요 없다.
Claude Desktop / Claude Code 등 MCP 클라이언트가 아래 도구를 직접 호출한다.

실행:
    python mcp_server/server.py            # stdio (Claude Desktop/Code가 자동 실행)
환경변수:
    TBM_API_BASE_URL  백엔드 주소 (기본: https://time-black-market-api.onrender.com)
"""

import os
from typing import Any, Literal

import httpx
from mcp.server.mcpserver import MCPServer


API_BASE_URL = os.getenv("TBM_API_BASE_URL", "https://time-black-market-api.onrender.com").rstrip("/")
TIMEOUT = httpx.Timeout(90.0, connect=70.0)  # Render 무료 티어 콜드스타트(최대 ~1분) 고려

server = MCPServer(
    name="time-black-market",
    title="시간 암시장 · 몰래 사장의 외상 장부",
    description="오늘 못 한 일을 미래의 시간에서 외상으로 당겨 쓰고 갚아나가는 시간 외상 장부",
    instructions=(
        "사용자의 '시간 외상' 장부를 다루는 도구 모음이다. value는 그날 마감 시점 장부에 남은 외상(분)이다. "
        "전체 현황은 get_ledger_summary, 특정 기간의 이유는 get_records, 요일/월 비교는 get_statistics, "
        "오늘 남은 일은 list_tasks를 사용한다. 할 일을 추가하기 전에는 estimate_task로 예상 시간을 받아 사용자에게 고르게 한다."
    ),
    version="1.0.0",
)


class ApiError(RuntimeError):
    pass


def _request(method: str, path: str, **kwargs: Any) -> Any:
    try:
        with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT) as client:
            response = client.request(method, path, **kwargs)
    except httpx.TimeoutException as exc:
        raise ApiError("백엔드 응답이 너무 늦어요(무료 서버가 깨어나는 중일 수 있음). 잠시 후 다시 시도하세요.") from exc
    except httpx.HTTPError as exc:
        raise ApiError(f"백엔드에 연결하지 못했어요: {exc}") from exc
    data = response.json() if response.content else None
    if response.status_code >= 400:
        detail = data.get("detail") if isinstance(data, dict) else data
        raise ApiError(f"[{response.status_code}] {detail}")
    return data


# ---------------- 조회 ----------------
@server.tool(title="장부 요약")
def get_ledger_summary() -> dict:
    """외상 장부 전체 요약: 기간, 기록 수, 지금/평균/최대/최소 외상(분), 7일 추세, 갚기 좋은 날, 다 갚는 날 예측, 손님 등급, 최근 7일 기록."""
    return _request("GET", "/api/data/summary")


@server.tool(title="장부 통계")
def get_statistics(section: Literal["weekday", "monthly", "all"] = "all") -> dict:
    """요일별(평균 외상, 평균 변화) 또는 월별(평균, 최대, 최소, 순변화) 통계. 일별 시계열은 제외한다."""
    stats = _request("GET", "/api/data/statistics")
    stats.pop("series", None)
    if section in ("weekday", "monthly"):
        return {"count": stats["count"], section: stats[section]}
    return stats


@server.tool(title="기간 기록 조회")
def get_records(start: str, end: str) -> dict:
    """특정 기간(YYYY-MM-DD ~ YYYY-MM-DD)의 일별 원본 기록. value=그날 남은 외상(분), memo=미룬/끝낸 일. 최대 62일."""
    records = _request("GET", "/api/data", params={"start": start, "end": end})
    return {"start": start, "end": end, "count": len(records), "records": records[:62]}


@server.tool(title="할 일 목록")
def list_tasks(status: Literal["open", "done"] = "open") -> dict:
    """open=아직 장부에 남은 일(합계가 오늘의 외상), done=최근 끝낸 일(예상 vs 실제 시간)."""
    tasks = _request("GET", "/api/tasks", params={"status": status, "limit": 30})
    return {
        "status": status,
        "count": len(tasks),
        "total_estimated_minutes": sum(t["estimated_minutes"] for t in tasks),
        "tasks": tasks,
    }


@server.tool(title="지난 상담 목록")
def list_conversations(limit: int = 10) -> list:
    """몰래 사장과 나눈 지난 상담 목록(제목, 최근 수정 시각, 메시지 수)."""
    return _request("GET", "/api/conversations", params={"limit": max(1, min(limit, 50))})


@server.tool(title="지난 상담 보기")
def get_conversation(conversation_id: str) -> dict:
    """특정 상담의 전체 메시지. id는 list_conversations로 확인."""
    return _request("GET", f"/api/conversations/{conversation_id}")


# ---------------- AI ----------------
@server.tool(title="외상값 감정 (AI 예상 시간)")
def estimate_task(title: str) -> dict:
    """할 일 하나에 걸릴 시간을 몰래 사장(AI)이 빠르게/보통/넉넉히 3가지로 제안. 사용자의 과거 예상 vs 실제 기록으로 보정된다."""
    return _request("POST", "/api/tasks/estimate", json={"title": title})


@server.tool(title="몰래 사장에게 묻기")
def ask_mollae(message: str, conversation_id: str | None = None) -> dict:
    """몰래 사장(장부 요약이 주입된 AI)에게 질문하고 답을 받는다. 대화는 서비스의 상담 기록에 자동 저장된다."""
    result = _request("POST", "/api/chat", json={"message": message, "conversation_id": conversation_id})
    return {
        "reply": result["reply"],
        "conversation_id": result["conversation_id"],
        "tools_used_by_mollae": result.get("tool_calls", []),
    }


# ---------------- 변경 ----------------
@server.tool(title="외상 달기 (할 일 추가)")
def add_task(title: str, estimated_minutes: int) -> dict:
    """할 일을 장부에 추가한다. 남은 일 합계로 오늘의 외상이 자동 재계산된다."""
    return _request("POST", "/api/tasks", json={"title": title, "estimated_minutes": estimated_minutes})


@server.tool(title="외상 갚기 (할 일 완료)")
def complete_task(task_id: str, actual_minutes: int) -> dict:
    """할 일을 끝내고 실제 걸린 시간을 기록한다. 장부에서 빠지고 오늘의 외상이 줄어든다. task_id는 list_tasks로 확인."""
    return _request("POST", f"/api/tasks/{task_id}/complete", json={"actual_minutes": actual_minutes})


if __name__ == "__main__":
    server.run("stdio")
