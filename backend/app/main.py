import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import comparison, health, metadata, observations, places, summary

logging.basicConfig(level="INFO", format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("pyra.main")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """Own the ingest worker: one uvicorn starts and stops both.

    The worker runs in a thread (blocking provider/DB calls stay off the
    event loop). WORKER_ENABLED=1 in root .env turns it on; an empty
    WATCH_BBOXES list is fine — the job phase still drains user gap-fill.
    """
    task = None
    try:
        from app.settings import get_settings
        from scripts import ingest_worker

        settings = get_settings()
        configured = "+".join(
            name
            for name, value in (
                ("primary", settings.database_url),
                ("fallback", settings.database_url_fallback),
                ("local", settings.database_url_local),
            )
            if value
        )
        log.info("database tiers configured: %s", configured or "none (fixture mode)")
        if settings.worker_enabled:
            areas = ingest_worker.parse_watch_bboxes(settings.watch_bboxes)
            task = asyncio.create_task(
                asyncio.to_thread(
                    ingest_worker.serve,
                    settings.worker_interval_s,
                    areas,
                    settings.worker_recent_days,
                    30,
                    settings.worker_max_jobs,
                )
            )
            log.info("ingest worker started (%d watch area(s))", len(areas))
        else:
            log.info("ingest worker disabled (WORKER_ENABLED=1 to run it with the API)")
    except Exception as exc:
        log.warning("ingest worker did not start: %s", exc)
    yield
    if task is not None:
        from scripts import ingest_worker

        ingest_worker.request_stop()
        await task


app = FastAPI(title="Pyra", version="0.1.0", lifespan=lifespan)

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(observations.router, prefix="/api/v1", tags=["observations"])
app.include_router(summary.router, prefix="/api/v1", tags=["summary"])
app.include_router(comparison.router, prefix="/api/v1", tags=["comparison"])
app.include_router(metadata.router, prefix="/api/v1", tags=["metadata"])
app.include_router(places.router, prefix="/api/v1", tags=["places"])


@app.get("/")
def root() -> dict:
    return {"service": "pyra-backend", "version": "0.1.0", "api": "/api/v1"}
