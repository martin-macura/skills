---
name: act-local-ci
description: Run a repo's GitHub Actions workflows locally with nektos `act`, including the settings and failure workarounds that make it actually work. Use when running CI locally via act, verifying a workflow before pushing (e.g. remote runners unavailable), or debugging act errors like "context canceled", artifact upload/download failures, or `unknown field "mime_type"`.
---

# Running CI locally with act

[`act`](https://github.com/nektos/act) runs `.github/workflows/*` locally in Docker — useful to verify CI without pushing (e.g. when remote runners are blocked). The defaults rarely "just work"; below are the settings and workarounds that do.

## Prerequisites

- **Docker must be running.** `docker info` must succeed. On macOS: `open -a Docker`, then wait until `docker info` returns.
- Inspect first: `act -l` lists jobs. Run the workflow's trigger event (`act pull_request`, `act push`, …).

## Recommended invocation

```bash
act <event> \
  -P ubuntu-latest=catthehacker/ubuntu:act-latest \   # real runner image (has node/yarn/etc.)
  --container-architecture linux/amd64 \              # Apple Silicon: match GitHub, avoid arch crashes
  --concurrent-jobs 1                                 # serial: avoids "context canceled"
```

- `-P ubuntu-latest=catthehacker/ubuntu:act-latest` — the default `act` image is tiny and lacks tools; this medium image also skips the interactive first-run image prompt.
- `--container-architecture linux/amd64` — on Apple Silicon, run amd64 (emulated) so behavior matches GitHub runners and amd64-only images (e.g. Playwright) resolve. **Keep every job on the same arch** — a `build` job's `node_modules` artifact must match the arch of the job that consumes it.
- `--concurrent-jobs 1` — many parallel containers (image pulls + installs at once) can make act abort mid-run with `Error: context canceled` (Docker-socket teardown). Serial is far more reliable, just slower.
- Single job: `act <event> -j <job-id>`. Secrets/vars: `-s NAME=val` / `--var NAME=val`, or persist flags in `~/.actrc`.

## Artifacts (upload-artifact / download-artifact)

Jobs that hand off via artifacts (e.g. `build` → `e2e`) need act's artifact server, and the directory must already exist:

```bash
mkdir -p /tmp/artifacts
act <event> --artifact-server-path /tmp/artifacts
```

**Known breakage:** `actions/upload-artifact@v4+` (v4–v8) use a newer artifact backend act's built-in server can't decode. The `build` job fails with:

```
level=error msg="Error decode request body: proto: unknown field \"mime_type\""
::error::Failed to CreateArtifact: Failed to make request after 5 attempts: Unexpected end of JSON input
```

This is a protocol-version mismatch — `--artifact-server-path` does **not** fix it. Two workarounds:

1. **Pin to the legacy v3 API (local, uncommitted):** change every `actions/upload-artifact@vN` and `actions/download-artifact@vN` to `@v3`, run act, then **revert before committing** — real GitHub Actions needs v4+ (v3 is sunset there). v3 speaks the API act's server implements.
   ```bash
   # macOS/BSD sed (Linux: drop the '')
   sed -i '' -E 's#(actions/(upload|download)-artifact)@v[0-9]+#\1@v3#g' .github/workflows/*.yml
   # …run act…
   git restore .github/workflows   # undo before committing
   ```
2. **Run artifact-dependent jobs directly instead of via act** — e.g. build + run the test command on the host, skipping the artifact handoff entirely. Often faster and avoids the issue.

## When act fights you

If act keeps failing on its **own** environment (artifact protocol, arch/container crashes, cross-job orchestration) rather than on your code, stop fighting it: the workflow's shell commands (`install` / `build` / `lint` / `test`) are the real CI check — run them directly. Use act to confirm the simple jobs, and run artifact-/container-heavy jobs (e.g. E2E) directly on the host.
