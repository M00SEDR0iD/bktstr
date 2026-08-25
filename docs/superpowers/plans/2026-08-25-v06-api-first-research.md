# BKTSTR v0.6 API-First Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Deliver a typed FastAPI research API with durable, reproducible Railway-volume experiments while preserving the v0.5 strategy and execution core.

**Architecture:** FastAPI routes and Pydantic schemas authenticate, validate, and delegate only. The four service modules own backtest orchestration, data/provenance acquisition, regime resolution, and durable experiment lifecycle state. A SQLite index plus canonical JSON artifacts on the Railway volume backs a shared experiment envelope while each operation keeps strongly typed inputs and outputs.

**Tech Stack:** Python 3.12, FastAPI 0.141.1 with its standard Uvicorn dependencies, Pydantic v2, SQLite from the standard library, pandas, httpx, pytest, Railway Volume.

**Spec:** docs/superpowers/specs/2026-08-25-v06-api-design.md

## Global Constraints

- REST is BKTSTR's permanent product interface; a future MCP server is only a thin adapter over the same typed services.
- Keep FastAPI and Pydantic types out of the v0.5 engine, immutable contracts, provider adapters, and formula functions.
- Preserve Tier A/B immutability; regime, sentiment, and fragility remain Tier B; C/D cannot influence A/B; automatic backfill stays disabled; forced optional filters stay degraded and non-canonical.
- Preserve existing formulas, causal execution semantics, provider behavior, and frozen v0.5 legacy output unless retaining the legacy endpoint would require more than a thin adapter.
- Every submitted backtest, sweep, comparison, or regime comparison creates one durable immutable completed experiment record with canonical request, result, and provenance artifacts.
- Protect all /api/v1 routes with BKTSTR_API_KEY bearer authentication except the unauthenticated /health probe.
- In auto mode, a bounded backtest completes inline; sweeps and comparisons queue. A sync request that policy cannot run inline returns 409 execution_not_available.
- Store experiments under BKTSTR_EXPERIMENT_DIR, defaulting to RAILWAY_VOLUME_MOUNT_PATH/bktstr-experiments and then /tmp/bktstr-experiments.
- Run focused tests for Tasks 1 through 7. Run the complete suite only in Task 8.

## File Structure

| Path | Responsibility |
| --- | --- |
| requirements.txt and Dockerfile | FastAPI/Uvicorn runtime dependency and Railway start command. |
| bktstr/api/app.py | Application factory, lifespan worker, exception handlers, router assembly. |
| bktstr/api/auth.py | Bearer-key dependency and request-ID generation. |
| bktstr/api/schemas.py | Typed public requests, results, envelopes, and errors. |
| bktstr/api/routes.py | Thin versioned system, research, experiment, market-data, and legacy routes. |
| bktstr/services/data.py | Provider/cache conversion and normalized market-data inspection. |
| bktstr/services/regimes.py | Registered causal context validation and conversion. |
| bktstr/services/backtest.py | Typed backtest orchestration, research result projection, provenance. |
| bktstr/services/experiments.py | SQLite/artifact repository, idempotency, lifecycle, queue worker. |
| bktstr/server.py | Compatibility entrypoint only; it does not execute a second HTTP stack. |
| tests/test_api_*.py | OpenAPI, auth, error, route, and response contracts. |
| tests/test_experiments.py and tests/test_experiment_worker.py | Persistence, lifecycle, idempotency, worker recovery. |
| tests/test_services_*.py | Formula/execution-parity and high-level operation tests without HTTP. |

---

### Task 1: Establish FastAPI, typed system routes, and error/auth boundaries

**Files:**

- Modify: requirements.txt, Dockerfile, bktstr/server.py
- Create: bktstr/api/__init__.py, bktstr/api/app.py, bktstr/api/auth.py, bktstr/api/schemas.py, bktstr/api/routes.py, tests/test_api_system.py

**Interfaces:**

- Produces create_app() -> FastAPI, require_api_key(), ApiError, ErrorResponse, and typed health/capability routes.
- Consumes existing health_payload() and registered capability builders; it does not duplicate core metadata.

