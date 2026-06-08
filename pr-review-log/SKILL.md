---
name: pr-review-log
description: Summarize the GitHub PR reviews you submitted on a repo over a time window — grouped by PR with issue numbers, local-time review sessions, event counts, and approve/changes-requested verdicts. Defaults to last week (the previous Mon–Sun). Use when the user asks "what reviews did I do", "list/show my PR reviews", "my review activity/log", wants their reviews for some period, or wants to mark or exclude their own PRs.
---

# PR review log

Reports the pull-request reviews a GitHub user submitted on a repository within a date
window, grouped by PR. For each PR it shows the linked issue, the author (yours are marked
`★ you`), the times you reviewed (clustered into sessions in **local** time), how many
review events there were, and your final verdict (approved / changes requested).

The work is done by the bundled script — `fetch_reviews.py` in this skill's directory
(e.g. `~/.claude/skills/pr-review-log/fetch_reviews.py`). It only reads GitHub (`gh`
read-only), never writes.

## Steps

1. **Resolve the repo** (the script never hardcodes one). In order:
   1. **Current project** — if the working directory is a GitHub repo, the script
      auto-detects it via `gh repo view`. You can pass it explicitly with
      `--repo owner/repo` (derive from `git remote get-url origin` if needed).
   2. **Memory** — if there's no current repo, check the user's memory for the repo
      they usually mean.
   3. **Ask** — if still unknown, ask the user for `owner/repo`. Don't guess.
2. **Resolve the window.** Default is **last week** (previous Mon–Sun) — run with no date
   flags. Otherwise translate the user's phrasing into `--since` / `--until`
   (`YYYY-MM-DD`, inclusive, local dates):
   - "this week" → `--since <this Monday>`
   - "yesterday" / "today" → `--since`=`--until`=that date
   - "last N days" → `--since <today−N+1>`
   - "in <month>" / "between X and Y" → the matching `--since`/`--until`
   - Only `--since` given → window runs to today; only `--until` → 7-day window ending then.
3. **Run it.** Reports the authenticated `gh` user by default; pass `--login <user>` for
   someone else.
   ```bash
   python3 ~/.claude/skills/pr-review-log/fetch_reviews.py            # last week, current repo
   python3 ~/.claude/skills/pr-review-log/fetch_reviews.py --repo owner/repo --since 2026-06-01 --until 2026-06-07
   ```
4. **Present** the Markdown table the script prints. Make the PR numbers links
   (`https://github.com/<repo>/pull/<n>`). Then offer follow-ups: filter to peer reviews
   only (`--exclude-own`), only your own (`--only-own`), or other formats (`--format raw`
   for per-event timestamps, `--format csv`).

## Flags

| Flag | Meaning |
| --- | --- |
| `--repo owner/repo` | Target repo (default: current dir's GitHub repo) |
| `--login user` | Whose reviews (default: authenticated `gh` user) |
| `--since` / `--until` | Inclusive local dates `YYYY-MM-DD` (default: last week) |
| `--exclude-own` / `--only-own` | Drop / keep only PRs the user authored |
| `--gap-minutes N` | Session split threshold (default 45) |
| `--format md\|csv\|raw` | Output shape (default `md`) |

## Notes

- **Times are local** (the machine's timezone, DST-correct); the header states which.
- **Why so many "events"?** GitHub records a separate review object for each inline
  comment submitted on its own, so a single sitting can be 10–25 events. The script
  groups events within `--gap-minutes` of each other into one session and shows the span;
  the raw count stays in the **Events** column.
- **Reviewing your own PR**: GitHub lets you leave review *comments* on your own PR (no
  formal approve/changes), so your own PRs show up. They're marked `★ you` — use
  `--exclude-own` to drop them.
- **Issue number** is derived from the PR title (`#123`), else the branch
  (`feat/123-…`), else a `Fixes/Closes/Resolves/Relates #123` line in the body; `?` if
  none found.
- **Coverage**: candidate PRs come from `gh search prs --reviewed-by` capped at 300 most
  recently-updated. Plenty for a week; for very long-ago windows some older PRs could be
  missed.
