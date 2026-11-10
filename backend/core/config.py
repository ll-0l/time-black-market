import datetime as dt
import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


load_dotenv()

APP_TIMEZONE = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Seoul"))

DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
]


def get_allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "")
    origins = [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
    return origins or DEFAULT_ORIGINS


def today() -> dt.date:
    """서버 위치(Render는 UTC)와 무관하게 서비스 기준 시간대의 오늘 날짜."""
    return dt.datetime.now(APP_TIMEZONE).date()
