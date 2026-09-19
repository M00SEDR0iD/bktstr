# Local BKTSTR keys

The local helper stores your BKTSTR API key in Windows Credential Manager. Agents run trusted research programs through it. They do not need you to paste the key into chat.

This is a local Windows tool. It needs no server changes and adds no dependencies to the service. It works with Python 3.12 and the project's existing requirements. Run the commands below in PowerShell from the BKTSTR project folder, under your usual Windows account.

## First setup: use the existing key

1. Install the project dependencies if this is a new checkout:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

   Skip this step if the project's `.venv` is already set up.

2. Open the BKTSTR service in Railway. Under **Variables**, copy the value of `BKTSTR_API_KEY`. This is the BKTSTR service key, not the market-data provider's key.

3. Run this command yourself in a terminal, paste the key at its hidden prompt, and press Enter:

   ```powershell
   .\.venv\Scripts\python.exe -m bktstr.local_credentials save
   ```

   Success reads `Key verified and saved as active.` A rejected key does not replace anything already saved. Do not enter the key in an agent message or as a command argument.

4. Verify setup:

   ```powershell
   .\.venv\Scripts\python.exe -m bktstr.local_credentials check
   ```

   Success reads `Authentication succeeded.` Local agents using this Windows account can now use the saved key.

5. To enable production acceptance in GitHub Actions, save the same value in the repository's **Settings > Secrets and variables > Actions > New repository secret**, named `BKTSTR_API_KEY`. You can copy the active local key again without displaying it:

   ```powershell
   .\.venv\Scripts\python.exe -m bktstr.local_credentials copy
   ```

   Local setup does not configure GitHub automatically. Clear the clipboard after pasting with `Set-Clipboard -Value ''`. Also remove the entry from Windows clipboard history using Win+V, if history is enabled. Clipboard history and synchronization may retain copies; disable them before copying secrets if you use those features.

## Agent instructions

Use the current saved key. Do not generate a key during ordinary research. Start with `status` to see whether a key is present, or `check` to verify it against the service:

```powershell
.\.venv\Scripts\python.exe -m bktstr.local_credentials status
.\.venv\Scripts\python.exe -m bktstr.local_credentials check
```

Wrap a trusted program with `run --`. The helper supplies `BKTSTR_API_KEY` and `BKTSTR_BASE_URL` to that program's environment and preserves its exit code. It does not change the parent terminal's environment.

```powershell
.\.venv\Scripts\python.exe -m bktstr.local_credentials run -- .\.venv\Scripts\python.exe scripts/production_acceptance.py --base-url https://bktstr-production.up.railway.app --expected-version 0.6.0
```

That example runs the real production acceptance backtests and writes experiment records on the service. It is not just a connectivity check. To verify a particular deployment, append `--expected-commit` and the full deployed Git commit.

A research script should read the key from `os.environ["BKTSTR_API_KEY"]`, use `os.environ["BKTSTR_BASE_URL"]` as its service address, and send the key in the `Authorization: Bearer ...` header. Keep TLS verification enabled, reject redirects, and never print the key, headers, or environment. No raw-key retrieval command is provided.

Only wrap trusted programs. The child and its descendants can access the key and control their own output. The helper does not redact arbitrary child output or stop a child from sending the key elsewhere. Windows Credential Manager protects storage; other processes with access under the same Windows account can retrieve generic credentials too. Cloud agents and GitHub runners need their own secret configuration.

## Generate and activate a replacement

Use this for initial server provisioning or an intentional rotation. Existing clients stop authenticating when the server changes to the replacement key. Arrange a short pause in research and update every client that uses the old key.

1. Generate a pending key. The current active key stays saved:

   ```powershell
   .\.venv\Scripts\python.exe -m bktstr.local_credentials generate
   .\.venv\Scripts\python.exe -m bktstr.local_credentials copy --pending
   ```

2. Paste the copied value into Railway's `BKTSTR_API_KEY` and GitHub's Actions secret of the same name. Apply the Railway variable change and wait for its deployment to finish. Clear clipboard and clipboard history afterward.

3. Verify the pending key against the deployed service and make it active locally:

   ```powershell
   .\.venv\Scripts\python.exe -m bktstr.local_credentials activate
   .\.venv\Scripts\python.exe -m bktstr.local_credentials check
   ```

If activation fails, both the old active key and pending replacement stay saved. Correct the server configuration or wait for deployment, then retry `activate`. To roll back before activation, `copy` retrieves the old active key so you can restore it in Railway and GitHub. Successful activation replaces the old local key and clears the pending slot.

Running `generate` twice refuses to discard a pending key. Only use `generate --replace-pending` when you intend to discard that pending value. This tool never updates Railway or GitHub automatically.

## Other environments and troubleshooting

The default service is `https://bktstr-production.up.railway.app`. For another deployment, put `--base-url https://your-service.example` **before** the command on every invocation. Each HTTPS origin gets separate saved keys, so a production key is not selected automatically for another host. Only supply an origin you control and intend to trust with that key.

The helper refuses HTTP, URL credentials, paths, queries, fragments, and redirects. Verification uses a direct HTTPS connection with certificate checks and a 15-second timeout; it does not use proxy settings from the environment.

- **No active key:** run `save` yourself, or complete generation and activation.
- **Service rejected the key:** confirm the value in Railway and wait for the deployment carrying it to finish.
- **Hidden input unavailable:** use an interactive Windows Terminal or PowerShell terminal. Input is never allowed to fall back to visible typing.
- **Credential storage unavailable:** run under your normal Windows account with access to Credential Manager. There is no plaintext fallback.
- **Storage entry is invalid:** open **Credential Manager > Windows Credentials > Generic Credentials**. The entry is `bktstr/api/` followed by a hash of the service origin. Remove only the affected entry and repeat `save`; this also discards any pending value in that entry.

For a read-only way to find the exact entry name, run:

```powershell
.\.venv\Scripts\python.exe -c "from bktstr.local_credentials import credential_target, DEFAULT_ORIGIN; print(credential_target(DEFAULT_ORIGIN))"
```

## Verification and deployment

Merge the helper through the normal PR checks, then update the local checkout. No Railway configuration change is needed when importing an existing key. The CI suite runs helper behavior tests on Linux and a dedicated Windows job exercises real Credential Manager storage and process locking with disposable credentials that are deleted after testing.

The helper tests do not validate your production key. After you complete setup, run `check`, then run production acceptance locally through the helper or dispatch **BKTSTR Production Acceptance** in GitHub Actions using the deployed commit and version. A healthy public `/health` response alone does not validate authentication.
