---
name: pr-status
description: Show a GitHub user's authored PRs with their review status — per PR the review decision, who's requested as reviewer, each human reviewer's latest verdict (approved / changes requested / commented), draft state, and whether a changes-requested PR is still awaiting re-review. Defaults to your own open PRs in the current repo. Use when the user asks "what are my open PRs", "status of my PRs", "review status of my PRs", "which of my PRs are approved / blocked / have no reviewer", or says "/pr-status" / "check my PRs".
---

# PR status (authored)

Reports the pull requests a GitHub user **authored** on a repository, with each PR's review
state at a glance: the overall review decision, who is requested to review, each human
reviewer's most recent verdict, whether it's a draft, and — for changes-requested PRs —
whether the blocking reviewer was re-requested (so you can spot ones stalled on you).

The work is done by the bundled script — `fetch_pr_status.py` in this skill's directory
(e.g. `~/.claude/skills/pr-status/fetch_pr_status.py`). It only reads GitHub (`gh`
read-only), never writes.

## Steps

1. **Resolve the repo** (the script never hardcodes one). In order:
   1. **Current project** — if the working directory is a GitHub repo, the script
      auto-detects it via `gh repo view`. Pass `--repo owner/repo` to override (derive
      from `git remote get-url origin` if needed).
   2. **Memory** — if there's no current repo, check the user's memory for the repo they
      usually mean (for this user that's `softero-cz/siegl-app`).
   3. **Ask** — if still unknown, ask for `owner/repo`. Don't guess.
2. **Resolve the author.** Defaults to the authenticated `gh` user (the user's own PRs).
   Pass `--author <login>` for someone else's PRs.
3. **Run it.**
   ```bash
   python3 ~/.claude/skills/pr-status/fetch_pr_status.py                    # your open PRs, current repo
   python3 ~/.claude/skills/pr-status/fetch_pr_status.py --repo softero-cz/siegl-app
   python3 ~/.claude/skills/pr-status/fetch_pr_status.py --author MiranDaniel --state all
   ```
4. **Present** the Markdown table the script prints verbatim — PR numbers are already
   links. Then lead with the actionable summary lines (approved/mergeable, changes
   requested with no re-review, awaiting a named reviewer, no reviewer set). Offer
   follow-ups: draft `gh pr edit <n> --add-reviewer <user>` commands for PRs with no
   reviewer, or drill into a specific PR's review comments.

## Flags

| Flag | Meaning |
| --- | --- |
| `--repo owner/repo` | Target repo (default: current dir's GitHub repo) |
| `--author login` | Whose PRs (default: authenticated `gh` user) |
| `--state open\|closed\|merged\|all` | Which PRs (default `open`) |
| `--limit N` | Max PRs to fetch (default 100) |
| `--format md\|json` | Output shape (default `md`) |

## Reading the output

Each PR shows a **Status** flag and a **Reviewers** cell:

- **Status**: `✅ approved` · `🔴 changes requested` · `⏳ awaiting review` (a named
  reviewer is requested but hasn't verdicted) · `⚠️ no reviewer set` (review required but
  nobody requested and no approval) · `•` (none of the above).
- **Reviewers** lists each human reviewer's *latest* verdict: `✅ <user>` approved,
  `🔴 <user>` requested changes, `⏳ <user>` requested-but-pending, `💬 <user>` only
  commented. `🤖 Copilot only` means just the Copilot bot reviewed; `— none` means nobody.
- A `🔴 <user> (no re-review)` tag flags the case from the user's recurring check:
  the reviewer requested changes and is **not** currently in the pending review-request
  set, so a re-review hasn't been asked for. `(re-review pending)` means they have been
  re-requested.

## Notes

- **Times are local** (machine timezone, DST-correct), shown in the header.
- **Self-comments are ignored** for the verdict — GitHub records the author's own inline
  review-comment replies as review events; the script drops the author and the Copilot
  bot when computing human verdicts (the bot is surfaced separately as `🤖 Copilot only`).
- **`reviewDecision` can be empty** (`•` / `(none)`) when the repo doesn't require review
  for that PR — that's not the same as "no reviewer". The script still shows requested
  reviewers and verdicts in that case.
- **Why not show last-commit date?** Fetching every PR's full commit list blows GitHub's
  GraphQL node budget at higher `--limit`; the **Updated** column (PR `updatedAt`) is the
  lean proxy.
- This is the authored-side companion to the `review-queue` skill (PRs awaiting *your*
  review) and `pr-review-log` (reviews you *submitted*). It's read-only — any
  `--add-reviewer` / merge actions are a separate explicit step the user runs.
