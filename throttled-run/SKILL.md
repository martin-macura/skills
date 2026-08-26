---
name: throttled-run
description: Run a heavy command (build, test suite, e2e, migration, seed) only once the machine's load average is low enough — it waits, prints why, and retries instead of piling onto an already-thrashing box. Use when starting anything CPU-heavy while other worktrees/sessions may be busy, when a suite just failed on timeouts that smell like contention, or when the user says "/throttled", "throttled yarn build", "spusť to, až bude klid", "wait for the load to drop".
---

# throttled-run

`throttled <command>` checks the load average, and:

- **load OK** → `exec`s the command straight away (exit code, signals and streams pass through untouched),
- **load high** → prints one line saying so, re-checks every 2 s, and starts the moment the machine frees up — or gives up on `--max-wait`.

```bash
throttled yarn build
```

```
[throttled] load is high — load1 46.84 (4.68/cpu) · ceiling 10.00 (1.0/cpu x 10 cpus) · 4% idle · mem normal · re-checking every 2s
[throttled] still waiting — load1 22.10 (2.21/cpu) · ceiling 10.00 (1.0/cpu x 10 cpus) · 61% idle · mem normal · 30s
[throttled] ok after 41s — load1 14.80 (1.48/cpu) · ceiling 10.00 (1.0/cpu x 10 cpus) · 88% idle, spike decaying · mem normal
$ ... the build's own output from here on ...
```

## Why this exists

Several worktrees/sessions share one machine. Two full vitest suites at once push a 10-core box past load 100, and the heavy specs then die on 60 s timeouts that look exactly like a regression in your diff but are not. Starting a third heavy job at that moment is the thing that makes it happen — `throttled` is the "don't add fuel" gate in front of it.

## Using it

| Situation | Command |
| --- | --- |
| Any heavy job, interactive | `throttled yarn build` |
| Heavy job from a Claude Code Bash call | `throttled -w 8m --then fail yarn build` |
| Just look at the machine first | `throttled --check` |
| Be stricter (leave headroom) | `throttled -p 0.5 yarn test:run` |
| Be lenient, just don't thrash | `throttled -p 2 yarn typecheck` |
| Run regardless, but politely | `throttled -p 99 -n 10 yarn build` |
| Gate on the smoothed average | `throttled -m 5 yarn test:e2e` |

Full option list: `throttled --help`.

### The gate

- Default ceiling is **1.0 × ncpu** on the **1-minute** load average — the textbook "fully busy, nothing queued" line (10.00 on a 10-core Mac). Override absolutely with `-l 20`, or per-core with `-p 1.5`.
- **Waiting costs at most ~2 s of start latency.** Reading the load is a `sysctl`, so the check runs every 2 s (`-i`) while the printed line is throttled to once every 30 s (`-r`) to keep the output readable. Don't raise `-i` to quieten it — that only delays the start; raise `-r`.
- **The load average lags.** It decays with a one-minute time constant, so it sits above the ceiling long after the machine is actually free — that lag was most of the "waited a minute for nothing" feeling. When the load is over the ceiling, `throttled` samples instantaneous CPU idle (`iostat`/`top`/`/proc/stat`, ~1 s) and starts anyway if the box is genuinely idle — 60 % by default, `--min-idle`. `--no-idle-rescue` gives pure load-average semantics; note the rescue overrides an explicit `-l` too, so a deliberately-blocking ceiling like `-l 0.01` needs it.
- `-m 1` (default) reacts the moment a spike ends; `-m 5` waits for the machine to actually stay calm. Use `-m 5` for a long job you don't want to abandon at the first dip.
- A **memory gate** runs alongside, and it vetoes even a successful idle rescue: macOS reads the kernel's own pressure level (`kern.memorystatus_vm_pressure_level`, blocks at warn/critical), Linux requires `MemAvailable` ≥ `--min-free-mem` % (default 10). Disable with `--no-mem`. Note macOS reports pressure `normal` even while swap is nearly full, so treat it as a veto for the genuinely bad case, not as a general memory check.
- If the load can't be read at all, the gate opens — this tool must never be the reason work didn't happen.

### Exit codes

- The command's own exit code, once it runs.
- **75** (`EX_TEMPFAIL`) — `--max-wait` expired under the default `--then fail`. Nothing ran; retry later.
- **64** — bad usage. **130/143** — interrupted/terminated while waiting (a `SIGTERM` mid-nap exits at once, it isn't deferred to the next check).
- `throttled --check` alone: **0** = gate open, **1** = busy. It prints the verdict and runs nothing.

### From an agent's Bash call

A `Bash` call is SIGKILLed at 10 minutes, and that cap covers time spent *waiting*. So don't let it wait open-endedly:

```bash
throttled -w 8m --then fail yarn build
```

Exit **75** means "still busy, nothing ran" — report that and retry in a later turn, don't treat it as a build failure. For a job that is itself longer than ~10 minutes, gate it and detach it (see the `detached-job` skill):

```bash
nohup throttled -w 30m --then run yarn test:e2e > /tmp/e2e.log 2>&1 &
disown
```

`--then run` is what makes that safe to walk away from: it waits up to 30 min for calm and then goes ahead regardless, instead of exiting 75 into a log nobody is watching.

### Escape hatch

`THROTTLED_DISABLE=1` bypasses the gate entirely (CI, or when you know you want it now). Defaults also come from `THROTTLED_PER_CPU`, `THROTTLED_MAX_LOAD`, `THROTTLED_METRIC`, `THROTTLED_INTERVAL`, `THROTTLED_REPORT`, `THROTTLED_MAX_WAIT`, `THROTTLED_MIN_IDLE`, `THROTTLED_MIN_FREE_MEM`, `THROTTLED_QUIET`.

## Don't gate these

The wait only pays off for jobs that are themselves heavy and interruptible-by-nature. Leave alone: dev servers you're waiting on, anything interactive, git commands, single-file `yarn test:run <file>`, and anything a human is watching a prompt for.

## Install / repair

The script is `throttled` next to this SKILL.md, symlinked onto `PATH`:

```bash
ln -sf ~/projects/2bad2furious/skills/throttled-run/throttled /opt/homebrew/bin/throttled
```

Pure bash 3.2 (macOS system bash) + awk — no dependencies, and it reads load from `sysctl vm.loadavg` on macOS or `/proc/loadavg` on Linux. If `throttled: command not found`, re-run the symlink above.
