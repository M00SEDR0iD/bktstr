# Tracked pytest artifact cleanup hotfix implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove generated `.pytest-*` artifacts from Git tracking, prevent future tracking of pytest/test-run output, and preserve runtime and trading behavior.

**Architecture:** Treat this as a Git hygiene hotfix with three layers: remove generated paths from the index, ignore the path families locally, and make CI reject recurrence. Do not rewrite published history, change application code, or purge local artifact data during the hotfix.

**Tech Stack:** Git, PowerShell, GitHub Actions, Python 3.12, pytest.

**Spec:** `CONTRIBUTING.md` and `docs/development/git-workflow.md`

## Global constraints

- `main` remains deployable and receives the change through an Issue, short-lived branch, pull request, CI, and squash merge.
- Never use `git reset --hard`, `git restore`, `git clean`, force-push, or history rewriting.
- Preserve unrelated working-tree changes. The current checkout already contains generated-artifact deletions and must not be normalized destructively.
- Remove only tracked paths whose first component matches `.pytest-*` or `.testtmp-*`.
- Do not change BKTSTR runtime, trading formulas, cache behavior, API behavior, release version, or production configuration.
- Keep local generated files recoverable until the cleanup commit and CI verification are complete.

## Baseline

The current `main` tree tracks 26,934 files below 16 `.pytest-*` roots. The current working tree reports 26,917 deletions under those roots. These names are directories, not Git branches. Do not delete the real `codex/*` or `release/*` branches as part of this work.

Run from a fresh isolated worktree based on current `main`:

~~~powershell
git status --short --branch
git rev-parse HEAD
$trackedArtifacts = @(git ls-files | Where-Object { $_ -match '^(\.pytest-[^\\/]+|\.testtmp-[^\\/]+)([\\/]|$)' })
"tracked_artifact_files=$($trackedArtifacts.Count)"
$trackedArtifacts | ForEach-Object { ($_ -split '[\\/]')[0] } | Sort-Object -Unique
~~~

Expected baseline: `tracked_artifact_files=26934`, with 16 `.pytest-*` roots. If the count or roots differ, stop and review the inventory before staging anything.

## File map

| File | Responsibility |
| --- | --- |
| `.gitignore` | Ignore generated pytest and temporary test-run directories. |
| `.github/workflows/ci.yml` | Reject tracked `.pytest-*` and `.testtmp-*` paths. |
| `tests/test_ops_assets.py` | Lock the CI hygiene command and its artifact guard. |

---

### Task 1: Isolate the hotfix

**Files:** None.

**Interfaces:**
- Consumes: current `main` commit and the existing working-tree state.
- Produces: an isolated hotfix worktree with a recorded artifact inventory.

- [ ] Create an incident Issue with these acceptance criteria: no generated pytest artifacts are tracked, CI rejects recurrence, no runtime files change, and Git history is not rewritten.

- [ ] Create a worktree from current `main` on `fix/<issue>-remove-tracked-test-artifacts`, replacing `<issue>` with the assigned Issue number. Do not stage from the dirty primary checkout.

- [ ] Record the baseline commands above and this scope check:

~~~powershell
git diff --name-status main...HEAD
git ls-tree -r --name-only HEAD -- .pytest-* .testtmp-*
~~~

Expected result: the branch starts without unrelated source changes, and the second command lists only generated test-run paths.

- [ ] Do not commit in this task. The task is complete when the isolated worktree is clean and the inventory is recorded in the pull request notes.

### Task 2: Add ignore rules

**Files:**
- Modify: `.gitignore`

**Interfaces:**
- Consumes: the artifact families from Task 1.
- Produces: local ignore rules for future test-run output.

- [ ] Append these exact lines to `.gitignore`, keeping the existing `.pytest_cache/` rule:

~~~gitignore
.pytest-*/
.testtmp-*/
~~~

- [ ] Verify both families are ignored:

~~~powershell
git check-ignore -v .pytest-hotfix-probe/sample.txt .testtmp-hotfix-probe/sample.txt
~~~

Expected result: both paths resolve to the new ignore rules. No probe files need to be created.

- [ ] Commit:

~~~powershell
git add .gitignore
git commit -m "chore: ignore generated pytest artifacts"
~~~

### Task 3: Remove generated paths from Git tracking

**Files:**
- Delete from the repository index: every tracked path whose first component matches `.pytest-*` or `.testtmp-*`.
- Preserve locally: any corresponding generated files that remain in the worktree.

**Interfaces:**
- Consumes: the explicit Task 1 inventory and Task 2 ignore rules.
- Produces: staged and committed deletion of generated artifacts only.

- [ ] Recompute exact roots:

~~~powershell
$artifactRoots = @(git ls-files | ForEach-Object { ($_ -split '[\\/]')[0] } | Where-Object { $_ -match '^(\.pytest-[^\\/]+|\.testtmp-[^\\/]+)$' } | Sort-Object -Unique)
"roots=$($artifactRoots.Count)"
$artifactRoots
~~~

Expected result: the same 16 `.pytest-*` roots and no application or documentation path.

- [ ] Remove only those roots from the index, leaving local files in place:

~~~powershell
foreach ($root in $artifactRoots) {
    git rm -r --cached -- "$root"
}
~~~

Do not replace this with a repository-wide wildcard, `git clean`, or a broad recursive deletion.

- [ ] Verify the staged scope:

~~~powershell
$staged = @(git diff --cached --name-only)
$staged | Where-Object { $_ -notmatch '^(\.pytest-[^\\/]+|\.testtmp-[^\\/]+)([\\/]|$)' }
~~~

