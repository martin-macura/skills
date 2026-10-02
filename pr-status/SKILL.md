---
name: pr-status
description: Show a GitHub user's authored PRs with their review status — per PR the review decision, who's requested as reviewer, each human reviewer's latest verdict (approved / changes requested / commented), draft state, whether a changes-requested PR is still awaiting re-review, and the project-board column of every issue the PR closes. Defaults to your own open PRs in the current repo. Use when the user asks "what are my open PRs", "status of my PRs", "review status of my PRs", "which of my PRs are approved / blocked / have no reviewer", "board status of my PRs/issues", or says "/pr-status" / "check my PRs".
---

# PR status (authored)

Reports the pull requests a GitHub user **authored** on a repository, with each PR's review
state at a glance: the overall review decision, who is requested to review, each human
reviewer's most recent verdict, whether it's a draft, and — for changes-requested PRs —
whether the blocking reviewer was re-requested (so you can spot ones stalled on you). When a
project board is configured it also adds a **Board** column with the column of every issue
the PR closes, and drafts move-to-"In Review" commands for issues stalled in "In Progress".

The work is done by the bundled script — `fetch_pr_status.py` in this skill's directory
(e.g. `~/.claude/skills/pr-status/fetch_pr_status.py`). It reads GitHub (`gh` read-only) for
the PR, issue, and board data and **never writes** — the move-to-"In Review" commands it
prints are drafts for the user to run.

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
   requested with no re-review, awaiting a named reviewer, no reviewer set). If the script
   printed a **Move to In Review** block (issues "In Progress" on the board where *every*
   open PR closing them has a non-author, non-Copilot reviewer), surface those `gh project
   item-edit` commands verbatim, one per fenced `bash` block and with **no trailing `#`
   comment** — the Run button's runner doesn't strip shell comments, so an inline comment
   becomes a bogus argument; put the issue/PR label on a prose line above each block
   instead. They are GitHub writes the **user** runs, not you. Pass on the
   **Staying In Progress** list too — those name the exact unreviewed PRs holding an issue
   back, which is the next thing to act on. Offer
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
| `--board N` | Project board number for the issue-status column (default: known per-repo board) |
| `--board-owner owner` | Owner of the project board (default: repo owner) |
| `--no-board` | Skip the Board column and move-to-"In Review" commands entirely |

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
- **Board** (only when a board is configured) shows the column of **every** issue the PR
  closes, e.g. `🔧 In Progress (#530)` · `👀 In Review (#1009)`. Issues sharing a column
  collapse onto one line and differing columns stack, so a batch PR reads as
  `🔧 In Progress (#1089, #1093, #1197)<br>👀 In Review (#1192)`. `—` means the PR closes
  no issue, and `#NNN _(not on board)_` means the issue exists but isn't on the board.
- **Move to In Review** block: printed below the summary when one or more issues are
  `In Progress` on the board **and every open PR closing them** has a non-author,
  non-Copilot reviewer (requested or already reviewed) — those are stalled in the wrong
  column. One ready-to-run `gh project item-edit` command per **issue** (a GitHub write the
  user runs), each in its own fenced block with its `Issue #N (PRs #A, #B):` label on a
  prose line above.
- **Staying In Progress** block: the mirror image — `In Progress` issues where part of the
  stack is still unreviewed, listed as `#issue — 3/5 open PR(s) without a reviewer: #A, #B,
  #C`. That's the actionable half: those PRs are what's holding the issue back.

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
- **Board column** is on by default only for repos in the script's `DEFAULT_BOARDS` map
  (currently `softero-cz/siegl-app` → project `#3`, owner `softero-cz`). For any other repo
  pass `--board N [--board-owner owner]` to enable it, or `--no-board` to force it off. The
  board reads need the `read:project` scope; if they fail the script still prints the PR
  table and adds a `> ⚠️ Board status unavailable: …` note instead of erroring out.
- **Linked issues come from GitHub's `closingIssuesReferences`**, i.e. the `Fixes #N` /
  `Closes #N` lines in the PR body — so a batch PR that closes five issues yields five
  board rows and five move commands. The `#NNN` in the PR title and the `<type>/NNN-...`
  branch name are **fallbacks only** (used when GitHub reports no link at all); each
  carries a single number, so relying on them silently hid the other four issues of a
  batch PR. If an issue is missing from the Board column, the PR body is missing its
  `Fixes #N` line.
- **A stacked issue moves only when the whole stack has a reviewer.** Work is often split
  into a stack of PRs that each carry `Fixes #N` for the same issue (e.g. "Vývozy 1/5…5/5").
  The move check is therefore grouped **by issue**, not by PR: one reviewed layer no longer
  drags the issue to "In Review" while four unreviewed ones sit behind it, and the issue's
  single board item yields one command rather than one per PR. Only **open** PRs count — a
  merged layer is done and waiting on nobody — while an unreviewed **draft** does block, on
  purpose: the issue isn't fully up for review yet.
- **Board items are fetched with a limit past the board's total item count.** A board can
  have hundreds of items; a short `item-list` limit silently drops issues and makes them
  show as a false `_(not on board)_`. The script reads the board's `totalCount` first and
  lists with `totalCount + 25`.
- **Move-to-"In Review" is the only write the skill emits, and it's a draft** — the script
  prints the `gh project item-edit` command; the user runs it. The skill never executes
  board edits itself.
- This is the authored-side companion to the `review-queue` skill (PRs awaiting *your*
  review) and `pr-review-log` (reviews you *submitted*). It's read-only — any
  `--add-reviewer` / merge / board-move actions are a separate explicit step the user runs.
