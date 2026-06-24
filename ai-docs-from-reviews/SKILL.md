---
name: ai-docs-from-reviews
disable-model-invocation: true
description: Scan recent PRs and the comments/fixes their reviewers left, distil the recurring issues into rules, and fold the genuinely-missing ones into the repo's AI-docs file (AGENTS.md / CLAUDE.md) so they stop recurring. Read-only on GitHub; only edits the local AI-docs file. Invoke explicitly via /ai-docs-from-reviews — never auto-triggered.
---

# AI docs from reviews

Turn the feedback reviewers left on recent PRs into durable AI-docs rules. The point is
**prevention**: a reviewer flagged the same class of mistake across several PRs, so the rule
that would have caught it belongs in the repo's agent instructions.

This skill is **explicit-invocation only** (`disable-model-invocation: true`) — it edits a
checked-in docs file and spends a chunk of `gh` calls, so it runs only when the user asks.

The data gathering is done by the bundled script — `fetch_review_findings.py` in this
skill's directory (e.g. `~/.claude/skills/ai-docs-from-reviews/fetch_review_findings.py`).
It only reads GitHub (`gh` read-only), never writes.

## Steps

1. **Resolve the repo** (the script auto-detects from the current dir via `gh repo view`;
   pass `--repo owner/repo` to override). If the cwd isn't a GitHub repo, check the user's
   memory for the repo they usually mean, else ask — don't guess.

2. **Resolve the AI-docs file** to edit, in order: `AGENTS.md` at repo root → root
   `CLAUDE.md` → `~/.claude/CLAUDE.md`. **If a synced `AGENTS.md` exists** (header says
   "Edit AGENTS.md only" / a pre-commit hook mirrors it), edit **only** `AGENTS.md` — see
   *Syncing* below. Read the whole file first; you must know what rules already exist before
   proposing any.

3. **Gather findings.** Default window is the **last 30 days**, the user's own PRs:
   ```bash
   python3 ~/.claude/skills/ai-docs-from-reviews/fetch_review_findings.py
   ```
   Translate any window the user gives into `--since` / `--until` (`YYYY-MM-DD`, local).
   Use `--all-authors` to learn from every PR, `--humans-only` to drop bot/Copilot
   reviewers, `--format json` if you'd rather post-process. The script groups every inline
   comment and review summary left by *someone other than the PR author*, per PR.

4. **Synthesise recurring patterns.** Read across all PRs and cluster the comments into
   issue categories. **Prioritise patterns that recur across 2+ PRs** — a one-off nit isn't
   worth a rule unless it points at a deeper trap. For each cluster note: the anti-pattern,
   the correct pattern / fix reviewers asked for, and how many PRs showed it. For a large
   window, a parallel fan-out (one agent per PR to extract, one to synthesise) speeds this
   up — but only if the user has opted into workflows; otherwise do it inline.

5. **Cross-reference against the existing AI-docs — this is the key judgment.** Split the
   clusters into two buckets:
   - **Already covered** by an existing rule but still violated → do **not** restate it.
     Restating a rule the agent already ignores adds noise, not signal. Note these to the
     user separately (the rule exists; it's a compliance gap, not a docs gap).
   - **Genuinely missing** (no rule, or a rule too weak/descriptive to bind) → these are the
     candidates. Also upgrade a soft mention to a `MUST`/`MUST NOT` when reviewers kept
     hitting it (e.g. a descriptive "use data-testid" → "MUST add data-testid to every new
     interactive element").

6. **Propose, then apply.** Show the user the candidate additions as a short diff with the
   PR evidence behind each (which reviewers, which PRs). In auto/unsupervised mode apply the
   well-evidenced ones directly; otherwise get a nod first. Edit in place, matching the
   file's existing section, voice, and `MUST`/`SHOULD` phrasing — slot each rule into the
   right existing section (Prohibitions, Drizzle, tRPC, …), don't bolt on a new "from
   reviews" section. Keep each rule one tight line; cite the concrete trap, not a vague
   principle.

7. **Sync & commit** (see below). Then summarise: rules added, and the "already-covered but
   still violated" compliance gaps as a separate list.

## Syncing the AGENTS.md mirror

Some repos (e.g. siegl-app) keep `AGENTS.md` as the source of truth and mirror it to
`CLAUDE.md` + `.github/copilot-instructions.md` via a pre-commit hook. **Edit `AGENTS.md`
only.** The hook regenerates the mirrors on commit — **but it lives at `.githooks/` and is
wired by `git config core.hooksPath .githooks` (the `prepare` npm script), which often
hasn't run in a fresh worktree.** If the mirrors didn't update on commit, sync them by hand
and amend/add:
```bash
cp AGENTS.md CLAUDE.md && cp AGENTS.md .github/copilot-instructions.md
```
CI (`yarn test:ai`) enforces byte-equality, so committing `AGENTS.md` without the synced
mirrors fails the build.

## Guardrails

- **GitHub is read-only here.** The script and every step use read-only `gh` only. Never
  post comments, never edit PRs/issues — repo rules forbid `gh` writes outright.
- **Commits are AI-attribution-free** (no `Co-Authored-By` / "Generated with"). If the repo
  uses GitMoji + a `Relates: #<issue>` trailer, follow it; derive the issue from the branch
  name when there is one. Use `git push`? No — leave pushing to the user.
- **Don't invent rules the reviews don't support.** Every added rule must trace to real
  reviewer comments in the window. If the harvest is thin, say so rather than padding.

## Flags

| Flag | Meaning |
| --- | --- |
| `--repo owner/repo` | Target repo (default: current dir's GitHub repo) |
| `--author user` | Whose PRs to scan (default: `@me`) |
| `--all-authors` | Scan PRs by anyone, not just `--author` |
| `--since` / `--until` | Inclusive local dates `YYYY-MM-DD` (default: last 30 days) |
| `--humans-only` | Exclude bot / Copilot reviewers |
| `--limit N` | Max PRs to consider (default 80) |
| `--format md\|json` | Output shape (default `md`) |
