---
name: issue-worklog
description: Summarize the GitHub issues you worked on in a repo over a time window — each issue's linked PR/branch with the per-day commit time ranges (in local time), plus a done/in-flight status. Defaults to last week (the previous Mon–Sun). Use when the user asks "what did I work on last week", "issues I did/closed this week", "my worklog", "commit time ranges for my issues", a timesheet of issues, or says "/issue-worklog".
---

# Issue worklog

Reports the issues a GitHub user worked on in a repo within a date window. For each issue it shows the related branch + PR(s), a status (merged / closed / open PR), and the **per-day time ranges of the commits** on that branch, in **local** time — so you get a timesheet-style view of when each issue was actually worked on.

The work is done by the bundled script — `worklog.py` in this skill's directory (e.g. `~/.claude/skills/issue-worklog/worklog.py`). It only reads GitHub (`gh` read-only) and git, never writes.

## Steps

1. **Resolve the repo** (the script never hardcodes one). In order:
   1. **Current project** — if the working directory is a GitHub repo, the script auto-detects it via `gh repo view`. Pass it explicitly with `--repo owner/repo` (derive from `git remote get-url origin` if needed).
   2. **Memory** — if there's no current repo, check the user's memory for the repo they usually mean.
   3. **Ask** — if still unknown, ask the user for `owner/repo`. Don't guess.
   Run the script from inside the target repo's checkout when you can — that lets it use local git history to find merged PRs and any not-yet-PR'd work. Cross-repo (`--repo` ≠ current dir) still works via `gh` alone.
2. **Resolve the window.** Default is **last week** (previous Mon–Sun) — run with no date flags. Otherwise translate the user's phrasing into `--since` / `--until` (`YYYY-MM-DD`, inclusive, local dates):
   - "this week" → `--since <this Monday>`
   - "yesterday" / "today" → `--since`=`--until`=that date
   - "last N days" → `--since <today−N+1>`
   - "in <month>" / "between X and Y" → the matching `--since` / `--until`
   - Only `--since` given → window runs to today; only `--until` → 7-day window ending then.
   The window filters which **issues** appear (by their `updated` time). Commit ranges still cover each branch's full history, so work that began before the window shows too.
3. **Run it.** Reports the authenticated `gh` user by default; pass `--login <user>` for someone else.
   ```bash
   python3 ~/.claude/skills/issue-worklog/worklog.py            # last week, current repo
   python3 ~/.claude/skills/issue-worklog/worklog.py --repo owner/repo --since 2026-06-01 --until 2026-06-07
   ```
4. **Present** the Markdown the script prints. Make the issue and PR numbers links (`https://github.com/<repo>/issues/<n>`, `…/pull/<n>`). Then offer follow-ups: a flat `--format csv` (one row per issue/day) or `--format raw` (per-commit timestamps), a different window, or `--no-default-excludes` to include epic/meeting/design issues.

## Flags

| Flag | Meaning |
| --- | --- |
| `--repo owner/repo` | Target repo (default: current dir's GitHub repo) |
| `--login user` | Whose issues (default: authenticated `gh` user) |
| `--since` / `--until` | Inclusive local dates `YYYY-MM-DD` (default: last week) |
| `--exclude-label LABEL` | Extra label to drop (repeatable) |
| `--no-default-excludes` | Keep `epic` / `meeting` / `design` issues (excluded by default) |
| `--tz ZONE` | IANA timezone for display, e.g. `Europe/Prague` (default: system / `$TZ`) |
| `--format md\|csv\|raw` | Output shape (default `md`) |

## Notes

- **Times are local** (the machine's timezone, DST-correct per timestamp); the header states which. Override with `--tz` or `$TZ`.
- **Which issues**: those assigned to the user (`assignee:`) and `updated` within the window — the same shape as a "my recently-updated issues" board view. The default excludes the non-implementation labels `epic`, `meeting`, `design`; adjust with `--exclude-label` / `--no-default-excludes`.
- **Per-day ranges** are the first→last commit *author* time that day, grouped by calendar day. Author time (not commit time) is used so a rebase doesn't collapse the timeline; the real start of work is a little before the first commit.
- **Finding the branch/PRs**: open PRs come from `gh pr list` (matched by the `<type>/<issue>-…` branch convention); merged ones also from squash-merge commits in local git (the trailing `(#PR)`). Both `2bad2furious`-style and bot/pair (`claude`) commits count as the issue's work. An issue with no PR falls back to commits that reference it locally; one with neither is listed as "no commits yet".
- **Status** is derived: `merged` (a PR merged) or `closed` (issue closed) = done; `open PR` / `no PR` = in flight. Issues often stay open after their PR merges (no auto-close link), so a `merged` status with an open issue is normal.
- **Coverage**: up to `--limit` issues (200 by default) and the 50 most-recent PRs per issue-number search — ample for a week.
