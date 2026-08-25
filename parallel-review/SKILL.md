---
name: parallel-review
disable-model-invocation: true
description: Run FOUR independent code-review subagents in parallel — each given the same blank view of the change but a different lens (correctness, martin-reviewer, simplify, MVP parity) and a mix of models — then triage the combined findings into actionable / nits / ambiguous, fix the first two on the user's own code, and **repeat the whole round up to three times, until one turns up nothing new** (review → fix → review on the user's own code; on someone else's PR the same three rounds run report-only, each a fresh independent sample of the unchanged diff); whatever stays ambiguous goes into a `/review-cockpit` for the user's call. Use after creating a PR, after a larger set of changes (e.g. addressing review feedback or resolving a merge), or whenever the user asks for a thorough / multi-agent review, a "triple review", "review with subagents", or to double-check a change before merge. Invoke only via the explicit `/parallel-review` command — model auto-invocation is disabled so a spawned subagent cannot recursively trigger another panel.
---

# Parallel review (four fresh subagents, four lenses)

Spawn **four separate, fresh subagents** on the same diff, run them **in parallel**, then triage and act on the combined findings.

Three properties do the work, and they are not the same thing:

- **Blank context about the change.** No "what this PR does" paragraph, no output-format instructions, and above all none of your conclusions. Reviewers that know nothing beyond the diff catch what the author rationalizes away.
- **Different lenses and different models.** Four identical clones pay for the same blind spot four times. Each reviewer gets exactly one lens paragraph and the panel spans more than one model, so their misses don't line up.
- **Repetition until it comes up empty.** One panel is a sample, not a verdict. Fixing a finding changes the diff, and the next panel reviews the fix too — which is where a fix's own regression, and the second-order finding the first round's noise hid, actually show up. The default is a **loop**: review → triage → fix → review again, stopping when a round produces nothing new. That holds even where nothing is fixed: on someone else's PR the bytes don't change, and the later rounds buy a **fresh independent sample** of them — twelve reviewers over one diff instead of four, which is where the long tail the first panel happened to miss turns up. Three rounds either way; whose code it is decides what a round *does* with its findings, not how many rounds there are.

A lens is an instruction about *how to look*, never information about the change. Keep that line clean and the first two properties hold at once.

## When to run

- Right after a PR is created.
- After any larger set of changes — addressing review feedback, resolving a merge/rebase, a multi-file refactor.
- Whenever the user asks to review, double-check, or "use subagents" on a change.

Skip for trivial one-line changes.

## How to run

