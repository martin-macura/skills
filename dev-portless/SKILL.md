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

The launcher only starts the server — it never opens a browser itself. Once the server actually serves, you open it in the **Claude browser pane** (see "Opening it").

## One surface for both audiences

There is no audience decision to make any more. The Claude browser pane is visible to the user *and* drivable by you, so the same tab serves "the user wants to look" and "you want to screenshot it". Start the server, wait for it to serve, open the pane.

When in doubt — e.g. the request is "see if the app works" with no stated audience — assume you're reviewing it yourself and skip the open; surface the URL in chat so the user can open it too if they want.

This skill assumes the project's stack: `yarn dev` with env loaded via `dotenvx` (`.env.local`), better-auth, and TanStack DevTools. Adjust the env vars below if a given project differs.

## Inputs you need before running

Everything is derived automatically — you normally run the recipe as-is, no values to pick.

1. **Branch slug** — the recipe slugifies the current git branch (drops the `type/` prefix, lowercases, hyphenates, caps length) into the app-name suffix, e.g. branch `feat/728-admin-filtration` → `728-admin-filtration`, giving `siegl-app-728-admin-filtration`. In detached HEAD it falls back to the worktree directory name (the session-ish identifier). This makes the URL self-describing and keeps parallel worktrees from colliding.
2. **Project name** — derived from the *main checkout's* directory name (stable across linked worktrees), falling back to the current directory name outside git.
3. **DevTools port** — derived from the first number in the slug (usually the issue #), or a stable hash of the slug when the branch has no number. See "Picking a DevTools port".
4. **`.env.local`** — required by `yarn dev` via `dotenvx`. Git worktrees don't inherit `.env.local` from the main checkout, so the recipe copies it from the main checkout if it's missing. (Override the source path if your main checkout lives elsewhere.)

## The recipe

Two steps: **(1)** generate a per-app launcher script — once — with the derived values (app name, URL, paths, DevTools base port) and its own pathname inlined; **(2)** run it. On later runs the script already exists, so you skip straight to step 2. All the project/branch derivation happens at generation time and is baked in, so the **script itself only** picks a free DevTools port and starts the server behind portless. It opens nothing: the Claude browser pane is an MCP surface, not something a shell command can reach.

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

# DevTools base port — first number in the slug (the issue #), else a stable hash. See below.
NUM=$(printf '%s' "$SLUG" | grep -oE '[0-9]+' | head -1)
[ -z "$NUM" ] && NUM=$(printf '%s' "$SLUG" | cksum | cut -d' ' -f1)
DEVTOOLS_PORT=$((42000 + NUM % 1000))
[ "$DEVTOOLS_PORT" = "42069" ] && DEVTOOLS_PORT=42070   # avoid the default 42069 collision

# --- launcher lives in the worktree root (one per worktree/branch), its own path inlined ---
SCRIPT="$PWD/dev-portless.sh"

# Always (re)generate so the inlined values track the current branch (one worktree = one branch,
# but a branch switch would otherwise leave stale values baked in). It's generated infra — don't
# hand-edit it; change the skill instead.
{
    printf '%s\n' '#!/usr/bin/env bash' 'set -euo pipefail'
    printf '%s\n' "# dev-portless launcher (generated) — re-run with: bash $SCRIPT"
    printf 'SELF=%q\n'          "$SCRIPT"          # this script's own pathname, inlined
    printf 'APP_NAME=%q\n'      "$APP_NAME"
    printf 'PORTLESS_URL=%q\n'  "$PORTLESS_URL"
    printf 'WORKTREE=%q\n'      "$PWD"
    printf 'MAIN_CHECKOUT=%q\n' "$MAIN_CHECKOUT"
    printf 'DEVTOOLS_PORT=%q\n' "$DEVTOOLS_PORT"
    cat <<'BODY'

cd "$WORKTREE"

# yarn dev needs .env.local; worktrees don't inherit it from the main checkout
test -f .env.local || cp "$MAIN_CHECKOUT/.env.local" .env.local

# pick a FREE DevTools port — bump by 10; never kill a listener we didn't start
while lsof -nP -iTCP:"$DEVTOOLS_PORT" -sTCP:LISTEN >/dev/null 2>&1; do
    DEVTOOLS_PORT=$((DEVTOOLS_PORT + 10))
done

exec env \
    BETTER_AUTH_URL="$PORTLESS_URL" \
    BETTER_AUTH_TRUSTED_ORIGINS="$PORTLESS_URL" \
    DEVTOOLS_PORT="$DEVTOOLS_PORT" \
    portless "$APP_NAME" yarn dev
BODY
} > "$SCRIPT"
chmod +x "$SCRIPT"

# Always keep it out of git via the repo-local exclude (never committed, no tracked .gitignore change).
# In a worktree the exclude path resolves to the shared common git dir via --git-path.
EXCLUDE=$(git rev-parse --git-path info/exclude); mkdir -p "$(dirname "$EXCLUDE")"
grep -qxF 'dev-portless.sh' "$EXCLUDE" 2>/dev/null || echo 'dev-portless.sh' >> "$EXCLUDE"

echo "launcher: $SCRIPT"
echo "app: $APP_NAME   url: $PORTLESS_URL"
```

Then **run the launcher** via `run_in_background: true` (the chat stays free; the server runs until the user stops it or you `TaskStop`). It takes no flags:

```bash
bash "$SCRIPT"          # starts the server; opens nothing — you open the pane yourself
```

App will be reachable at `https://<project>-<branch-slug>.localhost:1355` (e.g. `https://siegl-app-728-admin-filtration.localhost:1355`).

## Opening it

The Claude browser pane is an MCP surface, so *you* open it — the launcher can't:

```
mcp__Claude_Browser__preview_start   { url: "https://<project>-<branch-slug>.localhost:1355" }
```

Use `tabs_create` + `navigate` instead when the pane already holds something that should stay (a cockpit, a comparison page).

- **Wait for a 2xx/3xx first.** The portless proxy answers *before* `yarn dev` is up and returns 502/404, so opening too early lands on an error page. Poll `curl -sko /dev/null -w '%{http_code}' "$PORTLESS_URL"` — `$PORTLESS_URL` only exists inside the recipe's shell, so a fresh `Bash` call needs the literal URL.
- **A blank first page is usually Vite, not a crash.** On a cold worktree Vite re-optimizes deps mid-hydration and blanks the page; the server output says `optimized dependencies changed. reloading`. Navigate again — that's the fix.
- **Markdown links you put in chat open in the user's *default* browser**, not the pane. Surface the URL there anyway, so they can open it where they prefer.

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
