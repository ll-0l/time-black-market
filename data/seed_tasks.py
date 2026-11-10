"""데모용 할 일(tasks) 시드: 과거 완료 기록(예상 vs 실제) + 현재 남은 일.

완료 기록은 AI 예상 시간 보정에 쓰이고, 남은 일 합계는 오늘의 시간 부채로 자동 반영된다.

사용법 (프로젝트 루트에서):
    python -m data.seed_tasks          # tasks 컬렉션을 비우고 새로 넣음
"""

import datetime as dt

from backend.core.config import today
from backend.services import task_service
from backend.services.firebase_service import get_firestore_client


# (제목, 예상, 실제, 며칠 전 완료)
DONE = [
    ("주간 보고서 작성", 60, 80, 7),
    ("이메일 정리", 30, 25, 6),
    ("회의록 정리", 40, 55, 6),
    ("코드 리뷰", 45, 60, 5),
    ("발표 자료 준비", 90, 120, 4),
    ("영수증 정산", 20, 15, 3),
    ("강의 복습", 60, 70, 2),
    ("버그 수정", 60, 95, 2),
    ("방 청소", 40, 35, 1),
    ("문서화", 50, 65, 1),
]
# (제목, 예상)
OPEN = [
    ("주간 보고서 작성", 60),
    ("이메일 정리", 30),
    ("코드 리뷰", 45),
    ("장보기", 20),
]


def main() -> None:
    collection = get_firestore_client().collection(task_service.COLLECTION_NAME)
    removed = 0
    for doc in collection.stream():
        doc.reference.delete()
        removed += 1

    now = dt.datetime.now(dt.timezone.utc)
    base = today()
    for i, (title, estimated, actual, days_ago) in enumerate(DONE):
        done = base - dt.timedelta(days=days_ago)
        collection.document().set({
            "title": title,
            "estimated_minutes": estimated,
            "status": "done",
            "created_date": (done - dt.timedelta(days=1)).isoformat(),
            "done_date": done.isoformat(),
            "actual_minutes": actual,
            "created_at": now - dt.timedelta(days=days_ago, minutes=i),
            "ai_estimate": None,
        })
    for i, (title, estimated) in enumerate(OPEN):
        collection.document().set({
            "title": title,
            "estimated_minutes": estimated,
            "status": "open",
            "created_date": base.isoformat(),
            "created_at": now + dt.timedelta(seconds=i),
            "ai_estimate": None,
        })

    debt = task_service.sync_today_debt()
    print(f"기존 {removed}건 삭제 → 완료 {len(DONE)}건 + 남은 일 {len(OPEN)}건 추가")
    print(f"오늘({debt['date']}) 시간 부채 자동 계산: {debt['value']:.0f}분 / {debt['memo']}")


if __name__ == "__main__":
    main()
