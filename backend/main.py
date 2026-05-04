from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from . import admin, auth, credits, gateway, keys, settings, usage
from .cache import redis_client
from .config import ALLOWED_ORIGINS, LEGACY_STATIC_DIR, STATIC_DIR
from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    redis_client().ping()
    yield


app = FastAPI(title="OpenToken API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def frontend_dir():
    if (STATIC_DIR / "index.html").exists():
        return STATIC_DIR
    return LEGACY_STATIC_DIR


if (frontend_dir() / "assets").exists():
    app.mount("/assets", StaticFiles(directory=frontend_dir() / "assets"), name="assets")

app.include_router(auth.router)
app.include_router(keys.router)
app.include_router(gateway.router)
app.include_router(usage.router)
app.include_router(credits.router)
app.include_router(settings.router)
app.include_router(admin.router)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(frontend_dir() / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/{asset_name}")
def static_asset(asset_name: str, request: Request) -> FileResponse:
    if asset_name not in {"app.js", "styles.css", "favicon.ico"}:
        return FileResponse(frontend_dir() / "index.html", headers={"Cache-Control": "no-store"})
    path = frontend_dir() / asset_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, headers={"Cache-Control": "no-store"})


def main() -> None:
    uvicorn.run("backend.main:app", host="127.0.0.1", port=18080, reload=False)


if __name__ == "__main__":
    main()
