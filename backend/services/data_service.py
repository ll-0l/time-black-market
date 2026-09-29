from typing import Any

from google.cloud.firestore_v1.base_query import FieldFilter

from backend.models.data import DataCreate, DataUpdate
from backend.services.firebase_service import get_firestore_client


COLLECTION_NAME = "data"


def _serialize_document(
    document_id: str,
    document_data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": document_id,
        "date": document_data["date"],
        "value": document_data["value"],
        "memo": document_data.get("memo", ""),
    }


def create_data(data: DataCreate) -> dict[str, Any]:
    db = get_firestore_client()

    document_ref = db.collection(COLLECTION_NAME).document()

    document_data = {
        "date": data.date.isoformat(),
        "value": data.value,
        "memo": data.memo,
    }

    document_ref.set(document_data)

    return _serialize_document(
        document_ref.id,
        document_data,
    )


def get_all_data() -> list[dict[str, Any]]:
    db = get_firestore_client()

    documents = (
        db.collection(COLLECTION_NAME)
        .order_by("date")
        .stream()
    )

    result = []

    for document in documents:
        document_data = document.to_dict()

        result.append(
            _serialize_document(
                document.id,
                document_data,
            )
        )

    return result


def get_data_by_id(
    data_id: str,
) -> dict[str, Any] | None:
    db = get_firestore_client()

    document_ref = (
        db.collection(COLLECTION_NAME)
        .document(data_id)
    )

    document = document_ref.get()

    if not document.exists:
        return None

    return _serialize_document(
        document.id,
        document.to_dict(),
    )


def update_data(
    data_id: str,
    data: DataUpdate,
) -> dict[str, Any] | None:
    db = get_firestore_client()

    document_ref = (
        db.collection(COLLECTION_NAME)
        .document(data_id)
    )

    document = document_ref.get()

    if not document.exists:
        return None

    update_values = data.model_dump(
        exclude_unset=True
    )

    if "date" in update_values:
        update_values["date"] = (
            update_values["date"].isoformat()
        )

    document_ref.update(update_values)

    updated_document = document_ref.get()

    return _serialize_document(
        updated_document.id,
        updated_document.to_dict(),
    )


def delete_data(
    data_id: str,
) -> bool:
    db = get_firestore_client()

    document_ref = (
        db.collection(COLLECTION_NAME)
        .document(data_id)
    )

    document = document_ref.get()

    if not document.exists:
        return False

    document_ref.delete()

    return True


def get_summary() -> dict[str, Any]:
    data_list = get_all_data()

    if not data_list:
        return {
            "period": None,
            "count": 0,
            "metrics": {
                "average": None,
                "max": None,
                "min": None,
            },
            "trend": "데이터 없음",
        }

    values = [
        item["value"]
        for item in data_list
    ]

    average = sum(values) / len(values)

    if len(values) < 2:
        trend = "유지"

    else:
        recent_count = min(
            7,
            len(values),
        )

        recent_values = values[-recent_count:]

        midpoint = max(
            1,
            len(recent_values) // 2,
        )

        previous_values = (
            recent_values[:midpoint]
        )

        current_values = (
            recent_values[midpoint:]
        )

        previous_average = (
            sum(previous_values)
            / len(previous_values)
        )

        current_average = (
            sum(current_values)
            / len(current_values)
        )

        difference = (
            current_average
            - previous_average
        )

        if difference > 5:
            trend = "증가"

        elif difference < -5:
            trend = "감소"

        else:
            trend = "유지"

    return {
        "period": {
            "start": data_list[0]["date"],
            "end": data_list[-1]["date"],
        },
        "count": len(data_list),
        "metrics": {
            "average": round(
                average,
                2,
            ),
            "max": max(values),
            "min": min(values),
        },
        "trend": trend,
    }