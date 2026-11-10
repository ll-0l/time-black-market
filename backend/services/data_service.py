from typing import Any, Optional

from google.cloud.firestore_v1.base_query import FieldFilter

from backend.core.exceptions import BadRequestError, ConflictError, NotFoundError
from backend.models.data import DataCreate, DataUpdate
from backend.services.firebase_service import get_firestore_client


COLLECTION_NAME = "data"


def _collection():
    return get_firestore_client().collection(COLLECTION_NAME)


def _serialize(document_id: str, document_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": document_id,
        "date": document_data["date"],
        "value": document_data["value"],
        "memo": document_data.get("memo", ""),
    }


def _find_id_by_date(date_iso: str) -> Optional[str]:
    matches = _collection().where(filter=FieldFilter("date", "==", date_iso)).limit(1).get()
    return matches[0].id if matches else None


def _ensure_date_available(date_iso: str, own_id: Optional[str] = None) -> None:
    """하루 1건 규칙: 같은 날짜의 다른 문서가 있으면 409."""
    existing_id = _find_id_by_date(date_iso)
    if existing_id and existing_id != own_id:
        raise ConflictError(
            f"{date_iso} 기록이 이미 있습니다. 새로 추가하지 말고 기존 기록을 수정하세요. (id: {existing_id})"
        )


def create_data(data: DataCreate) -> dict[str, Any]:
    date_iso = data.date.isoformat()
    _ensure_date_available(date_iso)

    document_ref = _collection().document()
    document_data = {"date": date_iso, "value": data.value, "memo": data.memo}
    document_ref.set(document_data)
    return _serialize(document_ref.id, document_data)


def get_all_data(
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> list[dict[str, Any]]:
    query = _collection()
    if start:
        query = query.where(filter=FieldFilter("date", ">=", start))
    if end:
        query = query.where(filter=FieldFilter("date", "<=", end))
    return [_serialize(doc.id, doc.to_dict()) for doc in query.order_by("date").stream()]


def get_data_by_id(data_id: str) -> dict[str, Any]:
    document = _collection().document(data_id).get()
    if not document.exists:
        raise NotFoundError("해당 데이터를 찾을 수 없습니다.")
    return _serialize(document.id, document.to_dict())


def update_data(data_id: str, data: DataUpdate) -> dict[str, Any]:
    update_values = data.model_dump(exclude_unset=True, exclude_none=True)
    if not update_values:
        raise BadRequestError("수정할 항목(date, value, memo)을 1개 이상 입력하세요.")

    document_ref = _collection().document(data_id)
    if not document_ref.get().exists:
        raise NotFoundError("해당 데이터를 찾을 수 없습니다.")

    if "date" in update_values:
        update_values["date"] = update_values["date"].isoformat()
        _ensure_date_available(update_values["date"], own_id=data_id)
    if "memo" in update_values:
        update_values["memo"] = update_values["memo"].strip()

    document_ref.update(update_values)
    updated = document_ref.get()
    return _serialize(updated.id, updated.to_dict())


def delete_data(data_id: str) -> None:
    document_ref = _collection().document(data_id)
    if not document_ref.get().exists:
        raise NotFoundError("해당 데이터를 찾을 수 없습니다.")
    document_ref.delete()
