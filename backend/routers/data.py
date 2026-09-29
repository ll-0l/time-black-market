from fastapi import APIRouter, HTTPException, status

from backend.models.data import (
    DataCreate,
    DataResponse,
    DataUpdate,
)
from backend.services import data_service


router = APIRouter(
    prefix="/api/data",
    tags=["Data"],
)


@router.post(
    "",
    response_model=DataResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_data(data: DataCreate):
    return data_service.create_data(data)


@router.get(
    "",
    response_model=list[DataResponse],
)
def get_data_list():
    return data_service.get_all_data()


@router.get("/summary")
def get_data_summary():
    return data_service.get_summary()


@router.put(
    "/{data_id}",
    response_model=DataResponse,
)
def update_data(
    data_id: str,
    data: DataUpdate,
):
    updated_data = data_service.update_data(
        data_id,
        data,
    )

    if updated_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 데이터를 찾을 수 없습니다.",
        )

    return updated_data


@router.delete("/{data_id}")
def delete_data(data_id: str):
    deleted = data_service.delete_data(data_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 데이터를 찾을 수 없습니다.",
        )

    return {
        "message": "데이터가 삭제되었습니다.",
        "id": data_id,
    }