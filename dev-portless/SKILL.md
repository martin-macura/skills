---
name: dev-portless
description: Start a project's dev server behind portless so it gets a stable named .localhost URL — handles per-worktree env, isolated DevTools ports, and the auth env vars better-auth needs. Use when the user asks to run/start the dev server, says "/dev-portless", or wants to preview a worktree in the browser.
---

# dev-portless

Start `yarn dev` behind [portless](https://www.npmjs.com/package/portless) so the app is reachable at a per-task `.localhost` URL, the TanStack DevTools server doesn't collide with other dev servers, and better-auth accepts the proxied origin.

The portless app name is derived from the **project** and the **current branch** (`<project>-<branch-slug>`, e.g. `siegl-app-728-admin-filtration`), so the URL is self-describing, stable per worktree, collision-free across branches, and works in any of your repos without editing — nothing is hardcoded.

## When to use

The user wants to run the app locally — typically to verify a change, walk through a flow manually, or hand a URL to someone (themselves on another device, a reviewer, etc.). They may say "run the dev server", "start dev", "open the app", "/dev-portless".

If the user just wants `yarn dev` raw on `http://localhost:3000`, follow that instruction instead. This skill is for the portless workflow.

Once the server is up, the recipe opens the URL in **Chrome Canary** automatically (see "Opening in Chrome Canary") — **unless you (Claude) are the one reviewing the app**, in which case skip the open entirely (see "Who's looking: you vs. the user").

## Who's looking: you vs. the user

Decide the audience before running, and set `OPEN_BROWSER` accordingly:

- **The user wants to look** — they asked to preview a worktree, walk a flow, or get a URL to hand off. Auto-open Chrome Canary (`OPEN_BROWSER=1`, the default).
- **You (Claude) want to look** — you're starting the server so *you* can review/screenshot/drive the app yourself through the preview MCP tools (`mcp__Claude_Preview__*`) or Claude-in-Chrome. **Do not** call `open` — popping Chrome Canary on the user's screen is noise they didn't ask for. Set `OPEN_BROWSER=0`, then point your own preview tooling at `$PORTLESS_URL`.

When in doubt — e.g. the request is "see if the app works" with no stated audience — assume you're reviewing it yourself and skip the open; surface the URL in chat so the user can open it too if they want.

This skill assumes the project's stack: `yarn dev` with env loaded via `dotenvx` (`.env.local`), better-auth, and TanStack DevTools. Adjust the env vars below if a given project differs.

## Inputs you need before running

Everything is derived automatically — you normally run the recipe as-is, no values to pick.

1. **Branch slug** — the recipe slugifies the current git branch (drops the `type/` prefix, lowercases, hyphenates, caps length) into the app-name suffix, e.g. branch `feat/728-admin-filtration` → `728-admin-filtration`, giving `siegl-app-728-admin-filtration`. In detached HEAD it falls back to the worktree directory name (the session-ish identifier). This makes the URL self-describing and keeps parallel worktrees from colliding.
2. **Project name** — derived from the *main checkout's* directory name (stable across linked worktrees), falling back to the current directory name outside git.
3. **DevTools port** — derived from the first number in the slug (usually the issue #), or a stable hash of the slug when the branch has no number. See "Picking a DevTools port".
4. **`.env.local`** — required by `yarn dev` via `dotenvx`. Git worktrees don't inherit `.env.local` from the main checkout, so the recipe copies it from the main checkout if it's missing. (Override the source path if your main checkout lives elsewhere.)

## The recipe

```bash
# --- derive a stable project name + main checkout (works in linked worktrees too) ---
COMMON_GIT=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
MAIN_CHECKOUT=$(dirname "$COMMON_GIT")
PROJECT=$(basename "$MAIN_CHECKOUT")
case "$PROJECT" in ""|"."|"/") PROJECT=$(basename "$PWD"); MAIN_CHECKOUT=$PWD ;; esac

# --- derive a slug from the current branch (detached HEAD → worktree dir name) ---
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
case "$BRANCH" in ""|"HEAD") BRANCH=$(basename "$PWD") ;; esac
SLUG=${BRANCH#*/}                     # drop leading "feat/", "fix/", etc.
SLUG=$(printf '%s' "$SLUG" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-' \
        | sed -E 's/-+/-/g; s/^-//; s/-$//' | cut -c1-40)
SLUG=${SLUG%-}                        # re-trim if the length cap left a trailing hyphen
[ -z "$SLUG" ] && SLUG=dev            # last-resort fallback

APP_NAME="$PROJECT-$SLUG"             # portless app name, e.g. siegl-app-728-admin-filtration
PORTLESS_URL="https://$APP_NAME.localhost:1355"  # portless's default HTTPS port is 1355

# .env.local — yarn dev needs it (via dotenvx); worktrees don't inherit it, so copy from the main checkout
test -f .env.local || cp "$MAIN_CHECKOUT/.env.local" .env.local

# DevTools port — needs a number: first number in the slug (the issue #), else a stable hash. See below.
NUM=$(printf '%s' "$SLUG" | grep -oE '[0-9]+' | head -1)
[ -z "$NUM" ] && NUM=$(printf '%s' "$SLUG" | cksum | cut -d' ' -f1)
DEVTOOLS_PORT=$((42000 + NUM % 1000))
# Avoid the default 42069 collision if NUM mod 1000 happens to be 69.
[ "$DEVTOOLS_PORT" = "42069" ] && DEVTOOLS_PORT=42070

# Audience: 1 = the user wants to look (auto-open Chrome Canary), 0 = you (Claude)
# will review the app yourself via the preview MCP tools — skip the open. See
# "Who's looking: you vs. the user". Default to 1; set to 0 when you're the viewer.
OPEN_BROWSER=${OPEN_BROWSER:-1}

# Open the URL in Chrome Canary once the dev server is actually serving
# (backgrounded waiter, so it never races the boot). -k skips the portless
# self-signed cert check. The portless proxy answers immediately — before
# yarn dev is up — returning 502/404, so opening on mere reachability lands on
# an error page. Loop until the proxy returns a real upstream response (2xx/3xx);
# 502/503/504 = dev server not up yet, 404 = Vite booting, 000 = proxy not
# reachable yet. Give up after ~120s so a crashed boot doesn't wait forever.
# Skipped entirely when OPEN_BROWSER=0 (you're reviewing via your own tooling).
[ "$OPEN_BROWSER" = "1" ] && \
( for _ in $(seq 1 120); do \
    code=$(curl -sko /dev/null -w '%{http_code}' "$PORTLESS_URL"); \
    case "$code" in 2??|3??) open -a "Google Chrome Canary" "$PORTLESS_URL"; break ;; esac; \
    sleep 1; \
  done ) &

BETTER_AUTH_URL="$PORTLESS_URL" \
BETTER_AUTH_TRUSTED_ORIGINS="$PORTLESS_URL" \
DEVTOOLS_PORT="$DEVTOOLS_PORT" \
portless "$APP_NAME" yarn dev
```

Run it via `run_in_background: true` so the chat stays free for further work; the dev server stays up until the user stops it (or you call `TaskStop`). When `OPEN_BROWSER=1` (the default — the user is the viewer) the backgrounded waiter pops the app open in **Chrome Canary** once it's reachable. When you're reviewing the app yourself, run with `OPEN_BROWSER=0` and drive `$PORTLESS_URL` through your preview tooling instead — nothing opens on the user's screen.

App will be reachable at `https://<project>-<branch-slug>.localhost:1355` (e.g. `https://siegl-app-728-admin-filtration.localhost:1355`).

## Opening in Chrome Canary

The recipe auto-opens the URL in Chrome Canary once the **dev server is actually serving** (a 2xx/3xx upstream response) **when `OPEN_BROWSER=1`** (the user is the viewer). It does *not* open on the portless proxy alone being reachable — the proxy answers before `yarn dev` is up and returns a 502/404, so opening then would land Canary on an error page. When you're reviewing the app yourself (`OPEN_BROWSER=0`) nothing opens — use the preview MCP tools against `$PORTLESS_URL` instead. To open (or re-open) it by hand — e.g. after a restart, or to hand the user a copy-pasteable command — use:

```bash
open -a "Google Chrome Canary" "https://<project>-<branch-slug>.localhost:1355"
```

- `-a "Google Chrome Canary"` targets Canary specifically (bundle id `com.google.Chrome.canary`), not the OS default browser. Substitute the actual derived URL (`$PORTLESS_URL` is only set inside the recipe's shell; a fresh `Bash` call won't have it).
- Open it only **after** the dev server is serving — both Canary racing the boot (connection error) and the portless proxy answering before `yarn dev` is up (502/404 error page) produce a broken first load. When opening by hand, wait for the success line in the output, or poll until the URL returns a 2xx/3xx (`curl -sko /dev/null -w '%{http_code}' "$PORTLESS_URL"`).
- Markdown links you surface in chat open in the user's *default* browser, not Canary. So when you give the user the URL, also give them the `open -a "Google Chrome Canary" …` one-liner so they can land in Canary themselves.
- If Canary isn't installed (`ls "/Applications/Google Chrome Canary.app"` fails), fall back to `open "$PORTLESS_URL"` (default browser) and mention it.

## Why each env var

| Variable | Why it's needed |
|---|---|
| `BETTER_AUTH_URL` | better-auth uses this as its canonical base URL for session cookies, redirects, OAuth callbacks. If unset, cookies are scoped to `localhost`, not `*.localhost`, and auth breaks behind portless. Must include scheme and port. |
| `BETTER_AUTH_TRUSTED_ORIGINS` | Server-side allow-list for incoming origins. The server env schema validates it as `z.url().array()` after splitting on `;` (in siegl-app: `app/modules/env/server.ts`) — entries **must** be full URLs (scheme + host + port), bare hostnames fail validation. Multiple entries separated by `;`. |
| `DEVTOOLS_PORT` | TanStack DevTools event bus port. Defaults to `42069`. Two dev servers on the same machine can't share it; collisions throw `EADDRINUSE`. The recipe derives a per-branch value so worktrees don't clash. |

## Picking a DevTools port

Formula: `42000 + (NUM mod 1000)`, where `NUM` is the first number in the branch slug (usually the issue number), or a `cksum` hash of the slug when the branch has no number. Examples (by NUM):

| NUM | Port |
|---|---|
| 728 | 42728 |
| 732 | 42732 |
| 1234 | 42234 |
| 50 | 42050 |

Collisions to avoid:
- `42069` is the default — if the formula lands there (`NUM mod 1000 == 69`), bump by one (the recipe does this).
- If the port is held by something else (`lsof -nP -iTCP:$DEVTOOLS_PORT -sTCP:LISTEN` shows a listener), try `+10` increments until free. Don't kill processes you didn't spawn this session — they may be other agents' dev servers.

## Verifying it came up

After starting, watch the output file. Success looks like:

```
-- Proxy is running
-- <project>-<branch-slug>.localhost (auto-resolves to 127.0.0.1)
-- Using port <internal>
  -> https://<project>-<branch-slug>.localhost:1355
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
