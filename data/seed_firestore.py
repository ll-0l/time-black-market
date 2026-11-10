"""CSV → Firestore 'data' 컬렉션 업로드 (하루 1건 규칙 유지).

사용법 (프로젝트 루트에서):
    python -m data.seed_firestore                 # 이미 있는 날짜는 건너뜀
    python -m data.seed_firestore --overwrite     # 이미 있는 날짜는 값 덮어쓰기
    python -m data.seed_firestore --reset         # data 컬렉션 비우고 새로 업로드
"""

import argparse
import csv
from pathlib import Path

from backend.services.firebase_service import get_firestore_client


DEFAULT_CSV = Path(__file__).with_name("sample_time_debt.csv")
BATCH_LIMIT = 400


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    collection = get_firestore_client().collection("data")
    db = get_firestore_client()

    if args.reset:
        deleted = 0
        for doc in collection.stream():
            doc.reference.delete()
            deleted += 1
        print(f"기존 문서 {deleted}건 삭제")

    existing = {doc.to_dict()["date"]: doc.reference for doc in collection.stream()}

    with args.csv.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    batch, pending, created, updated, skipped = db.batch(), 0, 0, 0, 0
    for row in rows:
        payload = {"date": row["date"], "value": float(row["value"]), "memo": row.get("memo", "")}
        if row["date"] in existing:
            if not args.overwrite:
                skipped += 1
                continue
            batch.set(existing[row["date"]], payload)
            updated += 1
        else:
            batch.set(collection.document(), payload)
            created += 1
        pending += 1
        if pending >= BATCH_LIMIT:
            batch.commit()
            batch, pending = db.batch(), 0
    if pending:
        batch.commit()

    print(f"추가 {created}건 / 덮어쓰기 {updated}건 / 건너뜀 {skipped}건")


if __name__ == "__main__":
    main()
