# API comparison and contract stabilization implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make comparisons complete reliably, reject strategy-incompatible backtests before persistence, expose a truthful async/OpenAPI contract, retain safe worker diagnostics, and document the API for external clients.

**Architecture:** Keep immutable dataclasses inside the research service and normalize them to ordinary JSON containers at the API boundary. Enforce strategy compatibility in `BacktestInput`, derive polling metadata from `ExperimentRecord`, and keep lifecycle error classification in the durable worker. Verify the contract through real FastAPI routes, SQLite persistence, worker dispatch, and polling while replacing only external market-data execution with a deterministic fixture.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite, httpx, pytest, PowerShell development commands.

**Spec:** `docs/superpowers/specs/2026-08-26-api-comparison-contract-stabilization-design.md`

## Global constraints

- Preserve completed experiment immutability and the current SQLite schema.
- Preserve internal `MappingProxyType` immutability. Convert values only at the public JSON boundary.
- Provider selection remains automatic. Public requests accept only `source=auto`.
- Global market-data timeframes remain `1m`, `5m`, `15m`, `1h`, and `1d`; the baseline strategy registry still requires `1m`.
- Do not add accounts, API-key scopes, key expiry, ingress quotas, cancellation, progress reporting, or automatic experiment retries.
- Never persist bearer keys, provider authorization headers, tracebacks, environment variables, URL query values, or raw provider bodies in public experiment errors.
- Use a two-second polling recommendation for every nonterminal experiment.
- Write each production change only after its focused test has failed for the expected reason.
- Preserve unrelated working-tree changes and the existing tracked pytest-artifact deletions.

## File map

| File | Responsibility in this change |
| --- | --- |
| `bktstr/services/validation.py` | Typed strategy compatibility failure with prefix-preserving metadata. |
| `bktstr/services/backtest.py` | Registry compatibility check and recursive JSON normalization. |
| `bktstr/services/experiments.py` | Safe worker failure classification and diagnostic redaction. |
| `bktstr/api/lifecycle.py` | Shared status URL, retry timing, and response-header policy. |
| `bktstr/api/schemas.py` | Closed request enums and polling fields on experiment envelopes. |
| `bktstr/api/routes.py` | Normalized operation adapters, typed query values, response headers, and OpenAPI success responses. |
| `bktstr/api/app.py` | `422 strategy_incompatible` exception mapping. |
| `tests/research_fixtures.py` | Reusable deterministic backtest result for service/API contract tests. |
| `tests/test_services_backtest.py` | Direct strategy/timeframe compatibility tests. |
| `tests/test_services_research_operations.py` | JSON normalization and comparison service regression tests. |
| `tests/test_experiment_worker.py` | Safe diagnostic classification tests. |
| `tests/test_api_backtests.py` | Direct API compatibility, polling fields, and OpenAPI tests. |
| `tests/test_api_research_operations.py` | Nested compatibility and comparison worker regression tests. |
| `tests/test_api_market_data.py` | Request enum/OpenAPI behavior for `source` and timeframe. |
| `tests/test_api_post_contracts.py` | Every POST route through persistence, worker execution, idempotency, and polling. |
| `docs/API_REFERENCE.md` | Complete external API reference. |
| `README.md` | Link to the API reference and short lifecycle summary. |
| `docs/BKTSTR_SYSTEM_MANUAL.md` | Replace duplicated API details with the canonical reference and retain architectural context. |
| `scripts/production_acceptance.py` | Deployed comparison and polling acceptance. |
| `tests/test_production_acceptance.py` | Mock-transport proof of the deployed comparison flow. |

---

### Task 1: Enforce strategy/timeframe compatibility in the service

**Files:**
- Modify: `bktstr/services/validation.py:1-28`
- Modify: `bktstr/services/backtest.py:68-179`
- Test: `tests/test_services_backtest.py`

**Interfaces:**
- Consumes: `baseline_strategy_registry().get(strategy_id, strategy_version)` and `StrategyDefinition.timeframe`.
- Produces: `StrategyCompatibilityError(message, fields, strategy_id, strategy_version, required_timeframe, received_timeframe)` with prefix-preserving `prefixed()` and `replace_fields()` methods.

- [ ] **Step 1: Write failing direct-service tests**

Add these imports and tests to `tests/test_services_backtest.py`:

```python
from datetime import date

import pytest

from bktstr.services.backtest import BacktestInput
from bktstr.services.validation import StrategyCompatibilityError


def test_backtest_input_rejects_timeframe_incompatible_with_registered_strategy():
    with pytest.raises(StrategyCompatibilityError) as raised:
        BacktestInput(
            strategy_id="bktstr.bearish-regime-scalp",
            strategy_version="1.0.0",
            symbol="NVDA",
            start=date(2026, 8, 17),
            end=date(2026, 8, 17),
            timeframe="1d",
            side="short",
            entry="close.cross_below:vwap",
        )

    error = raised.value
    assert error.fields == ("market.timeframe",)
    assert error.strategy_id == "bktstr.bearish-regime-scalp"
    assert error.strategy_version == "1.0.0"
    assert error.required_timeframe == "1m"
    assert error.received_timeframe == "1d"


def test_strategy_compatibility_error_keeps_metadata_when_prefixed():
    original = StrategyCompatibilityError(
        "incompatible",
        ("market.timeframe",),
        strategy_id="strategy",
        strategy_version="1",
        required_timeframe="1m",
        received_timeframe="1d",
    )

    prefixed = original.prefixed("base")

    assert isinstance(prefixed, StrategyCompatibilityError)
    assert prefixed.fields == ("base.market.timeframe",)
    assert prefixed.required_timeframe == "1m"
    assert prefixed.received_timeframe == "1d"
```

