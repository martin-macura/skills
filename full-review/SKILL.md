---
name: full-review
disable-model-invocation: true
description: Run BOTH review skills over one committed SHA, in order and to completion — the four-lens `/parallel-review` panel (mechanical sweep, triage, fixes, cockpit) first, then `/qa-swarm` as a second, independent sample over the fixed tree — with one shared preflight, one merged triage and one hand-over, so neither skill can swallow the other as its `$ARGUMENTS`. Use when the user wants "both reviews", "panel + swarm", "full review", or types `/full-review` (optionally followed by a PR number, URL or branch). Explicit command only — model auto-invocation is disabled for the same reason as `/parallel-review`: a spawned reviewer must never be able to start another panel.
---

# Full review (panel, then swarm, one hand-over)

`/qa-swarm /parallel-review` on one line runs **only qa-swarm** — the second name is parsed as its
`$ARGUMENTS` and the panel never starts; the reverse order drops `/qa-swarm` the same way. On
siegl-app PRs #1516–#1545 that silently cost the panel in 13 of 20 sessions. This skill is the one
place where both are guaranteed to run, over the same committed code, with the guarantees neither
sub-skill enforces on its own: a frozen target, a retry for a dead reviewer, one voice per swarm,
a disposition for every finding, and a hand-over that says exactly what ran.

Nothing below re-explains the sub-skills. Each runs **as written in its own SKILL.md**; this file
only fixes the order, the target, the overrides that apply on this repo and machine, and the glue.

## Step 0: Arguments

