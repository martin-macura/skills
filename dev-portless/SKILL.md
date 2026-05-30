---
name: dev-portless
description: Start a project's dev server behind portless so it gets a stable named .localhost URL — handles per-worktree env, isolated DevTools ports, and the auth env vars better-auth needs. Use when the user asks to run/start the dev server, says "/dev-portless", or wants to preview a worktree in the browser.
---

# dev-portless

Start `yarn dev` behind [portless](https://www.npmjs.com/package/portless) so the app is reachable at a per-task `.localhost` URL, the TanStack DevTools server doesn't collide with other dev servers, and better-auth accepts the proxied origin.

The portless app name is derived from the **project** (`<project>-<suffix>`), so this skill works in any of your repos without editing — no project name is hardcoded.

## When to use

The user wants to run the app locally — typically to verify a change, walk through a flow manually, or hand a URL to someone (themselves on another device, a reviewer, etc.). They may say "run the dev server", "start dev", "open the app", "/dev-portless".

If the user just wants `yarn dev` raw on `http://localhost:3000`, follow that instruction instead. This skill is for the portless workflow.

This skill assumes the project's stack: `yarn dev` with env loaded via `dotenvx` (`.env.local`), better-auth, and TanStack DevTools. Adjust the env vars below if a given project differs.

## Inputs you need before running

1. **Suffix** — a short identifier for *this* instance, so multiple worktrees can run in parallel without colliding. The branch's issue number is the natural choice (e.g. branch `fix/732-container-change-rework` → suffix `732`). If there's no obvious number, ask the user. The suffix becomes part of the portless app name **and** the DevTools port.
2. **Project name** — derived automatically from the git repo: the *main checkout's* directory name (stable across linked worktrees), falling back to the current directory name outside git. You normally don't set this by hand; the recipe computes it.
3. **`.env.local`** — required by `yarn dev` via `dotenvx`. Git worktrees don't inherit `.env.local` from the main checkout, so the recipe copies it from the main checkout if it's missing. (Override the source path if your main checkout lives elsewhere.)

## The recipe

```bash
# --- derive a stable project name + main checkout (works in linked worktrees too) ---
COMMON_GIT=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
MAIN_CHECKOUT=$(dirname "$COMMON_GIT")
PROJECT=$(basename "$MAIN_CHECKOUT")
case "$PROJECT" in ""|"."|"/") PROJECT=$(basename "$PWD"); MAIN_CHECKOUT=$PWD ;; esac

SUFFIX=732                           # ← the suffix you picked (see "Inputs")
APP_NAME="$PROJECT-$SUFFIX"          # portless app name, e.g. siegl-app-732
PORTLESS_URL="https://$APP_NAME.localhost:1355"  # portless's default HTTPS port is 1355

# .env.local — yarn dev needs it (via dotenvx); worktrees don't inherit it, so copy from the main checkout
test -f .env.local || cp "$MAIN_CHECKOUT/.env.local" .env.local

# DevTools port — see "Picking a DevTools port" below.
DEVTOOLS_PORT=$((42000 + SUFFIX % 1000))
# Avoid the default 42069 collision if the suffix mod 1000 happens to be 69.
[ "$DEVTOOLS_PORT" = "42069" ] && DEVTOOLS_PORT=42070

BETTER_AUTH_URL="$PORTLESS_URL" \
BETTER_AUTH_TRUSTED_ORIGINS="$PORTLESS_URL" \
DEVTOOLS_PORT="$DEVTOOLS_PORT" \
portless "$APP_NAME" yarn dev
```

Run it via `run_in_background: true` so the chat stays free for further work; the dev server stays up until the user stops it (or you call `TaskStop`).

App will be reachable at `https://<project>-<suffix>.localhost:1355` (e.g. `https://siegl-app-732.localhost:1355`).

## Why each env var

| Variable | Why it's needed |
|---|---|
| `BETTER_AUTH_URL` | better-auth uses this as its canonical base URL for session cookies, redirects, OAuth callbacks. If unset, cookies are scoped to `localhost`, not `*.localhost`, and auth breaks behind portless. Must include scheme and port. |
| `BETTER_AUTH_TRUSTED_ORIGINS` | Server-side allow-list for incoming origins. The server env schema validates it as `z.url().array()` after splitting on `;` (in siegl-app: `app/modules/env/server.ts`) — entries **must** be full URLs (scheme + host + port), bare hostnames fail validation. Multiple entries separated by `;`. |
| `DEVTOOLS_PORT` | TanStack DevTools event bus port. Defaults to `42069`. Two dev servers on the same machine can't share it; collisions throw `EADDRINUSE`. Pick a per-suffix value so worktrees don't clash. |

## Picking a DevTools port

Formula: `42000 + (suffix mod 1000)`. Examples:

| Suffix | Port |
|---|---|
| 732 | 42732 |
| 729 | 42729 |
| 1234 | 42234 |
| 50 | 42050 |

Collisions to avoid:
- `42069` is the default — if your formula lands there (suffix mod 1000 == 69), bump by one.
- If the port is held by something else (`lsof -nP -iTCP:$DEVTOOLS_PORT -sTCP:LISTEN` shows a listener), try `+10` increments until free. Don't kill processes you didn't spawn this session — they may be other agents' dev servers.

## Verifying it came up

After starting, watch the output file. Success looks like:

```
-- Proxy is running
-- <project>-<suffix>.localhost (auto-resolves to 127.0.0.1)
-- Using port <internal>
  -> https://<project>-<suffix>.localhost:1355
Server is running on http://localhost:<internal>
```

Failure modes to recognise in the output:

| Symptom | Cause | Fix |
|---|---|---|
| `EADDRINUSE: ... :::42069` | Leftover dev server holding default DevTools port | Set `DEVTOOLS_PORT=` to a free one (per formula above) |
| `Invalid environment variables [...path: ['BETTER_AUTH_TRUSTED_ORIGINS', 0], message: 'Invalid URL']` | Origin was passed as a bare hostname | Use full URL with `https://` scheme and port |
| `Cannot find module '../../.env.local'` (or env validation fails for `DATABASE_URL`/`BETTER_AUTH_SECRET`/etc.) | `.env.local` missing in the worktree | Copy it in from the main checkout |
| Hangs at "Starting development server" with no further output for >30s | Vite SSR error suppressed early — read the full output file | Check the output file's tail for stack traces |

## Notes

- Portless's HTTPS port (`1355`) is fixed and shared across all portless apps on the machine — that's the point. Each `portless <name>` registers an additional name on the same proxy.
- The first time you start portless on a new machine, it may install a local CA / write to `/etc/hosts`. That's a one-time prompt; once done, `<name>.localhost` works for any name without further config.
- Don't run `yarn dev` directly on `http://localhost:3000` *and* through portless at the same time — better-auth's URL won't match and sessions won't survive a redirect. Pick one.