- [ ] **Step 2: Run the tests and confirm the red state**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_services_backtest.py -k 'timeframe_incompatible or compatibility_error_keeps' -v
```

Expected: collection fails because `StrategyCompatibilityError` does not exist, or the first test fails because `BacktestInput` accepts `1d`.

- [ ] **Step 3: Add the typed error**

Add `Self` to the typing imports in `bktstr/services/validation.py`, then add:

```python
class StrategyCompatibilityError(SemanticValidationError):
    """A selected strategy cannot run against part of the typed request."""

    def __init__(
        self,
        message: str,
        fields: Iterable[str],
        *,
        strategy_id: str,
        strategy_version: str,
        required_timeframe: str,
        received_timeframe: str,
    ) -> None:
        super().__init__(message, fields)
        self.strategy_id = strategy_id
        self.strategy_version = strategy_version
        self.required_timeframe = required_timeframe
        self.received_timeframe = received_timeframe

    def _with_fields(self, fields: Iterable[str]) -> Self:
        return type(self)(
            str(self),
            fields,
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            required_timeframe=self.required_timeframe,
            received_timeframe=self.received_timeframe,
        )

    def prefixed(self, prefix: str) -> Self:
        normalized_prefix = str(prefix).strip(".")
        if not normalized_prefix:
            raise ValueError("semantic validation prefix cannot be empty")
        return self._with_fields(
            f"{normalized_prefix}.{field}" for field in self.fields
        )

    def replace_fields(self, fields: Iterable[str]) -> Self:
        return self._with_fields(fields)
```

Export both validation error types in `__all__`.

- [ ] **Step 4: Enforce the registry contract**

Import `StrategyCompatibilityError` in `bktstr/services/backtest.py`. Immediately after the strategy definition lookup succeeds, add:

```python
if market.timeframe != definition.timeframe:
    raise StrategyCompatibilityError(
        (
            f"Strategy {self.strategy_id!r} version {self.strategy_version!r} "
            f"requires timeframe {definition.timeframe!r}; "
            f"received {market.timeframe!r}."
        ),
        ("market.timeframe",),
        strategy_id=self.strategy_id,
        strategy_version=self.strategy_version,
        required_timeframe=definition.timeframe,
        received_timeframe=market.timeframe,
    )
```

- [ ] **Step 5: Run focused and adjacent service tests**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_services_backtest.py tests/test_services_research_operations.py -q
```

Expected: all tests pass. Existing `1m` construction remains valid.

- [ ] **Step 6: Commit the service validation change**

```powershell
git add bktstr/services/validation.py bktstr/services/backtest.py tests/test_services_backtest.py
git commit -m "fix(api): reject strategy timeframe mismatches"
```

---

### Task 2: Return `422 strategy_incompatible` and publish request enums

**Files:**
- Modify: `bktstr/api/schemas.py:1-435`
- Modify: `bktstr/api/routes.py:1-216`
- Modify: `bktstr/api/app.py:14-191`
- Test: `tests/test_api_backtests.py`
- Test: `tests/test_api_research_operations.py`
- Test: `tests/test_api_market_data.py`

**Interfaces:**
- Consumes: `StrategyCompatibilityError` from Task 1.
- Produces: `MarketTimeframe`, `AutomaticSource`, closed OpenAPI enums, and the HTTP error code `strategy_incompatible`.

- [ ] **Step 1: Write failing direct and nested HTTP tests**

Add to `tests/test_api_backtests.py`:

```python
def test_incompatible_backtest_timeframe_returns_422_before_persistence(
    monkeypatch, tmp_path
):
    body = deepcopy(BACKTEST_BODY)
    body["market"]["timeframe"] = "1d"
    with _client(monkeypatch, tmp_path) as client:
        response = client.post("/api/v1/backtests", json=body, headers=AUTH)
        assert client.app.state.experiment_store.claim_next() is None

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "strategy_incompatible"
    assert response.json()["error"]["details"] == {
        "fields": ["market.timeframe"],
        "strategy_id": "bktstr.bearish-regime-scalp",
        "strategy_version": "1.0.0",
        "required_timeframe": "1m",
        "received_timeframe": "1d",
    }
```

Add a parameterized nested test to `tests/test_api_research_operations.py`:

```python
@pytest.mark.parametrize(
    ("endpoint", "body", "field"),
    [
        (
            "/api/v1/parameter-sweeps",
            {**deepcopy(SWEEP_BODY), "base": deepcopy(BACKTEST_BODY)},
            "base.market.timeframe",
        ),
        (
            "/api/v1/compare",
            {
                "candidates": [
                    {"name": "daily", "backtest": deepcopy(BACKTEST_BODY)},
                    "exp_valid",
                ],
                "execution": "auto",
            },
            "candidates.0.backtest.market.timeframe",
        ),
        (
            "/api/v1/regime-comparison",
            {**deepcopy(REGIME_BODY), "base": deepcopy(BACKTEST_BODY)},
            "base.market.timeframe",
        ),
    ],
)
def test_compound_requests_reject_incompatible_timeframe_before_enqueue(
    monkeypatch, tmp_path, endpoint, body, field
):
    target = body["candidates"][0]["backtest"] if endpoint.endswith("compare") else body["base"]
    target["market"]["timeframe"] = "1d"
    with _client(monkeypatch, tmp_path) as client:
        response = client.post(endpoint, json=body, headers=AUTH)
        assert client.app.state.experiment_store.claim_next() is None

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "strategy_incompatible"
    assert response.json()["error"]["details"]["fields"] == [field]
```

- [ ] **Step 2: Write failing enum/OpenAPI tests**

Update `tests/test_api_market_data.py` so `source=massive` expects `422 validation_error`, then assert:

```python
document = client.get("/openapi.json").json()
schemas = document["components"]["schemas"]
assert schemas["MarketCreate"]["properties"]["timeframe"]["$ref"].endswith(
    "/MarketTimeframe"
)
assert schemas["MarketCreate"]["properties"]["source"]["$ref"].endswith(
    "/AutomaticSource"
)
assert schemas["MarketTimeframe"]["enum"] == ["1m", "5m", "15m", "1h", "1d"]
assert schemas["AutomaticSource"]["enum"] == ["auto"]

market_parameters = {
    item["name"]: item for item in document["paths"]["/api/v1/market-data"]["get"]["parameters"]
}
assert market_parameters["timeframe"]["schema"]["$ref"].endswith("/MarketTimeframe")
assert market_parameters["source"]["schema"]["$ref"].endswith("/AutomaticSource")
```

