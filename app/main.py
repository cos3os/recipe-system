"""
RefrigerAI - FastAPI 메인 앱
-----------------------------
실행:
  uvicorn app.main:app --reload

Swagger UI:
  http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.recipes import router as recipes_router

app = FastAPI(
    title="RefrigerAI API",
    description="냉장고 기반 맞춤형 영양·레시피 최적화 API (KG + LP + LLM)",
    version="0.1.0",
)

# ── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # 개발 단계; 배포 시 프론트 도메인으로 좁힐 것
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 라우터 등록 ───────────────────────────────────────────
app.include_router(recipes_router)

# ── 헬스체크 ──────────────────────────────────────────────
@app.get("/", tags=["health"])
async def root():
    return {"status": "ok", "service": "RefrigerAI API"}

@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
