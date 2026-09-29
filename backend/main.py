from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers.data import router as data_router


app = FastAPI(
    title="Time Black Market API",
    description=(
        "미래로 이월된 업무 시간을 Time Debt로 관리하고 "
        "AI가 상환 계획을 분석하는 서비스 API"
    ),
    version="0.2.0",
)


# 개발 단계 CORS 설정
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(data_router)


@app.get("/")
def root():
    return {
        "service": "Time Black Market",
        "message": "Time Black Market API is running.",
        "version": "0.2.0",
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "time-black-market",
    }