from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import get_allowed_origin_regex, get_allowed_origins
from backend.core.exceptions import register_exception_handlers
from backend.routers.chat import router as chat_router
from backend.routers.conversations import router as conversations_router
from backend.routers.data import router as data_router
from backend.routers.tasks import router as tasks_router


APP_VERSION = "0.5.0"

app = FastAPI(
    title="Time Black Market API",
    description=(
        "오늘 못 한 일을 미래의 시간에서 외상으로 당겨 쓰고 "
        "몰래 사장(AI)과 함께 갚아나가는 시간 외상 장부 API"
    ),
    version=APP_VERSION,
)

# CORS: 허용 도메인은 ALLOWED_ORIGINS 환경변수(쉼표 구분)로 관리
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_origin_regex=get_allowed_origin_regex(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(data_router)
app.include_router(conversations_router)
app.include_router(tasks_router)
app.include_router(chat_router)


@app.get("/", tags=["System"])
def root():
    return {
        "service": "Time Black Market",
        "message": "Time Black Market API is running.",
        "version": APP_VERSION,
        "docs": "/docs",
    }


@app.get("/health", tags=["System"])
def health_check():
    return {"status": "ok", "service": "time-black-market"}
