"""할 일(tasks) 관리 + 오늘의 시간 외상 자동 계산.

- 남은 업무(status=open)의 예상 시간 합계 = 오늘 마감 시점 장부에 달린 외상
- 업무가 추가/수정/완료/삭제될 때마다 data 컬렉션의 '오늘' 기록을 자동으로 갱신(upsert)한다.
  → 기존 요약/캘린더/AI 상담이 별도 수정 없이 자동 계산된 값을 사용
"""

import datetime as dt
from typing import Any, Optional

from google.cloud.firestore_v1.base_query import FieldFilter

from backend.core.config import today
from backend.core.exceptions import BadRequestError, NotFoundError
from backend.models.task import AiEstimate
from backend.services import data_service
from backend.services.firebase_service import get_firestore_client


COLLECTION_NAME = "tasks"
MEMO_LIMIT = 500


def _collection():
    return get_firestore_client().collection(COLLECTION_NAME)


def _fmt(minutes: float) -> str:
    minutes = int(round(minutes))
    hours, rest = divmod(minutes, 60)
    if hours and rest:
        return f"{hours}시간 {rest}분"
    return f"{hours}시간" if hours else f"{rest}분"


def _serialize(document_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": document_id,
        "title": data["title"],
        "estimated_minutes": data["estimated_minutes"],
        "status": data.get("status", "open"),
        "created_date": data["created_date"],
        "done_date": data.get("done_date"),
        "actual_minutes": data.get("actual_minutes"),
        "ai_estimate": data.get("ai_estimate"),
        "_created_at": data.get("created_at"),
    }


def _public(task: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in task.items() if not k.startswith("_")}


def _by_status(status: str) -> list[dict[str, Any]]:
    # 복합 색인 없이 동작하도록 정렬은 파이썬에서 처리
    docs = _collection().where(filter=FieldFilter("status", "==", status)).stream()
    return [_serialize(d.id, d.to_dict()) for d in docs]


def list_tasks(status: str = "open", done_limit: int = 30) -> list[dict[str, Any]]:
    if status == "open":
        tasks = sorted(_by_status("open"), key=lambda t: (t["created_date"], str(t["_created_at"])))
    elif status == "done":
        tasks = sorted(_by_status("done"), key=lambda t: (t["done_date"] or "", str(t["_created_at"])), reverse=True)
        tasks = tasks[:done_limit]
    else:
        tasks = list_tasks("open") + list_tasks("done", done_limit)
        return tasks
    return [_public(t) for t in tasks]


def _get(task_id: str):
    ref = _collection().document(task_id)
    doc = ref.get()
    if not doc.exists:
        raise NotFoundError("해당 업무를 찾을 수 없습니다.")
    return ref, doc.to_dict()


def create_task(title: str, estimated_minutes: int, ai_estimate: Optional[AiEstimate]) -> dict[str, Any]:
    ref = _collection().document()
    data = {
        "title": title,
        "estimated_minutes": estimated_minutes,
        "status": "open",
        "created_date": today().isoformat(),
        "created_at": dt.datetime.now(dt.timezone.utc),
        "ai_estimate": ai_estimate.model_dump() if ai_estimate else None,
    }
    ref.set(data)
    return _public(_serialize(ref.id, data))


def update_task(task_id: str, values: dict[str, Any]) -> dict[str, Any]:
    values = {k: v for k, v in values.items() if v is not None}
    if not values:
        raise BadRequestError("수정할 항목(title, estimated_minutes)을 입력하세요.")
    ref, data = _get(task_id)
    ref.update(values)
    data.update(values)
    return _public(_serialize(task_id, data))


def complete_task(task_id: str, actual_minutes: int) -> dict[str, Any]:
    ref, data = _get(task_id)
    if data.get("status") == "done":
        raise BadRequestError("이미 완료된 업무입니다.")
    values = {"status": "done", "done_date": today().isoformat(), "actual_minutes": actual_minutes}
    ref.update(values)
    data.update(values)
    return _public(_serialize(task_id, data))


