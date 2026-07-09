---
name: unstuck
disable-model-invocation: true
description: Diagnose and recover a stuck Claude Code desktop (CCD) session — one that stopped responding, won't post messages, or can't rewind — by finding its backing engine process, confirming it is wedged (not working), and killing it so the app respawns a fresh engine from the intact transcript. Invoke explicitly via /unstuck [session title / PR number] — never auto-triggered.
---

# Unstuck a frozen CCD session

A CCD session tab freezes when its backing `claude` engine process is wedged: the app spawned
(or re-spawned) an engine with `--resume <uuid>`, and that process hung at startup — it never
reads the queued message and never writes output. While it sits there, the tab can't post
messages or rewind. The fix is to kill the wedged engine; the app spawns a fresh resume from
the transcript on the next user interaction, and nothing is lost — **the `.jsonl` transcript
on disk is the source of truth**, including the queued prompt.

Everything here is local `ps` / `ls` / `kill` — no GitHub writes, no file edits.

## Steps

### 1. Identify the stuck session

The user names it loosely ("the PR1042 session", a title fragment). Map it to a session via
`mcp__ccd_session_mgmt__list_sessions` (load with ToolSearch if deferred) — note its `cwd`
and, if present, `prNumber`. Never target the **current** session's own engine.

### 2. Locate its transcript

Transcripts live under `~/.claude/projects/<encoded-cwd>/`, where `<encoded-cwd>` is the
session's cwd with every `/` and `.` replaced by `-` (e.g.
`/Users/macik/projects/softero-cz/siegl-app/.claude/worktrees/awesome-shtern-f11ce6` →
`-Users-macik-projects-softero-cz-siegl-app--claude-worktrees-awesome-shtern-f11ce6`).

```
ls -lat ~/.claude/projects/<encoded-cwd>/*.jsonl | head -5
```

The most recently modified `.jsonl` is the session; its basename UUID is the resume id.
Several sessions can share a worktree dir — if ambiguous, cross-check the UUID against the
`--resume` args in step 3.

### 3. Find the backing engine process

```
ps aux | grep "resume <uuid>" | grep -v grep | grep -v disclaimer
```

Each engine has two processes: a `disclaimer` wrapper and the real
`…/claude-code/<ver>/claude.app/Contents/MacOS/claude` engine. A brand-new session's engine
has no `--resume` — match on the session cwd instead. **No process at all** means the engine
died; the app will respawn it when the user interacts (that respawn may itself wedge — keep
going, you'll diagnose it when it appears).

### 4. Diagnose: wedged or working?

Do NOT kill on suspicion — a resume of a 10 MB+ transcript legitimately takes a while, and a
healthy engine may be mid-turn. Sample:

```
for i in 1 2 3; do ps -o pid,%cpu,rss,state,etime -p <PID> | tail -1; sleep 3; done
ls -la <transcript>.jsonl   # mtime = last write
date
```

- **Wedged**: ~0% CPU across samples, state S, RSS flat, and **zero transcript writes since
  the process spawned** (mtime ≈ spawn time, minutes ago). A healthy resume streams output
  within seconds of finishing load.
- **Working**: CPU bouncing, or transcript mtime advancing / size growing → leave it alone
  and tell the user it's alive, just slow.

Also check the tail of the transcript:

```
tail -1 <transcript>.jsonl | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('type'), d.get('timestamp'))"
```

A final `last-prompt` entry = the user's message was queued to disk but no engine processed
it — it will replay on the next resume, so it is safe.

### 5. Kill the wedged engine

Plain SIGTERM on the engine PID only (the disclaimer wrapper exits with it). Never `killall`,
never `-9` first:

```
kill <PID>; sleep 2; ps -p <PID> -o pid,state | tail -1
```

Verify it's gone, then check whether the app already respawned
(`ps aux | grep "resume <uuid>"`). Usually it won't until the user interacts.

### 6. Report and hand back

Tell the user:
- to go to the stuck tab and **send their message again** (or just poke the tab) — a fresh
  engine resumes from the intact transcript; the queued prompt is preserved;
- if the tab itself stays frozen: close and reopen the session from the session list; worst
  case restart the Claude desktop app — the transcript survives all of it;
- where that session's work stands if you know it (branch pushed? CI state?), so they lose no
  thread.

### 7. Repeated wedges = environmental

Two sessions wedging on `--resume` within minutes is not coincidence. Known suspect: session
startup blocking on `npx`-spawned stdio MCP servers (figma / notion) that stall or flap.
Recommend restarting the Claude desktop app to reset all engines and MCP servers in one go.

## Safety rules

- Verify the wedge (step 4) before killing — never kill a process whose transcript is
  advancing.
- Kill only the one engine PID for the stuck session; never the current session's engine,
  never `killall claude`.
- Before killing, glance at the session's worktree (`git status`) if it's doing code work —
  a clean/pushed tree confirms zero risk; a dirty tree is still safe (killing the engine
  doesn't touch files) but worth mentioning in the report.
