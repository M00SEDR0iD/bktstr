# BKTSTR v1 GitHub Delivery Governance Design

**Status:** Approved design

**Date:** 2026-08-24

**Current production baseline:** v0.3.5

**Target:** A professional, human-readable, GitHub-native delivery system for the path to v1.0.0

## Purpose

BKTSTR will use Git and GitHub as the durable record for product direction, implementation work, verification, production deployment, and releases. Every roadmap milestone will become a tested production release. Planning must remain understandable to a solo maintainer, recoverable from repository history, and explicit enough that a future contributor can reconstruct why a change was made and how it reached production.

This design complements `docs/roadmap/standalone-web-app.md`. The standalone application roadmap defines what BKTSTR will become; this document defines how that work is planned, reviewed, released, and recorded.

## Goals

- Turn every roadmap milestone into an immutable production release.
- Keep `main` deployable and protect it from unreviewed or unverified changes.
- Use short-lived branches and pull requests for all normal work, including work by the maintainer.
- Keep durable decisions in versioned repository documents and changing work status in GitHub.
- Make commits, pull requests, release notes, and rollback history understandable without private context.
- Automate repeatable checks while retaining deliberate human approval for production releases.
- Provide one outcome-driven GitHub Project for the path from v0.3.5 to v1.0.0.

## Non-goals

- Fixed release deadlines or sprint commitments
- A long-lived `develop` branch
- Long-lived milestone or release branches
- Required approval from another human while BKTSTR has one maintainer
- Fully automatic tagging or release publication after a merge
- Rewriting existing Git history or moving the published v0.3.5 tag
- Duplicating live task status across Markdown files and GitHub Projects
- Introducing commit signing before its account and key-management cost is justified

## Source-of-truth model

Each artifact has one responsibility:

| Artifact | Authority |
| --- | --- |
| Repository roadmap and design documents | Product direction, architecture, policies, and release exit criteria |
| GitHub Issues and sub-issues | Actionable work, acceptance criteria, dependencies, and discussion |
| GitHub Milestones | The exact issue and pull-request scope of a production version |
| GitHub Project | Current status, priority, work area, effort, and roadmap views |
| Pull requests | Proposed changes, review discussion, linked work, test evidence, deployment impact, and rollback notes |
| `CHANGELOG.md` | Concise human-readable history of shipped behavior |
| Git commits | Durable, ordered changes to the repository |
| Annotated Git tags | Immutable identities for verified production versions |
| GitHub Releases | Published summaries, generated change lists, verification evidence, limitations, and operator guidance |

Live task status is not copied into Markdown. Architecture and exit-criteria changes are not left only in Project fields or issue comments.

## Production version ladder

Each existing roadmap milestone becomes one outcome-driven production release.

| Version | Roadmap milestone | Production outcome |
| --- | --- | --- |
| v0.4.0 | Baseline and documentation repair | Trustworthy documentation, executable examples, professional delivery governance, and a frozen v0.3.5 behavioral baseline |
| v0.5.0 | Strategy-neutral core | Current behavior runs through stable domain contracts with equal normalized output |
| v0.6.0 | FastAPI application foundation | Typed JSON API, generated OpenAPI, compatibility routing, structured errors, and health contracts |
| v0.7.0 | Persistence and single-owner authentication | Private owner access and durable strategies, runs, results, notes, and provenance |
| v0.8.0 | Durable execution jobs | Worker-backed jobs with idempotency, retries, cancellation, heartbeat, and recovery |
| v0.9.0 | React research workspace | Complete browser workflow for strategies, runs, history, notes, and comparison |
| v1.0.0 | Railway production cutover | The stable private web application becomes the normal BKTSTR interface |

### Version semantics

- Minor versions from v0.4.0 through v0.9.0 represent planned capability milestones.
- Patch versions contain compatible production fixes, documentation corrections, and operational improvements.
- v1.0.0 declares the documented web and API workflow stable for its intended private-owner use.
- Published version numbers and tags are never reused or moved.
- Pre-release tags such as `v0.7.0-rc.1` are reserved for a future staging workflow and will not be introduced until they solve an observed need.
- Incomplete work merged before a milestone release must be inactive, backward-compatible, or otherwise safe in production.

## Git workflow

BKTSTR uses GitHub Flow with one permanent delivery branch: `main`.

### Normal change flow

1. Create or select a GitHub Issue with an outcome, non-goals, acceptance criteria, and verification method.
2. Create a short-lived branch from current `main`.
3. Use a readable branch name that includes the Issue number, for example:
   - `feat/123-strategy-schema`
   - `fix/147-cache-corruption`
   - `docs/152-api-examples`
   - `chore/160-ci-hygiene`
4. Make focused commits while developing and keep the branch current enough to test against `main`.
5. Open a pull request that links the Issue with a closing keyword such as `Closes #123`.
6. Resolve all conversations and require the configured CI checks to pass.
7. Squash-merge the pull request with a Conventional Commit-style title.
8. Automatically delete the merged branch.

Squash merging gives `main` one human-readable commit per pull request while retaining intermediate work and discussion in the pull request. Existing history is not rewritten.

