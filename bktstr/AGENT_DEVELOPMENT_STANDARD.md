# Preferred Agent Development Workflow Standard

**Purpose:** This document defines the preferred development style for agent-assisted software work. Future agents should read this before changing code, infrastructure, tests, or deployment behavior.

**Primary goal:** Move quickly without sacrificing reproducibility. The agent should do as much technical work and verification as its tools allow, while keeping the human operator out of low-level diagnostics, file shuffling, and command-line work unless it is genuinely necessary.

---

## 1. Core Operating Principles

1. **GitHub is the source of truth.**
   - `main` represents the current deployable baseline.
   - Production must be traceable to an exact Git commit.
   - Never reconstruct source code from memory when the repository can be recovered or mirrored.

2. **Do not develop directly on `main`.**
   - Use a branch for every meaningful change.
   - Suggested naming:
     - `feature/<short-description>` for feature work.
     - `fix/<short-description>` for bug fixes.
     - `release/vX.Y.Z` for versioned release work.

3. **CI is a hard gate, not decoration.**
   - A pull request must pass automated tests before merge.
   - A red CI result is treated as useful evidence, not something to bypass.
   - Fix the cause on the branch and let CI rerun.

4. **Production verification is separate from CI.**
   - CI proves the source tree behaves correctly in the test environment.
   - Production acceptance proves the deployed service is the intended commit and preserves required real-world behavior.
   - A release is not complete until both pass.

5. **Evidence before claims.**
   - Do not say a feature, fix, deployment, benchmark, or release is complete without fresh verification.
   - Report concrete evidence: test count, exit status, commit SHA, version, deployment ID, regression values, or benchmark results.

6. **Prefer deterministic, reproducible behavior.**
   - Explicit formula/schema/cache versions are preferred over implicit behavior.
   - Runtime endpoints should expose enough build metadata to identify exactly what is executing.

7. **Keep unrelated changes separate.**
   - Do not combine trading/research-model changes with infrastructure changes unless there is a strong reason.
   - Do not add opportunistic refactors that are unrelated to the requested task.

8. **One good sample is not validation.**
   - Never promote a strategy feature simply because it improves one backtest period or one symbol.
   - Research changes require controls, out-of-sample testing, and cross-symbol/regime evidence before promotion.

---

## 2. Division of Responsibility

### The agent should normally handle

- Reading and understanding the current codebase.
- Comparing source to the deployed version.
- Designing the change.
- Writing tests first for behavior changes when practical.
- Implementing code.
- Running local tests, compile checks, scans, and benchmarks.
- Inspecting CI results when accessible.
- Inspecting production health/capabilities endpoints.
- Running production regression tests.
- Diagnosing failures before suggesting fixes.
- Maintaining technical documentation and release notes.
- Using connected systems or recovery bridges instead of asking the user to manually transfer data when a reliable tool path exists.

### The human operator should normally only need to handle

Actions that require their authenticated UI or explicit account authority, such as:

- Publishing a branch from GitHub Desktop.
- Creating a pull request.
- Merging an approved green pull request.
- Publishing a release/tag when appropriate.
- Approving cost/security-sensitive actions when required.

Do **not** use the human as a manual diagnostic layer if the agent can inspect the system directly.

---

## 3. Preferred Human Interface

The preferred manual Git workflow is **GitHub Desktop**, not PowerShell or terminal commands.

When a human action is required:

- Give exact UI steps.
- Keep the task small and specific.
- Explain what success should look like.
- Do not assume Git terminology is familiar.
- Use command-line instructions only when GitHub Desktop cannot reasonably perform the task or when the user specifically wants terminal instructions.

Example:

> GitHub Desktop → Current Branch → New Branch → `release/v0.3.6` → Create Branch → Publish Branch.

is preferred over a multi-command Git sequence for routine work.

---

## 4. Standard Development Lifecycle

### Phase A — Establish the baseline

Before changing code:

