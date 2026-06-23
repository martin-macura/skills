---
name: review-queue
description: List open GitHub PRs that are awaiting my review or that I could pick up — each with its bound issue, my review state, and a verdict of whether it's waiting on me or on the author; optionally queue /parallel-review tasks for the ones I haven't reviewed. Use when the user asks "what PRs are waiting on me", "my review queue/inbox", "what should I review", "PRs awaiting my review", "PRs I could review", or says "/review-queue".
---

# Review queue

Produces a triage report of open pull requests from **my reviewer's point of view**: which PRs are
waiting on **me**, which are back on the **author**, and which I'm **not assigned to but could pick
up**. For each it checks the bound issue, my latest review state, and whether the other side has
reacted since. Optionally queues a `/parallel-review PR <n>` task for any PR awaiting my first review.

This is the forward-looking counterpart to `pr-review-log` (which summarises reviews I've *already
submitted*) and feeds `parallel-review` (which actually reviews a PR).

## Constraints (hard rules)

- **Read-only GitHub only**: `gh pr list`, `gh pr view`, and GET-only `gh api`. NEVER perform any
  GitHub write (no comments, reviews, approvals, edits, labels, assignments, merges, or
  `gh api -X POST/PATCH/PUT/DELETE`). The only things this skill creates are local task chips.

## Step 0 — Resolve identity & repo

- My GitHub login: `gh api user --jq .login` (e.g. `2bad2furious`).
- Target repo: `gh repo view --json nameWithOwner -q .nameWithOwner` from the current directory; if
  not in a repo, default to `softero-cz/siegl-app`.

Call my login `ME` below.

## Step 1 — List open PRs

```
gh pr list --repo <REPO> --state open --limit 100 \
  --json number,title,author,headRefName,isDraft,reviewRequests,reviewDecision,updatedAt
```

Partition: drop PRs authored by `ME` (never report my own). The rest are candidates.

## Step 2 — Section "PRs awaiting / in my review"

Include candidates where I am or have been a reviewer — I appear in `reviewRequests`, **or** I have
already submitted at least one review. For each, fetch detail:

```
gh pr view <n> --repo <REPO> --json number,title,author,url,headRefName,body,\
closingIssuesReferences,reviews,reviewRequests,commits,comments
```

Report one row per PR with:

- **Issue binding** — bound if `closingIssuesReferences` is non-empty, **or** the body has a closing
  keyword (`Fixes/Closes/Resolves #N`) or a `Relates: #N` trailer. Cross-check the branch pattern
  `<feat|fix>/<issue>-...`. Flag mismatches explicitly: `bound #N`, `branch implies #N but not linked`,
  `#N via Relates only (not a closing link)`, or `no bound issue`.
- **My review** — latest review state from `ME` (APPROVED / CHANGES_REQUESTED / COMMENTED) + date, or
  `none`. **A `PENDING` review is an unsubmitted draft — treat it as "no submitted review" (i.e. still
  a first review owed by me), but note the draft exists.**
- **Reaction** — if I have a *submitted* review, whether the author acted since my latest review
  timestamp: a `commits` entry with `committedDate` after it, or a comment from the author after it.
  (Review-thread replies need GraphQL; commits + issue comments are a sufficient heuristic — say so if
  uncertain.)
- **Verdict**:
  - No submitted review from me → ⏳ **waiting on me (first review)**.
  - My latest review CHANGES_REQUESTED/COMMENTED **and** author pushed/replied since → ⏳ **waiting on
    me (re-review)**.
  - My latest review CHANGES_REQUESTED/COMMENTED **and** author has not responded → 👤 **waiting on
    author**.
  - My latest review APPROVED → ✅ **approved** (waiting on author/merge; note if commits landed after).

If the section is empty, say so.

## Step 3 — Queue review tasks (for the "first review" cases)

For every PR whose verdict is ⏳ **waiting on me (first review)** — i.e. no *submitted* review from me:

- **Dedup first.** Skip if a review task for that PR already exists (a pending task chip or a session
  whose title references `PR <n>` / `#<n>` — check via session list if available). Re-queue only if the
  author pushed new commits (head SHA changed) since the task was made.
- Create a background task chip (spawn_task) with prompt **exactly** `/parallel-review PR <n>` and a
  title like `Review PR #<n> (<short title>)`.
- Do **not** auto-queue re-review cases (I already have a submitted review) — list them and offer
  `/parallel-review PR <n>` instead, since the user's rule is "queue only when there's no review from
  me and no existing task".

**Interactive vs unattended:** when run unattended (e.g. from a scheduled task), auto-queue with the
dedup above. When a human is in the loop, you may instead just list the candidates and ask before
spawning chips — keep it to a one-line offer, don't block the report.

## Step 4 — Section "Could review"

Candidates where I am **neither** a requested reviewer **nor** have submitted any review. For each:
number, title, author, URL, bound issue, and a note for drafts / stale PRs (last activity). If empty,
say so.

## Output

A concise markdown report (GitHub-flavored) with a one-line summary first
(e.g. `3 waiting on me · 2 re-review · 4 could-review`), then the two sections as tables, then a short
"tasks queued / available" note from Step 3. Never list my own PRs. Use clickable PR links.
