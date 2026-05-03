from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from . import auth, credits, gateway, keys, settings, usage
from .config import ALLOWED_ORIGINS, STATIC_DIR
from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="OpenToken API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

app.include_router(auth.router)
app.include_router(keys.router)
app.include_router(gateway.router)
app.include_router(usage.router)
app.include_router(credits.router)
app.include_router(settings.router)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/{asset_name}")
def static_asset(asset_name: str, request: Request) -> FileResponse:
    if asset_name not in {"app.js", "styles.css"}:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(STATIC_DIR / asset_name)


def main() -> None:
    uvicorn.run("backend.main:app", host="127.0.0.1", port=18080, reload=False)


if __name__ == "__main__":
    main()
