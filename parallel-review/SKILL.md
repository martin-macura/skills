---
name: parallel-review
description: Run THREE independent, context-free code-review subagents in parallel (each prompted with just `/review PR <n>`, or `/review` for uncommitted work), then aggregate and act on the combined findings. Use after creating a PR, after a larger set of changes (e.g. addressing review feedback or resolving a merge), or whenever the user asks for a thorough / multi-agent review, a "triple review", "review with subagents", or to double-check a change before merge.
---

# Parallel review (three fresh subagents)

Spawn **three separate, fresh subagents** whose prompt is **exactly** `/review PR <number>` (or `/review` for uncommitted work) and **nothing else — no context whatsoever**, run them **in parallel**, then aggregate and act on the combined findings. The blank context is the point: independent reviewers that didn't write the code catch what the author rationalizes away, and three of them cut single-agent blind spots and variance.

## When to run

- Right after a PR is created.
- After any larger set of changes — addressing review feedback, resolving a merge/rebase, a multi-file refactor.
- Whenever the user asks to review, double-check, or "use subagents" on a change.

Skip for trivial one-line changes.

## How to run

1. **Resolve the target.** A PR number if one exists (`gh pr view --json number` read-only), else review the working diff (`/review` / `git diff origin/main...HEAD`).
2. **Spawn three `general-purpose` Agent calls in a single message** so they run concurrently. Each agent's prompt is **exactly** `/review PR <n>` (or `/review` for uncommitted work) — nothing else. No "what the change does" paragraph, no lens, no output-format instructions, and above all no conclusions of yours. The blank context is the entire point: the `/review` skill defines its own behavior and output, and the value comes from reviewers who know nothing beyond the diff. The agent's final message is its report.
3. **Aggregate** — merge and dedupe across the three. A finding raised by **any one** counts.

## Acting on findings

- **Authorship gate — do not edit anything unless the user authored the PR or explicitly asked for edits.** Check first (read-only): `gh pr view <n> --json author`. If the author is **not** the user (GitHub: `2bad2furious`) and the user didn't prompt for fixes, **make no changes at all** — no commits, no merges, no branch checkouts that mutate state. Deliverable is then the aggregated findings report plus drafted suggestions (patches/commands the user or the PR author can apply). The points below apply only once that gate passes.
- **Fix anything in-scope** they flag.
- **Valid pre-existing / out-of-scope issues count too** — implement the fix when small and clearly correct, or spin off a task. Don't dismiss a finding just because "this PR didn't introduce it."
- **Contradictions are the user's call.** If the three disagree (e.g. one says soft-skip, another hard-throw), surface the contradiction and let the user decide — don't silently pick one.
  - **Exception:** when the disagreement is a *checkable fact*, verify it instead of escalating. Classic trap: a reviewer flags a "removed X regression" that's actually `main` advancing past the branch base (`git diff main..HEAD` attributes main's additions to your side). When a reviewer flags a removal you didn't make, check whether the branch is behind main first.
- Add tests for gaps the reviewers converge on; re-run typecheck / lint / tests after applying fixes.

## Working on the branch locally (run / verify / edit)

Once the authorship gate passes and you need to run, verify, or edit the PR branch, do it in an **isolated git worktree** — never switch the main checkout onto the PR branch. Switching the primary checkout's branch disrupts the user's workspace and any other agents working in it.

- **Pull latest first.** `git fetch origin <branch>` and base the checkout on the freshly-fetched `origin/<branch>`, so you review the current head — not a stale local copy.
- **Isolated, clean checkout.** `git worktree add <path> origin/<branch>` (detached) or a throwaway branch; the branch must not already be checked out elsewhere. Put `<path>` outside the repo tree to avoid recursive tsconfig / `.claude/worktrees` scanning.
- **Don't disrupt others.** Unique worktree path and unique ports (DevTools / dev-server). Never clobber or remove worktrees, branches, or processes you didn't create this session.
- **Restore + clean up.** Leave the main checkout on the branch you found it; `git worktree remove <path>` when done. A fresh worktree has no `node_modules` — install or share per the project before building/running.

## Honesty

If you only managed to run one agent (or claimed three but ran one), say so and run the full three — don't report a single review as if it were the panel.

## Notes

- This operationalizes the `review-after-pr` memory. Related habits: verify behavioral/business-rule claims against the source of truth (e.g. a legacy/reference implementation) rather than guessing; browser-verify UI behavior where relevant.
- Posting the findings as PR comments is a separate, explicit step — only do GitHub writes when the user/project allows it; otherwise hand the user the reply commands.