def reopen_task(task_id: str) -> dict[str, Any]:
    ref, data = _get(task_id)
    values = {"status": "open", "done_date": None, "actual_minutes": None}
    ref.update(values)
    data.update(values)
    return _public(_serialize(task_id, data))


def delete_task(task_id: str) -> None:
    ref, _ = _get(task_id)
    ref.delete()


def completed_history(limit: int = 15) -> list[dict[str, Any]]:
    """AI 예상 시간 보정용: 최근 완료 업무의 예상 vs 실제."""
    return [
        {"title": t["title"], "estimated": t["estimated_minutes"], "actual": t["actual_minutes"]}
        for t in list_tasks("done", limit)
        if t.get("actual_minutes") is not None
    ]


def sync_today_debt() -> dict[str, Any]:
    """남은 업무 합계로 오늘의 data 기록을 생성/갱신한다."""
    open_tasks = list_tasks("open")
    done_today = [t for t in list_tasks("done", 50) if t["done_date"] == today().isoformat()]
    total = float(sum(t["estimated_minutes"] for t in open_tasks))

    parts = []
    if open_tasks:
        parts.append("남은 일: " + ", ".join(f"{t['title']}({_fmt(t['estimated_minutes'])})" for t in open_tasks))
    if done_today:
        parts.append("완료: " + ", ".join(f"{t['title']}(실제 {_fmt(t['actual_minutes'] or 0)})" for t in done_today))
    memo = " / ".join(parts) or "남은 일 없음"
    if len(memo) > MEMO_LIMIT:
        memo = memo[: MEMO_LIMIT - 1] + "…"

    date_iso = today().isoformat()
    existing_id = data_service._find_id_by_date(date_iso)
    payload = {"date": date_iso, "value": total, "memo": memo}
    collection = get_firestore_client().collection(data_service.COLLECTION_NAME)
    if existing_id:
        collection.document(existing_id).set(payload)
    else:
        collection.document().set(payload)
    return {"date": date_iso, "value": total, "open_count": len(open_tasks), "memo": memo}


def _open_on(day: str, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """그날 마감 시점에 남아 있던 일: 그날까지 추가됐고, 아직 안 끝났거나 그날 이후에 끝난 일."""
    return [
        t for t in tasks
        if t["created_date"] <= day and (t["status"] == "open" or (t["done_date"] or "") > day)
    ]


def carry_forward() -> dict[str, Any]:
    """앱을 열 때 호출: 마지막 기록 다음 날 ~ 어제까지 빈 날을 할 일 이력으로 채우고, 오늘 기록을 갱신한다.

    할 일을 건드리지 않은 날에도 남은 일은 그대로이므로 외상이 이어져야 한다.
    """
    yesterday = today() - dt.timedelta(days=1)
    previous = data_service.get_all_data(end=yesterday.isoformat())
    filled: list[str] = []
    if previous:
        tasks = _by_status("open") + _by_status("done")
        last = dt.date.fromisoformat(previous[-1]["date"])
        collection = get_firestore_client().collection(data_service.COLLECTION_NAME)
        day = last + dt.timedelta(days=1)
        while day <= yesterday:
            iso = day.isoformat()
            remaining = _open_on(iso, tasks)
            finished = [t for t in tasks if t.get("done_date") == iso]
            parts = []
            if remaining:
                parts.append("남은 일(이월): " + ", ".join(f"{t['title']}({_fmt(t['estimated_minutes'])})" for t in remaining))
            if finished:
                parts.append("완료: " + ", ".join(f"{t['title']}(실제 {_fmt(t['actual_minutes'] or 0)})" for t in finished))
            memo = (" / ".join(parts) or "남은 일 없음")[:MEMO_LIMIT]
            if not data_service._find_id_by_date(iso):
                collection.document().set(
                    {"date": iso, "value": float(sum(t["estimated_minutes"] for t in remaining)), "memo": memo}
                )
                filled.append(iso)
            day += dt.timedelta(days=1)
    return {"filled_dates": filled, "today_debt": sync_today_debt()}
