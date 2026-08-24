# Release workflow

## 1. Release readiness

Confirm that Milestone Issues are closed or explicitly deferred, the changelog is complete, and every release exit criterion is met.

## 2. Release-preparation PR

Open a focused pull request titled `release: prepare vX.Y.Z`. Change only the version, changelog, release-plan state, and version-sensitive checks.

## 3. Merge and deploy

Squash-merge the release-preparation pull request after all required checks pass. Record the merge SHA, then wait for Railway health to report the expected Git SHA and version before running production acceptance.

## 4. Manual production gate

Manually dispatch `.github/workflows/production-acceptance.yml` with the version, SHA, and production URL. Retain the resulting JSON artifact as release evidence. A candidate cannot be tagged until this gate passes against the expected deployment.

## 5. Publish

Create the annotated tag with:

```bash
git tag -a vX.Y.Z -m "BKTSTR vX.Y.Z"
git push origin vX.Y.Z
```

Generate and review the GitHub release notes, record production verification and known limitations, and close the Milestone and release tracker.

## 6. Patch releases

Repeat the same readiness, preparation, deployment, manual production gate, and publication process with an incremented patch number.

## 7. Rollback

Do not tag a failed candidate. Fix or revert the candidate through a pull request. When necessary, redeploy the last known-good tag, and record the incident and recovery.
