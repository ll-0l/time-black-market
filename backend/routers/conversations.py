from fastapi import APIRouter, Query, status

from backend.models.conversation import ConversationCreate, ConversationDetail, ConversationListItem
from backend.services import conversation_service


router = APIRouter(prefix="/api/conversations", tags=["Conversations"])


@router.post(
    "",
    response_model=ConversationDetail,
    status_code=status.HTTP_201_CREATED,
    summary="대화 저장 (채팅 API는 자동 저장하므로 수동 저장/가져오기용)",
)
def create_conversation(body: ConversationCreate):
    return conversation_service.create_conversation(body.messages, body.title)


@router.get(
    "",
    response_model=list[ConversationListItem],
    summary="대화 목록 (최근 수정순, messages 미포함 — 전체는 GET /{id})",
)
def list_conversations(limit: int = Query(default=50, ge=1, le=100)):
    return conversation_service.list_conversations(limit)


@router.get("/{conversation_id}", response_model=ConversationDetail, summary="특정 대화 불러오기 (전체 messages)")
def get_conversation(conversation_id: str):
    return conversation_service.get_conversation(conversation_id)


@router.delete("/{conversation_id}", summary="대화 삭제")
def delete_conversation(conversation_id: str):
    conversation_service.delete_conversation(conversation_id)
    return {"message": "대화가 삭제되었습니다.", "id": conversation_id}