- [ ] **Step 1: Write failing contract tests**

    from fastapi.testclient import TestClient
    from bktstr.api.app import create_app

    def test_openapi_and_authenticated_system_routes(monkeypatch):
        monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
        client = TestClient(create_app())
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/capabilities").status_code == 401
        response = client.get("/api/v1/capabilities", headers={"Authorization": "Bearer test-key"})
        assert response.status_code == 200
        assert "/api/v1/backtests" in client.get("/openapi.json").json()["paths"]

    def test_error_envelope_has_request_id(monkeypatch):
        monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
        body = TestClient(create_app()).get("/api/v1/health").json()
        assert body["error"]["code"] == "unauthorized"
        assert body["error"]["request_id"].startswith("req_")

- [ ] **Step 2: Verify red**

Run: python -m pytest tests/test_api_system.py -v -p no:cacheprovider

Expected: FAIL because bktstr.api.app does not exist.

- [ ] **Step 3: Implement the minimal application foundation**

Add fastapi[standard]==0.141.1 after httpx in requirements.txt. Create the application
factory and shared public error model:

    class ApiError(BaseModel):
        code: str
        message: str
        details: dict[str, Any] = Field(default_factory=dict)
        request_id: str

    class ErrorResponse(BaseModel):
        error: ApiError

    def create_app() -> FastAPI:
        app = FastAPI(title="BKTSTR Research API", version=__version__)
        app.include_router(api_router, prefix="/api/v1")
        return app

Define api_router = APIRouter() in bktstr/api/routes.py before registering the
three system routes.