`$ARGUMENTS` may be a PR number, a PR URL, or a branch — that is the target for **both** skills.
Anything that starts with `/` is a command, not a target: stop and say so ("`/full-review` already
runs both — drop the extra command"). Never pass an argument down to either sub-skill; the target is
resolved here, once.

## Step 1: Lock, freeze, preflight (once, shared by both skills)

1. **Lock.** `TaskList` for an in-progress `full-review:` / `parallel-review:` task or live review
   subagents; if found, stop. Otherwise `TaskCreate` `full-review: <target>` → `in_progress`, and
   `completed` at the end (also on error). If the Task tools are missing in this build, say so once
   and continue — the sub-skills will hit the same gap; do not let them mention it twice.
2. **Clean tree or no review.** `git status --porcelain` must be empty. If it is not, stop and say
   what is dirty; the user decides whether to commit (a WIP commit is fine) or discard. Both panels
   review a SHA, never a tree that is being edited — and nothing edits the tree while any reviewer
   or helper is still running.
3. **Fetch and freeze.** `git fetch origin`. Base is `origin/main` (never the local `main`).
   Target: `gh pr view --json number,author,headRefOid` (read-only) → PR mode, else the local branch
   (`git diff origin/main...HEAD`). Record `reviewed: <full sha>`; every commit after it will be
   listed as unreviewed unless Step 4 read it. Authorship: the user is GitHub `martin-macura`
   (formerly `2bad2furious` — the parallel-review file still says that; treat both as the user).
4. **Preflight FACTS** — deterministic, yours, before any agent, each one line with its command and
   result (`n/a` is a result; silence is not):
   - `git rev-list --count HEAD..origin/main`; if non-zero, a trial merge in a throwaway worktree
     (`git worktree add <absolute path under the main checkout's .claude/worktrees> HEAD`,
     `git merge --no-commit origin/main`): conflicts, files changed on both sides, and the result of
     the unit specs among them plus every spec the diff adds. Remove the worktree afterwards.
   - New `drizzle/*` folder → its `prevId` vs `origin/main`'s newest snapshot **and** vs every open
     PR that adds a snapshot (`gh pr list --state open --json number,headRefName`, fetch, compare).
   - `gh pr list --state open --json number,headRefName,files` → open PRs sharing a file with this
     diff, and for each `git merge-tree --write-tree <their head> HEAD` (fetch the head first).
   - A rule the diff introduces (MUST NOT, lint rule, mock ban) → the grep for the banned pattern
     over the whole tree at HEAD.

   FACTS are findings-in-waiting: they enter the panel's triage in Step 2 as drafted findings, and
   the swarm router gets them as input in Step 3. They are measurements, never a description of
   the change — no lens and no router may learn what the author thinks the diff does.

## Step 2: The panel — `/parallel-review`, complete

Invoke it: call the `Skill` tool with `skill: parallel-review` and **no arguments**. If that call is
ever refused as user-invocable-only, the `disable-model-invocation` flag has come back to
`parallel-review/SKILL.md`: **stop and tell the user**. Do *not* read the file and run the panel
yourself — the refusal message forbids exactly that ("do not replicate this skill's workflow by
other means"), so there is no fallback here, and a `full-review` that quietly reconstructs the panel
is worse than one that says it could not start it. The flag was removed on 2026-09-22 so this step
can work; the recursion it used to prevent is now caught by the panel's own step 1 `TaskList` bail.
The whole skill runs — four lenses spawned in one message, the guard block verbatim, the mechanical
sweep, verification, triage, the own-code fixes with a fix commit, the cockpit, the honesty section.
Skip nothing because "the swarm will look at it too".

Additions the panel does not carry itself:

- **Every lens delivers or is NOT RUN.** A lens ending on `ECONNRESET`, the 600 s watchdog or an
  empty output is re-spawned once, blank. If it fails again: `Review panel: NOT RUN (<lens>,
  <reason>, <time>)` in the summary and in the PR body. Never stop a running lens because you
  "have enough findings"; if a lens must be stopped, first collect every report its helpers already
  wrote (`subagents/agent-*.jsonl` of the session) and aggregate them as that lens's report.
- **FACTS become cards.** A red post-merge spec, a forked snapshot chain, a merge-order hazard with
  an open PR, a rule violated by code `origin/main` brought — each is at least `actionable` or
  `ambiguous` in the panel's triage, never a note under the summary.
- **Rate-limited session.** If this session has already hit a 429 / session limit, spawn the four
  lenses two at a time instead of four at once and say so; the panel is still one pass.
- **Record the result.** `sha_panel` (what the lenses read) and `sha_after_panel` (HEAD after the
  fix commit; equal to `sha_panel` when nothing was fixed or the code is not the user's), the
  cockpit id, and the bucket counts. Do not hand over yet.

## Step 3: The swarm — `/qa-swarm` over the fixed tree, report-only

Invoke this one with the `Skill` tool: `skill: qa-swarm` and **no arguments**. Unlike the panel,
qa-swarm carries no `disable-model-invocation`, so the tool call is the right way in; only if it is
missing from the skill list anyway, read `~/.claude/skills/qa-swarm/SKILL.md` in full and follow it.
Run it **after** the panel finished (lenses, helpers and fix
commit included), never concurrently: each panel lens may fan out into
`/code-review`'s angles, and a second orchestrator on top of that is the shape that deadlocked the
panel at ~30 agents.

The target is **`sha_after_panel`** — `git diff origin/main...HEAD` at that point — so the swarm is
a second blank sample of the final diff and the only reviewer of the panel's own fixes.

Overrides that apply on this repo and this machine (the sub-skill file is unchanged; these win
where they differ from it):

- **Blank router.** The router prompt is the diff, the changed-file list, the commit log and the
  FACTS lines from Step 1 — nothing else. No "what this change does", no list of files to focus on,
  no danger hint, and nothing the panel found. The router is a second sample; a router that knows
  the panel's cards confirms them and looks nowhere else.
- **Roster reality.** Say in the summary header which delegation targets resolved and which did
  not (`qa-team` has never been on disk here, `security-audit` needs the PostHog MCP, `glm-5.2`
  is not pinnable → router runs on `sonnet`). When the router delegates nothing and the diff touches
  its own danger rubric — payments, receipts, PII, a migration or a removed constant, auth/secrets/
  TLS/webhooks, generated docs, lint rules or hooks — dispatch **one** `general-purpose` reviewer on
  `opus` yourself, blank, scoped to that surface, with the matching framing (security, deploy story,
  correctness under failure, reader, tooling), and say `forced delegation: <framing> — router
  declined`. A router-only run over such a diff is one sonnet reading a diff, and the summary must
  not call it a multi-perspective review.
- **No GitHub writes.** On a repo whose AGENTS.md forbids agent writes (siegl-app does, and a local
  hook blocks `gh pr comment` / `gh pr review`), qa-swarm's Step 5 is **not executed**. Build the
  round as **one review** exactly as qa-swarm Step 5 describes — the 5b summary as the review body,
  the 5a inline comments with the bot header in `comments[]`, `event` `COMMENT` unless the user asks
  for `APPROVE` / `REQUEST_CHANGES` (then the user's own note tops the body, above the summary).
  Write the JSON payload plus a readable `qa-swarm-<short sha>.md` to the worktree's gitignored
  `docs/superpowers/review/` (the user's shell cannot see the session scratchpad), and draft the
  **single** `gh api …/pulls/<n>/reviews --method POST --input <json>` command. Never a separate
  summary comment next to the review, never an approve as its own review — one round, one review
  (user decision, #1639, 2026-09-29). Do this even when no PR exists yet, so the file can be posted
  once the PR is open. Never "fall back" to individual comments to get past the hook — that is the
  same write.
- **Verdict tier always printed**, terminal and file, even with no PR.
- **A dead router** is re-spawned once; a second failure is `qa-swarm: NOT RUN (<reason>)` in the
  hand-over, with the command to rerun. FACTS alone are never reported as a swarm result.

## Step 4: Merge the swarm into the panel's triage

The swarm's findings go through the panel's own "Verification before triage" and "Triage" sections
— the same buckets, the same evidence rule, the same cockpit:

- **One voice.** The router and its delegates together are **one** entry in a card's `agents`
  list — a delegate pointed at a hunk because the router found something there confirms, it does
  not converge. A swarm finding that matches a finding the panel already fixed is a confirmation:
  note it on the archived card, do not open a new one.
- **Own code:** fix `actionable` + `nit`, test in the same commit as its fix, commit (GitMoji +
  `Relates: #<issue>`), archive into the **same** cockpit (same id) with `change` blocks; new
  `ambiguous` cards go live next to the panel's. Someone else's PR: report only, nothing touched.
- **Fix-increment check, once.** After the swarm's fix commit lands, re-run the panel's mechanical
  sweep over `git diff <sha_after_panel>..HEAD`, and spawn one fresh `general-purpose` agent (opus,
  label `review:fix-increment`) with only that diff, the panel's guard block verbatim, and this
  lens: *"These commits are fixes made in reaction to a review. Look only for what the fix broke,
  half-did or skipped: a gate changed on one side (client vs server) but not the other; a path that
  used to work and is now hidden; an early exit that now skips a step below it; a mock wider than
  the test that needed it; a test that pins the old behaviour; a comment, docblock or PR body
  sentence the fix made false; a convention the new code misses."* Then typecheck, lint and the
  affected unit specs — gated, `throttled -w 8m --then fail zsh -c '<chain>'`, per the sub-skills'
  *Heavy commands* section; running both skills back to back means this machine has had no quiet
  stretch for a while. This is bounded and not a second panel; the panel itself never runs twice.
- **Every finding has a disposition.** Each finding of every lens, helper, router or delegate ends
  as fixed (sha) / ambiguous (card) / deferred (named in the PR body) / dismissed (with the command
  and output that killed it). The dismissed list is a section of the hand-over, "Zvážené
  a zahozené", and its length matches the count in the prose. A NIT is not exempt.

## Step 4b: Show it — check in the browser, attach what the reader needs

Two rules, both conditional, both applied before the cards are final:

- **Check it in the running app when you can.** A finding about what the app shows or does — a
  tile, a dialog, a flow, the state after an action, a layout — is reproduced in the real app, not
  only in jsdom or by reading code: a unit harness mounts one component, and the parent chain (what
  stays mounted after a status change, what else refetches, what the server really answers) is
  exactly where such a claim breaks. The cheap route on siegl-app is an **untracked** repro spec next
  to the PR's own e2e spec, reusing its fixture and helpers, in the session's own worktree (the Write
  hook refuses any other, even a throwaway one): `yarn bin playwright` must point inside the worktree
  (else `yarn install --immutable`), build with the compiler ON, run gated through `throttled` with
  `E2E_BASE_PORT` moved off the default. Measure three variants — head / head + the proposed fix /
  head − the suspected cause — and put that table in the finding: a red head proves the symptom, only
  the other two prove the cause and the fix. Layout and visual claims go through `/dev-portless` and
  the browser tools (or `dev-hires-screenshot`). Mutations are restored from copies, and
  `git status --porcelain` is empty again before the hand-over. When the check is not possible — no
  fixture reaches the state, it needs a real terminal, printer or device, the machine never quiets
  down — the finding says how it *was* measured ("jsdom", "čtením kódu"), so it never reads as
  observed.
- **Attach evidence where it helps the reader — and only there.** Pick by what the reader has to
  see: a **GIF** for a flow or a state that changes after an action; an **element screenshot** for
  layout, spacing, clipping or colour (never a full page with customer data); a **Mermaid diagram**
  for a sequence, state machine or call chain spread over several files (render it once — a parser
  accepts unreadable ones). A finding one sentence already settles gets nothing. The GIF comes from
  the same repro: `test.use({ video: { mode: 'on', size: <viewport> } })` plus a pause between steps,
  a 1 fps `ffmpeg … tile` contact sheet to find the cut, then `fps=8`, width ~540 and
  `palettegen`/`paletteuse` (#1666: 9 s → 1 MB). Put the file on the cockpit card (`images`) so the
  user judges it together with the finding, and for the PR upload it with `/r2-upload` — the only way
  an agent's image reaches GitHub. Before uploading, look at the file itself and get the user's OK
  for anything that resembles personal or customer data, fixture data included; an upload cannot be
  taken back. Say that Softero R2 objects expire after 2 days — for evidence that must outlive the
  round, the user drags the file into the GitHub comment instead.

## Step 5: One hand-over

A single message, after both skills and the fix-increment check:

```
Review panel: RUN (4 lenses @ <sha_panel>) | NOT RUN (<lens>, <reason>)
qa-swarm:     RUN (router=<model>, delegations=<list | none | forced:<framing>>) @ <sha_after_panel> | NOT RUN (<reason>)
reviewed:     <sha_panel> → fixes <sha_after_panel> → swarm fixes <head>; commits after <head>: none | <list, unreviewed>
```

then the bucket counts for both skills (`n actionable fixed, n nits fixed, n ambiguous in the
cockpit, n dismissed`), the FACTS block, the "Zvážené a zahozené" list, the cockpit link, the path
of the qa-swarm review file, and:

- the PR body draft (new PR) or the refreshed body (existing PR) carrying those three lines and a
  re-measured `## Jak ověřit` — plus the ready command to apply it; an offer to regenerate later is
  not a hand-over;
- the evidence from Step 4b: each file's local path, its R2 URL once uploaded, and the finding it
  belongs to — or, per finding that could not be checked in the app, why not;
- the one drafted `gh api …/reviews --input <json>` command that posts the round as a single
  review (summary in the body, findings inline, the user's event and note if they gave one), and, when the diff touched
  `data-testid`s, e2e helpers, routes, tRPC procedures or the driver flow, `gh workflow run e2e.yml
  --ref <branch>` — dispatch it yourself if the workflow exists on `main`; the signoff is the user's,
  and it needs a completed green run over the exact head SHA.

Release the lock. Remove any throwaway worktree.

## Honesty

Say what ran. Two skills, one pass each, in this order, over the SHAs named above — never a loop,
never a second panel folded into the same report. If the panel ran and the swarm did not (or the
other way round), the first line of the hand-over is `full-review: PARTIAL` and says which half is
missing and why; a partial run is never reported as a full review. Helpers, delegates and the router
are not extra reviewers — report four lenses plus one swarm. The lens list, the roster line and the
NOT RUN lines are copied into the PR body, so a human reviewer knows what the code went through
before it reached them.
