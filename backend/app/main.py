import logging
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import get_settings
from .database import SessionLocal, engine
from .models import Base
from .routers import accounts, alerts, auth, ledger, public, transactions

settings = get_settings()
settings.validate_for_production()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("blocktrace")

Base.metadata.create_all(engine)

app = FastAPI(title="BlockTrace API", version="1.0.0",
              docs_url=None if settings.environment == "production" else "/docs",
              redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["GET", "POST", "PATCH"], allow_headers=["Authorization", "Content-Type"])

_hits: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def guard(request: Request, call_next):
    """Request id, sliding-window rate limit (use Redis for multi-instance), security headers."""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    ip = request.client.host if request.client else "?"
    login = request.url.path == "/auth/login"
    limit = settings.login_rate_limit_per_minute if login else settings.rate_limit_per_minute
    bucket, now = _hits[f"{ip}:{'login' if login else 'api'}"], time.time()
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= limit:
        return JSONResponse({"detail": "Too many requests"}, status_code=429, headers={"Retry-After": "60"})
    bucket.append(now)
    start = time.perf_counter()
    response = await call_next(request)
    response.headers.update({"X-Request-ID": rid, "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
                             "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"})
    log.info("%s %s %s %.1fms rid=%s", request.method, request.url.path, response.status_code, (time.perf_counter() - start) * 1000, rid)
    return response


for r in (auth.router, accounts.router, transactions.router, alerts.router, ledger.router, public.router):
    app.include_router(r)


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["ops"])
def ready():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        return JSONResponse({"status": "db unavailable"}, status_code=503)
