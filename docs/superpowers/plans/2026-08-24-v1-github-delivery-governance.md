# BKTSTR v1 GitHub Delivery Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the repository files, automated checks, GitHub planning structure, and protection rules that make every BKTSTR milestone from v0.4.0 through v1.0.0 a traceable production release.

**Architecture:** Git stores durable product direction, workflow policy, release history, and executable governance checks. GitHub Issues, Milestones, and one Project store changing work state; pull requests and Actions provide review and verification evidence; Railway health plus a manually dispatched production workflow gate annotated tags and GitHub Releases.

**Tech Stack:** Git, GitHub Issues/Milestones/Projects/Actions/Rulesets/Releases, Markdown, YAML issue forms, Python 3.12, pytest 8.4.1, Docker, Railway

**Spec:** `docs/superpowers/specs/2026-08-24-v1-github-delivery-governance-design.md`

## Global Constraints

- Every roadmap milestone is an outcome-driven production release: v0.4.0, v0.5.0, v0.6.0, v0.7.0, v0.8.0, v0.9.0, and v1.0.0.
- `main` is the only permanent delivery branch and must remain deployable.
- Normal changes require a linked Issue, a short-lived branch, a pull request, passing CI, resolved conversations, and a squash merge.
- The repository has one human maintainer, so pull requests require zero external approvals.
- The canonical application version remains `bktstr/__init__.py` until a later packaging design changes it.
- GitHub Projects owns live status; repository documents own architecture, policy, release definitions, and durable history.
- Published `v*` tags are annotated, immutable, and never moved or reused.
- Production publication remains manually approved after Railway reports the exact SHA and production acceptance passes.
- The existing v0.3.5 tag remains at `add435d`; its later roadmap-only production commit is documented rather than rewriting the tag.
- Do not change trading formulas, entry or exit rules, fills, slippage, sizing, cache semantics, or frozen baseline values during this governance bootstrap.
- Do not commit secrets, `.venv`, caches, bytecode, generated manifests, or machine-local output.

---

## File Map

### Repository documents

- Create `CONTRIBUTING.md`: concise contributor entry point and daily Git flow.
- Create `CHANGELOG.md`: Unreleased section and durable release history.
- Create `docs/roadmap/v1-release-plan.md`: version ladder, coarse release state, outcomes, and exit criteria.
- Create `docs/development/git-workflow.md`: branches, commits, pull requests, emergency changes, and recovery.
- Create `docs/development/releases.md`: release preparation, Railway verification, tagging, GitHub Release publication, and rollback.
- Create `docs/archive/releases/v0.3.5.md`: immutable historical release note and post-release documentation exception.
- Modify `README.md`: link the roadmap, contributing guide, changelog, and release procedure.
- Delete `MERGE_CHECKLIST.md` only after its still-relevant content is preserved in the new release documentation and v0.3.5 archive.

### GitHub templates and automation

- Create `.github/ISSUE_TEMPLATE/config.yml`.
- Create `.github/ISSUE_TEMPLATE/feature.yml`.
- Create `.github/ISSUE_TEMPLATE/bug.yml`.
- Create `.github/ISSUE_TEMPLATE/documentation.yml`.
- Create `.github/ISSUE_TEMPLATE/release.yml`.
- Create `.github/PULL_REQUEST_TEMPLATE.md`.
- Create `.github/release.yml`.
- Modify `.github/workflows/ci.yml`: stable required checks for hygiene, tests, compilation, Docker, documentation, and cache benchmark.
- Create `.github/workflows/production-acceptance.yml`: manual production identity and frozen-baseline gate.

### Executable governance

- Create `scripts/check_release_consistency.py`: canonical-version and local-Markdown-link validation.
- Modify `scripts/production_acceptance.py`: expected-commit polling and JSON report output.
- Create `tests/test_governance_docs.py`: release plan and contributor-document contracts.
- Create `tests/test_github_templates.py`: issue, pull-request, release-note, and workflow contracts.
- Create `tests/test_release_consistency.py`: unit and repository tests for the consistency checker.
- Modify `tests/test_docs.py`: remove hard-coded duplicate version authority and point historical checks at the archive.
- Modify `tests/test_ops_assets.py`: assert stable CI and production-workflow contracts.
- Modify `tests/test_production_acceptance.py`: deployment identity, polling, and report-output tests.

## Spec Coverage Matrix

| Approved design section | Implemented by |
| --- | --- |
| Source-of-truth model | Tasks 2-5 and the contributor/release documents |
| Production version ladder | Task 2 release plan and Task 9 Milestones/trackers |
| Git workflow | Tasks 1, 3, 8, and 10 |
| Branch and tag protection | Task 10 |
| GitHub planning model | Task 9 |
| Repository documentation and templates | Tasks 2-4 |
| Updating plans without drift | Tasks 2, 3, and 9 Project status rules |
| Release lifecycle | Tasks 3, 7, 8, and 10 |
| Verification gates | Tasks 5-8 and 10 |
| Failure and rollback policy | Task 3 release documentation and Task 8 PR evidence |
| Governance bootstrap rollout | Tasks 1-10 in order |
| Bootstrap acceptance criteria | Task 10 and the final verification checklist |

---

### Task 1: Create the Governance Bootstrap Issue and Align the Branch

**Files:**
- No repository file changes
- GitHub Issue: `Bootstrap GitHub-native v1 delivery governance`
- Rename local branch: `codex/v1-delivery-governance` to `codex/<issue-number>-v1-delivery-governance`

**Interfaces:**
- Consumes: approved governance spec at `docs/superpowers/specs/2026-08-24-v1-github-delivery-governance-design.md`
- Produces: one durable Issue URL and a branch name linked to that Issue

- [ ] **Step 1: Open the bootstrap Issue in the signed-in GitHub browser**

Navigate to `https://github.com/M00SEDR0iD/bktstr/issues/new` and create the Issue with this title:

```text
Bootstrap GitHub-native v1 delivery governance
```

Use this body:

```markdown
## Outcome

Establish the repository documentation, templates, checks, GitHub Project, release milestones, and protection rules defined by the approved v1 delivery-governance design.

## Non-goals

- No trading-formula or backtest behavior changes
- No v0.4.0 release publication
- No rewrite of the existing v0.3.5 tag or Git history

## Acceptance criteria

- Governance documents and templates are versioned in the repository.
- CI exposes stable required checks, including a production Docker build.
- Production acceptance can verify and record an expected deployment SHA.
- The BKTSTR v1 Roadmap Project and v0.4.0-v1.0.0 Milestones exist.
- `main` requires pull requests and passing CI with zero external approvals.
- Published `v*` tags are protected from update and deletion.

## Verification

- Full local pytest suite
- Pull-request CI
- Repository and tag ruleset inspection
- Project, Milestone, label, and release-tracker inspection

Design: `docs/superpowers/specs/2026-08-24-v1-github-delivery-governance-design.md`
```

- [ ] **Step 2: Record the Issue number and rename the local branch**

Run, replacing `42` with the created Issue number:

