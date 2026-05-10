import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

log = logging.getLogger(__name__)

_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


@dataclass
class StepRecord:
    index: int
    text: str
    status: str = "pending"
    duration_ms: int = 0
    tools_used: list[str] = field(default_factory=list)
    output: str = ""


@dataclass
class Case:
    id: str
    description: str
    status: str = "pending"
    runbook_id: str = ""
    steps: list[StepRecord] = field(default_factory=list)
    final_output: str = ""
    error: str = ""
    started_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    on_update: Callable[["Case"], None] | None = field(default=None, repr=False, compare=False)
    _subscribers: list[asyncio.Queue] = field(default_factory=list)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def apply(self, event_type: str, data: dict) -> None:
        if event_type == "task_started":
            self.status = "running"
        elif event_type == "runbook_selected":
            self.runbook_id = data.get("runbook_id", "")
            self.steps = [
                StepRecord(index=i, text=t)
                for i, t in enumerate(data.get("step_texts", []))
            ]
        elif event_type == "step_started":
            i = data.get("step_index", 0)
            if i < len(self.steps):
                self.steps[i].status = "running"
        elif event_type == "step_completed":
            i = data.get("step_index", 0)
            if i < len(self.steps):
                s = self.steps[i]
                s.status = "completed"
                s.duration_ms = data.get("duration_ms", 0)
                s.tools_used = data.get("tools_used", [])
                s.output = data.get("output", "")
        elif event_type == "task_completed":
            self.status = "completed"
            self.final_output = data.get("final_output", "")
            self.completed_at = time.time()
        elif event_type == "task_failed":
            self.status = "failed"
            self.error = data.get("error", "")
            self.completed_at = time.time()

        if self.on_update:
            try:
                self.on_update(self)
            except Exception as e:
                log.warning("store sync failed: %s", e)

        event = {"type": event_type, "case_id": self.id, **data}
        if _loop:
            for q in list(self._subscribers):
                _loop.call_soon_threadsafe(q.put_nowait, event)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status,
            "runbook_id": self.runbook_id,
            "steps": [
                {
                    "index": s.index,
                    "text": s.text,
                    "status": s.status,
                    "duration_ms": s.duration_ms,
                    "tools_used": s.tools_used,
                    "output": s.output,
                }
                for s in self.steps
            ],
            "final_output": self.final_output,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class InMemoryCaseStore:
    def __init__(self) -> None:
        self._cases: dict[str, Case] = {}

    def create(self, description: str) -> Case:
        case_id = uuid.uuid4().hex[:8]
        case = Case(id=case_id, description=description)
        self._cases[case_id] = case
        return case

    def get(self, case_id: str) -> Case | None:
        return self._cases.get(case_id)

    def all(self) -> list[Case]:
        return sorted(self._cases.values(), key=lambda c: c.started_at, reverse=True)


class DynamoCaseStore:
    def __init__(self, table_name: str, region: str, endpoint_url: str = "") -> None:
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for DynamoDB store. Install with: pip install 'moon[aws]'"
            )
        kwargs: dict = {"region_name": region}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        self._dynamo = boto3.resource("dynamodb", **kwargs)
        self._table = self._dynamo.Table(table_name)
        self._live: dict[str, Case] = {}
        self._ensure_table(table_name)

    def _ensure_table(self, table_name: str) -> None:
        from botocore.exceptions import ClientError
        for attempt in range(10):
            try:
                self._table.load()
                log.info("DynamoDB table '%s' ready", table_name)
                return
            except ClientError as e:
                if e.response["Error"]["Code"] == "ResourceNotFoundException":
                    log.info("creating DynamoDB table '%s'", table_name)
                    self._table = self._dynamo.create_table(
                        TableName=table_name,
                        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                        BillingMode="PAY_PER_REQUEST",
                    )
                    self._table.wait_until_exists()
                    log.info("DynamoDB table '%s' created", table_name)
                    return
                raise
            except Exception:
                if attempt < 9:
                    log.info("waiting for DynamoDB... (%d/10)", attempt + 1)
                    time.sleep(1)
                else:
                    raise

    def _sync(self, case: Case) -> None:
        from decimal import Decimal
        self._table.put_item(Item={
            "id": case.id,
            "description": case.description,
            "status": case.status,
            "runbook_id": case.runbook_id,
            "final_output": case.final_output,
            "error": case.error,
            "started_at": Decimal(str(case.started_at)),
            "completed_at": Decimal(str(case.completed_at)),
            "steps": json.dumps([
                {
                    "index": s.index,
                    "text": s.text,
                    "status": s.status,
                    "duration_ms": s.duration_ms,
                    "tools_used": s.tools_used,
                    "output": s.output,
                }
                for s in case.steps
            ]),
        })

    def _from_item(self, item: dict) -> Case:
        steps = [StepRecord(**s) for s in json.loads(item.get("steps", "[]"))]
        return Case(
            id=item["id"],
            description=item["description"],
            status=item["status"],
            runbook_id=item.get("runbook_id", ""),
            steps=steps,
            final_output=item.get("final_output", ""),
            error=item.get("error", ""),
            started_at=float(item.get("started_at", 0)),
            completed_at=float(item.get("completed_at", 0)),
        )

    def create(self, description: str) -> Case:
        case_id = uuid.uuid4().hex[:8]
        case = Case(id=case_id, description=description, on_update=self._sync)
        self._live[case_id] = case
        self._sync(case)
        return case

    def get(self, case_id: str) -> Case | None:
        if case_id in self._live:
            return self._live[case_id]
        from botocore.exceptions import ClientError
        try:
            resp = self._table.get_item(Key={"id": case_id})
        except ClientError as e:
            log.error("DynamoDB get_item failed: %s", e)
            return None
        item = resp.get("Item")
        return self._from_item(item) if item else None

    def all(self) -> list[Case]:
        from botocore.exceptions import ClientError
        try:
            resp = self._table.scan()
            items = resp.get("Items", [])
        except ClientError as e:
            log.error("DynamoDB scan failed: %s", e)
            return list(self._live.values())
        cases = []
        for item in items:
            cid = item["id"]
            cases.append(self._live[cid] if cid in self._live else self._from_item(item))
        return sorted(cases, key=lambda c: c.started_at, reverse=True)


def make_store() -> InMemoryCaseStore | DynamoCaseStore:
    from moon import config
    if config.DYNAMO_TABLE:
        return DynamoCaseStore(config.DYNAMO_TABLE, config.DYNAMO_REGION, config.DYNAMO_ENDPOINT_URL)
    return InMemoryCaseStore()


store = make_store()
