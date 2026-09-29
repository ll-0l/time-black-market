from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class DataCreate(BaseModel):
    date: date
    value: float = Field(
        ...,
        ge=0,
        description="해당 날짜의 총 시간 부채(분)",
    )
    memo: str = Field(
        default="",
        max_length=500,
        description="해당 날짜의 주요 시간 부채 메모",
    )


class DataUpdate(BaseModel):
    date: Optional[date] = None
    value: Optional[float] = Field(
        default=None,
        ge=0,
    )
    memo: Optional[str] = Field(
        default=None,
        max_length=500,
    )


class DataResponse(BaseModel):
    id: str
    date: date
    value: float
    memo: str