**Steps 1–3 run once per invocation. Steps 4–7 are one round, and the default is to repeat them** — [The loop](#the-loop) below says how many times and when to stop.

1. **Bail if a review is already in progress.** Before anything else, call `TaskList` and check whether a parallel-review is already running — an `in_progress` task whose subject starts `parallel-review:` (the lock below), or in-progress review subagents from a prior invocation. If one is active, **stop**: tell the user a review is already in progress and do **not** spawn a second panel — a duplicate concurrent panel wastes tokens and muddles aggregation. To make this detectable across background / automation / `/loop` / `review-queue` runs (where the panel doesn't block a turn), register a lock: `TaskCreate` a `parallel-review: <target>` task, set it `in_progress` before the first round's panel, and `TaskUpdate` it to `completed` only when the **loop** ends — one lock for the whole run, never one per round (release it even if the review errors).
2. **Resolve the target.** Pick the command by what exists — don't push or open a PR just to get a number; review the diff in place:
   - **A PR exists** (`gh pr view --json number` read-only finds one) → `/review PR <n>`.
   - **No PR** — a branch committed ahead of `main` but not yet pushed/opened, *or* uncommitted working-tree changes → `/code-review`. In this setup `/review` alone is GitHub-PR-only; `/code-review` is the working-diff reviewer and resolves the diff itself (committed branch changes vs the base, i.e. `git diff origin/main...HEAD`, plus any unstaged edits). A clean tree with no branch commits ahead of `main` means there's nothing to review — say so instead of spawning a panel.
3. **Resolve authorship now, not later.** `gh pr view <n> --json author` (read-only). The user is GitHub `2bad2furious`. **Own code** = the user authored the PR, *or* the user explicitly asked for fixes, *or* it's a no-PR diff (a local branch or working tree — always theirs). Everything downstream — whether findings get fixed or only reported — branches on this one answer, so settle it before the panel lands. What it does **not** decide is how many rounds run: **three either way**. It decides what a round *does* — on own code a round fixes, and the next panel reviews the fix too; on someone else's the diff stays put, and the next panel is a fresh independent sample of it. Both are worth three rounds; see [The loop](#the-loop).
4. **Spawn four `general-purpose` Agent calls in a single message** so they run concurrently. Each agent's prompt is assembled from exactly three parts, in this order, and nothing else — **in every round**, including the later ones. Round 2's agents are as blank as round 1's: they are never told what an earlier round found or that anything was fixed.

   **(a) The command** resolved in step 2 — `/review PR <n>` or `/code-review`.

   **(b) The guard block, verbatim, identical for all four:**
   > Be **extra critical** — flag every potential issue you see, no matter how minor. When in doubt, report it.
   >
   > Review this change YOURSELF in this single context. Do **NOT** spawn subagents, do **NOT** use the Agent/Task tools, and do **NOT** invoke `/parallel-review` or any multi-agent / parallel / "ultra" review mode — if a skill offers a fan-out path, decline it and review directly. Treat the Agent tool as if it were absent from your tool set: *if the Agent tool is not available in your current tool set, do not error — perform each angle (and each verification) yourself, sequentially, in this context.* Report only; do not edit files, commit, or run any write command.

   The escape-hatch sentence is load-bearing. `/code-review` itself orders a fan-out into ~10 angles via the Agent tool and its instructions outrank a bare "don't spawn subagents" — that produced ~30 nested agents that deadlocked the whole panel on the 600 s stream watchdog. You can spot it in a report by agents you never launched (`Angle A`, `Angle B`, `Angle Reuse`…).

   **(c) One lens paragraph**, different per agent:

   | label | model | lens paragraph appended to the prompt |
   | --- | --- | --- |
   | `review:correctness` | opus | Lens: **correctness under real data**. Boundary and empty cases, `null` vs `0` vs `false` tri-state traps, timezone and DST handling, money as integer cents and rounding at every conversion, transaction boundaries and partial-failure states, error paths and what the caller actually sees, race conditions between a query and the mutation that invalidates it. |
   | `review:martin` | opus | Lens: **the reviewer's own recurring catches**. Does the fixed pattern survive at a twin site (Guess↔Specify, Create↔Edit, other call sites of the touched mutation, sibling list procedures)? Would each new test go red with the fix reverted, or does it pass on a degenerate/all-tied seed? Does any success toast claim more than the server response confirmed? Does the PR body or a new comment assert a quantifier ("all", "only", "never") or a count/version that was not verified? Is the risky half of the diff mocked away in its own spec? |
   | `review:simplify` | sonnet | Lens: **reuse and simplification only** — no bug hunting. An existing helper/type/component that already does this, duplicated logic that wants extracting, an abstraction at the wrong altitude, dead code and unused exports left behind, a hand-rolled loop where a language or repo built-in exists. Report; do not apply anything. |
   | `review:mvp-parity` | opus | Lens: **parity with the legacy MVP**, which is the default answer for any ambiguous business rule. Its source is at `~/projects/softero-cz/mvp` (`logistics-backend`, `logistics-frontend`) — read the code there; a running instance exists only under docker. For every behaviour this diff adds or changes, find the MVP's equivalent and say whether the new behaviour matches, deliberately diverges, or silently drifts. Quote the MVP file:line you compared against. "No MVP equivalent exists" is a valid and useful finding. Divergence is not automatically a bug — an unacknowledged one is. |

   Set the model via the Agent call's `model` option. Use each agent's label as its `label`.
5. **Mechanical sweep (orchestrator-side, while the panel runs).** The four reviewers stay blank — this deterministic layer is yours. Run the greps and checklist in "Mechanical sweep + recurring-classes checklist" below over the diff. **Re-run it every round in which the diff changed** — after a fix round it contains your own edits, and this is the cheapest check there is on them. On someone else's PR the bytes are identical from round to round, so it runs **once**, in round 1: deterministic greps over unchanged input can only return the same answer.
6. **Aggregate, verify, triage.** Merge and dedupe across the four and fold in the mechanical sweep — a finding raised by **any one** counts, and one raised by several keeps its `agents` list (the cockpit renders it as a "N× nezávisle" badge). From round 2 on, dedupe **against the ledger of every earlier round** as well, so only what is new to the *run* reaches triage. Then run "Verification before triage" and "Triage" below.
7. **Act on the triage.** Own code: fix `actionable` + `nits`, archive them with how they were fixed, and put only `ambiguous` in front of the user. Someone else's: fix nothing, report everything. Go to "Acting on the triage".
8. **Decide whether to run another round.** The round moved something — a fix landed (own code), or a finding new to the ledger surfaced (someone else's) — the cap is not reached and no stop condition fired → say so in chat and go back to step 4 with a fresh panel. Otherwise stop and hand over. The conditions are in [The loop](#the-loop).

## The loop

**Three rounds, hard cap.** Not "about three", not "until it feels clean" — the third round's fixes
ship unreviewed by this panel, and that is the accepted price of a loop that terminates. A lower cap
is fine (`/parallel-review 1`, or the user saying "jednou" / "bez smyčky", runs a single round); a
higher one is not, whatever the panel is still finding. If round 3 still turns up actionable
findings, that is a signal to report — *"kolo 3 pořád našlo 2 věci, strop je 3, tady jsou"* — not a
reason to keep going.

Every round is steps 4–7: a fresh four-lens panel on the current diff, the mechanical sweep,
verification, triage, and — on the user's own code — the fixes. **Stop as soon as any of these is true:**

- **The round produced nothing new to the ledger.** This is the intended exit, and what counts as
  "nothing" depends on whose code it is. On the user's own code it is **no new `actionable` and no
  new `nits`**: leftover `ambiguous` findings do **not** keep the loop alive — they are the user's
  pass, not work, and a loop that waited for them would never end. On someone else's PR every bucket
  is a deliverable, `ambiguous` included, so there it is **no new finding in any bucket**.
- **Three rounds are done.** Say the loop hit the cap rather than letting it read as convergence.
- **Nothing was actually fixed this round — own code only.** If every finding turned out to be a
  no-op, a duplicate or wrong on verification, the diff has not changed and the next panel would
  review the same bytes. This is **not** a stop condition on someone else's PR: there the diff never
  changes by design, and re-reading the same bytes with a fresh blank panel is the entire point of
  the round.
- **The panel is oscillating — own code only.** A finding that asks you to undo a previous round's
  fix is not `actionable`; it is `ambiguous`, it goes to the user with both sides stated, and it ends
  the loop. Two rounds arguing with each other is the failure mode this cap exists to bound. On a
  report-only run there is no fix to undo, so two reviewers contradicting each other is just an
  `ambiguous` card and the loop carries on.

**The ledger is orchestrator-side and lives across the whole run.** Keep every finding you have
already seen — fixed, archived, dropped by the user, or judged wrong on verification — keyed by file
+ anchor + the claim itself, and match each round's output against it before triaging. Three things
follow:

- **"New" means new to the ledger**, not new to the round. A finding four reviewers raise again in
  round 2 because it is still visible in the diff is not new — it is round 1's card, already
  answered.
- **A finding the user dropped is never re-raised** — not as a card, not in the summary, not as a
  follow-up task, and not in a later round either. Archived is archived for the rest of the run.
- **A regression introduced by one of your fixes is genuinely new**, and catching it is the entire
  reason the loop exists. Don't let the dedupe swallow it because it names a file that already
  appeared in an earlier round.

**The ledger never enters a reviewer's prompt.** It is how *you* read their output. Handing round 2
"we already fixed X, don't report it again" trades the blank-context property for a small dedupe
saving — and blank context is the whole point of the panel. The dedupe is yours to do, after they
answer.

**Say the round count out loud as you go**, before each new panel and in the final summary. Three
rounds of four agents is twelve reviewer runs plus the fixing, which is deliberate — PostHog's
version of this budget is *"something like 60% of my token spend is burned automating the toil of
handling CI and review and I don't regret a single dollar"* — but the user gets to call it off, and
they can only do that if they can see it running. When a further round is triggered by a single nit
fix, say that too; they may prefer to stop there.

### Someone else's PR: the same three rounds, report-only

Nothing is fixed, nothing is committed, no branch is touched — and the loop runs anyway. Rounds 2 and
3 are pure sampling, and that is worth paying for: twelve reviewers over one diff instead of four,
each blind to what the others found. What changes versus an own-code loop:

- **The panel prompt is identical every round** — same four lenses, same models, still blank. That
  means the draws are correlated and the yield falls off round by round; that is the honest cost of
  sampling an unchanged diff, not a reason to leak the ledger into round 2's prompt to "make it look
  somewhere else".
- **The mechanical sweep runs once**, in round 1 (step 5).
- **Report the yield, not the raw count, before each new panel** — *"kolo 2: 3 nové nálezy z 11
  nahlášených"*, *"kolo 3: 1 nový"*. On an unchanged diff most of what a later round says is round
  1's cards again, and the user decides whether the next four runs are worth it. They can only do
  that if they see the new-to-ledger number.
- **One cockpit across the whole loop**, everything still live, each card carrying the round it came
  from. A finding the user drops mid-run is `archived: true` and never re-raised in a later round —
  that is the one thing that gets archived here, since nothing is being fixed.
- **Hand over the drafted `gh` commands once, after the last round.** A reply set drafted after round
  1 is missing two thirds of the review.

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
4. **One commit per round** (GitMoji + `Relates: #<issue>`), summarising per-finding what changed — not one commit for the whole loop, so each round's cockpit `change` block has a real before/after pair of shas. Push is the user's — the hook blocks it.
5. **Leave E2E and the signoff for the last round.** The signoff status is bound to the head SHA, so every further fix commit invalidates it; running the suite after round 1 of 3 buys a signoff that is dead by the time the loop ends.

### Someone else's PR

**Edit nothing** — no commits, no merges, no branch checkouts that mutate state. Triage still runs, but every bucket goes into the cockpit as a live finding (nothing archived, nothing fixed), with drafted patches/commands the user or the author can apply. Posting to GitHub is a separate explicit step and follows `review-feedback` Step 5 for the mechanics; this repo forbids agent GitHub writes, so hand over the `gh` commands.

**The loop still runs — three rounds**, each a fresh blank panel on the same unchanged diff, each round's new findings appended to the same cockpit and marked with their round. See ["Someone else's PR: the same three rounds, report-only"](#someone-elses-pr-the-same-three-rounds-report-only) for what differs from a fixing loop.

### Building the cockpit

Invoke **`/review-cockpit`** — it is the surface for this, and it takes the findings in the schema documented there. `review-feedback` is superseded for the reaction pass and kept only for the GitHub posting mechanics.

Spawn the panel *first* and build the walkthrough while it runs, with `review.status: "running"` and one `agents` entry per reviewer; the page fills itself in when the findings land. Never make the user wait for the panel before showing them anything.

**One cockpit for the whole loop, rebuilt each round** — same id, so the open page updates itself and anything the user typed survives. Set `review.status` back to `"running"` when a new round starts, with a `label` that names it (`"Kolo 2 běží — 4 recenzenti"`) and the round in each agent's name, or a page that already looks finished will hide the fact that the loop is still going. Historie accumulates across rounds; a card carries the round it came from, so "nalezeno až ve 2. kole, po opravě prvního" stays visible.

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

Same for the loop: report **how many rounds actually ran and why it stopped** — a round that came up empty and a round that hit the three-round cap are opposite outcomes and must never be reported with the same sentence. One round because the panel converged is a good result; one round because you decided to skip the loop is a shortcut, and the user needs to know which they got.

On a report-only run the same honesty applies to the **yield**: report how many of each round's
findings were *new to the ledger*, never how many it raised. Twelve reviewers re-raising round 1's
four findings is one review, not three, and "11 nálezů ve 3 kolech" when four of them are distinct is
the report-only version of claiming a four-agent panel you ran twice.

## Notes

- This operationalizes the `review-after-pr` memory, extended with the lens/model diversity, the actionable/nit/ambiguous triage and the outer loop from PostHog's "Stop being the code review bottleneck" (2026-08) — their `qa-swarm` + `review-triage` "iterates up to three times or until no new actionable threads appear", which is where the three-round cap comes from. Related habits: verify behavioral/business-rule claims against the source of truth (the MVP) rather than guessing; browser-verify UI behavior where relevant.
- **Where this deliberately differs from their swarm.** Theirs is unattended and closes the loop on GitHub: findings are fixed *and pushed*, nits are auto-replied on the thread, a companion agent auto-approves low-risk PRs. Ours stops at the commit — pushes are hook-blocked, agent GitHub writes are forbidden by the repo, and the loop's whole output for anything requiring an opinion is a cockpit card. Ours also has two layers theirs doesn't name: the **MVP as a domain oracle** (the legacy app is the default answer for any ambiguous business rule, and every behavioural finding is checked against it before triage) and the **orchestrator-side mechanical sweep**, which is deterministic rather than a fifth agent. And where their `qa-team` deliberately fans out into nested subagents, ours forbids it — that shape deadlocked this panel at ~30 agents on the 600 s stream watchdog, which is what the guard block exists for. No security lens here either; it was dropped as not worth a slot on this codebase.
- **Browser-verifying a modifier click:** Playwright's `mouse.click(x, y, { modifiers: ['Meta'] })` did **not** set `metaKey` on the DOM event in a real run — the guard under test saw a plain click and the result looked like the opposite of the truth. Hold the key instead (`keyboard.down('Meta')` → `mouse.click()` → `keyboard.up('Meta')`) and **assert the modifier arrived** (record `e.metaKey` from a capture-phase listener) before believing any modifier-click result. Note also that on macOS `Ctrl`+click is a context-menu gesture, so no `click` event fires at all.
- Posting the findings as PR comments is a separate, explicit step — only do GitHub writes when the user/project allows it; otherwise hand the user the reply commands.