require_api_key must use secrets.compare_digest, return 401 without exposing the
configured key, and protect every versioned route. Install typed handlers for
authentication, Pydantic validation, ValueError, httpx provider errors, and
unexpected errors. Keep /health unauthenticated and make /api/v1/health
authenticated. Replace the ThreadingHTTPServer process with the same FastAPI
application run by Uvicorn; Docker uses:

    CMD ["uvicorn", "bktstr.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

The entrypoint must translate Railway PORT before starting Uvicorn rather than
creating a second HTTP implementation.

- [ ] **Step 4: Verify green**

Run: python -m pytest tests/test_api_system.py tests/test_server.py -v -p no:cacheprovider

Expected: PASS; OpenAPI contains typed system routes and capabilities remain
registry-derived.

- [ ] **Step 5: Commit**

    git add requirements.txt Dockerfile bktstr/server.py bktstr/api tests/test_api_system.py tests/test_server.py
    git commit -m "feat(api): add typed FastAPI foundation"

### Task 2: Add a shared experiment envelope and Railway-volume persistence

**Files:**

- Create: bktstr/services/__init__.py, bktstr/services/experiments.py, tests/test_experiments.py
- Modify: bktstr/api/schemas.py

**Interfaces:**

- Produces ExperimentStatus, ExecutionMode, ExperimentStateError, IdempotencyConflictError, ExperimentRecord, ExperimentStore, create_experiment(), load_experiment(), claim_next(), complete(), and fail().
- Consumes only canonical typed request/result mappings. It imports neither FastAPI nor route schemas.

- [ ] **Step 1: Write failing persistence tests**

    def test_same_idempotency_key_returns_same_experiment(tmp_path):
        store = ExperimentStore(tmp_path)
        first, made_first = store.create_experiment("backtest", {"symbol": "NVDA"}, "auto", "client-key")
        second, made_second = store.create_experiment("backtest", {"symbol": "NVDA"}, "auto", "client-key")
        assert made_first is True and made_second is False
        assert second.experiment_id == first.experiment_id

    def test_completed_record_is_immutable_and_has_artifacts(tmp_path):
        store = ExperimentStore(tmp_path)
        record, _ = store.create_experiment("backtest", {"symbol": "NVDA"}, "sync", None)
        completed = store.complete(record.experiment_id, {"metrics": {"trade_count": 1}}, {"software": {"bktstr_version": "0.5.0"}})
        assert completed.status is ExperimentStatus.COMPLETED
        with pytest.raises(ExperimentStateError):
            store.complete(record.experiment_id, {"metrics": {}}, {})

- [ ] **Step 2: Verify red**

Run: python -m pytest tests/test_experiments.py -v -p no:cacheprovider

Expected: FAIL because bktstr.services.experiments does not exist.

- [ ] **Step 3: Implement append-only storage**

Use these domain types:

    class ExperimentStatus(StrEnum):
        QUEUED = "queued"
        RUNNING = "running"
        COMPLETED = "completed"
        FAILED = "failed"

    @dataclass(frozen=True)
    class ExperimentRecord:
        experiment_id: str
        operation: str
        status: ExperimentStatus
        execution: str
        created_at: datetime
        started_at: datetime | None
        completed_at: datetime | None
        request: Mapping[str, Any]
        result: Mapping[str, Any] | None
        error: Mapping[str, Any] | None
        provenance: Mapping[str, Any] | None

Resolve the root from BKTSTR_EXPERIMENT_DIR, then Railway's volume mount, then
/tmp. Create experiments.sqlite3 with a unique (operation, idempotency_key)
constraint. Store sorted-key, UTF-8, no-NaN canonical JSON with
temp-file-plus-rename below artifacts/<experiment_id>/. Equal canonical requests
reuse an idempotency record; different requests raise IdempotencyConflictError.
Allow only queued -> running -> completed or failed; terminal records are never
overwritten. Add Pydantic ExperimentEnvelope, ExperimentError, and public enum
schemas, converting the service record only at the API edge.

- [ ] **Step 4: Verify green**

Run: python -m pytest tests/test_experiments.py -v -p no:cacheprovider

Expected: PASS; reopening the store sees the same records, artifacts are
canonical, and terminal records cannot mutate.

- [ ] **Step 5: Commit**

    git add bktstr/services bktstr/api/schemas.py tests/test_experiments.py
    git commit -m "feat(experiments): persist reproducible research records"

### Task 3: Extract typed data, regime, and backtest services

**Files:**

- Create: bktstr/services/data.py, bktstr/services/regimes.py, bktstr/services/backtest.py, tests/test_services_backtest.py
- Modify: bktstr/service.py

**Interfaces:**

- Produces BacktestInput, RegimeInput, BacktestResearchResult, to_legacy_request(), project_research_result(), run_backtest(), normalize_market_request(), and normalize_regime_request().
- Consumes existing BacktestRequest, execute_backtest, registries, cache/provider adapters, and result serializer.
- Later tasks call run_backtest(input); routes never call execute_backtest directly.

- [ ] **Step 1: Write failing service parity tests**

    def test_typed_backtest_projects_research_fields(monkeypatch):
        result = asyncio.run(run_backtest(BacktestInput(
            strategy_id="bktstr.bearish-regime-scalp",
            strategy_version="1.0.0", symbol="NVDA",
            start=date(2026, 8, 17), end=date(2026, 8, 17),
            timeframe="1m", side="short", entry="close.cross_below:vwap",
        )))
        assert result.metrics.trade_count >= 0
        assert result.provenance.strategy["id"] == "bktstr.bearish-regime-scalp"
        assert {"entry_timestamp", "exit_timestamp", "mfe", "mae"} <= result.trades[0].model_fields_set

    def test_non_overridable_strategy_parameter_is_rejected():
        with pytest.raises(ValueError, match="overridable"):
            BacktestInput(
                strategy_id="bktstr.bearish-regime-scalp", strategy_version="1.0.0",
                symbol="NVDA", start=date(2026, 8, 17), end=date(2026, 8, 17),
                timeframe="1m", side="short", entry="close.cross_below:vwap",
                parameters={"execution_model": "other"},
            )

- [ ] **Step 2: Verify red**

Run: python -m pytest tests/test_services_backtest.py -v -p no:cacheprovider

Expected: FAIL because the typed service does not exist.

- [ ] **Step 3: Implement typed adapters without changing formulas**

Define:

    @dataclass(frozen=True)
    class BacktestInput:
        strategy_id: str
        strategy_version: str
        symbol: str
        start: date
        end: date
        timeframe: str
        side: str
        entry: str
        parameters: Mapping[str, float | int | str | bool] = field(default_factory=dict)
        regime: RegimeInput | None = None
        execution: str = "auto"

    async def run_backtest(input: BacktestInput) -> BacktestResearchResult:
        request = to_legacy_request(input)
        return project_research_result(input, await execute_backtest(request))

services/data.py validates symbol/date/timeframe/source and invokes the existing
provider/cache contract. services/regimes.py validates only registered,
causally safe regime/context settings. services/backtest.py resolves the exact
registered strategy/version and allowed overrides, maps to the existing domain
BacktestRequest, invokes the current path exactly once, and projects the result
to typed metrics, trades, configuration, and provenance.

Projection calculates EV/trade, win rate, profit factor, max drawdown, Sharpe,
and trade count from the frozen result without re-running signals or changing
prices. Each trade has timestamps/prices, holding time, realized P&L, MFE, MAE,
entry signals, and available regime variables. Unsupported metric values are
explicit null, never invented.

- [ ] **Step 4: Verify green and parity**

Run: python -m pytest tests/test_services_backtest.py tests/test_service.py tests/test_v05_equivalence.py -v -p no:cacheprovider

Expected: PASS; typed projection is richer while formula, execution, and legacy
equivalence remain unchanged.

- [ ] **Step 5: Commit**

    git add bktstr/services bktstr/service.py tests/test_services_backtest.py
    git commit -m "feat(services): add typed backtest research service"

### Task 4: Add execution policy and durable in-process worker

**Files:**

- Modify: bktstr/services/experiments.py, bktstr/api/app.py
- Create: tests/test_experiment_worker.py

**Interfaces:**

- Produces ExecutionPolicy, ExperimentWorker, submit(), and recover_incomplete().
- Consumes ExperimentStore and registered operation callables returning canonical result/provenance mappings.

- [ ] **Step 1: Write failing policy and recovery tests**

    def test_auto_runs_bounded_backtest_inline_and_queues_sweep():
        policy = ExecutionPolicy(sync_max_calendar_days=31)
        assert policy.choose("backtest", ExecutionMode.AUTO, calendar_days=1) is ExecutionMode.SYNC
        assert policy.choose("parameter_sweep", ExecutionMode.AUTO, calendar_days=1) is ExecutionMode.ASYNC

    def test_sync_request_outside_policy_raises_stable_error():
        with pytest.raises(ExecutionNotAvailableError):
            ExecutionPolicy(sync_max_calendar_days=31).choose("backtest", ExecutionMode.SYNC, calendar_days=32)

    def test_worker_recovers_queued_record_after_restart(tmp_path):
        store = ExperimentStore(tmp_path)
        record, _ = store.create_experiment("parameter_sweep", {"grid": {}}, "async", None)
        worker = ExperimentWorker(store, {"parameter_sweep": lambda record: ({"items": []}, {})})
        worker.run_one()
        assert store.load(record.experiment_id).status is ExperimentStatus.COMPLETED

- [ ] **Step 2: Verify red**

Run: python -m pytest tests/test_experiment_worker.py -v -p no:cacheprovider

Expected: FAIL because policy and worker classes do not exist.

- [ ] **Step 3: Implement the configured hybrid policy**

auto runs only backtest requests at or below BKTSTR_SYNC_MAX_CALENDAR_DAYS
(default 31) inline. auto queues parameter_sweep, compare, and
regime_comparison. async always queues. sync uses the same bound or raises
ExecutionNotAvailableError.

The worker transactionally claims one queued SQLite row, marks it running,
invokes the operation, atomically persists result/provenance, then marks it
completed. Expected domain/provider errors persist a stable structured error and
mark failed. On FastAPI lifespan startup, stale running rows become queued and
one polling worker starts. On shutdown it stops claiming work and completes the
active state transition. Do not make FastAPI BackgroundTasks the source of
durable lifecycle truth.

- [ ] **Step 4: Verify green**

Run: python -m pytest tests/test_experiments.py tests/test_experiment_worker.py -v -p no:cacheprovider

Expected: PASS; policy choices are deterministic and durable queued work can
recover after process restart.

- [ ] **Step 5: Commit**

    git add bktstr/services/experiments.py bktstr/api/app.py tests/test_experiment_worker.py
    git commit -m "feat(experiments): add durable execution policy"

### Task 5: Deliver typed backtests, polling, and conditional legacy compatibility

**Files:**

- Modify: bktstr/api/schemas.py, bktstr/api/routes.py, bktstr/server.py
- Create: tests/test_api_backtests.py
- Modify: tests/test_server.py, tests/test_production_acceptance.py

**Interfaces:**

- Produces POST /api/v1/backtests, GET /api/v1/backtests/{id}, GET /api/v1/experiments/{id}, and a thin legacy adapter or documented removal response.
- Consumes run_backtest, ExperimentStore, ExecutionPolicy, and ExperimentEnvelope.

- [ ] **Step 1: Write failing HTTP tests**

    def test_completed_backtest_returns_typed_experiment(client):
        response = client.post("/api/v1/backtests", json=BACKTEST_BODY, headers=AUTH)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        assert body["experiment_id"].startswith("exp_")
        assert {"metrics", "trades", "configuration", "provenance"} <= body["result"].keys()

    def test_async_idempotent_submission_can_be_polled(client):
        headers = {**AUTH, "Idempotency-Key": "once"}
        first = client.post("/api/v1/backtests", json={**BACKTEST_BODY, "execution": "async"}, headers=headers)
        second = client.post("/api/v1/backtests", json={**BACKTEST_BODY, "execution": "async"}, headers=headers)
        assert first.status_code == second.status_code == 202
        assert first.json()["experiment_id"] == second.json()["experiment_id"]

- [ ] **Step 2: Verify red**

Run: python -m pytest tests/test_api_backtests.py -v -p no:cacheprovider

Expected: FAIL because research routes are absent.

- [ ] **Step 3: Implement thin routes**

Define BacktestCreate, BacktestResult, and BacktestExperimentResponse Pydantic
models. POST /backtests canonicalizes BacktestCreate, creates the experiment
before execution, selects policy, and either returns a completed 200 envelope or
a queued 202 envelope. GET /backtests/{id} rejects non-backtest IDs with 404;
GET /experiments/{id} returns any operation's shared envelope.

Read Idempotency-Key, require 1 through 128 visible ASCII characters, map
different reused keys to 409 idempotency_conflict, policy refusal to 409
execution_not_available, and unknown IDs to 404 experiment_not_found.

Retain GET /api/v1/backtest only if its query parser delegates to this service
and its exact frozen legacy payload passes compatibility tests. Then add
Deprecation: true, a BKTSTR_LEGACY_BACKTEST_SUNSET value, and a Link header to
/openapi.json. Otherwise return one documented 410 legacy_endpoint_removed
envelope. Never retain the old threaded handler.

- [ ] **Step 4: Verify green**

Run: python -m pytest tests/test_api_backtests.py tests/test_server.py tests/test_production_acceptance.py -v -p no:cacheprovider

Expected: PASS; response envelopes are typed and idempotent, and compatibility is
either safely adapted or explicitly migrated.

- [ ] **Step 5: Commit**

    git add bktstr/api bktstr/server.py tests/test_api_backtests.py tests/test_server.py tests/test_production_acceptance.py
    git commit -m "feat(api): add reproducible backtest experiments"

### Task 6: Add bounded sweeps, comparisons, and regime comparisons

**Files:**

- Modify: bktstr/services/backtest.py, bktstr/services/experiments.py, bktstr/api/schemas.py, bktstr/api/routes.py
- Create: tests/test_services_research_operations.py, tests/test_api_research_operations.py

**Interfaces:**

- Produces ParameterSweepInput, CompareInput, RegimeComparisonInput, ParameterSweepCreate, CompareCreate, RegimeComparisonCreate, run_parameter_sweep(), compare_experiments(), run_regime_comparison(), and their typed service results.
- Consumes completed backtest experiment IDs and run_backtest; all three operations use the Task 4 worker in auto mode.

- [ ] **Step 1: Write failing high-level operation tests**

    def test_parameter_sweep_rejects_non_overridable_grid_key():
        with pytest.raises(ValueError, match="overridable"):
            ParameterSweepInput(base=BASE, grid={"execution_model": ["other"]}, objective="profit_factor")

    def test_compare_records_changed_inputs_and_metric_deltas(tmp_path):
        result = compare_experiments(("exp_a", "exp_b"), store=ExperimentStore(tmp_path))
        assert result.items[0].changed_inputs == ["strategy.parameters.stop_pct"]
        assert "profit_factor" in result.metric_deltas

    def test_research_operation_routes_queue_in_auto_mode(client):
        assert client.post("/api/v1/parameter-sweeps", json=SWEEP_BODY, headers=AUTH).status_code == 202
        assert client.post("/api/v1/compare", json=COMPARE_BODY, headers=AUTH).status_code == 202

- [ ] **Step 2: Verify red**

Run: python -m pytest tests/test_services_research_operations.py tests/test_api_research_operations.py -v -p no:cacheprovider

Expected: FAIL because typed high-level research operations do not exist.

- [ ] **Step 3: Implement bounded research operations**

ParameterSweepInput accepts one BacktestInput, a mapping of registered
overridable parameter names to scalar candidates, and one objective from
ev_per_trade, profit_factor, sharpe, max_drawdown, or total_pnl. Reject empty
grids, duplicate canonical candidates, unsupported objectives, and more than
BKTSTR_MAX_SWEEP_VARIANTS combinations (default 500). Execute in deterministic
sorted parameter order, persist each child backtest as a linked experiment, and
return ordered scored variants with child IDs.

CompareInput accepts two through twenty completed experiment IDs or typed named
variants. It aligns metrics, retains each candidate's provenance, and returns a
sorted list of exact changed canonical input paths. It must not claim causality
or select a winner automatically.

RegimeComparisonInput accepts one base backtest and two through twelve labels,
each with an inclusive date range and optional registered rule. It persists
linked child backtests and returns per-label metrics, trade records, and a
comparison matrix. Overlapping labels are allowed unless disjoint_periods is
true; all caller labels remain in provenance.

- [ ] **Step 4: Verify green**

Run: python -m pytest tests/test_services_research_operations.py tests/test_api_research_operations.py tests/test_experiment_worker.py -v -p no:cacheprovider

Expected: PASS; auto mode queues operations, grids are bounded/deterministic, and
linked child experiments reproduce each comparison.

- [ ] **Step 5: Commit**

    git add bktstr/services bktstr/api tests/test_services_research_operations.py tests/test_api_research_operations.py
    git commit -m "feat(api): add high-level research operations"

### Task 7: Publish normalized market-data inspection and discovery metadata

**Files:**

- Modify: bktstr/services/data.py, bktstr/api/schemas.py, bktstr/api/routes.py, docs/BKTSTR_SYSTEM_MANUAL.md
- Create: tests/test_api_market_data.py, tests/test_api_capabilities.py

**Interfaces:**

- Produces typed GET /api/v1/market-data pagination and expanded capability metadata.
- Consumes the same provider/cache contract as a backtest and does not expose provider credentials or raw responses.

- [ ] **Step 1: Write failing discovery and data tests**

    def test_capabilities_publish_api_limits_and_policy(client):
        response = client.get("/api/v1/capabilities", headers=AUTH)
        assert response.json()["api"]["openapi_url"] == "/openapi.json"
        assert response.json()["experiments"]["execution_policy"]["auto_queues"] == ["parameter_sweep", "compare", "regime_comparison"]

    def test_market_data_is_normalized_paginated_and_secret_free(client):
        response = client.get("/api/v1/market-data?symbol=NVDA&start=2026-08-17&end=2026-08-17&timeframe=1m&limit=2", headers=AUTH)
        assert response.status_code == 200
        assert {"timestamp", "open", "high", "low", "close", "volume"} <= set(response.json()["bars"][0])
        assert "api_key" not in response.text.lower()

- [ ] **Step 2: Verify red**

Run: python -m pytest tests/test_api_market_data.py tests/test_api_capabilities.py -v -p no:cacheprovider

Expected: FAIL because the typed route models and capability sections do not exist.

- [ ] **Step 3: Implement safe inspection and capability publication**

Accept symbol, start, end, timeframe, source, limit (1 through 1000), and an
opaque cursor. Use services/data.py to acquire normalized provider/cache bars,
return only timestamp/OHLCV, and create next_cursor from the last returned row.
Reject a cursor whose canonical data identity differs from the request.

Extend capabilities with api.open_api_url, authentication, operation names,
limits, idempotency behavior, experiment states, and the exact Task 4 policy.
Retain all v0.5 capability keys and derive strategy/variable details from the
registries. Document bearer setup, polling, execution modes, idempotency,
reproducibility, error codes, pagination, and legacy migration in the manual.

- [ ] **Step 4: Verify green**

Run: python -m pytest tests/test_api_market_data.py tests/test_api_capabilities.py tests/test_docs.py -v -p no:cacheprovider

Expected: PASS; clients can discover supported work and inspect deterministic,
safe normalized data.

- [ ] **Step 5: Commit**

    git add bktstr/services/data.py bktstr/api docs/BKTSTR_SYSTEM_MANUAL.md tests/test_api_market_data.py tests/test_api_capabilities.py tests/test_docs.py
    git commit -m "docs(api): publish research API contract"

### Task 8: Wire release/acceptance checks and run the final gate

**Files:**

- Modify: bktstr/__init__.py, railway.json, scripts/check_release_consistency.py, tests/test_release_consistency.py, tests/test_production_acceptance.py, docs/roadmap/v1-release-plan.md
- Test: complete suite, compilation, release consistency, OpenAPI, and production acceptance.

**Interfaces:**

- Produces v0.6.0 runtime metadata, Railway Uvicorn deployment configuration, and released API contract evidence.
- Consumes all earlier tasks and does not add routes, formulas, or operation types.

- [ ] **Step 1: Write failing release and acceptance tests**

    def test_v060_release_metadata_requires_fastapi_research_contract():
        assert __version__ == "0.6.0"
        schema = create_app().openapi()
        expected = {"/api/v1/backtests", "/api/v1/parameter-sweeps", "/api/v1/compare", "/api/v1/regime-comparison", "/api/v1/experiments/{id}", "/api/v1/market-data"}
        assert expected <= set(schema["paths"])

    def test_production_acceptance_uses_bearer_and_completed_backtest(monkeypatch):
        report = run_acceptance("https://bktstr.example", api_key="test-key", transport=_transport())
        assert report["backtest"]["status"] == "completed"

- [ ] **Step 2: Verify red**

Run: python -m pytest tests/test_release_consistency.py tests/test_production_acceptance.py -v -p no:cacheprovider

Expected: FAIL until v0.6 metadata and acceptance behavior are wired.

- [ ] **Step 3: Finish release wiring and compatibility audit**

Set the runtime version to 0.6.0. Configure Railway/Docker for the Uvicorn
factory. Document BKTSTR_API_KEY, BKTSTR_EXPERIMENT_DIR,
BKTSTR_SYNC_MAX_CALENDAR_DAYS, BKTSTR_MAX_SWEEP_VARIANTS, and
BKTSTR_LEGACY_BACKTEST_SUNSET. Update release consistency and production
acceptance for bearer-authenticated FastAPI health, capabilities, OpenAPI, and a
completed backtest envelope. Audit old server tests: retain their frozen
assertions only through the thin adapter, or replace them with the documented
410 migration response. Mark the API-first v0.6 milestone delivered in the
roadmap and leave MCP/UI for future work.

- [ ] **Step 4: Run the single final verification gate**

Run:

    python -m pytest -q -p no:cacheprovider
    python -m compileall -q bktstr bktstr_cache integration scripts benchmarks tests
    python scripts/check_release_consistency.py
    python -c "from bktstr.api.app import create_app; assert create_app().openapi()['openapi']"
    git diff --check main...HEAD
    git status --short --branch

Expected: complete suite passes, compilation/release checks pass, OpenAPI is
generated, diff hygiene is clean, and the worktree has no uncommitted changes.

- [ ] **Step 5: Commit**

    git add bktstr/__init__.py railway.json scripts/check_release_consistency.py tests/test_release_consistency.py tests/test_production_acceptance.py docs/roadmap/v1-release-plan.md
    git commit -m "chore(release): prepare v0.6 research API"

## Plan Self-Review

| Spec requirement | Tasks |
| --- | --- |
| Thin FastAPI routes, OpenAPI, one bearer key | 1, 5, 7, 8 |
| Shared envelope with typed operations | 2, 3, 5, 6 |
| Railway-volume reproducibility and immutable completion | 2, 4, 8 |
| Hybrid inline/queued execution | 4, 5, 6, 7 |
| Backtest metrics, trades, configuration, provenance | 3, 5 |
| Sweep, variant comparison, and regime comparison | 6 |
| Normalized paginated market data | 3, 7 |
| Conditional thin legacy adapter | 5, 8 |
| v0.5 trust/formula/execution compatibility | 3, 5, 8 |
| Documentation, release, and production acceptance | 1, 7, 8 |

The plan contains an explicit test-first cycle, exact commands, interface names,
initial numerical limits, error codes, lifecycle transitions, and commits for
every task. Later tasks consume only interfaces introduced in earlier tasks.
