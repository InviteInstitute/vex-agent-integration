import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from src.routes.students import router as students_router
from src.routes.admin import router as admin_router
from src.routes.stream import router as stream_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

load_dotenv()


def get_allowed_origins() -> list[str]:
    configured_origins = os.getenv("BACKEND_CORS_ORIGINS", "")
    if configured_origins.strip():
        return [
            origin.strip()
            for origin in configured_origins.split(",")
            if origin.strip()
        ]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


app = FastAPI(title="Pedagogical AI Agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(students_router)
app.include_router(admin_router)
app.include_router(stream_router)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
