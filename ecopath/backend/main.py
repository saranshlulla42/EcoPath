"""
EcoPath Backend — Main FastAPI Application
"""

import asyncio
import logging
import uvicorn
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from agent.session import cleanup_stale_sessions
from config import get_settings
from routers import species, maps, anomalies, chat, xenocanto, movebank, extinction_risk
from services.extinction_risk_service import warm_report_model

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ecopath")

settings = get_settings()


# ─── Lifespan ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🦜 EcoPath API starting up...")
    logger.info(f"  Supabase URL: {settings.supabase_url[:40]}...")
    logger.info(f"  Gemini Pro Model: {settings.gemini_pro_model}")
    logger.info(f"  Ollama Model: {settings.ollama_report_model}")
    logger.info(f"  CORS Origins: {settings.cors_origins_list}")
    # Warm up the report model in background without blocking startup
    asyncio.create_task(warm_report_model())

    cleanup_task = asyncio.create_task(cleanup_stale_sessions())
    logger.info("  Research session cleanup task started.")

    yield

    cleanup_task.cancel()
    with suppress(asyncio.CancelledError):
        await cleanup_task
    logger.info("🦜 EcoPath API shutting down...")


# ─── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="EcoPath API",
    description=(
        "Diagnostic Ecological Intelligence API for Indian Bird Biodiversity. "
        "Provides species data, geospatial heatmaps, migration routes, "
        "anomaly detection, and Gemini-powered causal reasoning."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── Middleware ───────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ─── Routers ─────────────────────────────────────────────────────────────────
app.include_router(species.router, prefix="/api/species", tags=["Species"])
app.include_router(maps.router, prefix="/api/maps", tags=["Maps"])
app.include_router(
    anomalies.router, prefix="/api/anomalies", tags=["Anomalies"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(xenocanto.router, prefix="/api/xenocanto",
                   tags=["Xeno-Canto"])
app.include_router(movebank.router, prefix="/api/movebank", tags=["Movebank"])
app.include_router(extinction_risk.router,
                   prefix="/api/extinction-risk", tags=["Extinction Risk"])


# ─── Health Check ────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "service": "EcoPath API",
        "version": "1.0.0",
    }


@app.get("/", tags=["System"])
async def root():
    return {
        "message": "🦜 EcoPath — Diagnostic Ecological Intelligence Dashboard",
        "docs": "/docs",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level=settings.log_level,
    )