- [ ] **Step 3: Run the new API tests and confirm the red state**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_api_backtests.py tests/test_api_research_operations.py tests/test_api_market_data.py -k 'incompatible or enum or source' -v
```

Expected: timeframe requests return `400`, and OpenAPI still reports plain strings.

- [ ] **Step 4: Add closed request types**

Import `StrEnum` from `enum` in `bktstr/api/schemas.py`, then define and use:

```python
class MarketTimeframe(StrEnum):
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"


class AutomaticSource(StrEnum):
    AUTO = "auto"


class MarketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    start: date
    end: date
    timeframe: MarketTimeframe = Field(
        default=MarketTimeframe.ONE_MINUTE,
        description=(
            "Globally valid market-data timeframe. The selected strategy may "
            "narrow this set; the baseline strategy requires 1m."
        ),
    )
    source: AutomaticSource = AutomaticSource.AUTO
```

Import both aliases in `bktstr/api/routes.py` and annotate the query parameters:

```python
timeframe: MarketTimeframe = MarketTimeframe.ONE_MINUTE,
source: AutomaticSource = AutomaticSource.AUTO,
```

- [ ] **Step 5: Map the compatibility exception to HTTP**

Import `StrategyCompatibilityError` in `bktstr/api/app.py` and register:

```python
@app.exception_handler(StrategyCompatibilityError)
async def handle_strategy_compatibility_error(
    request: Request, exc: StrategyCompatibilityError
) -> JSONResponse:
    return _error_response(
        request,
        422,
        "strategy_incompatible",
        str(exc),
        {
            "fields": list(exc.fields),
            "strategy_id": exc.strategy_id,
            "strategy_version": exc.strategy_version,
            "required_timeframe": exc.required_timeframe,
            "received_timeframe": exc.received_timeframe,
        },
    )
```

Keep the general semantic handler unchanged at `400 invalid_request`.

- [ ] **Step 6: Run all API schema and validation tests**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_api_backtests.py tests/test_api_research_operations.py tests/test_api_market_data.py tests/test_api_system.py -q
```

Expected: all tests pass, including exact nested field paths.

- [ ] **Step 7: Commit the HTTP validation contract**

```powershell
git add bktstr/api/schemas.py bktstr/api/routes.py bktstr/api/app.py tests/test_api_backtests.py tests/test_api_research_operations.py tests/test_api_market_data.py
git commit -m "fix(api): publish and enforce market request constraints"
```

---

### Task 3: Normalize immutable results at the API boundary

**Files:**
- Modify: `bktstr/services/backtest.py:962-973,1270-1285`
- Modify: `bktstr/api/routes.py:137-264`
- Test: `tests/test_services_research_operations.py`
- Test: `tests/test_api_research_operations.py`

**Interfaces:**
- Consumes: immutable service result dataclasses and Pydantic operation result models.
- Produces: `to_json_value(value: Any) -> Any` and `_validated_result_payload(model_type, value) -> dict[str, Any]`.

- [ ] **Step 1: Write the recursive normalization test**

Add to `tests/test_services_research_operations.py`:

```python
from datetime import datetime, timezone
from enum import StrEnum

from bktstr.services.backtest import to_json_value


class _FixtureState(StrEnum):
    READY = "ready"


def test_to_json_value_recursively_thaws_domain_values():
    value = MappingProxyType(
        {
            "candidate": MappingProxyType({"metrics": BacktestMetrics(1, 2, 3, 4, 5, 6, 7, 8)}),
            "states": (_FixtureState.READY,),
            "at": datetime(2026, 8, 26, tzinfo=timezone.utc),
        }
    )

    normalized = to_json_value(value)

    assert type(normalized) is dict
    assert type(normalized["candidate"]) is dict
    assert normalized["candidate"]["metrics"]["trade_count"] == 8
    assert normalized["states"] == ["ready"]
    assert normalized["at"] == "2026-08-26T00:00:00+00:00"
```

- [ ] **Step 2: Write a failing compare-worker regression test**

Add a test beside the existing compare API tests. Seed two completed backtests with `_completed_backtest`, create a queued compare record using `CompareCreate.model_validate`, and run the real operation adapter:

```python
def test_compare_worker_serializes_immutable_result_for_experiment_ids(
    monkeypatch, tmp_path
):
    with _client(monkeypatch, tmp_path) as client:
        store = client.app.state.experiment_store
        first = _completed_backtest(store, stop_pct=1.0, profit_factor=1.5)
        second = _completed_backtest(store, stop_pct=2.0, profit_factor=2.0)
        response = client.post(
            "/api/v1/compare",
            json={"candidates": [first, second], "execution": "async"},
            headers=AUTH,
        )
        completed = client.app.state.experiment_worker.run(
            response.json()["experiment_id"]
        )

    assert completed.status.value == "completed"
    assert completed.error is None
    assert completed.result["metric_deltas"]["profit_factor"][second] == 0.5
    assert completed.result["candidates"][0]["provenance"]["strategy"]["id"] == (
        "bktstr.bearish-regime-scalp"
    )
```

Import or move the existing completed-backtest helper rather than mocking `CompareResult` or Pydantic.

