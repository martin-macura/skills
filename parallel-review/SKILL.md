---
name: parallel-review
disable-model-invocation: true
description: Run FOUR independent code-review subagents in parallel — each given the same blank view of the change but a different lens (correctness, martin-reviewer, simplify, MVP parity) and a mix of models, and each free to delegate to helpers of its own, which may not delegate further — then triage the combined findings into actionable / nits / ambiguous, fix the first two on the user's own code (report-only on someone else's PR), and put whatever stays ambiguous into a `/review-cockpit` for the user's call. **One pass, no loop.** Use after creating a PR, after a larger set of changes (e.g. addressing review feedback or resolving a merge), or whenever the user asks for a thorough / multi-agent review, a "triple review", "review with subagents", or to double-check a change before merge. Invoke only via the explicit `/parallel-review` command — model auto-invocation is disabled so a spawned subagent cannot recursively trigger another panel.
---

# Parallel review (four fresh subagents, four lenses)

Spawn **four separate, fresh subagents** on the same diff, run them **in parallel**, then triage and act on the combined findings. **One pass — there is no loop.**

Three properties do the work, and they are not the same thing:

- **Blank context about the change.** No "what this PR does" paragraph, no output-format instructions, and above all none of your conclusions. Reviewers that know nothing beyond the diff catch what the author rationalizes away.
- **Different lenses and different models.** Four identical clones pay for the same blind spot four times. Each reviewer gets exactly one lens paragraph and the panel spans more than one model, so their misses don't line up.
- **Fan-out that goes one level, not a second round.** One panel is a sample, not a verdict — and the answer to that is depth inside the round, not repeating the round. A reviewer may hand helpers slices of its own lens — halves of a large diff, one claim that needs checking against the code — as many as the change actually warrants. The one hard rule is that **helpers never spawn helpers**: the fan-out is exactly one level deep and the panel never runs twice. Both halves of that are scars: the old three-round loop mostly re-raised the first round's cards at three times the spend, and a *recursive* fan-out multiplied itself into ~30 nested agents that deadlocked the panel.

A lens is an instruction about *how to look*, never information about the change. Keep that line clean and the first two properties hold at once.

## When to run

- Right after a PR is created.
- After any larger set of changes — addressing review feedback, resolving a merge/rebase, a multi-file refactor.
- Whenever the user asks to review, double-check, or "use subagents" on a change.

Skip for trivial one-line changes.

## How to run

