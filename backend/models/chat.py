from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="사용자 질문")
    conversation_id: Optional[str] = Field(default=None, description="이어서 대화할 대화 id (없으면 새 대화)")

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("질문을 입력하세요.")
        return value

    model_config = {"json_schema_extra": {"example": {"message": "갚기 좋은 날이 언제야?", "conversation_id": None}}}


class ToolCallLog(BaseModel):
    name: str
    arguments: dict[str, Any]


class ChatResponse(BaseModel):
    conversation_id: str
    title: str
    reply: str
    tool_calls: list[ToolCallLog] = Field(default_factory=list, description="AI가 호출한 도구와 인자 (호출 근거 확인용)")
    summary: dict[str, Any] = Field(description="시스템 프롬프트에 주입된 데이터 요약")
    model: str
