import datetime as dt
from typing import Any, Optional

from google.cloud import firestore as gcf

from backend.core.exceptions import NotFoundError
from backend.models.conversation import MAX_MESSAGES_PER_CONVERSATION, Message
from backend.services.firebase_service import get_firestore_client


COLLECTION_NAME = "conversations"
TITLE_LENGTH = 30
PREVIEW_LENGTH = 60


def _collection():
    return get_firestore_client().collection(COLLECTION_NAME)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _make_title(messages: list[Message]) -> str:
    first_user = next((m.content for m in messages if m.role == "user"), messages[0].content)
    first_line = first_user.splitlines()[0]
    return first_line[:TITLE_LENGTH] + ("…" if len(first_line) > TITLE_LENGTH else "")


def _message_to_doc(message: Message) -> dict[str, Any]:
    return {
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at or _now(),
        "tools_used": message.tools_used,
    }


def _serialize(document_id: str, data: dict[str, Any], include_messages: bool) -> dict[str, Any]:
    messages = data.get("messages", [])
    last = messages[-1]["content"] if messages else ""
    result = {
        "id": document_id,
        "title": data.get("title", "제목 없음"),
        "created_at": data["created_at"],
        "updated_at": data.get("updated_at", data["created_at"]),
        "message_count": len(messages),
        "last_message": last[:PREVIEW_LENGTH],
    }
    if include_messages:
        result["messages"] = messages
    return result


def create_conversation(messages: list[Message], title: Optional[str] = None) -> dict[str, Any]:
    now = _now()
    document_ref = _collection().document()
    data = {
        "title": (title or "").strip() or _make_title(messages),
        "messages": [_message_to_doc(m) for m in messages],
        "created_at": now,
        "updated_at": now,
    }
    document_ref.set(data)
    return _serialize(document_ref.id, data, include_messages=True)


def list_conversations(limit: int = 50) -> list[dict[str, Any]]:
    query = _collection().order_by("updated_at", direction=gcf.Query.DESCENDING).limit(limit)
    return [_serialize(doc.id, doc.to_dict(), include_messages=False) for doc in query.stream()]


def get_conversation(conversation_id: str) -> dict[str, Any]:
    document = _collection().document(conversation_id).get()
    if not document.exists:
        raise NotFoundError("해당 대화를 찾을 수 없습니다.")
    return _serialize(document.id, document.to_dict(), include_messages=True)


def append_messages(conversation_id: str, messages: list[Message]) -> dict[str, Any]:
    document_ref = _collection().document(conversation_id)
    document = document_ref.get()
    if not document.exists:
        raise NotFoundError("해당 대화를 찾을 수 없습니다.")

    data = document.to_dict()
    stored = data.get("messages", []) + [_message_to_doc(m) for m in messages]
    stored = stored[-MAX_MESSAGES_PER_CONVERSATION:]  # 문서 크기 제한(1MB) 보호
    data.update({"messages": stored, "updated_at": _now()})
    document_ref.update({"messages": stored, "updated_at": data["updated_at"]})
    return _serialize(conversation_id, data, include_messages=True)


def delete_conversation(conversation_id: str) -> None:
    document_ref = _collection().document(conversation_id)
    if not document_ref.get().exists:
        raise NotFoundError("해당 대화를 찾을 수 없습니다.")
    document_ref.delete()
