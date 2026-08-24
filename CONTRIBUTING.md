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