```powershell
git branch -m codex/42-v1-delivery-governance
git status --short --branch
```

Expected: the branch name contains the Issue number and the working tree contains only the already committed design plus this plan when it is committed.

---

### Task 2: Add the v1 Release Plan and Changelog

**Files:**
- Create: `CHANGELOG.md`
- Create: `docs/roadmap/v1-release-plan.md`
- Create: `tests/test_governance_docs.py`

**Interfaces:**
- Consumes: version ladder and exit criteria from the approved governance spec and standalone web-app roadmap
- Produces: `RELEASE_ROWS` test contract and durable version/release documents used by later GitHub Milestones

- [ ] **Step 1: Write failing release-document tests**

Create `tests/test_governance_docs.py` with:

```python
from pathlib import Path


ROOT = Path(__file__).parents[1]
RELEASE_ROWS = {
    "v0.4.0": "Baseline and documentation repair",
    "v0.5.0": "Strategy-neutral core",
    "v0.6.0": "FastAPI application foundation",
    "v0.7.0": "Persistence and single-owner authentication",
    "v0.8.0": "Durable execution jobs",
    "v0.9.0": "React research workspace",
    "v1.0.0": "Railway production cutover",
}


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_release_plan_publishes_complete_v1_ladder():
    text = _read("docs/roadmap/v1-release-plan.md")
    for version, milestone in RELEASE_ROWS.items():
        assert version in text
        assert milestone in text
    assert "outcome-driven" in text.lower()
    assert "GitHub Project owns live status" in text


def test_changelog_has_unreleased_and_immutable_v035_history():
    text = _read("CHANGELOG.md")
    assert "## [Unreleased]" in text
    assert "## [0.3.5] - 2026-08-24" in text
    assert "[Unreleased]: https://github.com/M00SEDR0iD/bktstr/compare/v0.3.5...HEAD" in text
    assert "[0.3.5]: https://github.com/M00SEDR0iD/bktstr/releases/tag/v0.3.5" in text
```

- [ ] **Step 2: Run the release-document tests and verify the expected failure**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_governance_docs.py -v
```

Expected: FAIL because `CHANGELOG.md` and `docs/roadmap/v1-release-plan.md` do not exist.

- [ ] **Step 3: Create the changelog**

Create `CHANGELOG.md` using Keep-a-Changelog categories with this initial content:

```markdown
# Changelog

All notable BKTSTR changes are recorded here. BKTSTR uses Semantic Versioning; releases before v1.0.0 may change interfaces while the stable contract is being established.

## [Unreleased]

### Added

- GitHub-native delivery governance for the roadmap to v1.0.0.

## [0.3.5] - 2026-08-24

### Added

- Runtime build and Railway deployment identity in health and capability responses.
- Deterministic production acceptance for the frozen NVDA baseline.
- GitHub Actions checks for tests, compilation, generated-file hygiene, and cache behavior.
- Standalone web-application roadmap as a post-release documentation-only production update.

### Preserved

- v0.3.3 trading formulas and v0.3.4 deterministic derived-cache semantics.

[Unreleased]: https://github.com/M00SEDR0iD/bktstr/compare/v0.3.5...HEAD
[0.3.5]: https://github.com/M00SEDR0iD/bktstr/releases/tag/v0.3.5
```

- [ ] **Step 4: Create the v1 release plan**

Create `docs/roadmap/v1-release-plan.md` with these sections and exact release states:

```markdown
# BKTSTR v1 Release Plan

This outcome-driven plan maps the standalone web-application roadmap to production versions. GitHub Project owns live status; this document owns stable outcomes, order, and exit criteria.

| Version | State | Milestone | Production outcome |
| --- | --- | --- | --- |
| v0.4.0 | Active planning | Baseline and documentation repair | Trustworthy docs, executable examples, professional delivery governance, and a frozen v0.3.5 baseline |
| v0.5.0 | Planned | Strategy-neutral core | Stable domain contracts with equal normalized trading output |
| v0.6.0 | Planned | FastAPI application foundation | Typed API, OpenAPI, compatibility routing, structured errors, and health contracts |
| v0.7.0 | Planned | Persistence and single-owner authentication | Private owner access and durable research records |
| v0.8.0 | Planned | Durable execution jobs | Worker jobs with idempotency, retries, cancellation, heartbeat, and recovery |
| v0.9.0 | Planned | React research workspace | Complete browser research workflow |
| v1.0.0 | Planned | Railway production cutover | Stable private web application as the normal BKTSTR interface |

## Release rules

- A release ships when its outcome and exit criteria pass, not on a fixed date.
- Minor versions represent roadmap capability milestones; patch versions contain compatible production fixes.
- Incomplete merged work must remain inactive, backward-compatible, or production-safe.
- Every release uses a final version-preparation pull request, exact-SHA Railway verification, production acceptance, an annotated tag, and a GitHub Release.
- Published tags are never moved or reused.

## Exit criteria

### v0.4.0

Current tests and production acceptance pass; published examples execute in CI; documentation has one entry point; the v0.3.5 baseline is versioned and reproducible; GitHub governance is active.

### v0.5.0

The migrated baseline produces byte-equivalent normalized trades and equal summaries with caches enabled and disabled.

### v0.6.0

API contract, legacy compatibility, structured-error, and production baseline tests pass through FastAPI.

### v0.7.0

Authentication, authorization, migration, immutability, and backup/restore checks pass from empty and previous database states.

### v0.8.0

Runs survive web restarts; worker interruption cannot duplicate results; cancellation, retry, heartbeat, and recovery match the state machine.

### v0.9.0

Browser tests cover login, strategy versioning, submission, completion, failure, rerun, notes, tags, comparison, and logout.

### v1.0.0

Production is owner-only; deployed identity matches the released commit; frozen baseline and durable saved-state checks pass across web and worker redeployments.
```

- [ ] **Step 5: Run the release-document tests**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_governance_docs.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit the release plan and changelog**

```powershell
git add CHANGELOG.md docs/roadmap/v1-release-plan.md tests/test_governance_docs.py
git commit -m "docs(roadmap): add v1 release plan"
```

---

### Task 3: Add Contributor, Git, Release, and v0.3.5 Archive Documentation

**Files:**
- Create: `CONTRIBUTING.md`
- Create: `docs/development/git-workflow.md`
- Create: `docs/development/releases.md`
- Create: `docs/archive/releases/v0.3.5.md`
- Modify: `README.md`
- Modify: `tests/test_governance_docs.py`
- Modify: `tests/test_docs.py`
- Delete: `MERGE_CHECKLIST.md`

**Interfaces:**
- Consumes: `RELEASE_ROWS`, current v0.3.5 checklist, approved workflow policy
- Produces: human entry points and the durable release procedure used by all later milestones

- [ ] **Step 1: Add failing contributor-document tests**

Append to `tests/test_governance_docs.py`:

```python
def test_contributor_entry_point_links_detailed_workflows():
    text = _read("CONTRIBUTING.md")
    for required in [
        "Closes #",
        "short-lived branch",
        "squash",
        "docs/development/git-workflow.md",
        "docs/development/releases.md",
    ]:
        assert required in text


