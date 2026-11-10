import datetime as dt
from typing import Optional

from fastapi import APIRouter, Query, status

from backend.models.data import DataCreate, DataResponse, DataUpdate
from backend.services import analytics_service, data_service


router = APIRouter(prefix="/api/data", tags=["Data"])


@router.post(
    "",
    response_model=DataResponse,
    status_code=status.HTTP_201_CREATED,
    summary="새 데이터 추가 (하루 1건, 같은 날짜가 있으면 409)",
)
def create_data(data: DataCreate):
    return data_service.create_data(data)


@router.get("", response_model=list[DataResponse], summary="데이터 목록 조회 (날짜 오름차순)")
def get_data_list(
    start: Optional[dt.date] = Query(default=None, description="시작일 (포함)"),
    end: Optional[dt.date] = Query(default=None, description="종료일 (포함)"),
):
    return data_service.get_all_data(
        start.isoformat() if start else None,
        end.isoformat() if end else None,
    )


@router.get("/summary", summary="데이터 요약 (AI 시스템 프롬프트 주입용)")
def get_data_summary():
    return analytics_service.build_summary(data_service.get_all_data())


@router.get("/statistics", summary="확장 통계 (요일별/월별/7일 이동평균)")
def get_data_statistics():
    return analytics_service.build_statistics(data_service.get_all_data())


@router.get("/{data_id}", response_model=DataResponse, summary="단건 조회")
def get_data(data_id: str):
    return data_service.get_data_by_id(data_id)


@router.put("/{data_id}", response_model=DataResponse, summary="데이터 수정 (보낸 항목만 변경)")
def update_data(data_id: str, data: DataUpdate):
    return data_service.update_data(data_id, data)


@router.delete("/{data_id}", summary="데이터 삭제")
def delete_data(data_id: str):
    data_service.delete_data(data_id)
    return {"message": "데이터가 삭제되었습니다.", "id": data_id}
