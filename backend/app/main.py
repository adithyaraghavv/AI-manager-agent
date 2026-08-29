from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes_chat import router as chat_router
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_documents import router as documents_router
from app.config import settings

# Present only in the combined production image (see Dockerfile.prod, which
# builds the frontend and copies its output here) — absent in normal local
# dev, where the frontend runs via its own Vite dev server instead. This
# path staying absent is what keeps the mount below a safe no-op locally.
_STATIC_FRONTEND_DIR = Path(__file__).resolve().parents[1] / "static_frontend"

app = FastAPI(title="Marlabs Delivery AI Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.cors_allowed_origins.split(",")
        if origin.strip()
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


class FrameAncestorsMiddleware(BaseHTTPMiddleware):
    """Lets specific origins (e.g. a SharePoint page) embed this app in an
    <iframe>. Browsers block cross-origin framing by default for security, so
    without this a SharePoint Embed web part would just show a blank box.
    A no-op when iframe_allowed_origins is unset — nothing is allowed to frame
    this app until an origin is explicitly configured."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        origins = [
            origin.strip()
            for origin in settings.iframe_allowed_origins.split(",")
            if origin.strip()
        ]
        if origins:
            response.headers["Content-Security-Policy"] = (
                f"frame-ancestors 'self' {' '.join(origins)}"
            )
        return response


app.add_middleware(FrameAncestorsMiddleware)

app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(dashboard_router)


@app.get("/health")
def health():
    return {"status": "ok"}


if _STATIC_FRONTEND_DIR.is_dir():
    # Registered last and mounted at "/" so it only ever catches requests
    # that didn't match an /api/* route or /health above — Starlette checks
    # routes in registration order. html=True serves index.html for any
    # unmatched path (client-side routing), same as a normal SPA host.
    app.mount(
        "/", StaticFiles(directory=_STATIC_FRONTEND_DIR, html=True), name="frontend"
    )