def test_git_workflow_documents_normal_and_emergency_paths():
    text = _read("docs/development/git-workflow.md")
    for required in [
        "main",
        "feat/<issue>-<slug>",
        "zero external approvals",
        "force push",
        "Emergency changes",
        "incident Issue",
    ]:
        assert required in text


def test_release_workflow_gates_tags_on_production_acceptance():
    text = _read("docs/development/releases.md")
    for required in [
        "release: prepare",
        "annotated tag",
        "expected Git SHA",
        "production-acceptance.yml",
        "Rollback",
    ]:
        assert required in text


def test_v035_archive_records_tag_and_post_release_doc_commit():
    text = _read("docs/archive/releases/v0.3.5.md")
    assert "add435d" in text
    assert "219dc71" in text
    assert "roadmap-only" in text
    assert "tag was not moved" in text
```

Change `test_readme_and_status_describe_v035_release_workflow` in `tests/test_docs.py` so it reads `docs/archive/releases/v0.3.5.md` instead of `MERGE_CHECKLIST.md`, and assert the archive contains `production_acceptance.py` and `git ls-files`.

- [ ] **Step 2: Run the focused documentation tests and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_governance_docs.py tests/test_docs.py -v
```

Expected: FAIL because the new contributor, development, and archive documents do not exist.

- [ ] **Step 3: Create the contributor entry point**

Create `CONTRIBUTING.md` with:

````markdown
# Contributing to BKTSTR

BKTSTR uses GitHub Issues, short-lived branches, pull requests, squash merges, and production-gated releases. `main` must remain deployable.

## Normal workflow

1. Select an Issue with acceptance criteria.
2. Branch from current `main` using `feat/<issue>-<slug>`, `fix/<issue>-<slug>`, `docs/<issue>-<slug>`, or `chore/<issue>-<slug>`.
3. Make focused changes and tests.
4. Open a pull request containing `Closes #<issue>`.
5. Require all CI checks and conversations to pass.
6. Squash-merge with a clear Conventional Commit-style title.
7. Delete the merged branch.

## Before opening a pull request

```powershell
& '.\.venv\Scripts\python.exe' -m pytest
& '.\.venv\Scripts\python.exe' scripts/check_release_consistency.py
& '.\.venv\Scripts\python.exe' benchmarks/benchmark_cache.py
git status --short
```

Never commit credentials, `.venv`, caches, bytecode, generated manifests, or machine-local output.

Read [the detailed Git workflow](docs/development/git-workflow.md), [the release procedure](docs/development/releases.md), and [the v1 release plan](docs/roadmap/v1-release-plan.md) before changing delivery behavior.
````

- [ ] **Step 4: Create the detailed Git workflow document**

Create `docs/development/git-workflow.md` with sections for principles, Issue readiness, branch naming, commit titles, pull-request contents, squash merging, branch cleanup, protected `main`, prohibited force pushes, and emergency changes. State these exact policies:

- `main` is the only permanent delivery branch.
- Every normal PR links an Issue and requires zero external approvals for the solo maintainer.
- Required CI and conversation resolution cannot be bypassed routinely.
- Force pushes to `main` and moving published tags are prohibited.
- Emergency changes require an incident Issue, the smallest safe change, production verification, a follow-up PR, and restoration of any temporarily changed rules.
- Existing Git history is never rewritten merely to make it look cleaner.

- [ ] **Step 5: Create the detailed release document**

Create `docs/development/releases.md` with these ordered sections:

1. **Release readiness:** milestone Issues closed or explicitly deferred; changelog complete; exit criteria met.
2. **Release-preparation PR:** title `release: prepare vX.Y.Z`; only version, changelog, release-plan state, and version-sensitive checks change.
3. **Merge and deploy:** squash-merge after required checks; record merge SHA; wait for Railway health to report the expected Git SHA and version.
4. **Manual production gate:** dispatch `.github/workflows/production-acceptance.yml` with version, SHA, and production URL; retain the JSON artifact.
5. **Publish:** create `git tag -a vX.Y.Z -m "BKTSTR vX.Y.Z"`, push the tag, generate and review GitHub release notes, record verification and limitations, close Milestone and tracker.
6. **Patch releases:** repeat the same process with an incremented patch number.
7. **Rollback:** do not tag a failed candidate; fix or revert by PR; redeploy the last known-good tag when necessary; record the incident and recovery.

- [ ] **Step 6: Archive the v0.3.5 checklist and historical exception**

Create `docs/archive/releases/v0.3.5.md` containing:

- tag `v0.3.5` and tagged commit `add435d`;
- frozen acceptance values: 7 trades, 6 wins, 1 loss, `$42.604714` total P&L, `$6.086388` expected P&L per trade;
- the retained `git ls-files` hygiene command;
- the production acceptance command;
- the fact that roadmap-only commit `219dc71` deployed after the tag;
- the explicit statement that the tag was not moved because published release identities are immutable;
- a link to the standalone web-app roadmap.

Delete `MERGE_CHECKLIST.md` after the archive contains every still-relevant check.

- [ ] **Step 7: Add repository navigation to the README**

Add a `## Project and contribution` section after Local development linking to:

- `CONTRIBUTING.md`
- `CHANGELOG.md`
- `docs/roadmap/standalone-web-app.md`
- `docs/roadmap/v1-release-plan.md`
- `docs/development/releases.md`

Keep the current-release header and production endpoint unchanged.

- [ ] **Step 8: Run focused and full tests**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_governance_docs.py tests/test_docs.py -v
& '.\.venv\Scripts\python.exe' -m pytest
```

Expected: all 63 existing tests plus the new governance tests pass; only the four existing NumPy timedelta deprecation warnings remain.

- [ ] **Step 9: Commit the contributor and release documentation**

```powershell
git add CONTRIBUTING.md README.md docs/development docs/archive/releases/v0.3.5.md tests/test_governance_docs.py tests/test_docs.py MERGE_CHECKLIST.md
git commit -m "docs: establish git and release workflow"
```

---

### Task 4: Add GitHub Issue, Pull-Request, and Release Templates

**Files:**
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/ISSUE_TEMPLATE/feature.yml`
- Create: `.github/ISSUE_TEMPLATE/bug.yml`
- Create: `.github/ISSUE_TEMPLATE/documentation.yml`
- Create: `.github/ISSUE_TEMPLATE/release.yml`
- Create: `.github/PULL_REQUEST_TEMPLATE.md`
- Create: `.github/release.yml`
- Create: `tests/test_github_templates.py`

**Interfaces:**
- Consumes: label names and PR evidence fields defined by the spec
- Produces: issue-form labels, PR checklist text, and release-note categories used by GitHub configuration

- [ ] **Step 1: Write failing template-contract tests**

Create `tests/test_github_templates.py` with:

