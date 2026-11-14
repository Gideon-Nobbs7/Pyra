import logging

from fastapi import FastAPI

from app.api.v1 import health, metadata, observations

logging.basicConfig(level="INFO", format="%(levelname)s %(name)s %(message)s")

app = FastAPI(title="Pyra", version="0.1.0")

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(observations.router, prefix="/api/v1", tags=["observations"])
app.include_router(metadata.router, prefix="/api/v1", tags=["metadata"])


@app.get("/")
def root() -> dict:
    return {"service": "pyra-backend", "version": "0.1.0", "api": "/api/v1"}
