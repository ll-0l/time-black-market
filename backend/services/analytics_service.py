"""시계열(하루 1건: 그날 마감 시점 장부에 남은 시간 외상, 분) 분석.

Firestore에 의존하지 않는 순수 함수로 두어 테스트/재사용이 쉽도록 했다.
"""

import datetime as dt
import statistics
from collections import defaultdict
from typing import Any, Optional


WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]
TREND_WINDOW = 7
TREND_THRESHOLD_PCT = 5.0


def _to_date(value: Any) -> dt.date:
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value))


def _round(value: Optional[float], digits: int = 1) -> Optional[float]:
    return None if value is None else round(value, digits)


def _fmt_minutes(minutes: float) -> str:
    minutes = int(round(minutes))
    hours, rest = divmod(abs(minutes), 60)
    sign = "-" if minutes < 0 else ""
    if hours and rest:
        return f"{sign}{hours}시간 {rest}분"
    if hours:
        return f"{sign}{hours}시간"
    return f"{sign}{rest}분"


def _prepare(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """날짜순 정렬 + 전일 대비 변화량(change) 계산. 양수=외상 달기, 음수=외상 갚기."""
    rows = sorted(
        ({"date": _to_date(r["date"]), "value": float(r["value"]), "memo": r.get("memo", "")} for r in records),
        key=lambda r: r["date"],
    )
    previous = None
    for row in rows:
        row["change"] = None if previous is None else row["value"] - previous["value"]
        previous = row
    return rows


def _trend(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows) < 2:
        return {"label": "유지", "change_pct": 0.0, "description": "데이터가 부족해 추세를 판단할 수 없음"}

    window = min(TREND_WINDOW, len(rows) // 2)
    recent = [r["value"] for r in rows[-window:]]
    previous = [r["value"] for r in rows[-2 * window : -window]]
    recent_avg, previous_avg = statistics.mean(recent), statistics.mean(previous)

    if previous_avg == 0:
        change_pct = 0.0 if recent_avg == 0 else 100.0
    else:
        change_pct = (recent_avg - previous_avg) / previous_avg * 100

    if change_pct > TREND_THRESHOLD_PCT:
        label = "증가"
    elif change_pct < -TREND_THRESHOLD_PCT:
        label = "감소"
    else:
        label = "유지"

    return {
        "label": label,
        "change_pct": round(change_pct, 1),
        "window_days": window,
        "recent_average": round(recent_avg, 1),
        "previous_average": round(previous_avg, 1),
        "description": f"{label} (최근 {window}일 평균이 직전 {window}일 대비 {change_pct:+.1f}%)",
    }


def weekday_stats(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values: dict[int, list[float]] = defaultdict(list)
    changes: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        weekday = row["date"].weekday()
        values[weekday].append(row["value"])
        if row["change"] is not None:
            changes[weekday].append(row["change"])

    return [
        {
            "weekday": WEEKDAYS_KO[i],
            "count": len(values[i]),
            "average_debt": _round(statistics.mean(values[i])) if values[i] else None,
            "average_change": _round(statistics.mean(changes[i])) if changes[i] else None,
        }
        for i in range(7)
    ]


def _next_dates(weekday_ko: str, reference: dt.date, count: int = 3) -> list[str]:
    """reference(오늘)부터 해당 요일이 돌아오는 날짜 count개."""
    target = WEEKDAYS_KO.index(weekday_ko)
    first = reference + dt.timedelta(days=(target - reference.weekday()) % 7)
    return [(first + dt.timedelta(weeks=i)).isoformat() for i in range(count)]


def _recommendation(weekdays: list[dict[str, Any]], reference: Optional[dt.date] = None) -> dict[str, Any]:
    """갚기 좋은 날: 평균 변화량이 가장 낮은(=평소 외상이 가장 많이 줄어드는) 요일.

    '평균 외상이 가장 낮은 요일'은 외상 '잔액'이라 전날의 영향을 크게 받는다.
    갚을 여력은 '그날 얼마나 줄였는가(변화량)'가 더 직접적인 지표이므로 변화량을 기준으로 한다.
    """
    candidates = [w for w in weekdays if w["average_change"] is not None]
    if not candidates:
        return {"weekday": None, "reason": "요일별 비교에 필요한 데이터가 부족함"}

    best = min(candidates, key=lambda w: w["average_change"])
    worst = max(candidates, key=lambda w: w["average_change"])
    next_dates = _next_dates(best["weekday"], reference or dt.date.today())
    return {
        "weekday": best["weekday"],
        "next_date": next_dates[0],
        "next_dates": next_dates,
        "average_change": best["average_change"],
        "avoid_weekday": worst["weekday"],
        "avoid_average_change": worst["average_change"],
        "reason": (
            f"{best['weekday']}요일에 평균 {_fmt_minutes(-best['average_change'])}씩 외상을 갚아서 갚기 제일 좋은 날. "
            f"{worst['weekday']}요일엔 평균 {_fmt_minutes(worst['average_change'])}씩 외상이 늘어나니 조심"
        ),
    }


def _payoff_forecast(rows: list[dict[str, Any]], window: int = 14) -> dict[str, Any]:
    """최근 순변화 속도가 유지될 때 외상이 0이 되는 날(다 갚는 날) 예측."""
    current = rows[-1]
    if current["value"] == 0:
        return {"status": "다 갚음", "estimated_date": current["date"].isoformat(), "days_left": 0}

    recent = rows[-(window + 1) :]
    if len(recent) < 2:
        return {"status": "판단 불가", "estimated_date": None, "days_left": None}

    elapsed_days = (recent[-1]["date"] - recent[0]["date"]).days or 1
    daily_rate = (recent[-1]["value"] - recent[0]["value"]) / elapsed_days
    if daily_rate >= 0:
        return {
            "status": "이대로면 못 갚음",
            "estimated_date": None,
            "days_left": None,
            "daily_rate": round(daily_rate, 1),
            "description": f"최근 {elapsed_days}일 동안 하루 평균 {_fmt_minutes(daily_rate)}씩 외상이 늘어 지금 속도로는 다 갚기 어려움",
        }

    days_left = int(-(-current["value"] // -daily_rate))  # ceil
    estimated = current["date"] + dt.timedelta(days=days_left)
    return {
        "status": "갚는 중",
        "estimated_date": estimated.isoformat(),
        "days_left": days_left,
        "daily_rate": round(daily_rate, 1),
        "description": f"하루 평균 {_fmt_minutes(-daily_rate)}씩 줄고 있어 {estimated.isoformat()}쯤 다 갚을 예정",
    }


def _credit_grade(current: float, average: float) -> dict[str, str]:
    """몰래 사장의 손님 등급: 지금 외상을 평소(기간 평균)와 비교."""
    ratio = current / average if average else 0
    if ratio < 0.8:
        grade, label = "A", "모범 손님 — 평소보다 외상이 적음"
    elif ratio < 1.0:
        grade, label = "B", "단골 손님 — 평소보다 조금 적음"
    elif ratio < 1.25:
        grade, label = "C", "외상 주의 — 평소보다 많이 쌓임"
    else:
        grade, label = "D", "장부 빨간불 — 평소보다 25% 이상 많아 얼른 갚아야 함"
    return {"grade": grade, "label": label, "ratio_to_average": round(ratio, 2)}


def build_summary(records: list[dict[str, Any]], reference: Optional[dt.date] = None) -> dict[str, Any]:
    """프롬프트 주입용 요약."""
    if not records:
        return {
            "period": None,
            "count": 0,
            "metrics": None,
            "trend": {"label": "데이터 없음", "description": "데이터 없음"},
            "recommendation": None,
            "payoff_forecast": None,
            "credit": None,
            "recent_records": [],
        }

    rows = _prepare(records)
    values = [r["value"] for r in rows]
    changes = [r["change"] for r in rows if r["change"] is not None]
    max_row = max(rows, key=lambda r: r["value"])
    min_row = min(rows, key=lambda r: r["value"])
    current = rows[-1]
    average = statistics.mean(values)
    start, end = rows[0]["date"], rows[-1]["date"]
    calendar_days = (end - start).days + 1

    return {
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": calendar_days,
            "label": f"{start.isoformat()} ~ {end.isoformat()}",
        },
        "count": len(rows),
        "coverage_pct": round(len(rows) / calendar_days * 100, 1),
        "unit": "분",
        "metrics": {
            "current": current["value"],
            "current_date": current["date"].isoformat(),
            "average": round(average, 1),
            "median": round(statistics.median(values), 1),
            "max": max_row["value"],
            "max_date": max_row["date"].isoformat(),
            "min": min_row["value"],
            "min_date": min_row["date"].isoformat(),
            "total_borrowed": round(sum(c for c in changes if c > 0), 1),
            "total_repaid": round(-sum(c for c in changes if c < 0), 1),
            "borrow_days": sum(1 for c in changes if c > 0),
            "repay_days": sum(1 for c in changes if c < 0),
        },
        "trend": _trend(rows),
        "recommendation": _recommendation(weekday_stats(rows), reference),
        "payoff_forecast": _payoff_forecast(rows),
        "credit": _credit_grade(current["value"], average),
        "recent_records": [
            {"date": r["date"].isoformat(), "value": r["value"], "memo": r["memo"]} for r in rows[-7:]
        ],
    }


def build_statistics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """시각화/인사이트용 확장 통계."""
    if not records:
        return {"count": 0, "weekday": [], "monthly": [], "series": []}

    rows = _prepare(records)

    monthly: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        monthly[row["date"].strftime("%Y-%m")].append(row)

    series = []
    for i, row in enumerate(rows):
        window = rows[max(0, i - 6) : i + 1]
        series.append(
            {
                "date": row["date"].isoformat(),
                "value": row["value"],
                "change": row["change"],
                "moving_average_7": round(statistics.mean(r["value"] for r in window), 1),
            }
        )

    values = [r["value"] for r in rows]
    return {
        "count": len(rows),
        "stdev": round(statistics.pstdev(values), 1),
        "weekday": weekday_stats(rows),
        "monthly": [
            {
                "month": month,
                "count": len(items),
                "average": round(statistics.mean(r["value"] for r in items), 1),
                "max": max(r["value"] for r in items),
                "min": min(r["value"] for r in items),
                "net_change": round(items[-1]["value"] - items[0]["value"], 1),
            }
            for month, items in monthly.items()
        ],
        "series": series,
    }