```python
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_issue_forms_require_outcome_acceptance_and_verification():
    forms = {
        "feature.yml": "type:feature",
        "bug.yml": "type:bug",
        "documentation.yml": "type:docs",
        "release.yml": "type:maintenance",
    }
    for filename, label in forms.items():
        text = _read(f".github/ISSUE_TEMPLATE/{filename}")
        assert label in text
        assert "acceptance" in text.lower()
        assert "verification" in text.lower()
    assert "non_goals" in _read(".github/ISSUE_TEMPLATE/feature.yml")


def test_pull_request_template_requires_release_evidence():
    text = _read(".github/PULL_REQUEST_TEMPLATE.md")
    for required in [
        "Closes #",
        "## Summary",
        "## Verification",
        "Trading semantics",
        "Documentation and changelog",
        "Deployment and rollback",
    ]:
        assert required in text


def test_generated_release_notes_use_governance_labels():
    text = _read(".github/release.yml")
    for required in [
        "type:feature",
        "type:bug",
        "type:docs",
        "type:security",
        "type:maintenance",
        'labels: ["*"]',
    ]:
        assert required in text
```

- [ ] **Step 2: Run the template tests and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_github_templates.py -v
```

Expected: FAIL because the templates do not exist.

- [ ] **Step 3: Create the Issue-form configuration and four forms**

Create `.github/ISSUE_TEMPLATE/config.yml`:

```yaml
blank_issues_enabled: false
contact_links:
  - name: Contribution workflow
    url: https://github.com/M00SEDR0iD/bktstr/blob/main/CONTRIBUTING.md
    about: Read the Issue, branch, pull-request, and verification workflow.
```

Create `.github/ISSUE_TEMPLATE/feature.yml`:

```yaml
name: Feature
description: Propose a new user or developer capability.
title: "[Feature] "
labels: ["type:feature"]
body:
  - type: markdown
    attributes:
      value: Describe one independently testable outcome.
  - type: textarea
    id: outcome
    attributes:
      label: Outcome
      description: What becomes possible when this is complete?
    validations:
      required: true
  - type: textarea
    id: non_goals
    attributes:
      label: Non-goals
      description: What adjacent work is explicitly excluded?
    validations:
      required: true
  - type: textarea
    id: acceptance
    attributes:
      label: Acceptance criteria
      placeholder: "- [ ] Observable criterion"
    validations:
      required: true
  - type: textarea
    id: verification
    attributes:
      label: Verification
      description: Name the automated and manual evidence required.
    validations:
      required: true
  - type: dropdown
    id: impact
    attributes:
      label: Primary impact
      options:
        - Trading semantics
        - Market data
        - API or schema
        - Deployment or operations
        - None
    validations:
      required: true
```

Create `.github/ISSUE_TEMPLATE/bug.yml`:

```yaml
name: Bug
description: Report incorrect or regressed behavior.
title: "[Bug] "
labels: ["type:bug"]
body:
  - type: textarea
    id: observed
    attributes:
      label: Observed behavior
      description: Include exact inputs, errors, and relevant environment details.
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: Expected behavior
    validations:
      required: true
  - type: textarea
    id: reproduction
    attributes:
      label: Reproduction
      description: Provide the shortest repeatable sequence.
    validations:
      required: true
  - type: textarea
    id: acceptance
    attributes:
      label: Acceptance criteria
      placeholder: "- [ ] Regression is covered by an automated test"
    validations:
      required: true
  - type: textarea
    id: verification
    attributes:
      label: Verification
      description: State how the fix and surrounding behavior will be checked.
    validations:
      required: true
  - type: dropdown
    id: impact
    attributes:
      label: Primary impact
      options:
        - Trading semantics
        - Market data
        - API or schema
        - Deployment or operations
        - None
    validations:
      required: true
```

Create `.github/ISSUE_TEMPLATE/documentation.yml`:

```yaml
name: Documentation
description: Correct or improve durable project documentation.
title: "[Docs] "
labels: ["type:docs"]
body:
  - type: textarea
    id: outcome
    attributes:
      label: Reader outcome
      description: What will a reader understand or complete afterward?
    validations:
      required: true
  - type: textarea
    id: non_goals
    attributes:
      label: Non-goals
      description: What documentation or product behavior is not changing?
    validations:
      required: true
  - type: textarea
    id: acceptance
    attributes:
      label: Acceptance criteria
      placeholder: "- [ ] Published commands and links are verified"
    validations:
      required: true
  - type: textarea
    id: verification
    attributes:
      label: Verification
      description: Name executable examples, link checks, and reviews.
    validations:
      required: true
  - type: dropdown
    id: impact
    attributes:
      label: Primary impact
      options:
        - Trading semantics
        - Market data
        - API or schema
        - Deployment or operations
        - None
    validations:
      required: true
```

Create `.github/ISSUE_TEMPLATE/release.yml`:

```yaml
name: Release tracker
description: Track one production version from scope through publication.
title: "[Release] v"
labels: ["type:maintenance"]
body:
  - type: input
    id: version
    attributes:
      label: Version
      placeholder: v0.4.0
    validations:
      required: true
  - type: textarea
    id: outcome
    attributes:
      label: Production outcome
    validations:
      required: true
  - type: textarea
    id: acceptance
    attributes:
      label: Exit and acceptance criteria
      placeholder: "- [ ] Milestone exit criterion"
    validations:
      required: true
  - type: textarea
    id: verification
    attributes:
      label: Production verification
      description: Link CI, Railway health, production acceptance, and the retained report.
    validations:
      required: true
  - type: textarea
    id: limitations
    attributes:
      label: Known limitations
    validations:
      required: true
  - type: textarea
    id: rollback
    attributes:
      label: Rollback plan
    validations:
      required: true
  - type: dropdown
    id: impact
    attributes:
      label: Primary impact
      options:
        - Trading semantics
        - Market data
        - API or schema
        - Deployment or operations
        - None
    validations:
      required: true
```

- [ ] **Step 4: Create the pull-request template**

Create `.github/PULL_REQUEST_TEMPLATE.md` with:

````markdown
## Summary

Describe the outcome and why this change is needed.

Closes #

## Verification

- [ ] Focused tests pass
- [ ] Full test suite passes
- [ ] Release-consistency check passes
- [ ] Relevant manual or production checks are recorded below

Commands and results:

```text
Record exact commands and concise results here.
```

## Impact

- [ ] Trading semantics
- [ ] Market data or cache contract
- [ ] API or schema
- [ ] Documentation and changelog
- [ ] Deployment or operations
- [ ] No impact in these areas

Explain every checked impact, including version changes where required.

## Deployment and rollback

State how this reaches production and the exact safe rollback. Write `No deployment change` only when the change cannot affect deployment.
````

- [ ] **Step 5: Create generated-release-note categories**

Create `.github/release.yml`:

```yaml
changelog:
  categories:
    - title: Features
      labels: ["type:feature"]
    - title: Fixes
      labels: ["type:bug"]
    - title: Security
      labels: ["type:security"]
    - title: Documentation
      labels: ["type:docs"]
    - title: Maintenance
      labels: ["type:maintenance"]
    - title: Dependency Updates
      labels: ["dependencies"]
    - title: Other Changes
      labels: ["*"]
      exclude:
        labels: ["dependencies"]
