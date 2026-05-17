import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
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


@app.on_event("startup")
async def startup() -> None:
    store_module.set_loop(asyncio.get_event_loop())


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


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


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