- [ ] **Step 3: Run the normalization and worker tests to verify red**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_services_research_operations.py::test_to_json_value_recursively_thaws_domain_values tests/test_api_research_operations.py::test_compare_worker_serializes_immutable_result_for_experiment_ids -v
```

Expected: `to_json_value` is unavailable and the worker regression ends in `operation_failed` with the reported `mappingproxy` serialization message.

- [ ] **Step 4: Promote the recursive converter**

Rename `_json_value` to `to_json_value` in `bktstr/services/backtest.py`, update its recursive calls, update `_execute_child_backtest`, and export it through `__all__`:

```python
def to_json_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: to_json_value(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): to_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [to_json_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value
```

- [ ] **Step 5: Normalize every operation result before Pydantic validation**

Import `BaseModel` and `to_json_value` in `bktstr/api/routes.py`. Add:

```python
ResultModel = TypeVar("ResultModel", bound=BaseModel)


def _validated_result_payload(
    model_type: type[ResultModel], value: Any
) -> dict[str, Any]:
    validated = model_type.model_validate(to_json_value(value))
    return validated.model_dump(mode="json")
```

Use it in all four adapters. The compare adapter becomes:

```python
result = compare_experiments(
    _compare_input(request),
    store=store,
    parent_experiment_id=record.experiment_id,
)
payload = _validated_result_payload(CompareResult, result)
return payload, payload["provenance"]
```

Apply the same shape to backtest, parameter sweep, and regime comparison. Keep the `include_trades` projection by updating the normalized Pydantic backtest model before dumping it.

- [ ] **Step 6: Add the named-variant regression**

Patch `bktstr.services.backtest.run_backtest` with the deterministic research-result fixture, submit two named variants, run the worker, and assert both linked child IDs and candidate names persist. The exact terminal assertions are:

```python
assert completed.status.value == "completed"
assert [item["name"] for item in completed.result["candidates"]] == ["control", "wide-stop"]
assert len(completed.result["provenance"]["candidate_experiment_ids"]) == 2
assert all(
    store.load_experiment(experiment_id).parent_experiment_id == completed.experiment_id
    for experiment_id in completed.result["provenance"]["candidate_experiment_ids"]
)
```

- [ ] **Step 7: Run comparison, sweep, and regime tests**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_services_research_operations.py tests/test_api_research_operations.py tests/test_experiment_worker.py -q
```

Expected: both comparison forms complete and adjacent operations remain green.

- [ ] **Step 8: Commit the serialization boundary fix**

```powershell
git add bktstr/services/backtest.py bktstr/api/routes.py tests/test_services_research_operations.py tests/test_api_research_operations.py
git commit -m "fix(compare): normalize immutable worker results"
```

---

### Task 4: Preserve safe worker failure diagnostics

**Files:**
- Modify: `bktstr/services/experiments.py:1-20,1099-1188`
- Test: `tests/test_experiment_worker.py`

**Interfaces:**
- Consumes: exceptions raised during operation execution and result persistence.
- Produces: `_safe_exception_message(exc, fallback)`, `_exception_details(exc, stage)`, and richer persisted experiment errors.

- [ ] **Step 1: Write failing unexpected-error redaction test**

Add to `tests/test_experiment_worker.py`:

```python
def test_worker_persists_redacted_unexpected_failure_details(monkeypatch, tmp_path):
    monkeypatch.setenv("BKTSTR_API_KEY", "service-secret")
    monkeypatch.setenv("MASSIVE_API_KEY", "provider-secret")
    store = ExperimentStore(tmp_path)
    record, _ = store.create_experiment("compare", {"candidates": []}, "async")

    def fail(_):
        raise RuntimeError(
            "Bearer service-secret provider-secret "
            "https://provider.example/data?apiKey=provider-secret"
        )

    failed = ExperimentWorker(store, {"compare": fail}).run(record.experiment_id)

    assert failed.error["code"] == "operation_failed"
    assert failed.error["details"] == {
        "stage": "execution",
        "exception_type": "RuntimeError",
    }
    rendered = json.dumps(dict(failed.error))
    assert "service-secret" not in rendered
    assert "provider-secret" not in rendered
    assert "apiKey=" not in rendered
    assert "[redacted]" in failed.error["message"]
```

- [ ] **Step 2: Write failing HTTP and persistence classification tests**

Add one test where an operation raises `httpx.HTTPStatusError` with a `429` response and assert:

```python
assert failed.error == {
    "code": "market_data_http_error",
    "message": "Market-data provider request failed.",
    "details": {
        "stage": "execution",
        "exception_type": "HTTPStatusError",
        "status_code": 429,
        "retryable": True,
    },
}
```

Extend the existing result-persistence failure test to assert:

```python
assert failed.error["details"] == {
    "stage": "persistence",
    "exception_type": "RuntimeError",
}
assert failed.error["message"] == "disk unavailable"
```

- [ ] **Step 3: Run the diagnostic tests and confirm red**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_experiment_worker.py -k 'redacted or provider_failures or persistence_errors' -v
```

Expected: current messages are generic and details are empty.

- [ ] **Step 4: Implement bounded redaction and details**

Add `re` and these constants/helpers to `bktstr/services/experiments.py`:

```python
_ERROR_MESSAGE_LIMIT = 1_000
_RETRYABLE_PROVIDER_STATUSES = frozenset({429, 500, 502, 503, 504})
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_URL_QUERY = re.compile(r"(https?://[^\s?]+)\?[^\s]*")


def _safe_exception_message(exc: BaseException, fallback: str) -> str:
    message = str(exc).strip() or fallback
    for variable in ("BKTSTR_API_KEY", "MASSIVE_API_KEY"):
        secret = os.getenv(variable)
        if secret:
            message = message.replace(secret, "[redacted]")
    message = _BEARER_TOKEN.sub("Bearer [redacted]", message)
    message = _URL_QUERY.sub(r"\1?[redacted]", message)
    return message[:_ERROR_MESSAGE_LIMIT]


def _exception_details(exc: BaseException, stage: str) -> dict[str, Any]:
    details: dict[str, Any] = {
        "stage": stage,
        "exception_type": type(exc).__name__,
    }
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        details.update(
            status_code=status_code,
            retryable=status_code in _RETRYABLE_PROVIDER_STATUSES,
        )
    return details
```

- [ ] **Step 5: Use the helpers in worker branches**

Capture exception variables in the HTTP, unexpected execution, and persistence branches. Keep safe expected domain errors unchanged. Use:

```python
except httpx.HTTPError as exc:
    return self._fail_survivably(
        record,
        {
            "code": "market_data_http_error",
            "message": "Market-data provider request failed.",
            "details": _exception_details(exc, "execution"),
        },
    )
except Exception as exc:
    return self._fail_survivably(
        record,
        {
            "code": "operation_failed",
            "message": _safe_exception_message(
                exc, "The experiment operation failed."
            ),
            "details": _exception_details(exc, "execution"),
        },
    )
```

For `store.complete` failures, use code `result_persistence_failed`, the safe exception message with the current generic fallback, and `stage="persistence"`.

- [ ] **Step 6: Run the complete worker suite**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_experiment_worker.py -q
```

Expected: all worker lifecycle, lease, race, and diagnostic tests pass.

- [ ] **Step 7: Commit worker diagnostics**

```powershell
git add bktstr/services/experiments.py tests/test_experiment_worker.py
git commit -m "fix(worker): retain safe failure diagnostics"
```

---

### Task 5: Standardize experiment status links and polling timing

**Files:**
- Create: `bktstr/api/lifecycle.py`
- Modify: `bktstr/api/schemas.py:681-758`
- Modify: `bktstr/api/routes.py:58-62,285-499`
- Test: `tests/test_api_backtests.py`
- Test: `tests/test_api_research_operations.py`

**Interfaces:**
- Consumes: `ExperimentRecord`, `ExperimentStatus`, and FastAPI `Response`.
- Produces: `POLL_RETRY_SECONDS`, `experiment_status_url(record)`, `experiment_retry_after(record)`, `apply_experiment_headers(response, record, include_location)`, `status_url`, and `retry_after_seconds`.

- [ ] **Step 1: Write failing body/header tests**

Extend the queued backtest and research-operation tests with exact assertions:

```python
payload = response.json()
expected_url = f"/api/v1/experiments/{payload['experiment_id']}"
assert payload["status_url"] == expected_url
assert payload["retry_after_seconds"] == 2
assert response.headers["location"] == expected_url
assert response.headers["retry-after"] == "2"
```

After worker completion and polling:

```python
assert polled.json()["status_url"] == expected_url
assert polled.json()["retry_after_seconds"] is None
assert "retry-after" not in polled.headers
```

Create a queued polling assertion that `GET /api/v1/experiments/{id}` returns `Retry-After: 2` while the record is queued.

- [ ] **Step 2: Write failing OpenAPI response-header tests**

For each POST path, assert that `200` and `202` use the operation-specific response model and declare `Location` and `Retry-After`. Assert polling GET `200` declares `Retry-After`.

```python
for status in ("200", "202"):
    response = operation["responses"][status]
    assert set(response["headers"]) == {"Location", "Retry-After"}
```

- [ ] **Step 3: Run focused tests and confirm red**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_api_backtests.py tests/test_api_research_operations.py -k 'polling or queue or openapi' -v
```

Expected: envelope fields and headers are absent.

- [ ] **Step 4: Create the lifecycle policy module**

Create `bktstr/api/lifecycle.py`:

```python
from __future__ import annotations

from fastapi import Response

from bktstr.services.experiments import ExperimentRecord, ExperimentStatus


POLL_RETRY_SECONDS = 2
_NONTERMINAL = frozenset({ExperimentStatus.QUEUED, ExperimentStatus.RUNNING})


def experiment_status_url(record: ExperimentRecord) -> str:
    return f"/api/v1/experiments/{record.experiment_id}"


def experiment_retry_after(record: ExperimentRecord) -> int | None:
    return POLL_RETRY_SECONDS if record.status in _NONTERMINAL else None


def apply_experiment_headers(
    response: Response,
    record: ExperimentRecord,
    *,
    include_location: bool,
) -> None:
    if include_location:
        response.headers["Location"] = experiment_status_url(record)
    retry_after = experiment_retry_after(record)
    if retry_after is not None:
        response.headers["Retry-After"] = str(retry_after)


__all__ = [
    "POLL_RETRY_SECONDS",
    "apply_experiment_headers",
    "experiment_retry_after",
    "experiment_status_url",
]
```

- [ ] **Step 5: Add envelope fields**

Import the two lifecycle derivation functions in `schemas.py`, add:

```python
status_url: str
retry_after_seconds: int | None
```

to `ExperimentEnvelope`, and set them in `from_record`:

```python
status_url=experiment_status_url(record),
retry_after_seconds=experiment_retry_after(record),
```

Add `Field` descriptions that tell clients to GET the status URL and wait the reported number of seconds while nonterminal.

- [ ] **Step 6: Apply runtime and OpenAPI headers**

Add route constants:

```python
_POLLING_HEADER_SCHEMA = {
    "Retry-After": {
        "description": "Seconds to wait before polling a nonterminal experiment.",
        "schema": {"type": "integer", "minimum": 1},
    }
}
_POST_EXPERIMENT_HEADER_SCHEMA = {
    "Location": {
        "description": "Relative canonical experiment status URL.",
        "schema": {"type": "string"},
    },
    **_POLLING_HEADER_SCHEMA,
}
```

Create `_post_success_responses(response_type)` to declare both `200` and `202` models with these headers. Merge its output into every POST decorator before error responses.

After each submission, call `apply_experiment_headers(response, record, include_location=True)` before selecting `200` or `202`. Add `response: Response` to both polling routes and call `apply_experiment_headers(..., include_location=False)` after loading the record.

- [ ] **Step 7: Run API and schema tests**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_api_backtests.py tests/test_api_research_operations.py tests/test_api_system.py -q
```

Expected: all response models, body fields, runtime headers, and OpenAPI headers pass.

- [ ] **Step 8: Commit polling metadata**

```powershell
git add bktstr/api/lifecycle.py bktstr/api/schemas.py bktstr/api/routes.py tests/test_api_backtests.py tests/test_api_research_operations.py
git commit -m "feat(api): standardize experiment polling metadata"
```

---

### Task 6: Add end-to-end contracts for every POST route and idempotency case

**Files:**
- Create: `tests/research_fixtures.py`
- Create: `tests/test_api_post_contracts.py`
- Modify: `tests/test_services_research_operations.py`
- Modify: `tests/test_api_backtests.py`

**Interfaces:**
- Consumes: real FastAPI routes, `ExperimentStore`, `ExperimentWorker`, the operation adapters, and Tasks 1 through 5.
- Produces: `deterministic_research_result(value: BacktestInput) -> BacktestResearchResult` and four POST route contract cases.

- [ ] **Step 1: Extract a complete deterministic research fixture**

Create `tests/research_fixtures.py` by moving the existing `_research_result` construction from `tests/test_services_research_operations.py`. Name it `deterministic_research_result`. Ensure its provenance contains the complete public fields required by `ResearchProvenanceResponse`:

```python
market_data=MappingProxyType(
    {
        "source": "fixture",
        "requested_source": "auto",
        "version": "fixture-v1",
        "snapshot_id": "sha256:fixture",
        "coverage": {
            "requested_start": value.start.isoformat(),
            "requested_end": value.end.isoformat(),
            "available_start": value.start.isoformat(),
            "available_end": value.end.isoformat(),
            "observations": 2,
            "bars": 2,
        },
        "cache": {"hit_days": 0, "miss_days": 1, "fetched_ranges": 1},
    }
),
software=MappingProxyType(
    {
        "bktstr_version": "0.6.0",
        "git_commit": "fixture",
        "git_branch": None,
        "git_repo": None,
        "deployment_id": None,
        "build_time": None,
    }
),
```

Keep strategy, execution model, configuration, metrics, and empty trades from the existing helper. Replace local references with the imported fixture and rerun the service tests before adding new contracts.

- [ ] **Step 2: Create the HTTP contract harness**

In `tests/test_api_post_contracts.py`, define `AUTH`, canonical request bodies, and a client context that sets `BKTSTR_API_KEY`, sets a temporary `BKTSTR_EXPERIMENT_DIR`, prevents the background poll loop, and patches `bktstr.services.backtest.run_backtest`:

```python
@contextmanager
def _client(monkeypatch, tmp_path):
    async def deterministic(value):
        return deterministic_research_result(value)

    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_EXPERIMENT_DIR", str(tmp_path / "experiments"))
    monkeypatch.setattr(ExperimentWorker, "run_forever", lambda self, stop_event: None)
    monkeypatch.setattr(backtest_service, "run_backtest", deterministic)
    with TestClient(create_app()) as client:
        yield client
```

Define one valid async body for each path. The compare body uses two named variants named `control` and `wide-stop`. The sweep uses one grid candidate to keep the contract test bounded. The regime comparison uses two one-day labels.

- [ ] **Step 3: Write the failing terminal POST contract test**

Parameterize path, body, operation, and result key:

```python
@pytest.mark.parametrize(
    ("path", "body", "operation", "result_key"),
    [
        ("/api/v1/backtests", BACKTEST_ASYNC_BODY, "backtest", "metrics"),
        ("/api/v1/parameter-sweeps", SWEEP_BODY, "parameter_sweep", "variants"),
        ("/api/v1/compare", COMPARE_BODY, "compare", "candidates"),
        ("/api/v1/regime-comparison", REGIME_BODY, "regime_comparison", "items"),
    ],
)
def test_post_route_persists_executes_and_polls_typed_terminal_result(
    monkeypatch, tmp_path, path, body, operation, result_key
):
    with _client(monkeypatch, tmp_path) as client:
        accepted = client.post(path, json=body, headers=AUTH)
        experiment_id = accepted.json()["experiment_id"]
        client.app.state.experiment_worker.run(experiment_id)
        completed = client.get(
            f"/api/v1/experiments/{experiment_id}", headers=AUTH
        )

    assert accepted.status_code == 202
    assert accepted.headers["location"] == accepted.json()["status_url"]
    assert accepted.headers["retry-after"] == "2"
    assert completed.status_code == 200
    assert completed.json()["operation"] == operation
    assert completed.json()["status"] == "completed"
    assert completed.json()["error"] is None
    assert result_key in completed.json()["result"]
    assert completed.json()["retry_after_seconds"] is None
```

- [ ] **Step 4: Write idempotency replay/conflict contracts for all routes**

Create `_different_payload(path, body)` that deep-copies and changes one valid semantic field per operation:

- backtest changes `include_trades`;
- sweep changes `objective` from `profit_factor` to `sharpe`;
- compare changes the second candidate name;
- regime comparison changes `disjoint_periods`.

Then add:

```python
@pytest.mark.parametrize("path,body", POST_CASES)
def test_post_route_idempotency_replays_same_payload_and_conflicts_on_change(
    monkeypatch, tmp_path, path, body
):
    headers = {**AUTH, "Idempotency-Key": "contract-key"}
    with _client(monkeypatch, tmp_path) as client:
        first = client.post(path, json=body, headers=headers)
        replay = client.post(path, json=body, headers=headers)
        conflict = client.post(
            path, json=_different_payload(path, body), headers=headers
        )

    assert replay.status_code == first.status_code == 202
    assert replay.json()["experiment_id"] == first.json()["experiment_id"]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    assert conflict.headers["x-request-id"].startswith("req_")
```

Add a separate store/API test proving the same key on `/backtests` and `/compare` creates independent experiment IDs.

- [ ] **Step 5: Run new contracts and confirm they catch missing behavior**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_api_post_contracts.py -v
```

Expected before Tasks 3 through 5: comparison or polling metadata assertions fail. After those tasks, all cases pass.

- [ ] **Step 6: Run all service/API/worker contract tests**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_services_backtest.py tests/test_services_research_operations.py tests/test_experiment_worker.py tests/test_api_backtests.py tests/test_api_research_operations.py tests/test_api_market_data.py tests/test_api_post_contracts.py -q
```

Expected: all focused contracts pass without live provider calls.

- [ ] **Step 7: Commit end-to-end POST coverage**

```powershell
git add tests/research_fixtures.py tests/test_api_post_contracts.py tests/test_services_research_operations.py tests/test_api_backtests.py
git commit -m "test(api): cover every POST through terminal polling"
```

---

### Task 7: Publish the external API reference

**Files:**
- Create: `docs/API_REFERENCE.md`
- Modify: `README.md:54-97`
- Modify: `docs/BKTSTR_SYSTEM_MANUAL.md:704-806`

**Interfaces:**
- Consumes: the runtime contracts verified in Tasks 1 through 6.
- Produces: one canonical human-facing API reference linked by the existing entry-point documents.

- [ ] **Step 1: Write authentication and ownership sections**

Create `docs/API_REFERENCE.md` with sentence-case headings. State these exact facts:

- Send `Authorization: Bearer <BKTSTR_API_KEY>` on every `/api/v1/*` route except both health routes.
- The configured key is one nonempty opaque string. It has no prefix requirement, scopes, built-in expiry, or parallel grace key.
- The Railway deployment owner creates and distributes the key.
- Rotation replaces `BKTSTR_API_KEY` and redeploys. Revocation deletes or replaces it and redeploys.
- A rotated key stops working when the deployment using the replacement becomes active.
- Clients must not place the key in URLs, request bodies, experiment metadata, or logs.

- [ ] **Step 2: Add complete request examples**

Include four copyable JSON examples using the exact current schema. Use the canonical baseline request for backtests; a two-value `stop_pct` sweep with objective `profit_factor`; a mixed comparison with one experiment ID and one named variant; and a two-label regime comparison. Every nested backtest uses `timeframe: "1m"` and `source: "auto"`.

State that the comparison's first candidate is the reference, named variants create child backtests, and experiment IDs must name completed backtests when the worker executes.

- [ ] **Step 3: Document strategy and market rules**

Add a compact table with:

| Rule | Runtime behavior |
| --- | --- |
| Strategy | `bktstr.bearish-regime-scalp` version `1.0.0` |
| Backtest timeframe | `1m` |
| Market-data inspection timeframes | `1m`, `5m`, `15m`, `1h`, `1d` |
| Symbols | Normalize to uppercase; 1-15 characters; first character A-Z; remaining characters A-Z, 0-9, `.`, or `-` |
| Source request | `auto` only |
| Date span | At most 730 elapsed days |
| Percent parameters | `stop_pct=1` means 1%; `target_pct=3` means 3% |

Tell clients to read `/api/v1/capabilities` for registered parameter bounds, choices, overridability, strategy version, and evidence rules. List these exact baseline defaults from `BacktestCreate` and `_baseline_parameters()`:

| Field or parameter | Default |
| --- | --- |
| `side` | `short` |
| `entry` / `entry_rules` | `close.cross_below:vwap,rsi14.lt:50,volume_ratio20.gt:1.10` |
| `regime_rules` | `day_sma20_slope5.lt:0,relative_return20.lt:0` |
| `stop_pct` | `1.0` |
| `target_pct` | `3.0` |
| `max_hold_minutes` | `240` |
| `position_size` | `1000.0` |
| `starting_capital` | `10000.0` |
| `slippage_bps` | `2.0` |
| `regular_hours_only` | `true` |
| `same_day_only` | `true` |
| `entry_start_time` | `12:30` |
| `entry_end_time` | `16:00` |
| `sentiment` | `true` |
| `sentiment_data_profile` | `clean` |
| `sentiment_sources` | `["price"]` |
| request `execution` | `auto` |
| request `include_trades` | `true` |

- [ ] **Step 4: Document async lifecycle and idempotency**

Show a `202` body containing `experiment_id`, `status`, `status_url`, and `retry_after_seconds`. State:

- POST returns `202` for queued/running and `200` for terminal inline execution or terminal idempotent replay.
- `Location` identifies the canonical status URL.
- `Retry-After` and `retry_after_seconds` are `2` while nonterminal.
- Poll with authenticated GET and stop at `completed` or `failed`.
- Do not resubmit pending work.
- The four legal transitions remain `queued -> running -> completed|failed`.

Copy the idempotency table from the design without changing its operation scope or no-TTL statement. Include the visible ASCII length rule.

- [ ] **Step 5: Add the error catalog**

Document `400`, `401`, `404`, `409`, `410`, `422`, `500`, and `502`. Include codes `invalid_request`, `unauthorized`, `experiment_not_found`, `idempotency_conflict`, `execution_not_available`, `legacy_endpoint_removed`, `validation_error`, `strategy_incompatible`, `operation_failed`, `result_persistence_failed`, and `market_data_http_error`.

Explain that immediate HTTP errors include `error.request_id` and `X-Request-ID`. Worker errors live inside the experiment envelope and do not have an HTTP request ID because they may happen after the submitting request ends.

- [ ] **Step 6: Add provider limits, retention, rate limits, and cache behavior**

Document the exact runtime values:

- Massive is selected when configured, requests 50,000 rows per page, permits 100 pages, and retries `429/500/502/503/504` six times after the first request.
- Numeric upstream `Retry-After` wins; otherwise delay doubles from 2 seconds and caps at 30 seconds.
- Massive history depends on the account. BKTSTR promises only its 730-day request maximum.
- Yahoo is a development fallback for `1m`, `5m`, and `15m` data wholly within the latest 30 calendar days. It fetches seven-day chunks. Older history, `1h`, `1d`, regime, and sentiment runs require Massive.
- BKTSTR has no ingress request-per-minute limit. Clients still follow the two-second polling interval and provider/deployment limits.
- Historical raw cache keys are provider, symbol, timeframe, and day. Historical empty days are cached. The current day is volatile and not stored as a completed historical day.
- Derived caches contain deterministic measurements and context, never strategy decisions or simulation results.

- [ ] **Step 7: Link the canonical reference**

Add `[API reference](docs/API_REFERENCE.md)` to the README API section. In the system manual, retain the architectural explanation and replace duplicated operational details with a short summary plus `[API reference](API_REFERENCE.md)`.

Do not add tests that grep for exact prose. Run existing documentation and link checks because they exercise repository behavior, not wording.

- [ ] **Step 8: Run documentation verification**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_docs.py tests/test_governance_docs.py -q
```

Then run the repository's existing broken-link command if `tests/test_governance_docs.py` reports a named helper or CLI. Expected: all current documentation checks pass and the new links resolve.

- [ ] **Step 9: Commit the API reference**

```powershell
git add docs/API_REFERENCE.md README.md docs/BKTSTR_SYSTEM_MANUAL.md
git commit -m "docs(api): publish complete research API reference"
```

---

### Task 8: Add deployed comparison acceptance and complete verification

**Files:**
- Modify: `scripts/production_acceptance.py:14-190`
- Modify: `tests/test_production_acceptance.py:28-109`

**Interfaces:**
- Consumes: completed inline backtests, `status_url`, `retry_after_seconds`, and the compare endpoint.
- Produces: `_poll_experiment(client, envelope, sleeper) -> dict[str, Any]` and an acceptance report containing comparison status and candidate count.

- [ ] **Step 1: Write a failing mock-transport acceptance test**

Extend `_transport` so it returns two distinct completed backtest IDs, accepts a compare request containing those IDs, returns a queued compare with `status_url`, and returns `running` once then `completed` from that URL. Add:

```python
def test_production_acceptance_submits_and_polls_comparison():
    sleeps = []
    report = _module().run_acceptance(
        "https://bktstr.example",
        api_key="test-key",
        sleeper=sleeps.append,
        transport=_transport(include_comparison=True),
    )

    assert report["comparison"] == {
        "experiment_id": "exp_compare",
        "status": "completed",
        "candidate_count": 2,
    }
    assert sleeps == [2]
```

The mock handler must assert that the compare request candidates equal the two IDs returned by the preceding backtests.

- [ ] **Step 2: Run the acceptance test and confirm red**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_production_acceptance.py::test_production_acceptance_submits_and_polls_comparison -v
```

Expected: the report has no `comparison` key and no polling occurs.

- [ ] **Step 3: Add a second bounded backtest and polling helper**

Define a second request by changing only `stop_pct` to `2.0`. Add:

```python
def _poll_experiment(client, envelope, sleeper) -> dict[str, Any]:
    current = envelope
    while current.get("status") in {"queued", "running"}:
        status_url = current.get("status_url")
        retry_after = current.get("retry_after_seconds")
        if not isinstance(status_url, str) or not status_url.startswith("/api/v1/experiments/"):
            raise AcceptanceError("queued experiment is missing a valid status_url")
        if not isinstance(retry_after, int) or retry_after < 1:
            raise AcceptanceError("queued experiment is missing retry timing")
        sleeper(retry_after)
        current = _get_json(client, status_url)
    return current
```

In `run_acceptance`, submit the anchor and changed backtest, require both to complete inline, submit:

```python
comparison = _post_json(
    client,
    "/api/v1/compare",
    {
        "candidates": [
            backtest["experiment_id"],
            changed_backtest["experiment_id"],
        ],
        "execution": "async",
    },
)
comparison = _poll_experiment(client, comparison, sleeper)
```

Require `completed`, `error is None`, and exactly two result candidates. Add comparison identity, status, and candidate count to the report.

- [ ] **Step 4: Verify OpenAPI enums and async fields in acceptance**

Inspect the fetched schema and require:

```python
schemas = schema["components"]["schemas"]
market = schemas["MarketCreate"]["properties"]
if "$ref" not in market["timeframe"] or "$ref" not in market["source"]:
    raise AcceptanceError("OpenAPI does not publish market request enums")
experiment = schemas["CompareExperimentResponse"]["properties"]
if not {"status_url", "retry_after_seconds"} <= set(experiment):
    raise AcceptanceError("OpenAPI does not publish polling metadata")
```

- [ ] **Step 5: Run production acceptance unit tests**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_production_acceptance.py -q
```

Expected: all deployment identity, authentication, backtest, comparison, polling, and CLI tests pass.

- [ ] **Step 6: Run the full test suite**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q
```

Expected: zero failures. Record the pass count and any pre-existing warnings.

- [ ] **Step 7: Run compilation, release, and repository checks**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m compileall -q bktstr bktstr_cache integration scripts benchmarks tests
& '.\.venv\Scripts\python.exe' scripts/check_release_consistency.py
& '.\.venv\Scripts\python.exe' benchmarks/benchmark_cache.py
git diff --check
git status --short
```

Expected: each Python command exits `0`, the benchmark reports one compute call and a warm hit, `git diff --check` prints nothing, and `git status` shows only intended source changes plus the user's pre-existing unrelated deletions.

- [ ] **Step 8: Review the requirements against fresh evidence**

Check each acceptance criterion in the approved spec against a passing test or the rendered OpenAPI/documentation. Specifically record:

- comparison by experiment IDs and named variants;
- pre-enqueue `422` for `1d` baseline requests;
- safe worker error details;
- `source=auto` and timeframe enums;
- body and header polling metadata;
- operation-scoped idempotency replay/conflict;
- four terminal POST contracts;
- provider, retention, rate, cache, authentication, and comparison documentation;
- deployed comparison acceptance logic.

Do not claim completion if any item lacks fresh evidence.

- [ ] **Step 9: Commit acceptance and final integration changes**

```powershell
git add scripts/production_acceptance.py tests/test_production_acceptance.py
git commit -m "test(deploy): require terminal comparison acceptance"
```

Run the full verification commands from Steps 6 and 7 again after the commit. The final handoff must report the exact test count, verification commands, commit list, and any unrelated dirty-worktree entries left untouched.