```

- [ ] **Step 6: Run template and full tests**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_github_templates.py -v
& '.\.venv\Scripts\python.exe' -m pytest
```

Expected: PASS.

- [ ] **Step 7: Commit the GitHub templates**

```powershell
git add .github/ISSUE_TEMPLATE .github/PULL_REQUEST_TEMPLATE.md .github/release.yml tests/test_github_templates.py
git commit -m "chore(github): add planning and release templates"
```

---

### Task 5: Add Executable Version and Markdown-Link Consistency Checks

**Files:**
- Create: `scripts/check_release_consistency.py`
- Create: `tests/test_release_consistency.py`
- Modify: `tests/test_docs.py`

**Interfaces:**
- Produces: `extract_python_version(path: Path) -> str`, `find_broken_local_links(root: Path) -> list[str]`, `check_repository(root: Path) -> list[str]`, and CLI exit status 0/1
- Consumes later: `.github/workflows/ci.yml` Documentation job

- [ ] **Step 1: Write failing unit and repository tests**

Create `tests/test_release_consistency.py`:

```python
from pathlib import Path
import subprocess
import sys

from scripts import check_release_consistency as module


ROOT = Path(__file__).parents[1]


def test_extract_python_version_reads_literal_assignment(tmp_path):
    path = tmp_path / "version.py"
    path.write_text('__version__ = "0.4.0"\n', encoding="utf-8")
    assert module.extract_python_version(path) == "0.4.0"


def test_broken_link_check_ignores_urls_and_reports_missing_files(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "present.md").write_text("# Present\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "[present](docs/present.md) [missing](docs/missing.md) [web](https://example.com)\n",
        encoding="utf-8",
    )
    errors = module.find_broken_local_links(tmp_path)
    assert len(errors) == 1
    assert "docs/missing.md" in errors[0]


def test_repository_release_identity_and_links_are_consistent():
    assert module.check_repository(ROOT) == []


def test_consistency_cli_passes_repository():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_release_consistency.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Release consistency checks passed." in completed.stdout
```

- [ ] **Step 2: Run the consistency tests and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_release_consistency.py -v
```

Expected: FAIL because `scripts/check_release_consistency.py` does not exist.

- [ ] **Step 3: Implement the consistency checker**

Implement `scripts/check_release_consistency.py` using only the Python standard library:

- parse `bktstr/__init__.py` with `ast` and accept exactly one literal `__version__` assignment;
- extract the README release from `**Current release: vX.Y.Z**`;
- read `docs/gui/sentiment-data-contract.json` and its `version` field;
- parse the default `expected_version` value from `run_acceptance` in `scripts/production_acceptance.py` with `ast`;
- scan `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, and `docs/**/*.md` for Markdown links;
- ignore `http:`, `https:`, `mailto:`, `app:`, and fragment-only targets;
- URL-decode local targets, remove query/fragment suffixes, resolve them relative to the containing document, and report missing files;
- return every mismatch or broken link from `check_repository` rather than stopping at the first;
- print one `ERROR: <message>` line per problem and return exit code 1; print `Release consistency checks passed.` and return 0 otherwise.

The version comparison must enforce:

```python
runtime_version == readme_version == gui_contract_version == acceptance_default_version
```

Use this concrete structure:

```python
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote


ROOT = Path(__file__).parents[1]
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\((<[^>]+>|[^)\s]+)")
README_VERSION_PATTERN = re.compile(r"\*\*Current release: v([^*]+)\*\*")
IGNORED_PREFIXES = ("http:", "https:", "mailto:", "app:", "#")


def extract_python_version(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__version__":
                    values.append(ast.literal_eval(node.value))
    if len(values) != 1 or not isinstance(values[0], str):
        raise ValueError(f"expected one literal __version__ assignment in {path}")
    return values[0]


def extract_function_default(path: Path, function_name: str, parameter_name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            positional = [*node.args.posonlyargs, *node.args.args]
            defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
            for argument, default in zip(positional, defaults, strict=True):
                if argument.arg == parameter_name and default is not None:
                    value = ast.literal_eval(default)
                    if isinstance(value, str):
                        return value
    raise ValueError(f"missing literal default for {function_name}.{parameter_name} in {path}")


def markdown_documents(root: Path) -> list[Path]:
    documents = [root / "README.md", root / "CONTRIBUTING.md", root / "CHANGELOG.md"]
    documents.extend(sorted((root / "docs").rglob("*.md")))
    return [path for path in documents if path.exists()]


def find_broken_local_links(root: Path) -> list[str]:
    errors = []
    for document in markdown_documents(root):
        for match in LINK_PATTERN.finditer(document.read_text(encoding="utf-8")):
            target = match.group(1).strip("<>")
            if target.startswith(IGNORED_PREFIXES):
                continue
            path_text = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not path_text:
                continue
            destination = (document.parent / path_text).resolve()
            if not destination.exists():
                relative_document = document.relative_to(root).as_posix()
                errors.append(f"{relative_document}: missing local link {target}")
    return errors


def check_repository(root: Path) -> list[str]:
    errors = []
    runtime_version = extract_python_version(root / "bktstr" / "__init__.py")
    readme = (root / "README.md").read_text(encoding="utf-8")
    match = README_VERSION_PATTERN.search(readme)
    readme_version = match.group(1) if match else None
    gui_version = json.loads(
        (root / "docs" / "gui" / "sentiment-data-contract.json").read_text(encoding="utf-8")
    )["version"]
    acceptance_version = extract_function_default(
        root / "scripts" / "production_acceptance.py",
        "run_acceptance",
        "expected_version",
    )
    observed = {
        "README": readme_version,
        "GUI contract": gui_version,
        "production acceptance": acceptance_version,
    }
    for source, version in observed.items():
        if version != runtime_version:
            errors.append(f"{source} version {version!r} does not match runtime {runtime_version!r}")
    errors.extend(find_broken_local_links(root))
    return errors


def main() -> int:
    errors = check_repository(ROOT)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Release consistency checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Make the existing docs test use the runtime version dynamically**

Modify `tests/test_docs.py` so `test_gui_contract_matches_runtime_version_and_outputs` imports `bktstr.__version__` and asserts:

```python
assert c["version"] == CAPABILITIES["version"] == __version__
```

Replace the hard-coded README assertion with:

```python
assert f"Current release: v{__version__}" in readme
```

- [ ] **Step 5: Run focused tests and the checker**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_release_consistency.py tests/test_docs.py -v
& '.\.venv\Scripts\python.exe' scripts/check_release_consistency.py
```

Expected: all tests pass and the script prints `Release consistency checks passed.`

- [ ] **Step 6: Commit executable documentation governance**

```powershell
git add scripts/check_release_consistency.py tests/test_release_consistency.py tests/test_docs.py
git commit -m "test(docs): enforce release consistency"
```

