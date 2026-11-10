import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


MAX_MESSAGES_PER_CONVERSATION = 200


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)
    created_at: Optional[dt.datetime] = None
    tools_used: list[str] = Field(default_factory=list, description="이 답변을 만들 때 AI가 호출한 도구 이름")

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("메시지 내용이 비어 있습니다.")
        return value


class ConversationCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=100, description="생략하면 첫 질문으로 자동 생성")
    messages: list[Message] = Field(..., min_length=1, max_length=MAX_MESSAGES_PER_CONVERSATION)

    model_config = {
        "json_schema_extra": {
            "example": {
                "title": "이번 주 외상 갚을 계획",
                "messages": [
                    {"role": "user", "content": "이번 주 외상 어때?"},
                    {"role": "assistant", "content": "최근 7일 평균이 직전 주보다 16% 줄었어요."},
                ],
            }
        }
    }


class ConversationListItem(BaseModel):
    """목록 응답: messages는 포함하지 않는다(가볍게). 전체 메시지는 GET /api/conversations/{id}."""

    id: str
    title: str
    created_at: dt.datetime
    updated_at: dt.datetime
    message_count: int
    last_message: str = ""


class ConversationDetail(ConversationListItem):
    messages: list[Message]
