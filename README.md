# skills

Personal [Claude Code](https://docs.claude.com/en/docs/claude-code) skills.

Each subdirectory is one skill — a `SKILL.md` (plus any supporting files). Claude
reads a skill's `description` to decide when it applies.

## Skills

- **[act-local-ci](act-local-ci/SKILL.md)** — Run a repo's GitHub Actions
  workflows locally with nektos [`act`](https://github.com/nektos/act),
  including the settings and failure workarounds (architecture flags,
  `--concurrent-jobs 1`, the `upload-artifact@v4` `mime_type` breakage) that make
  it actually work.
- **[ai-docs-from-reviews](ai-docs-from-reviews/SKILL.md)** — Scan recent PRs and
  the comments reviewers left on them, distil the recurring issues into rules, and
  fold the genuinely-missing ones into the repo's AI-docs file (AGENTS.md /
  CLAUDE.md) so they stop recurring. The key judgment is separating "already
  covered but still violated" from "genuinely missing" — only the latter become
  new rules. Read-only on GitHub; explicit `/ai-docs-from-reviews` invocation only.
- **[dev-portless](dev-portless/SKILL.md)** — Start a project's dev server
  behind [portless](https://www.npmjs.com/package/portless) at a stable
  `<project>-<suffix>.localhost` URL. Handles per-worktree `.env.local`, isolated
  TanStack DevTools ports, and the better-auth origin env vars. The project name
  is derived from the git repo, so it works in any project without editing.
- **[figma-pixel-perfect](figma-pixel-perfect/SKILL.md)** — Implement a Figma
  frame/node pixel-perfectly and prove it: extract the node's raster, metadata,
  and generated code via the Figma MCP, translate every raw px/hex through the
  project's tokens and spacing scale, pin mock data to the design's exact
  values, then converge with an injected difference overlay, pixelmatch, and
  computed-style audits. Ground truth is the Figma raster; generated code is
  only ever a draft.
- **[issue-worklog](issue-worklog/SKILL.md)** — Summarize the GitHub issues you
  worked on in a repo over a time window — each issue's branch/PR with the
  per-day commit time ranges, in local time, plus a done/in-flight status.
  Defaults to last week; resolves the repo from the current project, so it works
  in any project without editing.
- **[parallel-review](parallel-review/SKILL.md)** — Run four independent,
  context-free review subagents in parallel on a PR (or the working diff), one
  lens each and a mix of models, each free to delegate to helpers of its own
  that may not delegate further; then aggregate and triage the combined findings
  into actionable / nits / ambiguous. One pass, no loop. Only applies fixes when
  you authored the PR or explicitly asked for edits; on someone else's PR it
  reports findings and drafts suggestions instead.
- **[pr-review-log](pr-review-log/SKILL.md)** — Summarize the GitHub PR reviews
  you submitted on a repo over a time window, grouped by PR with issue numbers,
  local-time review sessions, event counts, and approve/changes-requested
  verdicts. Defaults to last week; resolves the repo from the current project, so
  it works in any project without editing.
- **[pr-status](pr-status/SKILL.md)** — Show the PRs you authored with their
  review status: the review decision, who's requested to review, each human
  reviewer's latest verdict, draft state, and whether a changes-requested PR is
  still awaiting re-review. Defaults to your open PRs in the current repo.
- **[review-queue](review-queue/SKILL.md)** — The reviewer's-eye counterpart to
  `pr-status`: list open PRs that are awaiting your review or that you could pick
  up, each with its bound issue, your latest review state, and a verdict of
  whether it's waiting on you or the author. Optionally queues `/parallel-review`
  tasks for PRs you haven't reviewed yet. Resolves your login and the repo
  automatically, so it works in any project.
- **[throttled-run](throttled-run/SKILL.md)** — `throttled <command>` runs a
  heavy job (build, suite, e2e, migration) only once the machine's load average
  is under a ceiling; while it isn't, it prints why and retries instead of
  piling a third suite onto a box that is already thrashing. Ships the
  `throttled` script itself — pure bash 3.2 + awk, macOS and Linux, `exec`s the
  command so exit code and streams pass through untouched.

## Install

Symlink each skill into your personal skills directory (`~/.claude/skills`):

```bash
git clone https://github.com/2bad2furious/skills.git
cd skills
for d in */; do
  ln -sfn "$PWD/${d%/}" ~/.claude/skills/"${d%/}"
done
```

Symlinks mean a later `git pull` here updates the installed skills in place.

To install just one:

```bash
ln -sfn "$PWD/dev-portless" ~/.claude/skills/dev-portless
```