---

### Task 6: Split CI into Stable Required Checks

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/test_ops_assets.py`

**Interfaces:**
- Consumes: `scripts/check_release_consistency.py`
- Produces required check names: `Hygiene`, `Tests`, `Compile`, `Production image`, `Documentation`, `Cache benchmark`

- [ ] **Step 1: Replace the monolithic-workflow assertion with failing named-job assertions**

Update `test_ci_workflow_runs_full_release_checks` in `tests/test_ops_assets.py` to require:

```python
for required in [
    "hygiene:",
    "name: Hygiene",
    "tests:",
    "name: Tests",
    "compile:",
    "name: Compile",
    "production_image:",
    "name: Production image",
    "documentation:",
    "name: Documentation",
    "cache_benchmark:",
    "name: Cache benchmark",
    "python -m pytest -q",
    "python -m compileall -q bktstr bktstr_cache integration scripts benchmarks tests",
    "docker build --tag bktstr:${{ github.sha }} .",
    "python scripts/check_release_consistency.py",
    "python benchmarks/benchmark_cache.py",
]:
    assert required in text
```

Retain assertions for pull requests, pushes to main, Python 3.12, pinned requirements, read-only permissions, and tracked-file hygiene.

- [ ] **Step 2: Run the CI contract test and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_ops_assets.py::test_ci_workflow_runs_full_release_checks -v
```

Expected: FAIL because CI still has one `test` job.

- [ ] **Step 3: Refactor `.github/workflows/ci.yml`**

Keep the existing triggers and `contents: read`. Define six independent Ubuntu jobs with the exact names above:

- `hygiene`: checkout and reject tracked cache/bytecode artifacts with the existing `git ls-files` expression;
- `tests`: checkout, set up Python 3.12 with pip caching, install `requirements-dev.txt`, run `python -m pytest -q`;
- `compile`: checkout, set up Python 3.12, run the existing compileall command;
- `production_image`: checkout and run `docker build --tag bktstr:${{ github.sha }} .`;
- `documentation`: checkout, set up Python 3.12, install `requirements-dev.txt`, run `python scripts/check_release_consistency.py`;
- `cache_benchmark`: checkout, set up Python 3.12 with pip caching, install `requirements-dev.txt`, run `python benchmarks/benchmark_cache.py`.

Do not add write permissions or repository secrets.

Use this complete workflow:

```yaml
name: BKTSTR CI

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  hygiene:
    name: Hygiene
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v7
      - name: Reject tracked generated files
        shell: bash
        run: |
          bad="$(git ls-files | grep -E '(^|/)(__pycache__|\.pytest_cache)(/|$)|\.py[co]$' || true)"
          if [ -n "$bad" ]; then
            echo "Generated files are tracked and must be removed:"
            echo "$bad"
            exit 1
          fi

  tests:
    name: Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: '3.12'
          cache: pip
          cache-dependency-path: requirements-dev.txt
      - run: python -m pip install -r requirements-dev.txt
      - run: python -m pytest -q

  compile:
    name: Compile
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: '3.12'
      - run: python -m compileall -q bktstr bktstr_cache integration scripts benchmarks tests

  production_image:
    name: Production image
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - run: docker build --tag bktstr:${{ github.sha }} .

  documentation:
    name: Documentation
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: '3.12'
          cache: pip
          cache-dependency-path: requirements-dev.txt
      - run: python -m pip install -r requirements-dev.txt
      - run: python scripts/check_release_consistency.py

  cache_benchmark:
    name: Cache benchmark
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: '3.12'
          cache: pip
          cache-dependency-path: requirements-dev.txt
      - run: python -m pip install -r requirements-dev.txt
      - run: python benchmarks/benchmark_cache.py
```

- [ ] **Step 4: Run workflow-contract and full tests**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_ops_assets.py -v
& '.\.venv\Scripts\python.exe' -m pytest
```

Expected: PASS.

- [ ] **Step 5: Commit the stable CI checks**

```powershell
git add .github/workflows/ci.yml tests/test_ops_assets.py
git commit -m "chore(ci): split required release checks"
```

---

### Task 7: Add Expected-SHA Production Acceptance and Manual Workflow

**Files:**
- Modify: `scripts/production_acceptance.py`
- Modify: `tests/test_production_acceptance.py`
- Create: `.github/workflows/production-acceptance.yml`
- Modify: `tests/test_ops_assets.py`

**Interfaces:**
- Extends: `run_acceptance(base_url, expected_version="0.3.5", *, expected_commit=None, deployment_attempts=1, deployment_poll_seconds=10.0, sleeper=time.sleep, transport=None, timeout_seconds=300.0) -> dict[str, Any]`
- Produces CLI options: `--expected-commit`, `--deployment-wait-seconds`, `--deployment-poll-seconds`, `--output`
- Produces workflow artifact: `production-acceptance-report`

- [ ] **Step 1: Extend the mock health response with commit identity**

Modify `_transport` in `tests/test_production_acceptance.py` to accept `health_commits: list[str] | None`. Return the next commit on each `/health` request while preserving the last value after the list is exhausted. Default to `test-commit`.

- [ ] **Step 2: Write failing expected-commit and polling tests**

Add tests that require:

```python
def test_run_acceptance_requires_expected_deployment_commit():
    module = _module()
    report = module.run_acceptance(
        "https://bktstr.example",
        expected_commit="new-commit",
        deployment_attempts=2,
        deployment_poll_seconds=0,
        sleeper=lambda _: None,
        transport=_transport(health_commits=["old-commit", "new-commit"]),
    )
    assert report["git_commit"] == "new-commit"


def test_run_acceptance_rejects_commit_that_never_deploys():
    module = _module()
    with pytest.raises(module.AcceptanceError, match="expected commit new-commit"):
        module.run_acceptance(
            "https://bktstr.example",
            expected_commit="new-commit",
            deployment_attempts=2,
            deployment_poll_seconds=0,
            sleeper=lambda _: None,
            transport=_transport(health_commits=["old-commit"]),
        )
```

Add a CLI test using `monkeypatch` and `tmp_path` that calls `main()` with `--output <path>` and asserts the written JSON contains `status: pass` and the expected commit.

- [ ] **Step 3: Run the production-acceptance tests and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_production_acceptance.py -v
```

Expected: FAIL because `run_acceptance` does not accept deployment identity parameters.

- [ ] **Step 4: Implement bounded deployment polling**

Add `_wait_for_deployment` to `scripts/production_acceptance.py`. It must:

- request `/health` up to `deployment_attempts` times;
- accept health only when version equals `expected_version` and, when supplied, commit equals `expected_commit`;
- sleep only between attempts through the injected `sleeper`;
- retain the last observed version, commit, and HTTP error;
- raise `AcceptanceError` with expected and observed identities after exhaustion.

Call `_wait_for_deployment` before capabilities and backtest requests. Preserve current behavior when `expected_commit` is omitted and attempts remain 1.

- [ ] **Step 5: Add CLI wait and report options**