1. Identify the current GitHub `main` commit.
2. Identify the current production version and commit when possible.
3. Read the relevant code, tests, docs, and recent changes.
4. Run the existing test suite on the untouched baseline.
5. Record any pre-existing failures before implementation.

If source access is impaired, recover the exact source through an approved mirror/recovery path. Do not approximate the repository from conversation history.

### Phase B — Define the change

For bounded changes, state the intended behavior, files likely to change, and test strategy before implementation.

For architectural changes, create a design/spec first and record:

- Purpose.
- Scope.
- Interfaces.
- Data flow.
- Failure behavior.
- Testing strategy.
- Backward-compatibility requirements.

The default preference is **small, understandable releases** rather than large bundled rewrites.

### Phase C — Work on a branch

Create a branch from the current `main` baseline.

Do not modify production or `main` as the development workspace.

### Phase D — Implement with tests

For behavior changes:

1. Write or modify a test that demonstrates the intended behavior.
2. Confirm it fails for the expected reason.
3. Implement the minimum production change needed.
4. Re-run the focused test.
5. Re-run the relevant regression tests.
6. Refactor only after the behavior is green.

For configuration/docs-only work, use equivalent validation appropriate to the artifact.

### Phase E — Local verification

Before handing the branch to CI, run the complete relevant verification set.

Typical Python project gate:

```text
pytest
compileall
secret scan
generated-file scan
benchmark/smoke test when performance-sensitive
```

Generated files such as `__pycache__`, `.pyc`, `.pyo`, and `.pytest_cache` must not be committed.

### Phase F — Pull request and CI

The branch is pushed and a pull request is opened against `main`.

CI must verify at minimum:

- Generated-file hygiene.
- Automated tests.
- Compilation/import sanity.
- Relevant benchmark or smoke tests.

**Do not merge red CI.** Investigate the actual failure, fix it on the branch, push again, and let CI rerun.

### Phase G — Merge and deploy

After CI passes:

1. Merge the pull request into `main`.
2. Let the production platform deploy from `main`.
3. Confirm production reports the expected version and Git commit.

Do not assume a successful merge means the correct production deployment is live.

### Phase H — Production acceptance

Run an explicit production acceptance test appropriate to the project.

At minimum verify:

- Health endpoint returns success.
- Version matches the intended release.
- Git commit/branch metadata matches the deployed `main` commit.
- Capabilities/schema/formula versions are correct.
- Known locked regression controls reproduce expected behavior.
- Persistent cache behavior is correct when applicable.
- Data provenance/security constraints remain intact.

For systems with deterministic historical behavior, compare complete outputs when practical—not only summary metrics.

### Phase I — Tag the release

Only after production acceptance passes:

- Create/publish the version tag, e.g. `v0.3.5`.
- Treat that tag as a known-good production release.

The release sequence is therefore:

```text
branch
  ↓
implementation + local tests
  ↓
pull request
  ↓
CI green
  ↓
merge to main
  ↓
production deploy
  ↓
production acceptance
  ↓
version tag
```

---

## 5. Failure Handling Standard

When something fails:

1. Reproduce it.
2. Read the exact error/status output.
3. Identify which component boundary failed.
4. Determine the root cause before changing code.
5. Make the smallest targeted fix.
6. Add or update a regression test when the failure represents a real defect.
7. Re-run the complete verification gate.

Do not stack speculative fixes.

A useful CI failure should usually become a permanent guard against recurrence.

---

## 6. Deployment and Runtime Identity

Production services should expose enough information to answer:

- What version is running?
- What Git commit is running?
- What branch/repository produced it?
- What deployment ID is active?
- What formula/schema/cache versions are active?

A preferred health/release response looks conceptually like:

```json
{
  "service": "example-service",
  "version": "0.3.5",
  "git_commit": "<40-char SHA>",
  "git_branch": "main",
  "git_repo": "owner/repo",
  "deployment_id": "<platform deployment id>",
  "build_time": "<optional timestamp>"
}
```

