"""샘플 시계열 데이터 생성기 (하루 1건: 그날 마감 시점 총 시간 부채, 분).

현실적인 패턴을 넣어 분석/AI 답변이 의미 있도록 만든다.
- 평일(특히 월·화)에는 업무를 미뤄 부채가 늘고, 토요일에 크게 상환
- 월말 보고 주간에 차입 증가
- 9월 중순 '프로젝트 마감 크런치'로 부채 급증 후 회복
- 최근 한 달은 상환 습관이 생겨 완만한 감소 추세

사용법:
    python data/generate_sample_data.py              # 기본: 어제까지 150일
    python data/generate_sample_data.py --days 180 --end 2026-11-09
"""

import argparse
import csv
import datetime as dt
import random
from pathlib import Path


OUTPUT = Path(__file__).with_name("sample_time_debt.csv")

BORROW_TASKS = [
    ("주간 보고서 작성", 90), ("이메일 정리", 30), ("회의록 정리", 40), ("코드 리뷰", 60),
    ("과제 초안", 120), ("운동", 45), ("독서", 40), ("영수증 정산", 30),
    ("발표 자료 준비", 100), ("방 청소", 50), ("강의 복습", 70), ("포트폴리오 업데이트", 90),
    ("버그 수정", 80), ("문서화", 60), ("장보기", 40),
]
REPAY_TASKS = [
    "밀린 이메일 일괄 처리", "주간 보고서 제출", "회의록 정리 완료", "과제 초안 마무리",
    "발표 자료 완성", "청소 끝", "강의 복습 따라잡기", "문서화 완료", "코드 리뷰 몰아서 처리",
]

# 요일별 기본 순변화(분): 월~일
WEEKDAY_DRIFT = [50, 35, 20, 15, 10, -90, -40]


def generate(days: int, end: dt.date, seed: int) -> list[dict]:
    rng = random.Random(seed)
    start = end - dt.timedelta(days=days - 1)
    debt = 260.0
    baseline = 280.0  # 평소 수준(부채가 이 근처로 되돌아가는 경향)
    rows = []

    for i in range(days):
        day = start + dt.timedelta(days=i)
        progress = i / max(1, days - 1)
        drift = WEEKDAY_DRIFT[day.weekday()]

        if day.day >= 25:  # 월말 보고 주간
            drift += 25
        if dt.date(day.year, 9, 8) <= day <= dt.date(day.year, 9, 21):  # 마감 크런치
            drift += 70 if day.weekday() < 5 else 10
        if dt.date(day.year, 9, 22) <= day <= dt.date(day.year, 9, 30):  # 크런치 직후 회복
            drift -= 60
        if progress > 0.8:  # 최근: 상환 습관 형성 → 평소 수준 자체가 내려감
            baseline = 180.0
            drift -= 6

        change = drift + 0.08 * (baseline - debt) + rng.gauss(0, 30)
        debt = max(0.0, min(1500.0, debt + change))
        debt = round(debt / 5) * 5  # 5분 단위
        actual_change = debt - (rows[-1]["value"] if rows else 260.0)

        if actual_change > 10:
            picked = rng.sample(BORROW_TASKS, k=rng.randint(1, 2))
            memo = ", ".join(f"{name} 미룸" for name, _ in picked)
        elif actual_change < -10:
            memo = rng.choice(REPAY_TASKS)
        else:
            memo = "현상 유지"
        if day.day >= 25 and actual_change > 10:
            memo += " (월말 보고 주간)"
        if dt.date(day.year, 9, 8) <= day <= dt.date(day.year, 9, 21):
            memo += " (프로젝트 마감 크런치)"

        rows.append({"date": day.isoformat(), "value": debt, "memo": memo})

    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=150)
    parser.add_argument("--end", type=dt.date.fromisoformat, default=dt.date.today() - dt.timedelta(days=1))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rows = generate(args.days, args.end, args.seed)
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "value", "memo"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)}건 생성 → {OUTPUT} ({rows[0]['date']} ~ {rows[-1]['date']})")


if __name__ == "__main__":
    main()