Add CLI arguments with these defaults:

```text
--expected-commit: omitted
--deployment-wait-seconds: 0
--deployment-poll-seconds: 10
--output: omitted
```

Compute attempts as one when wait is zero; otherwise use `ceil(wait_seconds / poll_seconds) + 1`. Print the JSON report to stdout and, when `--output` is supplied, write the same report plus a final newline using UTF-8. Write failure JSON to the output path as well before returning exit code 1.

- [ ] **Step 6: Create the manual GitHub Actions workflow**

Create `.github/workflows/production-acceptance.yml` with:

- name `BKTSTR Production Acceptance`;
- `workflow_dispatch` inputs `expected_version` (required, default `0.3.5`), `expected_commit` (required), and `base_url` (required, default `https://bktstr-production.up.railway.app`);
- `contents: read` permission;
- one `production_acceptance` job named `Production acceptance`;
- checkout at `${{ inputs.expected_commit }}`;
- Python 3.12 and pinned `requirements-dev.txt`;
- the acceptance command with a 600-second deployment wait, 10-second polling, and `--output production-acceptance.json`;
- `actions/upload-artifact@v4` with `if: always()`, artifact name `production-acceptance-report`, and the JSON path.

Use this workflow body:

```yaml
name: BKTSTR Production Acceptance

on:
  workflow_dispatch:
    inputs:
      expected_version:
        description: Version expected from production health and capabilities
        required: true
        default: '0.3.5'
        type: string
      expected_commit:
        description: Full Git SHA expected from Railway health
        required: true
        type: string
      base_url:
        description: BKTSTR production base URL
        required: true
        default: https://bktstr-production.up.railway.app
        type: string

permissions:
  contents: read

jobs:
  production_acceptance:
    name: Production acceptance
    runs-on: ubuntu-latest
    steps:
      - name: Check out expected commit
        uses: actions/checkout@v7
        with:
          ref: ${{ inputs.expected_commit }}
      - name: Set up Python
        uses: actions/setup-python@v7
        with:
          python-version: '3.12'
          cache: pip
          cache-dependency-path: requirements-dev.txt
      - name: Install pinned dependencies
        run: python -m pip install -r requirements-dev.txt
      - name: Run production acceptance
        run: >-
          python scripts/production_acceptance.py
          --base-url "${{ inputs.base_url }}"
          --expected-version "${{ inputs.expected_version }}"
          --expected-commit "${{ inputs.expected_commit }}"
          --deployment-wait-seconds 600
          --deployment-poll-seconds 10
          --output production-acceptance.json
      - name: Retain acceptance report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: production-acceptance-report
          path: production-acceptance.json
          if-no-files-found: error
```

- [ ] **Step 7: Add workflow-contract assertions**

Add `test_production_acceptance_workflow_is_manual_and_sha_bound` to `tests/test_ops_assets.py`. Require all workflow/input names, `contents: read`, checkout at expected commit, the exact script flags, the 600-second wait, and artifact upload.

- [ ] **Step 8: Run focused and full verification**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_production_acceptance.py tests/test_ops_assets.py -v
& '.\.venv\Scripts\python.exe' -m pytest
& '.\.venv\Scripts\python.exe' scripts/check_release_consistency.py
```

Expected: PASS with only the four existing deprecation warnings in the full suite.

- [ ] **Step 9: Commit the production gate**

```powershell
git add scripts/production_acceptance.py tests/test_production_acceptance.py .github/workflows/production-acceptance.yml tests/test_ops_assets.py
git commit -m "chore(release): gate production on deployed commit"
```

---

### Task 8: Verify the Governance Branch and Publish Its Pull Request

**Files:**
- All repository files from Tasks 2-7
- GitHub pull request targeting `main`

**Interfaces:**
- Consumes: bootstrap Issue number and all repository deliverables
- Produces: one reviewable pull request and green GitHub CI checks

- [ ] **Step 1: Run complete local verification**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest
& '.\.venv\Scripts\python.exe' -m compileall -q bktstr bktstr_cache integration scripts benchmarks tests
& '.\.venv\Scripts\python.exe' scripts/check_release_consistency.py
& '.\.venv\Scripts\python.exe' benchmarks/benchmark_cache.py
git diff --check origin/main...HEAD
git status --short --branch
```

Expected: tests pass, compilation exits 0, consistency passes, benchmark reports one compute call with cold miss then warm hit, diff check is empty, and the working tree is clean.

- [ ] **Step 2: Review the complete branch scope**

```powershell
git log --oneline --decorate origin/main..HEAD
git diff --name-status origin/main...HEAD
git diff --stat origin/main...HEAD
```

Expected: only the approved design, implementation plan, governance documents/templates/tests, CI changes, and production-gate changes appear.

- [ ] **Step 3: Push the short-lived branch**

```powershell
git push -u origin HEAD
```

- [ ] **Step 4: Open the governance pull request**

Use title:

```text
docs(governance): establish v1 delivery system
```

The PR body must link the bootstrap Issue with `Closes #<issue-number>`, summarize each commit, paste the local verification results, state that trading semantics are unchanged, explain that this is the pre-ruleset bootstrap exception, and state rollback as reverting the squash commit.

- [ ] **Step 5: Wait for every CI job and inspect failures rather than bypassing**

Require `Hygiene`, `Tests`, `Compile`, `Production image`, `Documentation`, and `Cache benchmark` to complete successfully.

- [ ] **Step 6: Squash-merge and delete the branch**

Use the PR title as the squash commit subject. Confirm Railway deploys the documentation/governance-only commit without changing runtime version or trading output.

---

### Task 9: Configure Repository Labels, Milestones, Trackers, and Project

**Files:**
- No local file changes
- GitHub repository labels and Milestones
- User Project: `BKTSTR v1 Roadmap`
- Seven release-tracking Issues

**Interfaces:**
- Consumes: merged templates and `docs/roadmap/v1-release-plan.md`
- Produces: the live planning system used by every later implementation plan

- [ ] **Step 1: Normalize labels in the GitHub repository settings**

Rename existing labels:

| Existing | New | Color | Description |
| --- | --- | --- | --- |
| `enhancement` | `type:feature` | `1D76DB` | New user or developer capability |
| `bug` | `type:bug` | `D73A4A` | Incorrect or regressed behavior |
| `documentation` | `type:docs` | `0075CA` | Documentation-only work |

Create:

| Label | Color | Description |
| --- | --- | --- |
| `type:maintenance` | `6A737D` | Internal maintenance, tooling, or operations |
| `type:security` | `B60205` | Security hardening or vulnerability work |
| `risk:trading-semantics` | `E99695` | May affect formulas, signals, fills, or results |
| `risk:data-migration` | `F9D0C4` | Changes durable data or migration behavior |
| `risk:production` | `FBCA04` | Elevated deployment or operational risk |
| `release-blocker` | `B60205` | Must be resolved before the assigned release ships |
| `dependencies` | `0366D6` | Dependency updates |

