"""FastAPI application for the Revenue Leakage Agent."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from revenue_agent.api.routes import router
from revenue_agent.config import settings
from revenue_agent.services.data_loader import data_loader

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler - load data on startup."""
    # Load data on startup
    _ = data_loader.plans
    _ = data_loader.invoices
    _ = data_loader.credit_memos
    _ = data_loader.exchange_rates
    logger.info(
        "Loaded initial data",
        extra={
            "plans": len(data_loader.plans),
            "invoices": len(data_loader.invoices),
            "credit_memos": len(data_loader.credit_memos),
            "exchange_rates": len(data_loader.exchange_rates),
        },
    )
    yield
    # Cleanup on shutdown (if needed)


app = FastAPI(
    title="Revenue Leakage Agent API",
    description="AI agent for investigating billing anomalies and revenue leakage",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware for Chainlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for prototype
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    """Redirect root to Chainlit chat UI."""
    return RedirectResponse(url="/chat")


# Mount Chainlit chat UI at /chat (single-server: Socket.IO + API on one port)
from chainlit.utils import mount_chainlit  # noqa: E402

mount_chainlit(app=app, target=str(_PROJECT_ROOT / "frontend" / "app.py"), path="/chat")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "revenue_agent.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