### Commit and pull-request titles

Durable commit summaries are imperative, scoped when useful, and describe one coherent change. Examples:

- `feat(api): add strategy capability schema`
- `fix(cache): recover from corrupt metadata`
- `docs(roadmap): clarify v0.6.0 exit criteria`
- `test(engine): lock same-bar exit behavior`
- `chore(ci): reject generated cache files`
- `release: prepare v0.4.0`

Generated caches, bytecode, virtual environments, credentials, local outputs, and machine-specific artifacts are never committed.

### Emergency changes

Direct changes to `main` are reserved for a production emergency in which the normal pull-request path cannot be used. An emergency change requires:

- an incident Issue explaining why normal flow is unavailable;
- the smallest possible change;
- immediate production verification;
- a follow-up pull request restoring documentation and normal history;
- a note in the applicable release record.

The repository ruleset is not routinely bypassed. Any temporary ruleset change is documented in the incident Issue and restored immediately.

## Branch and tag protection

The `main` ruleset will:

- require a pull request before merging;
- require zero external approvals while BKTSTR has one human maintainer;
- require stable, named CI checks to pass against current `main`;
- require all conversations to be resolved;
- require linear history and allow squash merging as the normal merge method;
- block force pushes;
- block deletion of `main`;
- provide no routine bypass path.

A tag ruleset for `v*` will block updates and deletion of published version tags while allowing creation of new version tags through the documented release process.

## GitHub planning model

One user-level GitHub Project named **BKTSTR v1 Roadmap** tracks delivery through v1.0.0.

### Project fields

| Field | Values or use |
| --- | --- |
| Status | Backlog, Ready, In progress, In review, Blocked, Done |
| Priority | P0, P1, P2, P3 |
| Area | Docs, Core, Market Data, API, Persistence/Auth, Jobs, Web, Operations |
| Effort | XS, S, M, L |
| Milestone | Native GitHub milestone field; no duplicate Release field |
| Start and target dates | Primarily release-tracking issues; optional for individual work |

Iterations are not used because releases are outcome-driven rather than sprint-driven.

### Project views

- **Roadmap:** timeline grouped by Milestone
- **Current release:** table filtered to the active Milestone
- **Work board:** board grouped by Status
- **Backlog:** future work ordered by Priority
- **Blocked and risks:** blocked work and items with risk labels
- **Recently shipped:** completed work grouped by Milestone

Built-in workflows automatically add repository items and move closed Issues and merged pull requests to Done. Project status updates are published when a release starts, materially changes scope, becomes blocked, or ships.

### Issue hierarchy

Each version receives:

- one GitHub Milestone named `<version> — <outcome>`;
- one release-tracking Issue containing its exit checklist, risks, and verification links;
- independently testable Issues assigned to that Milestone;
- sub-issues only when a parent deliverable contains independently reviewable work;
- explicit blocking relationships where order matters.

Only the active release is decomposed into detailed implementation Issues. Future releases retain their tracker, outcome, and high-level scope until discovery is complete.

### Labels

Labels carry information useful outside Project views:

- `type:feature`
- `type:bug`
- `type:docs`
- `type:maintenance`
- `type:security`
- `risk:trading-semantics`
- `risk:data-migration`
- `risk:production`
- `release-blocker`
- `dependencies`

Status, priority, area, effort, and version are not duplicated as labels.

## Repository documentation and templates

The governance bootstrap creates or updates:

- `README.md` for product purpose, quick start, current stable release, and the production link;
- `CONTRIBUTING.md` as the concise entry point for the Issue-to-PR workflow;
- `CHANGELOG.md` with an Unreleased section and versioned release history;
- `docs/roadmap/v1-release-plan.md` for the version ladder, release status, outcomes, and exit criteria;
- `docs/development/git-workflow.md` for branching, commits, pull requests, emergencies, and recovery;
- `docs/development/releases.md` for preparation, deployment, acceptance, tagging, publication, and rollback;
- `docs/archive/releases/` for useful records from completed releases;
- structured feature, bug, documentation, and release Issue forms;
- a pull-request template;
- `.github/release.yml` for categorized generated release notes.

Issue forms require the intended outcome, non-goals, acceptance criteria, and verification approach. Pull requests require a linked Issue, summary, tests, trading/data/API impact, documentation and changelog impact, deployment notes, and rollback notes.

## Updating plans without drift

- Change live status only in GitHub Projects.
- Change milestone scope through Issue assignment and explain deferrals or removals in a comment.
- Change architectural direction or exit criteria through a roadmap or design pull request.
- Record user-visible changes in the `CHANGELOG.md` Unreleased section in the implementing pull request.
- Post a Project status update at release start, material scope change, sustained blockage, and shipment.
- Prefer a new patch release over changing an already published release record or tag.

## Release lifecycle

`bktstr/__init__.py` remains the canonical application-version source until packaging requirements justify a different single source. Documentation may display the version but does not define it.