Retain `accessibility`, `good first issue`, and `help wanted`. Delete `duplicate`, `invalid`, `question`, and `wontfix` only after confirming the repository still has zero Issues using them.

- [ ] **Step 2: Create seven GitHub Milestones without due dates**

Create the exact titles and descriptions:

| Title | Description |
| --- | --- |
| `v0.4.0 — Baseline and documentation repair` | Trustworthy docs, executable examples, governance, and frozen v0.3.5 baseline |
| `v0.5.0 — Strategy-neutral core` | Stable domain contracts with equal normalized trading output |
| `v0.6.0 — FastAPI application foundation` | Typed API, OpenAPI, compatibility routes, errors, and health |
| `v0.7.0 — Persistence and single-owner authentication` | Private owner access and durable research records |
| `v0.8.0 — Durable execution jobs` | Idempotent worker jobs, retries, cancellation, heartbeat, and recovery |
| `v0.9.0 — React research workspace` | Complete browser research workflow |
| `v1.0.0 — Railway production cutover` | Stable owner-only application as the normal BKTSTR interface |

- [ ] **Step 3: Create one release-tracking Issue per Milestone**

Use the merged Release Issue form. Title each tracker `[Release] vX.Y.Z — <milestone name>`, assign `type:maintenance`, assign its matching Milestone, and copy the exact exit criterion from `docs/roadmap/v1-release-plan.md`. Each tracker must link the standalone roadmap, release plan, release procedure, and its own Milestone.

Set v0.4.0 tracker Status to Ready after the Project exists; set later trackers to Backlog.

- [ ] **Step 4: Create the user-level Project**

Create a public user Project named `BKTSTR v1 Roadmap` owned by `M00SEDR0iD`. Link repository `M00SEDR0iD/bktstr`.

Create fields:

- Status: Backlog, Ready, In progress, In review, Blocked, Done
- Priority: P0, P1, P2, P3
- Area: Docs, Core, Market Data, API, Persistence/Auth, Jobs, Web, Operations
- Effort: XS, S, M, L
- Start date
- Target date

Use GitHub's native Milestone field; do not create a Release field or Iteration field.

- [ ] **Step 5: Create Project views**

Create and save:

- Roadmap: roadmap layout grouped by Milestone, using Start date and Target date
- Current release: table filtered to `milestone:v0.4.0`
- Work board: board grouped by Status
- Backlog: table filtered to `status:Backlog`, sorted Priority ascending
- Blocked and risks: table filtered to `status:Blocked` or labels beginning `risk:`
- Recently shipped: table filtered to `status:Done`, grouped by Milestone

- [ ] **Step 6: Configure Project automation**

Enable automatic addition of Issues and pull requests from `M00SEDR0iD/bktstr`, set newly added items to Backlog, move opened pull requests to In review, and move closed Issues and merged pull requests to Done.

- [ ] **Step 7: Add all seven trackers and publish the initial Project status**

Set Project status to `On track` with title `v0.4.0 governance and baseline planning started`. State that dates are intentionally omitted because releases are outcome-driven.

---

### Task 10: Protect Main and Version Tags, Then Verify the Bootstrap

**Files:**
- No local file changes
- GitHub repository merge settings and Rulesets

**Interfaces:**
- Consumes: green CI check names from the merged governance PR
- Produces: enforced pull-request flow and immutable published tags

- [ ] **Step 1: Configure merge settings**

In repository settings, enable squash merging, disable merge commits, disable rebase merging, use the pull-request title as the default squash commit message, and enable automatic deletion of head branches.

- [ ] **Step 2: Create the active `main` branch ruleset**

Target only `main` and configure:

- require a pull request before merging;
- required approvals: 0;
- require all conversations resolved;
- allow only squash merge for matching pull requests;
- require branches to be up to date before merging;
- require status checks `Hygiene`, `Tests`, `Compile`, `Production image`, `Documentation`, and `Cache benchmark` from GitHub Actions;
- require linear history;
- block force pushes;
- restrict deletion;
- no routine bypass actor.

Leave signed commits and merge queue disabled.

- [ ] **Step 3: Create the active `v*` tag ruleset**

Target tags matching `v*`. Restrict updates and deletions while allowing creation of new tags. Do not add a bypass actor for normal work.

- [ ] **Step 4: Inspect effective rules and repository settings**

Confirm in GitHub that both rulesets report Active, `main` lists all six required checks, only squash merge is available, branches delete after merge, and the v0.3.5 tag still points to `add435d`.

- [ ] **Step 5: Seed the actionable v0.4.0 Issues**

Create separate v0.4.0 Issues for:

1. documentation entry point and root-document cleanup;
2. corrected executable API examples;
3. frozen v0.3.5 characterization fixtures;
4. generated-file and manifest cleanup;
5. concise root `AGENTS.md` and archival review of the old release branch;
6. documentation link/example/version checks;
7. v0.4.0 release preparation and production acceptance.

Assign each to the v0.4.0 Milestone and Project. Give each an Area, Priority, Effort, acceptance criteria, and verification method. Add blocking relationships so release preparation is blocked by the other six Issues.

- [ ] **Step 6: Verify the complete governance acceptance criteria**

Confirm:

- the repository landing page links contributor, roadmap, changelog, and release guidance;
- all seven Milestones and trackers exist;
- v0.4.0 has actionable, dependency-linked Issues;
- the Project views display the expected items and state;
- new Issues use structured forms;
- new pull requests use the required checklist;
- `main` requires pull requests and all six checks;
- `v*` tag updates and deletions are restricted;
- the latest `main` and Railway production health report the same SHA and version 0.3.5;
- the manually dispatched production workflow passes for that SHA and retains its JSON artifact;
- the local checkout is clean and matches `origin/main` after returning to `main`.

- [ ] **Step 7: Publish the governance completion status**

Update the bootstrap Issue with links to the merged PR, Project, seven Milestones, active rulesets, CI run, production-acceptance run, and retained JSON artifact. Close it only after every bootstrap acceptance criterion is verified.

Do not create a new version tag: governance bootstrap is part of active v0.4.0 work, not the completed v0.4.0 release.

---

## Final Verification Checklist

- [ ] `python -m pytest` passes in the pinned `.venv`.
- [ ] `python -m compileall -q bktstr bktstr_cache integration scripts benchmarks tests` exits 0.
- [ ] `python scripts/check_release_consistency.py` exits 0.
- [ ] `python benchmarks/benchmark_cache.py` shows cold miss, warm hit, and one compute call.
- [ ] GitHub CI passes all six required jobs on the governance PR.
- [ ] Railway health matches the merged `main` SHA and version 0.3.5.
- [ ] Manual production acceptance passes and retains the JSON artifact.
- [ ] The BKTSTR v1 Roadmap Project, seven Milestones, seven trackers, and v0.4.0 Issues are visible.
- [ ] `main` and `v*` rulesets are active with the approved settings.
- [ ] The v0.3.5 tag still points to `add435d`.
- [ ] No unrelated files, trading semantics, credentials, generated artifacts, or published history changed.
