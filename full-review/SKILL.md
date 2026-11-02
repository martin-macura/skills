---
name: full-review
disable-model-invocation: true
description: One-wave review of one committed SHA — six independent blind lenses (correctness, martin, simplify, mvp-parity, paul, xp) plus a security lens when the diff touches a dangerous surface, or a lean three-lens wave (martin, simplify, mvp-parity) for presentation-only changes — then one sweep, one triage, own-code fixes, one cockpit, one drafted GitHub review and one hand-over. Replaces running `/parallel-review` and `/qa-swarm` in sequence. Use when the user types `/full-review` (optionally a PR number, URL or branch, and `full` or `lean`) or asks for "both reviews", "panel + swarm", "full review". Explicit command only — model auto-invocation is disabled so that a spawned reviewer can never start another wave.
---

# Full review (one wave, many lenses, one hand-over)

Mechanics in this file are **copied** from `parallel-review` and `qa-swarm` (2026-11-02, by user
decision) — they do not follow later edits to either; when one of them changes, diff it against the
matching section here.

`/qa-swarm /parallel-review` on one line ran only qa-swarm (the second name is parsed as its
`$ARGUMENTS`), and the two-skill sequence that replaced it treated the panel as the review and the
swarm as an afterthought. Both are now just **lenses**: one roster, one blind wave, one pass.

Four properties do the work:

- **Blank about the change.** No "what this PR does", no output-format instructions, none of your
  conclusions. A lens that knows only the diff catches what the author rationalizes away.
- **Different lenses, different models.** Identical clones pay for one blind spot several times.
- **Fan-out goes one level, never two.** A lens may hand helpers slices of its own work; helpers are
  leaves. The wave never runs twice.
- **One voice per lens.** A lens and its helpers arrive as one report and count once.

A lens is an instruction about *how to look*, never information about the change.

## Step 0: Arguments

`$ARGUMENTS` is zero to two tokens, in either order:

- **target** — PR number, PR URL or branch name (default: the current branch's PR, else the branch);
- **mode** — `full` or `lean` (default: decided in Step 1.6).

`1234 lean` is PR 1234 forced lean; bare `lean` is the current branch forced lean; `feat/x full` is
that branch forced full. A branch literally called `full` or `lean` is written `origin/full`. Anything
that starts with `/` is a command, not a target: stop and say so ("`/full-review` already runs
everything — drop the extra command"). Two targets, two modes or an unknown token: stop and say
which. Nothing is passed down to any other skill; the target is resolved here, once.

## Step 1: Lock, freeze, preflight

1. **Lock.** `TaskList` for an in-progress `full-review:` / `parallel-review:` task or live review
   subagents; if found, stop — a nested wave is what once produced ~30 agents and a deadlock on the
   600 s watchdog. Otherwise `TaskCreate` `full-review: <target>` → `in_progress`, `completed` at the
   end (also on error). If the Task tools are missing in this build, say so once and continue.
2. **Clean tree or no review.** `git status --porcelain` empty, else stop and say what is dirty (the
   user decides: WIP commit or discard). The wave reviews a SHA, never a tree being edited, and
   nothing edits the tree while any lens or helper runs.
3. **Fetch, freeze, base.** `git fetch origin`. PR mode: `gh pr view <target> --json
   number,author,headRefOid,baseRefName` (read-only), else the local branch. Record `reviewed: <full
   sha>`. The user is GitHub `martin-macura` (formerly `2bad2furious`; treat both as the user): their
   PR, a no-PR branch or an explicit request for fixes is **own code**, anything else is not.

   **Base is `origin/main`, never local `main` — unless the branch is stacked.** Stacked = the head of
   another open PR is an ancestor of this SHA and not of `origin/main`
   (`git merge-base --is-ancestor`). Then the review base is the parent, the exact diff is
   `BT=$(git merge-tree --write-tree <parent> $(git merge-base origin/main HEAD) | head -1)` →
   `git diff $BT <sha>` (the tree object is in the object db; subagents in the same worktree read it),
   every lens gets that line, and the hand-over and PR body say it — `origin/main...` vs `<parent>...`
   differ by an order of magnitude (136 files instead of 6 once measured). Inline anchors follow the diff
   GitHub shows (see Step 7).
4. **FACTS** — deterministic, yours, before any agent; each is one line with its command and result
   (`n/a` is a result, silence is not), each stamped with time and SHA, because open-PR facts go
   stale within the hour:
   - `git rev-list --count HEAD..origin/main`; if non-zero, a trial merge in a throwaway worktree
     (`git worktree add <absolute path under the MAIN checkout's .claude/worktrees> HEAD`, `git merge
     --no-commit origin/main`): conflicts, files changed on both sides, the unit specs among them and
     every spec the diff adds. Afterwards `git worktree remove --force <path>` — never leave it.
   - New `drizzle/*` folder → its `prevId` vs `origin/main`'s newest snapshot **and** vs every open PR
     that adds a snapshot (`gh pr list --state open --json number,headRefName`, fetch, compare).
   - `gh pr list --state open --json number,headRefName,files` → open PRs sharing a file with this
     diff (`files` ends at 100 per PR — use `git diff` for big ones), and for each `git merge-tree
     --write-tree <their head> HEAD` (fetch the head first, into your own ref prefix: refs are shared
     between worktrees).
   - **Silent collisions.** When the diff changes a signature, a required field or a renamed
     identifier: for **every** open PR (not only the ones sharing a file) count the *added* lines that
     use the old or new name — `git diff origin/main...<ref> -- app scripts | grep '^+' | grep -cE
     '<name1>|<name2>'` — read the hits (filter `t('…')` / `cs.…` noise), and measure real ones in a
     trial worktree with PR + main + this branch (`typecheck`, the affected spec) **with a control
     run without that PR**. A textually clean merge says nothing about typecheck or tests. For a
     rename also count who still writes the old name on branches without a PR (`git ls-remote
     --heads origin`) and in sibling sessions' worktrees (`git worktree list`), excluding
     `drizzle/*/snapshot.json`.
   - A rule the diff introduces (MUST NOT, lint rule, mock ban) → the grep for the banned pattern
     over the whole tree at HEAD.

   FACTS are findings-in-waiting: they enter triage as drafted cards (`agents: ["preflight"]`) and
   are **never** an input to a lens — no lens learns what the author thinks the diff does. A lens that
   later "confirms" a FACT only mentioned it; the card keeps `preflight`.
5. **Blind hygiene — before the wave.** Anything sitting in the scratchpad (repro scripts, logs,
   earlier results) or in the gitignored `docs/superpowers/` (an earlier review, a drafted PR body,
   cockpit data) is readable by every agent. `mv` it to a durable folder on the same volume —
   `~/.claude/projects/<slug>/cockpit-data/<id>/` — **never** to `/tmp` (a reboot clears it) and never
   as a copy-then-delete; it comes back after the audit in Step 2. A lens that reads a note about the
   topic stops being blind. For the same reason **nothing new is written into those places while the
   wave runs**: no cockpit skeleton, no `dismissed.md`, no review files, no repro scripts — they wait
   for the audit (Step 7).
6. **Mode.** `full` or `lean`, from the argument if given, otherwise decided here and **echoed in one
   line with the changed-file list** so the call is checkable. Lean exists for changes that are
   presentation only and compute nothing; it is the *only* reduction, there is no size gate.

   Lean is eligible only if **both** hold:
   - *Every* changed file is presentational: `*.tsx` under `components/`, `routes/` (no `loader` /
     `action` logic) or `app/modules/ui/`, `app/modules/locales/**`, styles, static assets, and specs
     / e2e that exercise exactly those. Any other file — a hook, a `utils/` helper, `schema`, a router,
     `db`, `drizzle`, `lib`, scripts, config, CI — makes it `full`.
   - Reading the diff finds no calculation or logic change: no tax, price, quantity, rounding, date
     arithmetic, status transition, filter / sort / grouping rule, validation boundary, no new
     branch on data. A component that merely *shows* a value computed elsewhere is fine; one that
     *derives* it is not.

   Anything that triggers `security` (below) is `full`. When unsure, `full`. A wrongly lean wave
   loses lenses that would have caught the change, so the boundary is narrow.

   **`security` trigger** (deterministic, by the file list and the added lines, not by judgement; it
   is *narrower* than the lean exclusion above — a plain router or `db` change forces `full`, but
   does not by itself add the security lens): a changed file under `app/lib/better-auth/**`,
   `app/modules/auth/**`, `app/modules/env/**`, `app/lib/premier/**`, `app/lib/terminal-provider*`,
   `app/modules/calls/server/**`, `drizzle/**`, `app/modules/db/schema/**`, `server/**`, `server.ts`, or
   the routers that move money or touch tenants' personal data: `app/modules/trpc/server/routers/`
   `receipts*`, `refunds*`, `invoices*`, `advanceInvoices*`, `invoicing*`, `invoiceCreation*`,
   `billingPeriods*`, `terminal*`, `calls*`, `users*`; or an added line matching
   `authed\(|allowedRoles|hasRole|process\.env|webhook|dangerouslySetInnerHTML|\bVITE_|\b(token|secret|
   password|apiKey)\b` — word boundaries, because `skipToken` is a repo-mandated pattern in every
   conditional query. Hand-over says `security: RUN (<which trigger>)` or `not triggered`.

   Print one line before spawning — `<mode>, <n> lenses, <files>/<lines>` — so the user can still
   stop a wave they did not want.

## Step 2: The wave — all lenses, one message

**Roster.** Every lens is a fresh `general-purpose` Agent; **all lenses of the mode are spawned
together in a single message.** Models are the `model` option. Label = the lens name below.

| lens | model | mode | what it looks for |
| --- | --- | --- | --- |
| `review:correctness` | opus | full | Lens: **correctness under real data**. Boundary and empty cases, `null` vs `0` vs `false` tri-state traps, timezone and DST handling, money as integer cents and rounding at every conversion, transaction boundaries and partial-failure states, error paths and what the caller actually sees, race conditions between a query and the mutation that invalidates it. |
| `review:martin` | opus | full, lean | Lens: **the reviewer's own recurring catches**. Does the fixed pattern survive at a twin site (Guess↔Specify, Create↔Edit, other call sites of the touched mutation, sibling list procedures)? Would each new test go red with the fix reverted, or does it pass on a degenerate/all-tied seed? Does any success toast claim more than the server response confirmed? Does the PR body or a new comment assert a quantifier ("all", "only", "never") or a count/version that was not verified? Is the risky half of the diff mocked away in its own spec? |
| `review:simplify` | sonnet | full, lean | Lens: **reuse and simplification only** — no bug hunting. An existing helper/type/component that already does this, duplicated logic that wants extracting, an abstraction at the wrong altitude, dead code and unused exports left behind, a hand-rolled loop where a language or repo built-in exists. Report; do not apply anything. |
| `review:mvp-parity` | opus | full, lean | Lens: **parity with the legacy MVP**, which is the default answer for any ambiguous business rule. Its source is at `~/projects/softero-cz/mvp` (`logistics-backend`, `logistics-frontend`) — read the code there; a running instance exists only under docker. For every behaviour this diff adds or changes, find the MVP's equivalent and say whether the new behaviour matches, deliberately diverges, or silently drifts. Quote the MVP file:line you compared against. "No MVP equivalent exists" is a valid and useful finding. Divergence is not automatically a bug — an unacknowledged one is. |
| `review:paul` | opus | full | **Voice lens.** Lens text = the file `~/.claude/skills/paul-reviewer/SKILL.md` plus `~/.claude/skills/paul-reviewer/references/real-review-examples.md`, which the agent reads itself. |
| `review:xp` | opus | full | **Voice lens.** Lens text = `~/.claude/skills/xp-reviewer/SKILL.md` plus `~/.claude/skills/xp-reviewer/c2wiki-wisdom.md`, read by the agent itself. |
| `review:security` | opus | full, only when triggered | Lens: **security at the boundaries**. Who can call this, as which role, on whose data: a tRPC procedure without `authed()` or with a wider `allowedRoles` than its twin; a driver reaching a back-office procedure; a record read or written by id without an ownership check; secrets, tokens or personal data (customers, drivers, addresses, phones, GPS) in logs, URLs, error messages, audit changes or client bundles (`VITE_*`); webhook and terminal-provider endpoints that trust the caller or a field it supplies; payment, receipt and refund paths that can be replayed, double-applied or run on a stale amount; SQL built from input; migrations that destroy or expose data. For each finding say who the attacker is, what they gain and the shortest path; a hypothetical with no reachable caller is a note, not a finding. |

`qa-team` and `security-audit` are not on this machine and are not part of the roster; there is no
store fallback — a voice lens whose file is missing is `NOT RUN (<path> missing)`.

**Prompt scaffold** — assembled from exactly these parts, in this order, nothing else:

**(0) The blind rule**, always the first paragraph, in one of two exact variants (pick one, send it
as is):

> *Voice and security lenses:* You review a change you know nothing about beyond the code. Do **not**
> read anything under `~/.claude/` (memory, projects, transcripts) except the lens files named below,
> nothing in the session scratchpad except your own subfolder, nothing under `docs/superpowers/`,
> and do not open GitHub PR or issue text, comments or reviews. If you notice you have read such a
> note, say so in your report.

> *Command lenses (`correctness`, `martin`, `simplify`, `mvp-parity`):* You review a change you know
> nothing about beyond the code. Do **not** read anything under `~/.claude/` (memory, projects,
> transcripts) except the files the review command itself loads, nothing in the session scratchpad
> except your own subfolder, nothing under `docs/superpowers/`, and open no GitHub PR or issue text,
> comments or reviews beyond what the `/review` command reads by itself. If you notice you have read
> such a note, say so in your report.

**(a) The target.** Command lenses (`correctness`, `martin`, `simplify`, `mvp-parity`) get the command:
`/review PR <n>` when a PR exists, otherwise `/code-review` (in this setup `/review` alone is
GitHub-PR-only; `/code-review` resolves the committed branch diff against the base). Voice and security
lenses get no command: *"The change under review is `git diff <base> <sha>` — read it yourself; you
may read any file in the working tree for context."* On a stacked branch append the exact diff line
from Step 1.3 to every lens.

**(b) The guard block, verbatim, identical for all lenses:**
> Be **extra critical** — flag every potential issue you see, no matter how minor. When in doubt, report it.
>
> You own this review. You may delegate to sub-agents to split the work — half the diff each, one helper per angle, one checking a single claim against the code while you keep reading — as many as this change actually warrants, spawned together in one message. There is no quota: spawning none and reading everything yourself is a good outcome, and so is a handful on a big diff. Size it to the diff, not to the tool.
>
> **Anything you spawn is a leaf.** Put this in every sub-agent's prompt, verbatim: *"Do NOT spawn subagents, do NOT use the Agent/Task tools, and do NOT invoke `/parallel-review`, `/code-review`'s multi-angle fan-out, or any other multi-agent / parallel / 'ultra' review mode — if a skill offers a fan-out path, decline it and do the work directly. Treat the Agent tool as if it were absent from your tool set: if the Agent tool is not available in your current tool set, do not error — perform each angle, and each verification, yourself, sequentially, in this context. Report only; do not edit files, commit, or run any write command. Prefix anything heavy you do run — a build, a test suite, an e2e run — with `throttled -w 8m --then fail`; exit 75 means the machine was busy and nothing ran, which is not a failing build."*
>
> What binds you: the agents you spawn are the last level — you are the only one who fans out. Do **NOT** invoke `/parallel-review` or any "ultra" review mode. `/code-review`'s ~10 angles are fine to spawn as your own leaves; what is not fine is letting any of them fan out again. Report only; do not edit files, commit, or run any write command.
>
> **Anything heavy goes through `throttled`.** If checking a claim needs a build, a test suite or an e2e run, prefix it — `throttled -w 8m --then fail <command>`. Exit **75** means the machine was busy and **nothing ran**: say that, never report it as a failing build or a red suite. Don't gate `git`, `gh`, greps or a single-file `yarn test:run <path>`.

**(c) One lens paragraph** from the table. For a voice lens this is the whole skill text plus these
overrides, which win where they differ from it: *"The diff is the one named above — do not look for
another. Stay in your voice, but start every finding with `file:line` and say what is wrong and why;
list concerns only: no approval, no praise section, no summary, no verdict. Anything specific to
PostHog or Kea does not apply — this is a React Router / tRPC / Drizzle repo, and its rules are in
`AGENTS.md`. The instruction above to flag every potential issue wins over any rule in your skill
text to pick only the 3–5 most important things or to leave minor ones out: report all of them."*

**Output format.** Free report, no imposed template (the four command lenses already work that way).
You extract `file:line`, severity and body in triage. The review JSON in Step 7 is built from your
triage, not from reviewer text.

**The fan-out rule.** One level, one pass. Depth is fixed, width is the lens's call: a lens over a
200-line diff needs no helpers, one over a 40-file migration may want one per area or `/code-review`'s
angles as its own leaves. Helpers are leaves because the lens pastes the guard block's sentence into
their prompts — the mechanism, not good intentions. Split the *input* (a slice of the diff each, one
helper verifying one claim), not the review. Helpers stay blank too. You aggregate one report per lens
however many agents produced it.

**Resilience.**
- **Every lens delivers or is NOT RUN.** A lens ending on `ECONNRESET`, the 600 s watchdog or an empty
  output is re-spawned once, blank. If it fails again: `NOT RUN (<lens>, <reason>, <time>)` in the
  summary and the PR body. Never stop a running lens because you have enough findings; if one must be
  stopped, first collect every report its helpers already wrote (`subagents/agent-*.jsonl` of the
  session, last `SubagentHandback` `input.message`) and aggregate them as that lens's report.
- **Rate-limited session.** If this session has already hit a 429 / session limit, spawn the lenses
  two at a time and say so; the wave is still one pass.
- **No loop.** If the user wants another sample after a big fix round they say so and run
  `/full-review` again. It is never automatic and never announced as "kolo 2" on your own initiative.

**Audit, immediately after each lens returns** (not before the hand-over). A script over
`~/.claude/projects/<slug>/<session>/subagents/agent-*.jsonl`: for every agent, its `tool_use` inputs
(leave out `SubagentHandback` — the report contains every word) classified as memory (match
`…/memory/*.md` as a path, not a substring), `~/.claude/projects`, `docs/superpowers`, scratchpad files
other than its own, `cockpit-data`, transcripts, and `gh pr|issue|api`. Depth and width from
`agent-<id>.meta.json` (`parentAgentId`, `spawnDepth`) — a third level is a violation to report, the
count comes from the script, never from the transcript. PR text is expected for the four command lenses
(`/review PR <n>` reads it; `martin` is built on the PR body's claims) and is a fact to confess, not a
leak; memory, `docs/superpowers`, held files and other worktrees are leaks. A lens that read a note
about the topic is not an independent voice on the finding it touched — its other findings still
count. The hand-over names who was blind and who was not. The folder from Step 1.5 stays where it was
moved until the **last lens and every helper** has returned and this audit has run — then, and not
earlier, `mv` it back.

**Record.** `sha_wave` (what the lenses read), the lenses that delivered, the audit result. Do not
hand over yet.

## Step 3: Mechanical sweep (yours, while the wave runs)

The lenses stay blank; this deterministic layer is yours. Run it **once** over the diff the wave
reviews (and again over your own fix commit in Step 5 — no lens ever sees your edits).

**Greps over the change** (`git diff <base>...HEAD`, added lines):

- `\bvar\b` → banned outright. (`let` is allowed where it's simpler — prefer `const`, but don't flag a reasonable `let`.)
- `\.\./\.\.` in imports → `~/*` alias MUST (relative imports get copied between subtrees).
- `String(` around a number input's `value` / `field.value` → react-dom 19 loose-compare rewrites the field mid-typing; use the numeric prop.
- `Boolean(` on a nullable field in filter/comparison logic → tri-state trap: `Boolean(null) === false` turns "unknown" into an explicit "No"; compare `=== filter.value`.
- `* 100` / `* 1000` unit conversions without `Math.round` at the site → float dust (`8.2 * 100 = 819.999…`) rejected by `z.int()` downstream, often as a *silent* submit block.
- Added/changed/removed `data-testid` values × `grep -rn` in the e2e suite → any hit means E2E must actually run + be signed off (signoff is SHA-bound — again after every push).
- New migration folder → snapshot chain still linear with a single head against `origin/main` (fork = regenerate under a **new** timestamp; never `db:generate-append` after a merge — it deletes the *other* PR's newest folder).
- Enum-driven helper (per-value config for a union) that is not exhaustive: a `switch` with a `default`/trailing `return` swallows a future member — prefer no `default` + explicit return type so it fails as `TS2366`; an if-ladder or genuine fallback needs a `const _x: never` guard instead.

**Aggregation checklist** — after merging the lens reports, answer each; a "no" becomes a drafted finding:

1. **Sibling sweep:** does the pattern the PR fixes/introduces survive at a twin site (Guess↔Specify, Create↔Edit, other call sites of the touched mutation, sibling list procedures)? Is every deliberate survivor named in the PR body as a follow-up?
2. **Mutant-killing tests:** would each new regression test go red with the fix reverted? Any fully-tied/degenerate seeds? Is the contract the UI branches on (error codes) asserted at the caller level? Is the risky half of the diff mocked away in its spec?
3. **Backfill evidence** (migrations/backfills only): LEFT JOINs over nullable FK chains, active-status scope on UPDATEs, NULL over unevidenced `false`, verification query run on the prod-copy DB with results in the PR body, irreversible UPDATEs counted on live data first, code-deploy-before-migration checked for enum narrowing?
4. **Claim accuracy:** do the PR body / new comments contain quantifiers ("all", "only", "impossible") or time-sensitive facts (versions, counts) that weren't verified or may have gone stale since the analysis?
5. **Toast honesty:** does any success toast claim more than the server response confirmed (create+send flows must return a status the UI branches on)?
6. **Paging:** does every offset-paginated `ORDER BY` end with an id tiebreaker following the primary sort's direction?
7. **Observation, not reasoning:** does the PR body end with a way to *see* the change working — a command to run and the output/screen to expect? A diff a reviewer can only reason about is a finding; ask for the command. (Repo rule: AGENTS.md, "Jak ověřit".)
8. **MVP parity:** is every behavioural change either matched to the MVP or explicitly named as a deliberate divergence in the PR body? A silent drift is a finding even when the new behaviour looks better.

## Step 4: Aggregate, verify, triage

Merge and dedupe across the lenses and fold in the sweep and the FACTS. A finding raised by **any
one** lens counts; one raised by several keeps its `agents` list (the cockpit renders "N× nezávisle").
**Independence is counted per lens, from what the lens's own report says** — never from who mentioned a
FACT, and never inflated by helpers. Paul and xp are separate voices (unlike the old one-voice swarm),
but both are style / design lenses: when they flag the same smell, say so rather than call it
convergence of independent evidence on a defect. Every surviving finding with a code remedy also gets a
drafted `proposedFix` (Step 7).

**Ledger as you go.** The moment a finding is dismissed, write it to `dismissed.md` in the scratchpad:
who raised it, what it claimed in one sentence in their words, the command and its output that killed
it, the card number it merged into. Context compaction otherwise leaves a label and no proof.
Dismissed-by-measurement (a mutant, a repro) goes first.

**Verification before triage.** Triage on unverified findings sorts noise.

- **Verify checkable claims.** Anything asserted about runtime behaviour, a business rule, or "X is
  missing/removed" is checked first — against the code, a real browser run (Step 6), or the MVP. A
  line "this cannot be fixed because the signal isn't in the data" needs a grep for the signal first;
  in state-machine domains (`ACTION_STATUS_SERIES`) it almost always exists in the same select. And
  when a reviewer says a docblock promises more than the code holds, try adding the invariant to the
  code before narrowing the text.
- **MVP parity on every finding where behaviour is in question**, not only `mvp-parity`'s own output:
  a business rule, default, rounding, status transition, ordering, validation boundary or user-visible
  label is an MVP question first. A finding that contradicts the MVP is usually wrong; one confirmed
  by it is usually `actionable`. Cite the MVP file:line. Skip it for new features with no MVP
  counterpart and pure code-quality findings.
- **Branch-behind trap.** A "removed X regression" is often `main` advancing past the branch base
  (`git diff main..HEAD` credits main's additions to your side). Check whether the branch is behind
  before believing a removal you didn't make.
- **Drop your own editorialising.** If the user stated a position (a PR comment, this session, memory),
  a finding must not contradict it; frame it conditionally against theirs.
- **FACTS become cards.** A red post-merge spec, a forked snapshot chain, a merge-order hazard with an
  open PR, a rule violated by code `origin/main` brought — each is at least `actionable` or
  `ambiguous`, never a note under the summary.

**Triage** — every finding lands in exactly one bucket:

- **`actionable`** — a real defect or required change with one unambiguous fix: a correctness bug, a
  missing `where`, a mandated convention, a test that doesn't kill its mutant, an MVP divergence that
  is clearly unintended.
- **`nit`** — small, clearly right, no judgement: naming, a duplicated literal, a stray export,
  formatting the linter misses, a comment the code no longer matches.
- **`ambiguous`** — the fix depends on an opinion the user holds and you don't: product/UX behaviour,
  an MVP divergence that might be deliberate, design direction, a trade-off with no obviously right
  side, two lenses contradicting each other on something that isn't a checkable fact, scope.

**When in doubt it is `ambiguous`.** Mis-filing an opinion as `actionable` edits the user's code on your
taste. Severity (for the review in Step 7): 🔴 CRITICAL — data loss, a security hole, wrong money;
🟠 HIGH — a defect users hit; 🟡 MEDIUM — a defect in a corner, a missing guard; 🟢 LOW; ⚪ NIT.

## Step 5: Act on the triage

### Own code

1. **Fix `actionable` and `nit` straight away.** No gate — the user asked for this. Test in the same
   commit as its fix; add tests for gaps lenses converge on. Re-run typecheck / lint / the affected
   specs; build + the affected e2e when UI or tRPC changed. All of it gated (see
   [Heavy commands](#heavy-commands-go-through-throttled)); this is the step that loads the machine.
2. **Record every fix in the cockpit's Historie**: `"archived": true`, a body stating *what was wrong
   and what changed*, ending with the commit sha, a `change` block (before at the base sha, after at
   head) for code edits, the `agents` list intact. A dropped finding is archived too, never deleted.
3. **Only `ambiguous` stays live**, each with its snippet, MVP comparison, the options and a
   `proposedFix` per option where the choice is the whole point. State the choice, not your preference
   dressed as a finding.
4. **Commit** (GitMoji + `Relates: #<issue>`), summarising per finding; one commit is usually right,
   split where the fixes are genuinely separate. Push is the user's — the hook blocks it.
5. **Fix-increment check, once.** After the fix commit, re-run the Step 3 sweep over `git diff
   <sha_wave>..HEAD` — plus a `git grep` of any renamed or reworded text across the whole of `app/`
   (a comment renamed in the component but not in its spec was a real catch) — and spawn **one fresh**
   `general-purpose` agent (opus, label `review:fix-increment`) with only that diff, the guard block
   verbatim and this lens: *"These commits are fixes made in reaction to a review. Look only for what
   the fix broke, half-did or skipped: a gate changed on one side (client vs server) but not the
   other; a path that used to work and is now hidden; an early exit that now skips a step below it; a
   lock or guard that covers one of the entities a transaction touches but not all of them; a mock
   wider than the test that needed it; a test that pins the old behaviour; a comment, docblock or PR
   body sentence the fix made false (a comment states what the code does, not what would happen
   without it); a convention the new code misses."* Ask of every guard: *which condition can I
   remove and have a test fail?* Then typecheck, lint and the affected specs gated. Bounded; not a
   second wave. Without it the fixes are read by nobody — in practice both fixes from one review were
   incomplete.
6. **E2E and the signoff go last**, after the final fix commit, started gated and detached
   (`nohup throttled -w 30m --then run yarn test:e2e … > <log> 2>&1 &`, then `disown`). The signoff is
   bound to the head SHA, so any later commit invalidates it, and the signoff itself is a human's
   command — report the run and hand the command over.

### Someone else's PR

**Edit nothing** — no commits, no merges, no branch checkouts that mutate state. Every bucket goes
into the cockpit live (nothing archived, nothing fixed), each with a `proposedFix` where it has a code
remedy and the commands the user or author can apply. Do not dispatch `e2e.yml` on someone else's PR;
say that it did not run. Leave the PR body alone. Posting is a separate explicit step; the repo forbids
agent GitHub writes, so you hand over the `gh` commands.

## Step 6: Show it — check in the browser, attach what the reader needs

Two conditional rules, both applied before the cards are final:

- **Check it in the running app when you can.** A finding about what the app shows or does — a tile,
  a dialog, a flow, the state after an action, a layout — is reproduced in the real app, not only in
  jsdom or by reading code: a unit harness mounts one component, and the parent chain (what stays
  mounted after a status change, what else refetches, what the server really answers) is exactly where
  such a claim breaks. The cheap route on siegl-app is an **untracked** repro spec next to the PR's
  own e2e spec, reusing its fixture and helpers, in the session's own worktree (the Write hook refuses
  any other, even a throwaway one): `yarn bin playwright` must point inside the worktree (else `yarn
  install --immutable`), build with the compiler ON, run gated through `throttled` with
  `E2E_BASE_PORT` moved off the default. Measure three variants — head / head + the proposed fix /
  head − the suspected cause — and put that table in the finding: a red head proves the symptom, only
  the other two prove the cause and the fix. Layout and visual claims go through `/dev-portless` and
  the browser tools (or `dev-hires-screenshot`). Mutations are restored from copies (not from git),
  and `git status --porcelain` is empty again before the hand-over. When the check is not possible —
  no fixture reaches the state, it needs a real terminal, printer or device, the machine never quiets
  down — the finding says how it *was* measured ("jsdom", "čtením kódu"), so it never reads as
  observed.
- **Attach evidence where it helps the reader — and only there.** A **GIF** for a flow or a state that
  changes after an action; an **element screenshot** for layout, spacing, clipping or colour (never a
  full page with customer data); a **Mermaid diagram** for a sequence, state machine or call chain
  spread over several files (render it once — a parser accepts unreadable ones). A finding one
  sentence settles gets nothing. The GIF comes from the same repro: `test.use({ video: { mode: 'on',
  size: <viewport> } })` plus a pause between steps, a 1 fps `ffmpeg … tile` contact sheet to find the
  cut, then `fps=8`, width ~540 and `palettegen`/`paletteuse` (9 s → 1 MB). Put the file on the
  cockpit card (`images`); for the PR upload it with `/r2-upload` — the only way an agent's image
  reaches GitHub. Before uploading, look at the file and get the user's OK for anything resembling
  personal or customer data, fixture data included; an upload cannot be taken back. Softero R2 objects
  expire after 2 days — for evidence that must outlive the round, the user drags the file into the
  GitHub comment instead.

## Step 7: Cockpit and the one drafted GitHub review

### The cockpit

Invoke **`/review-cockpit`** with the findings in the schema documented there — **only after the wave
and its audit have returned** (Step 2). The walkthrough's station notes are the author's narrative of
the change, which no lens may read, so the cockpit is not built, not even as a "running" skeleton,
while a lens is reading the tree. It opens already filled in: one `agents` entry per lens. **One
cockpit for the run**, a stable id across every rebuild, so the open page updates itself and anything
the user typed survives: rebuild when your fixes archive their cards, and once per reaction pass —
reaction round-trips, not review rounds. Cockpit data (`data.json`, images), `dismissed.md` and the review
files live in the worktree's gitignored `docs/superpowers/review/` (cockpit data in `cockpit-<n>/`) —
the scratchpad does not survive a restart and the user's shell cannot see it.

**Proposals on live cards.** A live finding with a code remedy carries `proposedFix: { "diff": "<git
diff>" }`, drafted in a scratch worktree or index and never applied to the tree. It goes on the card
only after `git apply --check` passes at the head sha and the test or repro that proved the finding
goes from red to green with it applied; a remedy you could only reason out stays in the body, marked
*neověřeno*. When reactions come back: apply each literally, **BEZ REAKCE means not approved**, a
dropped finding is archived, never re-raised. On own code a kept card with a `proposedFix` is
implemented from that proposal; on someone else's PR no one applies it.

### The review JSON — one round, one review

No GitHub write happens here: siegl-app's AGENTS.md forbids agent writes and a local hook blocks
`gh pr comment` / `gh pr review`. Build the round as **one review** and hand over one command; never a
separate summary comment, never an approve as its own review, never individual comments "to get past
the hook" (that is the same write). Do this even with no PR yet, so the file can be posted once the PR
exists. Files: `docs/superpowers/review/full-review-<short sha>.json` (the payload) and `.md`
(readable); the verdict tier is printed in the terminal and the file.

```json
{
  "commit_id": "<sha>",
  "event": "COMMENT",
  "body": "<summary body>",
  "comments": [
    { "path": "<file>", "line": 123, "side": "RIGHT", "body": "<comment body>" }
  ]
}
```
```bash
gh api repos/{owner}/{repo}/pulls/{pr}/reviews --method POST --input <review.json>
```

- **Event:** `COMMENT`. `APPROVE` / `REQUEST_CHANGES` only when the user asks; then their own words
  top the body, above the summary, separated by `---`. The event is always the user's call.
- **Inline comments (what goes in `comments[]`):** own code — only findings still **open** (`ambiguous`,
  deferred); fixed ones are summarised in the body with their sha, they would only clutter threads.
  Someone else's PR — every finding. Only lines inside the diff hunks (added or context, RIGHT side)
  can carry an inline comment; anything anchored elsewhere goes in the body's open findings with its
  `file:line`, because one bad anchor makes GitHub reject the whole review. On a stacked branch the
  anchors follow the diff GitHub shows for the PR (against its base): parse the RIGHT hunks of `gh pr
  diff` and verify **every** anchor by script before handing over the command.
- **One pending review per user per PR:** check `gh api repos/{owner}/{repo}/pulls/{pr}/reviews --jq
  '.[]|select(.state=="PENDING")'` first; if one exists, ask rather than work around it.
- **Verdict**, from the triage *after fixes* — for own code, what is still open; for someone else's PR
  (nothing is fixed), from all findings: ✅ **APPROVE** — nothing open; 💬 **APPROVE WITH NITS** —
  only deferred nits / LOW; ⚠️ **REQUEST CHANGES** — an open `ambiguous` or deferred `actionable`
  with a correctness, data or security stake; 🚫 **BLOCKED** — an unresolved CRITICAL (security,
  data loss, wrong money), open or with a failed fix. Printed even when everything was fixed (then
  APPROVE, with the fixes listed).
- **Comment body** (every comment, every one): 
  ```markdown
  > [!NOTE]
  > 🤖 Automated comment by **Full Review** — not written by a human

  **[<lens>]** <severity emoji> <severity>

  <finding text>
  ```
  A finding raised independently by two or more lenses is `**[convergent: <lens> + <lens>]**` — and
  only counts as convergent if the lens reports really are independent (Step 4).
- **Review body** — the round's summary, marked so a later round can find it:

  ```markdown
  <!-- full-review-summary -->
  > [!NOTE]
  > 🤖 Automated comment by **Full Review** — not written by a human
  >
  > <the header below, generated from what actually ran>

  ## Verdict: <emoji> <VERDICT> <sub>(round <N> @ <short_sha>)</sub>

  <1–2 sentences explaining it>

  ### Open findings
  <by severity; a finding that could not be anchored inline carries its `file:line`>

  ### Fixed in this round
  <one line per fix with its sha — own code only>

  ### Convergence
  <findings raised independently by 2+ lenses>

  ### Lenses
  | Lens | Model | Assessment |
  | --- | --- | --- |
  <one row per lens that actually ran, one sentence each>

  <details>
  <summary>Previous rounds (<n>)</summary>

  <one compact line per prior round: `round <N> @ <short_sha> — <verdict>: <1-line disposition>`>

  </details>

  ---
  *Automated by Full Review — not a human review*
  ```

  **The header says only what ran**, generated from the real lens list: `One wave, 7 independent
  lenses (correctness, martin, simplify, mvp-parity, paul, xp, security) @ <sha>`, or `lean wave, 3
  lenses (martin, simplify, mvp-parity) — presentation-only change`, or `… (<lens> NOT RUN: <reason>)`.
  Never a templated "multi-perspective" line the run did not earn — fix it in the generator
  (`full-review-<n>.build.py`), not in the JSON, or it returns on the next run.
- **A later round is a new review** (its inline comments need one anyway). Fold the history into the
  new body, and shrink the previous round's body — find it with `gh api …/reviews --paginate --jq
  '[.[] | select(.body | contains("<!-- full-review-summary -->") or contains("<!-- qa-swarm-summary
  -->"))] | last | .id'` — to a one-line pointer (`Nahrazeno kolem <N> @ <short_sha>.` plus the marker).
  A submitted review's body is edited with **PUT**, not PATCH: `gh api
  "repos/{owner}/{repo}/pulls/{pr}/reviews/{review_id}" -X PUT -F body=@<pointer.md>`. Earlier inline
  comments stay as they are.

## Step 8: One hand-over

A single message, after the wave, the fixes and the fix-increment check. First lines:

```
full-review: RUN (<full|lean>, <n> lenses: <list> @ <sha_wave>) | PARTIAL (<lens> NOT RUN, <reason>)
mode:        <full|lean> — <by argument | classified: <files>, <why>>
security:    RUN (<trigger>) | not triggered | n/a (lean)
reviewed:    <sha_wave> → fixes <sha_after> | commits after <sha_after>: none | <list — "nečetla ho žádná čočka">
blind:       <who was blind, who read what (audit result)>
```

`reviewed:` ends at the last SHA an agent actually read. A commit after the fix-increment check (a
reaction to *its* finding) was read by the gate and a diff only — it belongs in "commits after", named
as unread, never under "fixes". The header, the PR body and the generator must say the same thing.

Then, in this order: the bucket counts (`n actionable fixed, n nits fixed, n ambiguous in the
cockpit, n dismissed`); the FACTS block (re-measured at the final head, with time and SHA); the
"Zvážené a zahozené" list, whose length matches the count in the prose and whose every item carries
its command and output (from `dismissed.md`; a NIT is not exempt); the cockpit link; the paths of the
review JSON and `.md`; the evidence from Step 6 (local path, R2 URL once uploaded, the finding it
belongs to — or, per finding that could not be checked in the app, why not); and:

- **The PR body** — a draft (new PR) or the refreshed body (existing PR, own code only) carrying the
  header lines above and a `## Jak ověřit` whose every number is a measurement you took, stamped with
  the SHA it was measured on (a merge of `main` re-measures them), plus the ready `gh pr edit
  --body-file` command; an offer to regenerate later is not a hand-over. Placement: the header lines
  and their summary go in `## Review před otevřením PR`, the **last-but-one section, after `## Jak
  ověřit`**, immediately followed by `## Rozhodnuto při kontrole` when cards were decided; never near
  the top (see `pr-body-style`).
- **The one drafted `gh api …/reviews --input <json>` command** (Step 7), the user's event and note
  if they gave one. When the diff touched `data-testid`s, e2e helpers, routes, tRPC procedures or the
  driver flow on own code: `gh workflow run e2e.yml --ref <branch>` — dispatch it yourself if the
  workflow exists on `main`; the signoff needs a completed green run over the exact head SHA and is
  the user's to run.
- **Merge-of-main commands** (when the branch is behind): the gate `yarn typecheck && yarn ci && yarn
  lint:check` and `git add -u` go **between `git add` and `git commit --no-edit`** — the pre-commit hook
  skips itself mid-merge.

**Rename the session** in this same step (`set_session_title`, `session_id: "self"`): `❓` first while
the cockpit holds a live card, then the PR-state emoji, `PR<n>`, `#<issue>`, the existing short name;
someone else's PR: `❓ Review <⏳|✅|❌> PR<n> <short name> @<author>`. The title carries nothing else —
never review state, remaining questions or CI/E2E state; that goes in the hand-over above (memory
`session-title-from-pr-status`).

Release the lock. Remove any throwaway worktree. Check that what Step 1.5 moved is back (it returns
after the Step 2 audit).

## Heavy commands go through `throttled`

**Every build, test suite, e2e run, migration or seed this skill starts — orchestrator-side or inside
any agent — is prefixed with `throttled` (skill `throttled-run`).** One machine carries every worktree
and every session, and a wave is itself seven lenses plus their helpers: two vitest suites at once push
a 10-core Mac past load 100, the heavy specs then die on 60 s timeouts that read exactly like a
regression in the diff, and an agent waiting on its stream gets killed by the 600 s watchdog. On a free
machine the gate costs ~2 s.

| What you're running | Command |
| --- | --- |
| the repo gate after a fix | `throttled -w 8m --then fail zsh -c 'yarn typecheck && yarn ci && yarn lint:check'` |
| affected specs | `throttled -w 8m --then fail yarn test:run <paths>` |
| production build | `throttled -w 8m --then fail yarn build` |
| the e2e suite (longer than a Bash call may live) | `nohup throttled -w 30m --then run yarn test:e2e > <log> 2>&1 &` then `disown` (skill `detached-job`) |

- **One gate per chain, not per command** — `throttled … zsh -c '<a> && <b>'` checks once; two gated
  commands in a row make the second wait behind the load the first created.
- **Always bound the wait** (`-w`) from an agent Bash call — it is SIGKILLed at 10 minutes. **Exit 75
  means nothing ran**: report "machine busy, nothing ran" and retry later; never a red suite or a
  finding. `--then fail` while you watch, `--then run` when you've walked away.
- **Don't gate** `git`, `gh`, greps, a single-file `yarn test:run <path>`, the dev server, or anything a
  human is at a prompt for. `throttled --check` prints the verdict and runs nothing — one call before
  spawning the wave if the box already feels slow; quote it in the hand-over if a suite was skipped.

## Working on the branch locally (run / verify / edit)

For **someone else's PR branch** you don't have checked out: an **isolated git worktree**, never a
switch of the main checkout. `git fetch origin <branch>`, then `git worktree add <absolute path under
the MAIN checkout's .claude/worktrees/<name>> origin/<branch>` (detached or throwaway branch; never a
relative path typed from inside a worktree, never a sibling dir, never `/tmp`). Unique worktree path and
ports; never clobber a worktree, branch or process you didn't create. A fresh worktree has no
`node_modules` — install or share per the project. `git worktree remove --force <path>` when done: a
worktree you created and didn't clean up is a leak (100+ once pinned the CPU). Your own current branch
or tree: work in place.

## Honesty

Say what ran. **One wave, one pass** — over the SHAs named in the hand-over, never a loop, never a
second wave folded into the same report. If a lens did not deliver, the first line is
`full-review: PARTIAL` and names which and why; a partial run is never reported as a full one. A lean
wave is reported as lean, with the files that justified it. Report the lenses (four to seven), not the
helpers they spawned — mention helpers only where how the work was split matters, or where the audit
found a violation. The lens list, the `security` line and the NOT RUN lines are copied into the PR
body so a human reviewer knows what the code went through before it reached them. Triage counts as they
fell; never file something as a nit because fixing it silently is easier than asking. And say the
shape: *"jeden průchod, N čoček"* — one sample of the diff, not a verdict; a wave that converged on
little means this sample found little, not that the change is clean.

## Notes

- **History.** Until 2026-11-02 this skill ran `/parallel-review` (four fixed lenses, full triage and
  cockpit) and then `/qa-swarm` (a `sonnet` router that delegated to stronger models, on this machine
  mostly to nothing) over the fixed tree, report-only, as one voice. The user collapsed them into one
  roster: the router, the delegation plan, the model roster, `qa-team` (never on disk here),
  `security-audit` (PostHog MCP, never configured) and the swarm-after-fixes pass are gone; `paul` and
  `xp` are lenses of the same wave, `security` a conditional lens of its own, and the old swarm's
  other job — being the only reader of the panel's fixes — is the fix-increment check in Step 5. The
  old pair is still available standalone as `/parallel-review` and `/qa-swarm`; the previous version of
  this file is in `~/.claude/skills/.backups/full-review-SKILL-20261102.md`.
- **Why no loop.** The old three-round panel mostly re-raised the first round's cards at three times
  the spend, and a recursive fan-out multiplied itself into ~30 nested agents that deadlocked on the
  600 s watchdog; depth is fixed, width is the lens's call.
- **Browser-verifying a modifier click.** Playwright's `mouse.click(x, y, { modifiers: ['Meta'] })` did
  not set `metaKey` on the DOM event in a real run. Hold the key instead (`keyboard.down('Meta')` →
  `mouse.click()` → `keyboard.up('Meta')`) and assert the modifier arrived (record `e.metaKey` from a
  capture-phase listener) before believing any modifier-click result. On macOS `Ctrl`+click is a
  context-menu gesture, so no `click` event fires at all.
- **Where the shell trips.** `echo =====` fails under zsh — separators are `print -r -- '--- x ---'`;
  and a path glob `dir/**/*.ts` skips `dir/` itself, so list files with `git ls-files`.
