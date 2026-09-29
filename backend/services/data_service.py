from typing import Any
from uuid import uuid4

from backend.models.data import DataCreate, DataUpdate


# Firestore 연결 전 사용하는 임시 메모리 저장소
_data_store: list[dict[str, Any]] = []


def create_data(data: DataCreate) -> dict[str, Any]:
    new_data = {
        "id": str(uuid4()),
        "date": data.date,
        "value": data.value,
        "memo": data.memo,
    }

    _data_store.append(new_data)

    return new_data


def get_all_data() -> list[dict[str, Any]]:
    return sorted(
        _data_store,
        key=lambda item: item["date"],
    )


def get_data_by_id(data_id: str) -> dict[str, Any] | None:
    for item in _data_store:
        if item["id"] == data_id:
            return item

    return None


def update_data(
    data_id: str,
    data: DataUpdate,
) -> dict[str, Any] | None:
    existing_data = get_data_by_id(data_id)

    if existing_data is None:
        return None

    update_values = data.model_dump(exclude_unset=True)

    for key, value in update_values.items():
        existing_data[key] = value

    return existing_data


def delete_data(data_id: str) -> bool:
    existing_data = get_data_by_id(data_id)

    if existing_data is None:
        return False

    _data_store.remove(existing_data)

    return True


def get_summary() -> dict[str, Any]:
    if not _data_store:
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

    sorted_data = sorted(
        _data_store,
        key=lambda item: item["date"],
    )

    values = [
        item["value"]
        for item in sorted_data
    ]

    average = sum(values) / len(values)

    if len(values) < 2:
        trend = "유지"
    else:
        recent_count = min(7, len(values))

        recent_values = values[-recent_count:]

        midpoint = max(1, len(recent_values) // 2)

        previous_average = (
            sum(recent_values[:midpoint])
            / len(recent_values[:midpoint])
        )

        current_average = (
            sum(recent_values[midpoint:])
            / len(recent_values[midpoint:])
        )

        difference = current_average - previous_average

        if difference > 5:
            trend = "증가"
        elif difference < -5:
            trend = "감소"
        else:
            trend = "유지"

    return {
        "period": {
            "start": sorted_data[0]["date"],
            "end": sorted_data[-1]["date"],
        },
        "count": len(sorted_data),
        "metrics": {
            "average": round(average, 2),
            "max": max(values),
            "min": min(values),
        },
        "trend": trend,
    }