**All seven steps run exactly once.** There is no second round; [The fan-out rule](#the-fan-out-rule) below says where the extra agents go instead, and the one thing this skill will not spawn.

1. **Bail if a review is already in progress.** Before anything else, call `TaskList` and check whether a parallel-review is already running — an `in_progress` task whose subject starts `parallel-review:` (the lock below), or in-progress review subagents from a prior invocation. If one is active, **stop**: tell the user a review is already in progress and do **not** spawn a second panel — a duplicate concurrent panel wastes tokens and muddles aggregation. To make this detectable across background / automation / `/loop` / `review-queue` runs (where the panel doesn't block a turn), register a lock: `TaskCreate` a `parallel-review: <target>` task, set it `in_progress` before spawning the panel, and `TaskUpdate` it to `completed` when the review ends — one lock for the whole run (release it even if the review errors).
2. **Resolve the target.** Pick the command by what exists — don't push or open a PR just to get a number; review the diff in place:
   - **A PR exists** (`gh pr view --json number` read-only finds one) → `/review PR <n>`.
   - **No PR** — a branch committed ahead of `main` but not yet pushed/opened, *or* uncommitted working-tree changes → `/code-review`. In this setup `/review` alone is GitHub-PR-only; `/code-review` is the working-diff reviewer and resolves the diff itself (committed branch changes vs the base, i.e. `git diff origin/main...HEAD`, plus any unstaged edits). A clean tree with no branch commits ahead of `main` means there's nothing to review — say so instead of spawning a panel.
3. **Resolve authorship now, not later.** `gh pr view <n> --json author` (read-only). The user is GitHub `2bad2furious`. **Own code** = the user authored the PR, *or* the user explicitly asked for fixes, *or* it's a no-PR diff (a local branch or working tree — always theirs). Everything downstream — whether findings get fixed or only reported — branches on this one answer, so settle it before the panel lands. It decides only that: on own code the surviving findings get fixed, on someone else's they are reported and nothing is touched. The panel itself is identical either way, and runs once either way.
4. **Spawn four `general-purpose` Agent calls in a single message** so they run concurrently. Each agent's prompt is assembled from exactly three parts, in this order, and nothing else.

   **(a) The command** resolved in step 2 — `/review PR <n>` or `/code-review`.

   **(b) The guard block, verbatim, identical for all four:**
   > Be **extra critical** — flag every potential issue you see, no matter how minor. When in doubt, report it.
   >
   > You own this review. You may delegate to sub-agents to split the work — half the diff each, one helper per angle, one checking a single claim against the code while you keep reading — as many as this change actually warrants, spawned together in one message. There is no quota: spawning none and reading everything yourself is a good outcome, and so is a handful on a big diff. Size it to the diff, not to the tool.
   >
   > **Anything you spawn is a leaf.** Put this in every sub-agent's prompt, verbatim: *"Do NOT spawn subagents, do NOT use the Agent/Task tools, and do NOT invoke `/parallel-review`, `/code-review`'s multi-angle fan-out, or any other multi-agent / parallel / 'ultra' review mode — if a skill offers a fan-out path, decline it and do the work directly. Treat the Agent tool as if it were absent from your tool set: if the Agent tool is not available in your current tool set, do not error — perform each angle, and each verification, yourself, sequentially, in this context. Report only; do not edit files, commit, or run any write command."*
   >
   > What binds you: the agents you spawn are the last level — you are the only one who fans out. Do **NOT** invoke `/parallel-review` or any "ultra" review mode. `/code-review`'s ~10 angles are fine to spawn as your own leaves; what is not fine is letting any of them fan out again. Report only; do not edit files, commit, or run any write command.

   The leaf rule is the load-bearing half, and the numbers say why. `/code-review` orders a fan-out into ~10 angles; at one level that is ~10 agents under a reviewer, which finishes. Recursive, each of those angles orders its own fan-out — that is what produced ~30 nested agents fighting over slots until the whole panel deadlocked on the 600 s stream watchdog. You can spot the recursive shape in a report by agents nobody launched from here (`Angle A`, `Angle B`, `Angle Reuse`…) appearing *under* an angle rather than beside it. Width is a judgement call the reviewer makes and depth is not negotiable. The escape-hatch sentence stays in the leaf prompt for the reason it always did: without it, an agent that reads "no Agent tool" as an error condition stalls instead of reviewing.

   **(c) One lens paragraph**, different per agent:

   | label | model | lens paragraph appended to the prompt |
   | --- | --- | --- |
   | `review:correctness` | opus | Lens: **correctness under real data**. Boundary and empty cases, `null` vs `0` vs `false` tri-state traps, timezone and DST handling, money as integer cents and rounding at every conversion, transaction boundaries and partial-failure states, error paths and what the caller actually sees, race conditions between a query and the mutation that invalidates it. |
   | `review:martin` | opus | Lens: **the reviewer's own recurring catches**. Does the fixed pattern survive at a twin site (Guess↔Specify, Create↔Edit, other call sites of the touched mutation, sibling list procedures)? Would each new test go red with the fix reverted, or does it pass on a degenerate/all-tied seed? Does any success toast claim more than the server response confirmed? Does the PR body or a new comment assert a quantifier ("all", "only", "never") or a count/version that was not verified? Is the risky half of the diff mocked away in its own spec? |
   | `review:simplify` | sonnet | Lens: **reuse and simplification only** — no bug hunting. An existing helper/type/component that already does this, duplicated logic that wants extracting, an abstraction at the wrong altitude, dead code and unused exports left behind, a hand-rolled loop where a language or repo built-in exists. Report; do not apply anything. |
   | `review:mvp-parity` | opus | Lens: **parity with the legacy MVP**, which is the default answer for any ambiguous business rule. Its source is at `~/projects/softero-cz/mvp` (`logistics-backend`, `logistics-frontend`) — read the code there; a running instance exists only under docker. For every behaviour this diff adds or changes, find the MVP's equivalent and say whether the new behaviour matches, deliberately diverges, or silently drifts. Quote the MVP file:line you compared against. "No MVP equivalent exists" is a valid and useful finding. Divergence is not automatically a bug — an unacknowledged one is. |

   Set the model via the Agent call's `model` option. Use each agent's label as its `label`.
5. **Mechanical sweep (orchestrator-side, while the panel runs).** The four reviewers stay blank — this deterministic layer is yours. Run the greps and checklist in "Mechanical sweep + recurring-classes checklist" below over the diff. It runs **once**, over the diff the panel is reviewing. One exception, on own code: after your own fix commit lands, re-run the greps over it. No panel ever sees your edits — this deterministic pass is the only check they get, and it costs a few seconds.
6. **Aggregate, verify, triage.** Merge and dedupe across the four and fold in the mechanical sweep — a finding raised by **any one** counts, and one raised by several keeps its `agents` list (the cockpit renders it as a "N× nezávisle" badge). **A reviewer's own helpers are not independent voices** — everything under one lens arrives as that reviewer's single report and counts once, whoever inside it actually found it. A lens that split its diff across three helpers and got the same thing back from two of them is 1×, not 2×; inflating that badge is how one agent's opinion starts reading like a consensus. Then run "Verification before triage" and "Triage" below.
7. **Act on the triage.** Own code: fix `actionable` + `nits`, archive them with how they were fixed, and put only `ambiguous` in front of the user. Someone else's: fix nothing, report everything. Go to "Acting on the triage".

## The fan-out rule

**One level, one pass.** Each of the four reviewers may fan out as wide as the change warrants; none
of what they spawn may fan out again, and the panel itself never runs twice. That is the whole rule,
and no branch of this skill bends it:

- **Depth is fixed, width is the reviewer's call.** A lens over a 200-line diff needs no helpers at
  all; a lens over a 40-file migration may want one per area, or `/code-review`'s ~10 angles as its
  own leaves. Both are fine. What is never fine is a helper that spawns a helper.
- **Helpers are leaves, and the reviewer makes them so.** The guard block carries the verbatim
  no-fan-out paragraph the reviewer must paste into every sub-agent prompt. That paragraph is the
  mechanism — the reviewer's own good intentions are not.
- **Split the input, not the review.** The shapes that pay: *a slice of the diff each* (same lens,
  different files) and *one helper verifying one claim* — an MVP comparison, a "is this really
  removed" check — while the reviewer keeps reading. Several helpers re-running the same lens over
  the same files is many agents doing one agent's work.
- **Helpers stay blank too.** They get the lens and their slice, never "what this PR does" and never
  what the reviewer already suspects. It is the panel's own property, one level down.
- **One report per reviewer.** The reviewer folds its helpers' findings into its own report. You
  aggregate four reports however many agents produced them — see step 6 on why they still count as
  four voices.

**There is no loop.** One panel, one triage, one set of fixes, hand over. If the user wants another
sample after a big fix round they say so, and running `/parallel-review` again — a fresh blank panel
on the new diff — is a perfectly good answer. It is never automatic, never scheduled by this skill,
and never announced as "kolo 2" on your own initiative.

Say the honest version of what that buys: **one sample of the diff, not a verdict**. Sampling three
times used to be the default and is not any more — most of what the later rounds reported was the
first round's cards again, and the genuinely new ones did not pay for two more panels plus the ledger
bookkeeping needed to dedupe them. So the summary says *"jeden průchod, čtyři recenzenti"*, never
anything that implies the change was swept until clean.

### Someone else's PR: the same single pass, report-only

Nothing changes about the panel. Nothing is fixed, nothing committed, no branch touched, and every
bucket — `ambiguous` included — is a deliverable, so it all goes into one cockpit live. Hand over the
drafted `gh` commands once, at the end.

## Mechanical sweep + recurring-classes checklist

Derived from the classes human reviewers kept catching **after** the blank panel missed them (siegl-app PRs #1240–#1300, 2026-07). The panel's reviewers stay context-free; the orchestrator runs this deterministic layer itself.

**Greps over the change** (`git diff origin/main...HEAD` — added lines; for a PR, the PR diff):

- `\bvar\b` → banned outright. (`let` is allowed where it's simpler — prefer `const`, but don't flag a reasonable `let`.)
- `\.\./\.\.` in imports → `~/*` alias MUST (relative imports get copied between subtrees).
- `String(` around a number input's `value` / `field.value` → react-dom 19 loose-compare rewrites the field mid-typing; use the numeric prop.
- `Boolean(` on a nullable field in filter/comparison logic → tri-state trap: `Boolean(null) === false` turns "unknown" into an explicit "No"; compare `=== filter.value`.
- `* 100` / `* 1000` unit conversions without `Math.round` at the site → float dust (`8.2 * 100 = 819.999…`) rejected by `z.int()` downstream, often as a *silent* submit block.
- Added/changed/removed `data-testid` values × `grep -rn` in the e2e suite → any hit means E2E must actually run + be signed off (signoff is SHA-bound — again after every push).
- New migration folder → snapshot chain still linear with a single head against `origin/main` (fork = regenerate under a **new** timestamp; never `db:generate-append` after a merge — it deletes the *other* PR's newest folder).
- Enum-driven helper (per-value config for a union) that is not exhaustive: a `switch` with a `default`/trailing `return` swallows a future member — prefer no `default` + explicit return type so it fails as `TS2366`; an if-ladder or genuine fallback needs a `const _x: never` guard instead.

**Aggregation checklist** — after merging the four reports, answer each; a "no" becomes a drafted finding:

1. **Sibling sweep:** does the pattern the PR fixes/introduces survive at a twin site (Guess↔Specify, Create↔Edit, other call sites of the touched mutation, sibling list procedures)? Is every deliberate survivor named in the PR body as a follow-up?
2. **Mutant-killing tests:** would each new regression test go red with the fix reverted? Any fully-tied/degenerate seeds? Is the contract the UI branches on (error codes) asserted at the caller level? Is the risky half of the diff mocked away in its spec?
3. **Backfill evidence** (migrations/backfills only): LEFT JOINs over nullable FK chains, active-status scope on UPDATEs, NULL over unevidenced `false`, verification query run on the prod-copy DB with results in the PR body, irreversible UPDATEs counted on live data first, code-deploy-before-migration checked for enum narrowing?
4. **Claim accuracy:** do the PR body / new comments contain quantifiers ("all", "only", "impossible") or time-sensitive facts (versions, counts) that weren't verified or may have gone stale since the analysis?
5. **Toast honesty:** does any success toast claim more than the server response confirmed (create+send flows must return a status the UI branches on)?
6. **Paging:** does every offset-paginated `ORDER BY` end with an id tiebreaker following the primary sort's direction?
7. **Observation, not reasoning:** does the PR body end with a way to *see* the change working — a command to run and the output/screen to expect? A diff a reviewer can only reason about is a finding; ask for the command. (Repo rule: AGENTS.md, "Jak ověřit".)
8. **MVP parity:** is every behavioural change either matched to the MVP or explicitly named as a deliberate divergence in the PR body? A silent drift is a finding even when the new behaviour looks better.

## Verification before triage

Triage on unverified findings sorts noise. Before a finding gets a category:

- **Verify checkable claims.** Anything a reviewer asserts about runtime behaviour, a business rule, or "X is missing/removed" gets checked first — against the code, a real browser run, or the MVP.
- **Check MVP parity on every finding where behaviour is in question**, not only on the `mvp-parity` agent's own output. Any finding about a business rule, a default, a rounding, a status transition, an ordering, a validation boundary, or a user-visible label is an MVP question first: the legacy app's behaviour is the default answer, so a finding that contradicts it is usually wrong and a finding confirmed by it is usually `actionable`. Cite the MVP file:line in the finding body. Skip it only where it genuinely doesn't apply — new features with no MVP counterpart, and pure code-quality findings.
- **Watch the branch-behind trap.** A reviewer flagging a "removed X regression" is often seeing `main` advance past the branch base (`git diff main..HEAD` attributes main's additions to your side). Check whether the branch is behind main before believing any removal you didn't make.
- **Drop your own editorialising.** If the user has already stated a position (in a PR comment, in this session, in memory), a finding must not contradict it. Their stance wins; frame it conditionally against theirs.

## Triage

Every surviving finding lands in exactly one bucket:

- **`actionable`** — a real defect or a required change, and the correct fix is unambiguous. Correctness bugs, a missing `where`, a convention the repo mandates, a test that doesn't kill its mutant, an MVP divergence that is clearly unintended.
- **`nit`** — small and clearly right, no judgment call: naming, a duplicated literal, a stray export, formatting the linter doesn't catch, a comment that no longer matches the code.
- **`ambiguous`** — anything where the fix depends on an opinion the user holds and you don't: product/UX behaviour, a divergence from the MVP that might be deliberate, a design or architecture direction, a trade-off with no obviously right side, two reviewers contradicting each other on something that isn't a checkable fact, or scope ("should this PR even do that?").

**When in doubt it is `ambiguous`.** Mis-filing an opinion as `actionable` means editing the user's code on your own taste, which costs far more to unpick than an extra card in the cockpit.

## Acting on the triage

### Own code (the user's PR, or a local branch / working tree)

1. **Fix `actionable` and `nits` straight away.** No gate — the user asked for this. Apply the fix, add tests for gaps the reviewers converge on, and re-run typecheck / lint / affected tests. Build + affected e2e when UI or tRPC changed (production build first).
2. **Record every fix in the cockpit's Historie, with how it was fixed.** For each one, put the finding in `data.json` with:
   - `"archived": true` — this is what moves it out of the live review and into **Historie**, where it stays readable.
   - a body that states **what was wrong and what you changed**, ending with the commit sha. Not "fixed" — the sentence a reader needs to judge the fix without opening the diff.
   - a `change` block (`before` at the base sha, `after` at head) wherever the fix is a code edit, so Historie shows the actual before/after.
   - the `agents` list intact, so a finding four reviewers independently raised still reads that way.
3. **Only `ambiguous` stays live** in the Nálezy tab, each with its snippet, its MVP comparison, and the options — that is what the user's pass is for. Keep the card honest: state the choice, not your preference dressed as a finding.
4. **Commit the fixes** (GitMoji + `Relates: #<issue>`), summarising per-finding what changed, so every cockpit `change` block has a real before/after pair of shas. One commit is usually right; split it where the fixes are genuinely separate atomic changes, per the repo's commit rule. Push is the user's — the hook blocks it.
5. **E2E and the signoff go last**, after the final fix commit. The signoff status is bound to the head SHA, so any commit after it — yours, or the user's reaction pass — invalidates it; running the suite while you are still editing buys a signoff that is already dead.

### Someone else's PR

**Edit nothing** — no commits, no merges, no branch checkouts that mutate state. Triage still runs, but every bucket goes into the cockpit as a live finding (nothing archived, nothing fixed), with drafted patches/commands the user or the author can apply. Posting to GitHub is a separate explicit step and follows `review-feedback` Step 5 for the mechanics; this repo forbids agent GitHub writes, so hand over the `gh` commands.

**The panel runs once**, its findings land in one cockpit, and nothing is re-sampled. See ["Someone else's PR: the same single pass, report-only"](#someone-elses-pr-the-same-single-pass-report-only) above.

### Building the cockpit

Invoke **`/review-cockpit`** — it is the surface for this, and it takes the findings in the schema documented there. `review-feedback` is superseded for the reaction pass and kept only for the GitHub posting mechanics.

Spawn the panel *first* and build the walkthrough while it runs, with `review.status: "running"` and one `agents` entry per reviewer; the page fills itself in when the findings land. Never make the user wait for the panel before showing them anything.

**One cockpit for the run**, with a stable id across every rebuild, so the open page updates itself and anything the user typed survives. You rebuild it at least twice — once when the findings land (`review.status` from `"running"` to done) and again when your fixes archive their cards into Historie — and once more per reaction pass. Those are reaction round-trips, not review rounds: the panel does not run again.

When their reactions come back: apply each literally, **BEZ REAKCE means not approved**, and a dropped finding is archived (`archived: true`), never deleted and never re-raised in the summary or as a follow-up task.

## Working on the branch locally (run / verify / edit)

This applies to **someone else's PR branch**. When the diff is your own current working tree or local branch (the no-PR case), you're already on it — work in place and skip the worktree dance below.

Once the authorship gate passes and you need to run, verify, or edit a PR branch you don't already have checked out, do it in an **isolated git worktree** — never switch the main checkout onto the PR branch. Switching the primary checkout's branch disrupts the user's workspace and any other agents working in it.

- **Pull latest first.** `git fetch origin <branch>` and base the checkout on the freshly-fetched `origin/<branch>`, so you review the current head — not a stale local copy.
- **Isolated, clean checkout.** `git worktree add <path> origin/<branch>` (detached) or a throwaway branch; the branch must not already be checked out elsewhere. `<path>` is an **absolute** path under the MAIN checkout's `.claude/worktrees/<name>` — where every session worktree already lives — never a sibling dir next to the checkout and never `/tmp`. (This used to say "outside the repo tree" to dodge recursive tsconfig scanning; that noise is the accepted cost — scattered worktrees are not. Always absolute: a relative `.claude/worktrees/...` typed from inside a worktree nests one inside another.)
- **Don't disrupt others.** Unique worktree path and unique ports (DevTools / dev-server). Never clobber or remove worktrees, branches, or processes you didn't create this session.
- **Restore + clean up.** Leave the main checkout on the branch you found it; `git worktree remove <path>` when done. A fresh worktree has no `node_modules` — install or share per the project before building/running.

## Honesty

If you only managed to run one agent (or claimed four but ran two), say so and run the full four — don't report a partial panel as if it were the whole one. Same for the lenses: a panel where every agent got the same prompt is three wasted calls, not a four-lens review.

Report the triage counts as they actually fell (`n actionable fixed, n nits fixed, n ambiguous for you`), and never file something as a nit because fixing it silently is easier than asking.

Same for the fan-out: a reviewer's helpers belong to that reviewer's run and are not extra
reviewers. Reporting the agent count for a four-lens panel where the lenses split their diffs up is
inflation — report the four lenses, and mention the helpers only where how the work was split
actually matters.

And say the shape out loud: **one pass, no loop.** Never let a summary imply the diff was swept
repeatedly, and never quietly run a second panel and fold it into the same report. A panel that
converged on little means this one sample found little — not that the change is clean.

## Notes

- This operationalizes the `review-after-pr` memory, extended with the lens/model diversity and the actionable/nit/ambiguous triage from PostHog's "Stop being the code review bottleneck" (2026-08). Their `qa-swarm` + `review-triage` also "iterates up to three times or until no new actionable threads appear" — **we deliberately don't** (since 2026-08-25). That loop shipped here, and the later rounds mostly re-raised the first one's cards; the budget moved into a one-level fan-out inside the single round instead. Related habits: verify behavioral/business-rule claims against the source of truth (the MVP) rather than guessing; browser-verify UI behavior where relevant.
- **Where this deliberately differs from their swarm.** Theirs is unattended and closes the loop on GitHub: findings are fixed *and pushed*, nits are auto-replied on the thread, a companion agent auto-approves low-risk PRs. Ours stops at the commit — pushes are hook-blocked, agent GitHub writes are forbidden by the repo, and the panel's whole output for anything requiring an opinion is a cockpit card. Ours also has two layers theirs doesn't name: the **MVP as a domain oracle** (the legacy app is the default answer for any ambiguous business rule, and every behavioural finding is checked against it before triage) and the **orchestrator-side mechanical sweep**, which is deterministic rather than a fifth agent. And where their `qa-team` fans out into nested subagents, ours allows one level and forbids the second — recursive, that shape deadlocked this panel at ~30 agents on the 600 s stream watchdog, which is what the guard block exists for. No security lens here either; it was dropped as not worth a slot on this codebase.
- **Browser-verifying a modifier click:** Playwright's `mouse.click(x, y, { modifiers: ['Meta'] })` did **not** set `metaKey` on the DOM event in a real run — the guard under test saw a plain click and the result looked like the opposite of the truth. Hold the key instead (`keyboard.down('Meta')` → `mouse.click()` → `keyboard.up('Meta')`) and **assert the modifier arrived** (record `e.metaKey` from a capture-phase listener) before believing any modifier-click result. Note also that on macOS `Ctrl`+click is a context-menu gesture, so no `click` event fires at all.
- Posting the findings as PR comments is a separate, explicit step — only do GitHub writes when the user/project allows it; otherwise hand the user the reply commands.