1. Create the GitHub Milestone and release-tracking Issue.
2. Add scoped Issues with acceptance criteria, dependencies, effort, and area.
3. Implement each Issue through a short-lived branch and pull request.
4. Store architectural decisions in versioned roadmap or design documents.
5. Close every milestone Issue or explicitly move it with a written reason.
6. Open a final `release: prepare v0.x.0` pull request that only:
   - updates the canonical version;
   - moves changelog entries from Unreleased to the version and date;
   - updates the release-plan status;
   - updates version-sensitive tests and production-acceptance defaults.
7. Require full CI, then squash-merge the release pull request.
8. Wait for Railway to deploy the exact merge SHA.
9. Verify `/health` reports the expected version, branch, repository, and commit.
10. Run the manual production-acceptance workflow.
11. Create and push an annotated version tag.
12. Publish a reviewed GitHub Release.
13. Close the GitHub Milestone and release-tracking Issue and publish the Project status update.

GitHub Release notes contain a short human summary, categorized merged pull requests, production verification evidence, known limitations, and migration or rollback guidance when applicable.

## Verification gates

### Required pull-request checks

Protected `main` requires stable, separately named checks for:

- repository hygiene;
- the complete test suite with pinned dependencies;
- Python source and test compilation;
- the production Docker image build;
- the deterministic derived-cache benchmark;
- executable documentation, internal links, and version consistency as those checks are delivered in v0.4.0.

Milestone-specific gates are added without weakening existing checks:

| Version | Additional gate |
| --- | --- |
| v0.5.0 | Frozen normalized trading output and cache-on/cache-off equality |
| v0.6.0 | API schema and compatibility contracts |
| v0.7.0 | Migrations, authentication, authorization, and backup/restore |
| v0.8.0 | Idempotency, retries, cancellation, heartbeat, and stale-worker recovery |
| v0.9.0 | React component and complete browser workflow tests |
| v1.0.0 | Production cutover, persistence, recovery, and owner-access acceptance |

Pull requests labeled `risk:trading-semantics` include explicit evidence that formulas, fills, slippage, stops, targets, sizing, and causal timing either remain unchanged or have an intentional, separately approved version change.

### Manual production gate

A manually dispatched GitHub Actions workflow accepts an expected version and Git SHA. It:

1. waits for Railway health to report the exact SHA;
2. runs the frozen production regression;
3. verifies deterministic output and second-run cache hits;
4. saves its JSON report as a workflow artifact;
5. fails visibly when deployment identity or behavior differs.

The annotated tag and GitHub Release are created only after this workflow passes.

## Failure and rollback policy

- A failed deployment or production gate is not tagged and becomes a release blocker.
- A small defect is fixed through another pull request and the complete gate is repeated.
- An unsafe deployment is reverted through a pull request or Railway is redeployed from the last known-good tagged commit.
- A defect discovered after publication receives a patch release; the old tag remains unchanged.
- Production failures, reversions, and recovery outcomes are recorded in the release tracker.

## Governance bootstrap rollout

### Phase A: Repository foundation

Create one focused pull request containing the durable governance documents, templates, release-note configuration, CI improvements, and version-consistency checks. Record that v0.3.5 predates this workflow and received a post-release roadmap-only production commit without moving its tag.

### Phase B: GitHub configuration

After the repository documentation merges:

1. create the BKTSTR v1 Roadmap Project and approved fields, views, and automation;
2. create Milestones v0.4.0 through v1.0.0;
3. create one release-tracking Issue for each version;
4. create the label taxonomy;
5. seed detailed v0.4.0 Issues;
6. enable the `main` ruleset after required CI check names exist;
7. protect `v*` tags;
8. review the old `release/v0.3.5` branch separately and preserve any valuable content before an explicit deletion decision.

### Phase C: Repeatable milestone delivery

Each release follows this sequence:

```text
approve milestone design
        -> commit versioned design
        -> create scoped Issues and dependencies
        -> implement through focused pull requests
        -> complete exit criteria
        -> merge release-preparation pull request
        -> deploy exact main SHA to Railway
        -> pass manual production gate
        -> publish annotated tag and GitHub Release
        -> close Milestone and publish status
```

## Bootstrap acceptance criteria

The governance bootstrap is complete when:

- a new contributor can understand normal and emergency delivery from the repository;
- every planned v1 release has a GitHub Milestone and release tracker;
- v0.4.0 has actionable Issues with acceptance criteria;
- `main` requires pull requests and passing CI;
- `v*` tags cannot be moved or deleted through normal operations;
- production releases use the documented manual gate;
- Project views reflect live Issue and pull-request state;
- no planning fact has two competing sources of truth;
- the current full test suite and production acceptance remain green.

## References

- [BKTSTR standalone web app roadmap](../../roadmap/standalone-web-app.md)
- [GitHub Projects documentation](https://docs.github.com/en/issues/planning-and-tracking-with-projects)
- [GitHub Issues documentation](https://docs.github.com/en/issues/tracking-your-work-with-issues/learning-about-issues/about-issues)
- [GitHub ruleset options](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- [GitHub generated release notes](https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes)
- [GitHub Releases documentation](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
