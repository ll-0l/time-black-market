from typing import Literal

from fastapi import APIRouter, Depends, Query, status

from backend.core.rate_limit import chat_rate_limit
from backend.models.task import (
    EstimateRequest,
    EstimateResponse,
    TaskComplete,
    TaskCreate,
    TaskMutationResponse,
    TaskResponse,
    TaskUpdate,
)
from backend.services import estimate_service, task_service


router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


@router.post(
    "/estimate",
    response_model=EstimateResponse,
    dependencies=[Depends(chat_rate_limit)],
    summary="AI 예상 소요 시간 (빠르게/보통/넉넉히 3가지 제안, 과거 실제 기록으로 보정)",
)
def estimate_task(body: EstimateRequest):
    return estimate_service.estimate(body.title)


@router.post("/sync", summary="장부 이월: 빈 날을 할 일 이력으로 채우고 오늘 외상 갱신 (앱 시작 시 호출)")
def sync_ledger():
    return task_service.carry_forward()


@router.get("", response_model=list[TaskResponse], summary="업무 목록 (open: 남은 일, done: 완료한 일)")
def list_tasks(
    status_filter: Literal["open", "done", "all"] = Query(default="open", alias="status"),
    limit: int = Query(default=30, ge=1, le=100, description="done 목록 최대 개수"),
):
    return task_service.list_tasks(status_filter, limit)


@router.post(
    "",
    response_model=TaskMutationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="업무 추가 → 오늘의 외상 자동 재계산",
)
def create_task(body: TaskCreate):
    task = task_service.create_task(body.title, body.estimated_minutes, body.ai_estimate)
    return {"task": task, "today_debt": task_service.sync_today_debt()}


@router.put("/{task_id}", response_model=TaskMutationResponse, summary="업무 수정 (이름/예상 시간)")
def update_task(task_id: str, body: TaskUpdate):
    task = task_service.update_task(task_id, body.model_dump(exclude_unset=True))
    return {"task": task, "today_debt": task_service.sync_today_debt()}


@router.post("/{task_id}/complete", response_model=TaskMutationResponse, summary="업무 완료 (실제 소요 시간 기록 → 외상 갚음)")
def complete_task(task_id: str, body: TaskComplete):
    task = task_service.complete_task(task_id, body.actual_minutes)
    return {"task": task, "today_debt": task_service.sync_today_debt()}


@router.post("/{task_id}/reopen", response_model=TaskMutationResponse, summary="완료 취소 (다시 외상으로)")
def reopen_task(task_id: str):
    task = task_service.reopen_task(task_id)
    return {"task": task, "today_debt": task_service.sync_today_debt()}


@router.delete("/{task_id}", response_model=TaskMutationResponse, summary="업무 삭제")
def delete_task(task_id: str):
    task_service.delete_task(task_id)
    return {"task": None, "today_debt": task_service.sync_today_debt()}
