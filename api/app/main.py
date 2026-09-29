"""
Universa Doc Processor API
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import get_settings
from .routers import settlements, bank, items, receipts, rules

settings = get_settings()

app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="API für Universa Leistungsabrechnungen und Banktransaktionen",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(settlements.router)
app.include_router(bank.router)
app.include_router(items.router)
app.include_router(receipts.router)
app.include_router(rules.router)


@app.get("/")
async def root():
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "status": "running",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}
