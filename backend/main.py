from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import get_allowed_origins
from backend.core.exceptions import register_exception_handlers
from backend.routers.data import router as data_router


APP_VERSION = "0.3.0"

app = FastAPI(
    title="Time Black Market API",
    description=(
        "미래로 이월된 업무 시간을 Time Debt로 관리하고 "
        "AI가 상환 계획을 분석하는 서비스 API"
    ),
    version=APP_VERSION,
)

# CORS: 허용 도메인은 ALLOWED_ORIGINS 환경변수(쉼표 구분)로 관리
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(data_router)


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
