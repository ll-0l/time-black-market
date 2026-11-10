import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from backend.core.config import today


MAX_DEBT_MINUTES = 24 * 60 * 7  # 하루 기록 상한: 1주일치 시간(분)


def _validate_not_future(value: Optional[dt.date]) -> Optional[dt.date]:
    if value is not None and value > today():
        raise ValueError("미래 날짜는 기록할 수 없습니다.")
    return value


class DataCreate(BaseModel):
    date: dt.date = Field(..., description="기록 날짜 (하루 1건)")
    value: float = Field(
        ...,
        ge=0,
        le=MAX_DEBT_MINUTES,
        description="해당 날짜 마감 시점 장부에 남은 시간 외상(분)",
    )
    memo: str = Field(
        default="",
        max_length=500,
        description="해당 날짜에 미룬 업무 / 끝낸 업무 메모",
    )

    _check_date = field_validator("date")(_validate_not_future)

    @field_validator("memo")
    @classmethod
    def strip_memo(cls, value: str) -> str:
        return value.strip()

    model_config = {
        "json_schema_extra": {
            "example": {
                "date": "2026-11-10",
                "value": 240,
                "memo": "주간 보고서, 이메일 정리 미룸",
            }
        }
    }


class DataUpdate(BaseModel):
    date: Optional[dt.date] = None
    value: Optional[float] = Field(default=None, ge=0, le=MAX_DEBT_MINUTES)
    memo: Optional[str] = Field(default=None, max_length=500)

    _check_date = field_validator("date")(_validate_not_future)

    model_config = {
        "json_schema_extra": {"example": {"value": 180, "memo": "보고서 끝내서 외상 갚음"}}
    }


class DataResponse(BaseModel):
    id: str
    date: dt.date
    value: float
    memo: str
