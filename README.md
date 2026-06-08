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
- **[dev-portless](dev-portless/SKILL.md)** — Start a project's dev server
  behind [portless](https://www.npmjs.com/package/portless) at a stable
  `<project>-<suffix>.localhost` URL. Handles per-worktree `.env.local`, isolated
  TanStack DevTools ports, and the better-auth origin env vars. The project name
  is derived from the git repo, so it works in any project without editing.
- **[pr-review-log](pr-review-log/SKILL.md)** — Summarize the GitHub PR reviews
  you submitted on a repo over a time window, grouped by PR with issue numbers,
  local-time review sessions, event counts, and approve/changes-requested
  verdicts. Defaults to last week; resolves the repo from the current project, so
  it works in any project without editing.

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
