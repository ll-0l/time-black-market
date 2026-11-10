import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


MAX_TASK_MINUTES = 24 * 60


def _strip_title(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise ValueError("업무 이름을 입력하세요.")
    return value


class EstimateOption(BaseModel):
    label: str
    minutes: int = Field(..., ge=5, le=MAX_TASK_MINUTES)


class AiEstimate(BaseModel):
    options: list[EstimateOption]
    recommended: int = Field(..., ge=5, le=MAX_TASK_MINUTES)
    reason: str = ""


class EstimateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100, description="해야 할 업무")

    _strip = field_validator("title")(_strip_title)

    model_config = {"json_schema_extra": {"example": {"title": "주간 보고서 작성"}}}


class EstimateResponse(AiEstimate):
    title: str
    history_used: int = Field(description="예측에 참고한 과거 완료 업무 수")


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    estimated_minutes: int = Field(..., ge=1, le=MAX_TASK_MINUTES, description="사용자가 확정한 예상 소요 시간(분)")
    ai_estimate: Optional[AiEstimate] = Field(default=None, description="AI가 제안했던 값 (기록용)")

    _strip = field_validator("title")(_strip_title)

    model_config = {"json_schema_extra": {"example": {"title": "주간 보고서 작성", "estimated_minutes": 60}}}


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=100)
    estimated_minutes: Optional[int] = Field(default=None, ge=1, le=MAX_TASK_MINUTES)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else _strip_title(value)


class TaskComplete(BaseModel):
    actual_minutes: int = Field(..., ge=0, le=MAX_TASK_MINUTES, description="실제로 걸린 시간(분)")


class TaskResponse(BaseModel):
    id: str
    title: str
    estimated_minutes: int
    status: Literal["open", "done"]
    created_date: dt.date
    done_date: Optional[dt.date] = None
    actual_minutes: Optional[int] = None
    ai_estimate: Optional[AiEstimate] = None


class TodayDebt(BaseModel):
    date: dt.date
    value: float = Field(description="남은 업무 예상 시간 합계(분) = 오늘의 시간 부채")
    open_count: int
    memo: str


class TaskMutationResponse(BaseModel):
    task: Optional[TaskResponse] = None
    today_debt: TodayDebt