This metadata is part of reproducibility, not cosmetic information.

---

## 7. Connected-System Access Standard

### Normal source-control path

```text
Agent / developer
      ↓
GitHub branch
      ↓
Pull request + CI
      ↓
main
      ↓
Production deployment
```

### BKTSTR production control path

For the current BKTSTR project, the proven control path is:

```text
Agent
  ↓
Supabase SQL
  ↓
pg_net
  ↓
Railway BKTSTR API
  ↓
net._http_response
  ↓
Agent
```

This path is considered a valid, reproducible production-control interface.

Operational rules:

- Submit long HTTP requests asynchronously.
- Keep the returned request ID.
- Poll that exact ID rather than resubmitting.
- Run expensive 1-minute historical jobs sequentially when timeout pressure is likely.
- Prefer 180–300 second request timeouts for large backtests.

### GitHub recovery path

If an agent cannot reach GitHub directly, use the approved GitHub-through-Supabase recovery bridge rather than manually reconstructing source.

Current BKTSTR recovery sequence:

```text
bktstr_github_enqueue_commit(...)
        ↓
bktstr_github_enqueue_tree(snapshot_id)
        ↓
bktstr_github_enqueue_blobs(snapshot_id)
        ↓
bktstr_github_collect_blobs(snapshot_id)
```

Important properties:

- Commit/tree identity comes from GitHub.
- File contents are mirrored through the raw-content host to avoid exhausting anonymous GitHub REST quota.
- Generated Python cache artifacts are excluded.
- Every recovered file retains its Git blob SHA.
- Integrity should be verified by recomputing the Git blob SHA before trusting the snapshot.

This is a **recovery/control mechanism**, not a replacement for normal GitHub development.

---

## 8. Research-System Rules

For quantitative/research software:

1. Separate deterministic feature computation from strategy decisions.
2. Cache deterministic inputs/features when safe, but do not cache strategy decisions unless explicitly designed and validated.
3. Version formulas and cache formats explicitly.
4. Preserve strict point-in-time/look-ahead rules.
5. Track data provenance.
6. Keep lower-confidence or model-derived data clearly identified and independently switchable.
7. Do not silently mix clean and non-clean data.
8. Preserve a cache-off or equivalent control when caching could affect correctness.
9. Maintain locked historical regression anchors.
10. Validate strategy hypotheses across periods, symbols, and market regimes before promotion.

A performance optimization is acceptable only if cached and uncached execution produce equivalent research/trading results.

---

## 9. Performance Work

When optimizing performance:

1. Measure the current bottleneck first.
2. Separate data-fetch time, feature-computation time, strategy-evaluation time, and network/orchestration time.
3. Optimize the dominant bottleneck rather than adding speculative complexity.
4. Preserve deterministic output equality.
5. Benchmark cold and warm behavior separately when caches exist.
6. Do not present synthetic benchmark gains as production timing results.

If repeated HTTP orchestration becomes the bottleneck, prefer a batch/sweep interface that loads shared data once and evaluates many parameter combinations in-process.

---

## 10. Security and Repository Hygiene

Future agents must:

- Never commit API keys, service-role keys, passwords, tokens, or temporary proxy credentials.
- Scan release trees for secret-like patterns before packaging/pushing.
- Remove temporary public proxies or restore authentication after diagnostic use.
- Keep database staging/recovery tables protected by RLS or equivalent access controls.
- Avoid committing generated/cache files.
- Do not include `.env` or local caches in release packages.
- Run platform security/performance advisors after meaningful database schema changes when available.

Temporary infrastructure created for debugging must be explicitly cleaned up or locked down before the task is considered complete.

---

## 11. Documentation Standard

Every meaningful subsystem or architectural release should leave enough documentation that another competent agent can continue without reconstructing intent from chat history.

Documentation should capture:

