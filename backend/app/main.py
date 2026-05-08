import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.db import Base, engine, run_startup_migrations
from app.routes import auth, chat, payments

load_dotenv()

app = FastAPI(title="NeuroVault API", version="1.0.0")

cors_origins_env = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
allowed_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)
run_startup_migrations()

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(payments.router)


@app.middleware("http")
async def add_zero_trust_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
