"""FastAPI app. Sprint 1: upload, load run status, file list. Sprint 2:
mapping runs, review queue, freeze, P&L and balance sheet. Sprint 3:
financial overview, data health, exception queue. Sprint 4: Ask -- intent
classification and IR generation call a model (src/semantic/model_client.py),
unconfigured by explicit instruction until a vendor decision is made;
everything downstream of a valid IR is real and live. Sprint 5: the monthly
management pack -- generate, review, edit commentary, sign, export."""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import admin, ask, data_health, exceptions, load_runs, mapping, operating, overview, reports, statements, upload

app = FastAPI(title="SPEQULA API", version="0.7.0")

# The frontend (web/) is a separate origin (Next.js dev server on :3000,
# a separate deployed host in production) -- browsers block cross-origin
# fetch responses without this regardless of auth being otherwise correct.
# CORS_ALLOWED_ORIGINS, comma-separated, so a real deployment sets its own
# origin without a code change; defaults to the local dev frontend.
_allowed_origins = [
    o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router, tags=["ingest"])
app.include_router(load_runs.router, tags=["ingest"])
app.include_router(mapping.router, tags=["mapping"])
app.include_router(statements.router, tags=["statements"])
app.include_router(overview.router, tags=["overview"])
app.include_router(data_health.router, tags=["data-health"])
app.include_router(exceptions.router, tags=["exceptions"])
app.include_router(ask.router, tags=["ask"])
app.include_router(reports.router, tags=["reports"])
app.include_router(operating.router, tags=["operating"])
app.include_router(admin.router, tags=["admin"])


@app.get("/health")
def health():
    return {"status": "ok"}