- What the subsystem does.
- Why it exists.
- Inputs/outputs.
- Important formulas or semantic contracts.
- Versioning behavior.
- Data-flow diagrams when useful.
- Failure/recovery behavior.
- Test/validation commands.
- Deployment/production verification procedure.

Prefer durable repository documentation over relying on conversation memory.

For agent-facing operational docs, use explicit commands, expected outputs, and non-obvious semantics.

---

## 12. Communication Style for Future Agents

The preferred working style is collaborative but efficient.

Future agents should:

- Give concise progress updates during long technical work.
- Surface meaningful findings early.
- Explain architectural decisions in plain language.
- Avoid flooding the user with low-level logs unless they matter.
- Make a best effort instead of repeatedly asking for information that can be discovered with tools.
- Keep manual human steps minimal and explicit.
- When the user must act, explain exactly what to click or do and then resume technical verification afterward.
- Never claim background/asynchronous work will happen later unless an actual scheduled automation is being created.

The user should understand the important decisions without needing to become the system administrator.

---

## 13. Versioning Preference

For the current BKTSTR development line:

```text
0.3.0
0.3.1
...
0.3.9
0.4.0
```

Each version should have a clear purpose. Infrastructure-only releases should say so explicitly and preserve the prior research/trading semantics unless a model change is intentionally part of the release.

A version is considered **known-good** only after:

1. Local verification passes.
2. Pull-request CI passes.
3. `main` is deployed.
4. Production identity matches the intended commit.
5. Production acceptance/regression passes.
6. The successful commit is tagged.

---

## 14. Definition of Done

A development task is not done merely because code was written.

For a normal releasable change, “done” means:

- [ ] Exact baseline identified.
- [ ] Work performed on a branch, not `main`.
- [ ] Change documented/designed at the appropriate level.
- [ ] Focused tests written/updated.
- [ ] Full local verification passes.
- [ ] No generated files or secrets are tracked.
- [ ] Pull request created.
- [ ] CI passes.
- [ ] PR merged into `main`.
- [ ] Production deploy completes.
- [ ] Runtime version and Git commit match expectation.
- [ ] Production regression/acceptance passes.
- [ ] Security/provenance controls remain valid.
- [ ] Release is tagged only after production validation.
- [ ] Durable docs are updated so the next agent can continue cleanly.

---

## 15. Non-Negotiable Rules for Agents

**Do not:**

- Develop directly on `main`.
- Merge red CI.
- Declare success from an earlier test run.
- Guess what source code contains when exact source can be recovered.
- Ask the user to manually shuttle files/data if a reliable connected-tool path exists.
- Promote a research feature because one sample improved.
- Silently enable lower-confidence data.
- Mix infrastructure and strategy/model changes without documenting the reason.
- Leave temporary security exceptions active.
- Treat a successful deployment as proof of semantic correctness.

**Do:**

- Preserve reproducibility.
- Prefer explicit versions and provenance.
- Test before and after changes.
- Use CI as a gate.
- Verify production separately.
- Make the human workflow as simple as reasonably possible.
- Leave the repository easier for the next agent to understand than it was before.

---

## 16. Current Reference Implementation: BKTSTR v0.3.5

BKTSTR v0.3.5 is the first release completed through this standardized flow:

```text
release branch
    ↓
GitHub pull request
    ↓
BKTSTR CI
    ↓
repository-hygiene failure caught before merge
    ↓
branch fix + CI success
    ↓
merge to main
    ↓
Railway auto-deploy
    ↓
/health confirms version + exact Git commit
    ↓
/capabilities confirms formula/cache versions
    ↓
locked NVDA production regression repeated twice
    ↓
identical trades/results + valid cache/provenance
    ↓
release eligible for v0.3.5 tag
```

This sequence should be treated as the model for future BKTSTR releases and as the default template for other agent-assisted software projects unless a project has materially different deployment constraints.

---

**Recommended repository location:** `AGENT_DEVELOPMENT_STANDARD.md` at the repository root so future agents discover it immediately.