Before Tasks 4 and 5, the only non-artifact staged file should be `.gitignore`.

- [ ] Commit:

~~~powershell
git commit -m "chore: remove tracked pytest artifacts"
~~~

Prior Git commits retain the old files. That is intentional and complies with the no-history-rewrite rule.

### Task 4: Make CI reject recurrence

**Files:**
- Modify: `.github/workflows/ci.yml:20-28`
- Test: `tests/test_ops_assets.py:162-235`

**Interfaces:**
- Consumes: the existing read-only `hygiene` job.
- Produces: a CI failure when generated pytest/test-run paths are tracked.

- [ ] Update the exact expected hygiene command in `tests/test_ops_assets.py` first. The expected command must be:

~~~text
          bad="$(git ls-files | grep -E '(^|/)(__pycache__|\.pytest_cache|\.pytest-[^/]*|\.testtmp-[^/]*)(/|$)|\.py[co]$' || true)"
~~~

Add a semantic-mutation case that replaces `\\.pytest-[^/]*` with `pytest-artifacts` and expects the CI contract assertion to reject the weakened guard.

- [ ] Run the focused tests and verify they fail because the workflow still has the old command:

~~~powershell
& '.\.venv\Scripts\python.exe' -m pytest -q tests/test_ops_assets.py::test_ci_workflow_runs_full_release_checks tests/test_ops_assets.py::test_ci_workflow_contract_rejects_semantic_mutations
~~~

- [ ] Replace only the `bad=` line in `.github/workflows/ci.yml` with:

~~~yaml
          bad="$(git ls-files | grep -E '(^|/)(__pycache__|\.pytest_cache|\.pytest-[^/]*|\.testtmp-[^/]*)(/|$)|\.py[co]$' || true)"
~~~

Keep the existing read-only permissions, runner, job name, and failure behavior unchanged.

- [ ] Run the focused contract tests:

~~~powershell
& '.\.venv\Scripts\python.exe' -m pytest -q tests/test_ops_assets.py::test_ci_workflow_runs_full_release_checks tests/test_ops_assets.py::test_ci_workflow_contract_rejects_semantic_mutations tests/test_ops_assets.py::test_ci_is_read_only_by_default
~~~

Expected result: PASS.

- [ ] Commit:

~~~powershell
git add .github/workflows/ci.yml tests/test_ops_assets.py
git commit -m "ci: reject tracked pytest run artifacts"
~~~

### Task 5: Verify from a clean checkout

**Files:** None beyond the files changed above.

**Interfaces:**
- Consumes: the cleanup commits and existing repository checks.
- Produces: evidence that artifacts are gone and application behavior is untouched.

- [ ] Confirm no generated path remains tracked:

~~~powershell
$remaining = @(git ls-files | Where-Object { $_ -match '^(\.pytest-[^\\/]+|\.testtmp-[^\\/]+)([\\/]|$)' })
if ($remaining.Count -ne 0) { $remaining; throw "Generated test artifacts remain tracked" }
~~~

- [ ] Confirm the diff is scoped:

~~~powershell
git diff --check main...HEAD
git diff --stat main...HEAD
git diff --name-only main...HEAD
~~~

Expected result: only `.gitignore`, `.github/workflows/ci.yml`, `tests/test_ops_assets.py`, and generated artifact paths appear. No `bktstr/`, `bktstr_cache/`, API, provider, strategy, or release-runtime file appears.

- [ ] Run focused checks using an ignored local test directory:

~~~powershell
& '.\.venv\Scripts\python.exe' -m pytest -q --basetemp '.testtmp-hotfix' tests/test_ops_assets.py tests/test_release_consistency.py
~~~

- [ ] Run the full checks:

~~~powershell
& '.\.venv\Scripts\python.exe' -m pytest -q --basetemp '.testtmp-hotfix-full'
& '.\.venv\Scripts\python.exe' -m compileall -q bktstr bktstr_cache integration scripts benchmarks tests
& '.\.venv\Scripts\python.exe' scripts/check_release_consistency.py
& '.\.venv\Scripts\python.exe' benchmarks/benchmark_cache.py
~~~

Expected result: all commands pass. If pytest hits the known Windows temp-directory permission error, rerun in a fresh isolated worktree with a writable `--basetemp`; do not restore generated files or weaken the guard.

- [ ] Create a disposable fresh checkout of the hotfix branch and run:

~~~powershell
git ls-files | Select-String -Pattern '(^|[\\/])(\.pytest-[^\\/]*|\.testtmp-[^\\/]*)([\\/]|$)'
~~~

Expected result: no matches.

- [ ] Open the pull request with the Issue reference, before/after tracked-file counts, verification output, explicit scope statement, and confirmation that published history was not rewritten. Squash-merge only after required CI passes, then delete the short-lived branch.

## Acceptance criteria

- No `.pytest-*` or `.testtmp-*` path is tracked at the hotfix tip.
- `.gitignore` ignores both path families.
- CI fails if either family is reintroduced.
- No runtime, strategy, provider, cache, API, or release behavior changes.
- Focused tests, full tests, compile checks, documentation consistency, and the cache benchmark pass, or any environment-only blocker is documented.
- Existing published history remains intact.

## Self-review

- Target selection is based on an explicit Git inventory, not a broad delete.
- Local generated files remain recoverable during the hotfix.
- The CI contract test changes before the workflow and therefore fails for the expected reason.
- The plan does not delete Git branches or rewrite history.



