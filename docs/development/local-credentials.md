# Local BKTSTR credentials

The existing Windows helper stores the BKTSTR service key in Windows Credential
Manager, scoped to the service origin. It does not manage OpenRouter, macro-feed,
or Clear Street credentials.

Use Python 3.12 from the repository environment. Run these commands under the
Windows account that will run research.

## Save and verify

Retrieve the service's `BKTSTR_API_KEY` through its deployment secret settings.
Enter it yourself at the hidden terminal prompt:

```powershell
python -m bktstr.local_credentials save
python -m bktstr.local_credentials check
```

Use `status` to inspect whether an active key is stored. Do not paste keys in
chat, pass them as command arguments, or include them in logs or experiments.
Saving verifies the key before replacing the active value.

## Run a trusted research program

```powershell
python -m bktstr.local_credentials run -- python path/to/research_program.py
```

Replace the program path with the actual trusted script. The child receives
`BKTSTR_API_KEY` and `BKTSTR_BASE_URL`; the parent environment is unchanged.
The helper preserves the program's exit code. It does not redact arbitrary
child output, so run only code trusted to handle the key.

Send `Authorization: Bearer ...` to the configured origin, keep TLS verification
enabled, reject redirects, and never print headers or the environment.

## Deliberate rotation

```powershell
python -m bktstr.local_credentials generate
python -m bktstr.local_credentials copy --pending
```

Update the service secret and affected clients, wait for deployment, then run:

```powershell
python -m bktstr.local_credentials activate
python -m bktstr.local_credentials check
```

Generation creates a pending value; activation verifies it before replacing the
active value. The helper does not update Railway or GitHub automatically.
Clear the clipboard and its history after transferring a key. Do not generate
or rotate keys during ordinary research.

## Origin and environment

The default origin is `https://bktstr-production.up.railway.app`.
For another trusted deployment, put `--base-url https://your-service.example`
before the subcommand. Each origin has separate saved credentials.
The helper rejects HTTP, URL credentials, paths, query strings, fragments, and
redirects.

Cloud jobs and GitHub Actions need their own secret configuration. A local saved
key does not configure those environments. Windows Credential Manager protects
storage but does not isolate the key from other processes under the same account.

Use `check` for authentication verification. The
[production acceptance procedure](releases.md) also runs backtests and creates
experiment records.
