# Release procedure

A local change is not a verified production release.

1. Run the relevant tests, release-consistency check, compilation, and cache
   benchmark. Resolve required CI failures before merging.
2. Update the changelog and all versioned contracts together when releasing:
   `bktstr/__init__.py`, README, the GUI JSON contract, and production acceptance.
3. Open a focused pull request. Record compatibility and rollback behavior.
4. Merge after required GitHub Actions checks pass and review is complete.
5. Wait for Railway to report the expected version and `git_commit`.
6. Run authenticated acceptance against that exact deployment. Retain its output
   as a release artifact. Health alone does not prove authenticated access.
7. Tag and publish only after acceptance succeeds.

Use the existing production acceptance workflow or the local helper:

```powershell
python -m bktstr.local_credentials run -- python scripts/production_acceptance.py --base-url https://bktstr-production.up.railway.app --expected-version 0.6.0 --expected-commit <full-commit-sha>
```

Supply the intended release version and actual deployed commit. This command
creates research experiments. Use `local_credentials check` for authentication
verification without acceptance runs.

Keep persistent experiments and caches on the Railway volume. Supply secrets
through deployment configuration. Planned OpenRouter, macro, and paper adapters
need their own acceptance checks before they can be called released.

A failed candidate must not be tagged. Revert through a reviewed change or
redeploy the previous known-good release. Preserve experiment records and verify
storage compatibility before rollback. Do not silently reuse old execution or
model identities for changed behavior.
