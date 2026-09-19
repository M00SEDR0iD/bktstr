# Local credentials implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan. Steps use checkbox syntax for tracking.

**Goal:** Let local agents use the current verified BKTSTR key without putting it in chat, source files, or command arguments.

**Architecture:** A Windows Credential Manager record holds active and pending keys for one HTTPS origin. A local Python command imports, generates, copies, verifies, activates, and supplies keys to trusted child processes. The production server and its dependencies stay unchanged.

**Tech stack:** Python standard library, Windows credential APIs, existing httpx.

**Spec:** The user approved the four-function design in this conversation: save an existing key, generate a pending replacement, run a trusted process, and check authentication. Activation must follow server verification. GitHub Actions has a separate secret; local storage does not provision it.

## Global constraints

- No plaintext secret files, printed keys, key arguments, or plaintext fallback.
- Hidden input must fail closed when an interactive terminal is unavailable.
- HTTPS origins only; no redirects, URL credentials, paths, queries, or fragments.
- Active keys survive failed import, failed activation, and pending generation.
- Clipboard transfer is explicit and documented as temporary plaintext exposure.
- Run passes secrets only in a copied child environment; trust the child program.
- No production secret changes or service deployment during preparation.

## Review focus

1. Redirects, insecure URLs, proxy handling, and accidental key disclosure.
2. Failed vault writes and failed verification preserve the working credential.
3. Concurrent key updates do not overwrite a newer record.
4. Real Windows storage survives separate invocations and removes test records.
5. CLI errors, noninteractive import, clipboard failure, and child exit propagation.

### Task 1: Local helper and setup guide

**Files:** Create `bktstr/local_credentials.py`, `bktstr/windows_credentials.py`, `tests/test_local_credentials.py`, `tests/test_windows_credentials.py`, and `docs/development/local-credentials.md`. Update README, changelog, and CI with a Windows credential integration job.

**Interfaces:** `WindowsCredentialStore(target).read()/write(value)/delete()` stores UTF-8 JSON in one generic credential, with `locked()` serializing updates. `CredentialHelper(store, base_url)` implements save, generate, activate, check, status, copy, run. CLI: `python -m bktstr.local_credentials [--base-url URL] {save,generate,activate,check,status,copy,run}`.

- [x] Write behavior tests for safe import/rotation, origin validation, rejected authentication, hidden input, clipboard/child failures, and redaction. Run focused pytest; expect failure because helper is absent.
- [x] Implement vault and helper. Run focused pytest; expect all tests pass. Windows integration uses a unique disposable target and deletes it in finally.
- [x] Add human setup and agent invocation instructions. Include importing the existing key and manual Railway/GitHub rotation.
- [x] Run full pytest, release consistency, syntax checks, and cache benchmark. Expected: all pass, aside from existing deprecation warnings.
- [x] Request an independent read-only review and fix consequential findings with failing regression tests.

Delivery gate: commit explicit files and prepare a PR. Hosted Linux and Windows CI must pass before this change is ready to merge. The PR checks record this gate's result.

## Execution record

- Pre-flight: one task; no shared interfaces between tasks.
- The approved design and request to keep working authorize implementation without another approval checkpoint. Work uses a feature branch in the existing checkout; unrelated files remain untouched.
- Native PowerShell and pytest replace the skill's Bash bookkeeping scripts because this Windows checkout has no Bash executable available at the known Git path. Verification evidence is recorded here.
- Initial helper tests: 34 failed with missing implementation, then 34 passed. Expanded failure-path, clipboard, and native locking coverage brought this to 40 passed.
- First full suite: 448 passed, one failure in `test_ci_workflow_runs_full_release_checks`. Its exact job inventory needed the new Windows credential job and runner. Updated that existing contract.
- Independent review found one important issue: a session-local mutex did not cover the vault's cross-session persistence. Added a failing namespace/user-binding test, switched to a global mutex named with the current process token's user SID and service target, and reran native process contention coverage. Focused suite: 41 passed.
- Review scope decisions: production provisioning remains a user setup step; trusted child programs control their own output and networking; same-user programs can access the Windows vault. These limits are explicit in the setup guide. No minor findings were deferred.
- Final local verification: 450 tests passed with five existing deprecation warnings. Release consistency, Python syntax, and staged whitespace checks passed. Cache benchmark: 120,000 rows, one computation, cold 0.7217 seconds and warm 0.0230 seconds. The benchmark and full suite required normal Windows temporary-folder access; both passed with that access.
