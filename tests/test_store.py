import time
from moon.store import Case, InMemoryCaseStore, StepRecord, make_store


# --- Case state machine ---

def test_case_initial_state():
    case = Case(id="abc", description="test")
    assert case.status == "pending"
    assert case.steps == []
    assert case.final_output == ""
    assert case.error == ""
    assert case.completed_at == 0.0


def test_case_apply_task_started():
    case = Case(id="abc", description="test")
    case.apply("task_started", {})
    assert case.status == "running"


def test_case_apply_runbook_selected():
    case = Case(id="abc", description="test")
    case.apply("runbook_selected", {"runbook_id": "rb1", "step_texts": ["step 1", "step 2"]})
    assert case.runbook_id == "rb1"
    assert len(case.steps) == 2
    assert case.steps[0].text == "step 1"
    assert case.steps[0].status == "pending"
    assert case.steps[1].text == "step 2"


def test_case_apply_step_started():
    case = Case(id="abc", description="test")
    case.apply("runbook_selected", {"runbook_id": "rb1", "step_texts": ["step 1"]})
    case.apply("step_started", {"step_index": 0})
    assert case.steps[0].status == "running"


def test_case_apply_step_started_out_of_bounds_does_not_crash():
    case = Case(id="abc", description="test")
    case.apply("step_started", {"step_index": 99})  # no steps yet


def test_case_apply_step_completed():
    case = Case(id="abc", description="test")
    case.apply("runbook_selected", {"runbook_id": "rb1", "step_texts": ["step 1"]})
    case.apply("step_completed", {
        "step_index": 0, "duration_ms": 1234, "tools_used": ["tool_a"], "output": "done"
    })
    s = case.steps[0]
    assert s.status == "completed"
    assert s.duration_ms == 1234
    assert s.tools_used == ["tool_a"]
    assert s.output == "done"


def test_case_apply_task_completed():
    case = Case(id="abc", description="test")
    before = time.time()
    case.apply("task_completed", {"final_output": "result", "runbook_id": "rb1"})
    assert case.status == "completed"
    assert case.final_output == "result"
    assert case.completed_at >= before


def test_case_apply_task_failed():
    case = Case(id="abc", description="test")
    before = time.time()
    case.apply("task_failed", {"error": "something went wrong"})
    assert case.status == "failed"
    assert case.error == "something went wrong"
    assert case.completed_at >= before


def test_case_on_update_called_after_state_change():
    updates = []
    case = Case(id="abc", description="test", on_update=lambda c: updates.append(c.status))
    case.apply("task_started", {})
    assert updates == ["running"]


def test_case_on_update_receives_updated_state():
    captured = []
    case = Case(id="abc", description="test", on_update=lambda c: captured.append(c.final_output))
    case.apply("task_completed", {"final_output": "the answer"})
    assert captured == ["the answer"]


def test_case_on_update_exception_does_not_crash_apply():
    def bad_hook(c):
        raise RuntimeError("storage failed")

    case = Case(id="abc", description="test", on_update=bad_hook)
    case.apply("task_started", {})  # should not raise
    assert case.status == "running"


def test_case_to_dict_shape():
    case = Case(id="abc123", description="investigate ip")
    case.apply("task_started", {})
    d = case.to_dict()
    assert d["id"] == "abc123"
    assert d["description"] == "investigate ip"
    assert d["status"] == "running"
    assert isinstance(d["steps"], list)
    assert "started_at" in d
    assert "completed_at" in d
    assert "final_output" in d
    assert "error" in d


def test_case_to_dict_includes_step_fields():
    case = Case(id="abc", description="test")
    case.apply("runbook_selected", {"runbook_id": "rb1", "step_texts": ["step 1"]})
    case.apply("step_completed", {"step_index": 0, "duration_ms": 500, "tools_used": ["t"], "output": "out"})
    steps = case.to_dict()["steps"]
    assert len(steps) == 1
    assert steps[0]["text"] == "step 1"
    assert steps[0]["duration_ms"] == 500
    assert steps[0]["tools_used"] == ["t"]


# --- InMemoryCaseStore ---

def test_in_memory_store_create_returns_case():
    store = InMemoryCaseStore()
    case = store.create("test case")
    assert case.id
    assert case.description == "test case"
    assert case.status == "pending"


def test_in_memory_store_create_unique_ids():
    store = InMemoryCaseStore()
    ids = {store.create("task").id for _ in range(10)}
    assert len(ids) == 10


def test_in_memory_store_get_returns_same_object():
    store = InMemoryCaseStore()
    case = store.create("test case")
    assert store.get(case.id) is case


def test_in_memory_store_get_missing_returns_none():
    store = InMemoryCaseStore()
    assert store.get("nonexistent") is None


def test_in_memory_store_all_empty():
    store = InMemoryCaseStore()
    assert store.all() == []


def test_in_memory_store_all_sorted_by_started_at_desc():
    store = InMemoryCaseStore()
    c1 = store.create("first")
    c1.started_at = 1000.0
    c2 = store.create("second")
    c2.started_at = 2000.0
    result = store.all()
    assert result[0].description == "second"
    assert result[1].description == "first"


def test_in_memory_store_case_state_persists():
    store = InMemoryCaseStore()
    case = store.create("test")
    case.apply("task_started", {})
    fetched = store.get(case.id)
    assert fetched.status == "running"


# --- make_store factory ---

def test_make_store_returns_in_memory_by_default():
    import moon.config as cfg
    original = cfg.DYNAMO_TABLE
    try:
        cfg.DYNAMO_TABLE = ""
        s = make_store()
        assert isinstance(s, InMemoryCaseStore)
    finally:
        cfg.DYNAMO_TABLE = original
