from fastapi import APIRouter, Depends

from backend.core.rate_limit import chat_rate_limit
from backend.models.chat import ChatRequest, ChatResponse
from backend.services import chat_service


router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post(
    "",
    response_model=ChatResponse,
    dependencies=[Depends(chat_rate_limit)],
    summary="AI 대화 (요약 컨텍스트 주입 + Function Calling + 자동 저장)",
)
def chat(body: ChatRequest):
    return chat_service.chat(body.message, body.conversation_id)
