# Git workflow

## Principles

`main` is the only permanent delivery branch and must remain deployable. Existing Git history is never rewritten merely to make it look cleaner. Normal work moves through an Issue, a short-lived branch, a pull request, and a squash merge.

## Issue readiness

Begin normal work only when a GitHub Issue states the intended outcome and acceptance criteria. Every normal pull request links an Issue. The solo-maintainer policy requires zero external approvals, but required CI checks and conversation resolution still apply and cannot be bypassed routinely.

## Branch naming

Create a short-lived branch from the current `main` using the matching form:

- `feat/<issue>-<slug>` for a feature
- `fix/<issue>-<slug>` for a defect correction
- `docs/<issue>-<slug>` for documentation
- `chore/<issue>-<slug>` for maintenance

Keep each branch focused on one Issue.

## Commit titles

Use concise Conventional Commit-style titles that describe the result, such as `feat:`, `fix:`, `docs:`, or `chore:`. Keep intermediate commits understandable even though the pull request will be squash-merged.

## Pull-request contents

Each pull request must:

- include `Closes #<issue>`;
- summarize the change and its reason;
- identify tests and other verification performed;
- call out deployment, compatibility, security, or rollback considerations; and
- pass every required CI check with all review conversations resolved.

## Squash merging

Squash-merge a pull request only after its required checks pass and conversations are resolved. Use a clear Conventional Commit-style squash title so `main` has a readable delivery history.

## Branch cleanup

Delete the short-lived branch after its pull request is merged. Do not retain parallel permanent development or release branches.

## Protected `main`

Direct routine changes to `main` are prohibited. Required CI and conversation-resolution protections must remain enabled. Force pushes to `main` and moving published tags are prohibited.

## Prohibited history rewriting

Do not force push to `main`, move a published tag, or rewrite existing Git history merely to make it look cleaner. Corrections belong in new commits and pull requests so published identities remain auditable.

## Emergency changes

Emergency changes require an incident Issue and the smallest safe change. Verify the result in production, then create a follow-up pull request that records any cleanup and restores every rule that was changed temporarily. Emergency access does not authorize moving tags or rewriting existing Git history.
