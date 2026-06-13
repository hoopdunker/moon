import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from moon import config, logging_config
from moon.executor import execute_task
from moon.models import Task
from moon import store as store_module
from moon.store import store

logger = logging.getLogger("moon.server")

app = FastAPI(title="Moon")
_pool = ThreadPoolExecutor(max_workers=config.MAX_WORKERS)
_catalogs_path: Optional[Path] = None


def _parse_intel_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


async def _schedule_daily_intel() -> None:
    while True:
        now = datetime.now(timezone.utc)
        target = now.replace(hour=config.INTEL_SCHEDULE_HOUR, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        sleep_secs = (target - now).total_seconds()
        logger.info("Intel digest scheduled in %.0f s (at %s UTC)", sleep_secs, target.strftime("%H:%M"))
        await asyncio.sleep(sleep_secs)
        today_ts = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        already_ran = any(
            (c.runbook_id == "threat_intel_digest" or "threat intel" in c.description.lower())
            and c.started_at >= today_ts
            for c in store.all()
        )
        if not already_ran:
            logger.info("Running scheduled intel digest")
            case = store.create("threat intel digest last 24 hours")
            task = Task(description="threat intel digest last 24 hours", input_data={})

            def _run(_case=case, _task=task) -> None:
                try:
                    execute_task(_task, _catalogs_path, on_event=_case.apply)
                except Exception as e:
                    _case.apply("task_failed", {"error": str(e)})

            _pool.submit(_run)


_health_ok: bool = True
_health_checked_at: float = 0.0
_HEALTH_TTL = 300  # re-probe models every 5 minutes


def _check_models() -> bool:
    from moon import llm
    try:
        llm.init_models()
        return True
    except RuntimeError:
        return False


@app.on_event("startup")
async def startup() -> None:
    global _health_ok, _health_checked_at
    store_module.set_loop(asyncio.get_event_loop())
    ok = await asyncio.to_thread(_check_models)
    _health_ok = ok
    _health_checked_at = time.monotonic()
    if not ok:
        logger.error("No live Bedrock models found — service will be unhealthy")
    asyncio.create_task(_schedule_daily_intel())


class TaskRequest(BaseModel):
    description: str
    input_data: dict = {}


@app.post("/cases", status_code=201)
async def create_case(req: TaskRequest) -> dict:
    case = store.create(req.description)
    task = Task(description=req.description, input_data=req.input_data)

    def run() -> None:
        try:
            execute_task(task, _catalogs_path, on_event=case.apply)
        except Exception as e:
            case.apply("task_failed", {"error": str(e)})

    _pool.submit(run)
    return {"case_id": case.id}


@app.get("/cases")
async def list_cases() -> list[dict]:
    return [c.to_dict() for c in store.all()]


@app.get("/cases/{case_id}")
async def get_case(case_id: str) -> dict:
    case = store.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case.to_dict()


@app.get("/cases/{case_id}/stream")
async def stream_case(case_id: str) -> StreamingResponse:
    case = store.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    queue = case.subscribe()

    async def generator():
        # Send current state immediately so late-joining clients catch up
        yield f"data: {json.dumps({'type': 'snapshot', **case.to_dict()})}\n\n"
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                yield f"data: {json.dumps(event)}\n\n"
                if event["type"] in ("task_completed", "task_failed"):
                    break
        except asyncio.TimeoutError:
            yield "data: {\"type\": \"ping\"}\n\n"
        finally:
            case.unsubscribe(queue)

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/intel/latest")
async def intel_latest() -> dict:
    def _is_intel(c) -> bool:
        return c.runbook_id == "threat_intel_digest" or "threat intel" in c.description.lower()

    all_cases = store.all()
    intel = [c for c in all_cases if _is_intel(c)]
    if not intel:
        return {"status": "none"}

    running = next((c for c in intel if c.status in ("running", "pending")), None)
    completed = next((c for c in intel if c.status == "completed"), None)
    target = running or completed
    if not target:
        return {"status": "none"}

    result = target.to_dict()
    if target.final_output:
        result["sections"] = _parse_intel_sections(target.final_output)
    return result


@app.get("/health")
async def health() -> dict:
    global _health_ok, _health_checked_at
    if time.monotonic() - _health_checked_at > _HEALTH_TTL:
        ok = await asyncio.to_thread(_check_models)
        _health_ok = ok
        _health_checked_at = time.monotonic()
    if not _health_ok:
        raise HTTPException(status_code=503, detail="No live Bedrock models available")
    return {
        "status": "ok",
        "coordinator_model": config.COORDINATOR_MODEL,
        "agent_model": config.AGENT_MODEL,
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> str:
    html_path = Path(__file__).parent / "static" / "index.html"
    return html_path.read_text()


def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    catalogs: Optional[Path] = None,
    debug: bool = False,
) -> None:
    global _catalogs_path
    logging_config.setup(debug=debug)
    _catalogs_path = catalogs
    uvicorn.run(app, host=host, port=port)
