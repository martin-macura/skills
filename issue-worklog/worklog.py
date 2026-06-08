#!/usr/bin/env python3
"""Summarize the GitHub issues a user worked on in a date window, with the
per-day commit time ranges of each issue's PR(s)/branch(es).

Defaults to "last week" (the previous Mon-Sun) in local time. Issues are the
ones assigned to the user and updated within the window; for each, the commit
author-times of its linked PR(s) are grouped by day into local-time ranges. The
ranges cover each branch's full history, so work that started before the window
still shows (that's usually the point of a worklog).

Repo and login are auto-detected via `gh` — nothing is hardcoded. Times use the
machine's local timezone (DST-correct); override with --tz or the TZ env var.

Examples:
    # Last week, current repo, authenticated user:
    python3 worklog.py
    # Explicit repo + window:
    python3 worklog.py --repo owner/repo --since 2026-06-01 --until 2026-06-07
    # Keep epic/meeting/design issues too, as CSV:
    python3 worklog.py --no-default-excludes --format csv
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

DEFAULT_EXCLUDES = ('epic', 'meeting', 'design')  # non-implementation labels; see --no-default-excludes


def gh(args, *, fatal=True, retries=3):
    proc = None
    for attempt in range(retries):
        proc = subprocess.run(['gh', *args], capture_output=True, text=True)
        if proc.returncode == 0:
            return proc.stdout

        if attempt + 1 < retries:
            time.sleep(1.5 * (attempt + 1))

    sys.stderr.write(proc.stderr)
    if fatal:
        raise SystemExit(f"`gh {' '.join(args)}` failed")

    return None


def gh_json(args, *, fatal=False):
    out = gh(args, fatal=fatal)
    if not out or not out.strip():
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def parse_local(iso):
    utc = dt.datetime.strptime(iso, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)

    return utc.astimezone()


def resolve_window(today, since_arg, until_arg):
    if not since_arg and not until_arg:
        monday = today - dt.timedelta(days=today.weekday())

        return monday - dt.timedelta(days=7), monday - dt.timedelta(days=1)

    until = dt.date.fromisoformat(until_arg) if until_arg else today
    since = dt.date.fromisoformat(since_arg) if since_arg else until - dt.timedelta(days=6)

    return since, until


def issue_in_branch(n):
    return re.compile(rf'(^|[^0-9]){n}(-|$|[^0-9])')


def fetch_issues(repo, login, since, until, excludes, limit, start, end):
    # qualifiers go through flags (a positional query string gets quoted as a literal phrase);
    # label *exclusion* isn't a flag, so drop excluded-label issues client-side.
    lo = (since - dt.timedelta(days=1)).isoformat()
    hi = (until + dt.timedelta(days=1)).isoformat()
    raw = gh_json(['search', 'issues', '--repo', repo, '--assignee', login, '--updated', f'{lo}..{hi}',
                   '--json', 'number,title,state,url,updatedAt,labels', '--limit', str(limit)], fatal=True) or []
    drop = {label.lower() for label in excludes}
    out = []
    for it in raw:
        names = {(lbl['name'] if isinstance(lbl, dict) else lbl).lower() for lbl in it.get('labels', [])}
        if names & drop:
            continue
        if start <= parse_local(it['updatedAt']) < end:
            out.append(it)

    return out


def find_prs(repo, n):
    # The branch is the reliable link: the repo names every branch `<type>/<issue>-<slug>`,
    # so a PR belongs to the issue iff its head branch encodes the issue number. Searching
    # the number surfaces candidates (open + merged); the branch match drops false hits
    # (a PR that merely mentions the number, or shares a squash commit that cites two issues).
    listed = gh_json(['pr', 'list', '--repo', repo, '--state', 'all', '--search', str(n),
                      '--json', 'number,headRefName', '--limit', '50']) or []
    rx = issue_in_branch(n)

    return {pr['number']: pr['headRefName'] for pr in listed if rx.search(pr['headRefName'])}


def pr_data(repo, pr):
    return gh_json(['pr', 'view', str(pr), '--repo', repo, '--json', 'number,headRefName,state,commits'])


def local_git_commits(n):
    # fallback for issues whose work never became a PR: commits we hold locally
    proc = subprocess.run(['git', 'log', '--all', '--format=%H %aI', '-E', '--grep', rf'(#|/){n}([^0-9]|$)'],
                          capture_output=True, text=True)
    out = []
    for line in proc.stdout.splitlines():
        oid, _, iso = line.partition(' ')
        if iso:
            out.append((oid, dt.datetime.fromisoformat(iso).astimezone()))

    return out


def build_rows(repo, issues, use_git, workers):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        prmaps = list(pool.map(lambda it: find_prs(repo, it['number']), issues))
    issue_prs = {it['number']: pm for it, pm in zip(issues, prmaps)}

    unique = sorted({pr for pm in prmaps for pr in pm})
    with ThreadPoolExecutor(max_workers=workers) as pool:
        fetched = list(pool.map(lambda pr: (pr, pr_data(repo, pr)), unique))
    cache = {pr: data for pr, data in fetched}

    rows = []
    for it in issues:
        n = it['number']
        commits = {}  # oid -> (local datetime, pr number or None)
        branches, pr_states = [], []
        for pr in issue_prs[n]:
            data = cache.get(pr)
            if not data:
                continue

            branches.append(data['headRefName'])
            pr_states.append((pr, data['state']))
            for commit in data['commits']:
                commits[commit['oid']] = (parse_local(commit['authoredDate']), pr)
        if not commits and use_git:
            for oid, when in local_git_commits(n):
                commits[oid] = (when, None)
        days = defaultdict(list)
        for when, _ in commits.values():
            days[when.date()].append(when)
        rows.append({
            'n': n, 'title': it['title'], 'issue_state': it['state'],
            'branches': branches, 'pr_states': pr_states, 'commits': commits, 'days': days,
        })

    return rows


def status_of(row):
    if any(state == 'MERGED' for _, state in row['pr_states']):
        return 'merged'
    if row['issue_state'] == 'CLOSED':
        return 'closed'
    if any(state == 'OPEN' for _, state in row['pr_states']):
        return 'open PR'

    return 'no PR'


def is_done(row):
    return status_of(row) in ('merged', 'closed')


def first_when(row):
    if not row['days']:
        return dt.datetime.max.replace(tzinfo=dt.timezone.utc).astimezone()

    return min(min(times) for times in row['days'].values())


def day_label(day, times):
    lo, hi = times[0], times[-1]
    date = f'{day.day}.{day.month}.'
    fmt = lambda t: f'{t.hour}:{t.minute:02d}'

    return f'{date} {fmt(lo)}' if fmt(lo) == fmt(hi) else f'{date} {fmt(lo)}–{fmt(hi)}'


def branch_label(row):
    if not row['branches']:
        return '—'
    label = row['branches'][0]
    if len(row['branches']) > 1:
        label += f" (+{len(row['branches']) - 1})"

    return label


def pr_label(row):
    if not row['pr_states']:
        return 'no PR'

    return ', '.join(f'PR #{pr} ({state.lower()})' for pr, state in sorted(row['pr_states']))


def ordered(rows):
    worked = sorted((r for r in rows if r['days']), key=first_when)
    empty = sorted((r for r in rows if not r['days']), key=lambda r: r['n'])

    return worked + empty


def emit(rows, repo, login, since, until, tzname, fmt):
    if not rows:
        print(f'No issues assigned to {login} on {repo} updated between {since} and {until}.')

        return

    if fmt == 'raw':
        for row in ordered(rows):
            for oid, (when, pr) in sorted(row['commits'].items(), key=lambda kv: kv[1][0]):
                print(f"#{row['n']}\tPR{pr or '-'}\t{when.strftime('%Y-%m-%d %H:%M')}\t{oid[:8]}")

        return

    if fmt == 'csv':
        print('issue,title,status,branch,prs,date,start,end,commits')
        for row in ordered(rows):
            branch = ';'.join(row['branches'])
            prs = ';'.join(str(pr) for pr, _ in sorted(row['pr_states']))
            title = row['title'].replace('"', "'")
            if not row['days']:
                print(f"{row['n']},\"{title}\",{status_of(row)},{branch},{prs},,,,0")
                continue

            for day in sorted(row['days']):
                times = sorted(row['days'][day])
                print(f"{row['n']},\"{title}\",{status_of(row)},{branch},{prs},"
                      f"{day.isoformat()},{times[0]:%H:%M},{times[-1]:%H:%M},{len(times)}")

        return

    done = sum(1 for row in rows if is_done(row))
    empty = sum(1 for row in rows if not row['days'])
    print(f'**GitHub issue worklog by `{login}` on `{repo}`**')
    print(f'Window: {since} – {until}  ·  times in local {tzname}\n')
    for row in ordered(rows):
        print(f"### #{row['n']} — {row['title']}")
        meta = [branch_label(row)] + ([pr_label(row)] if row['pr_states'] else [])
        meta += [status_of(row), f"{len(row['commits'])} commits"]
        print(' · '.join(meta))
        if not row['days']:
            print('- no commits / branch found in the searched history')
        for day in sorted(row['days']):
            times = sorted(row['days'][day])
            print(f'- {day_label(day, times)}  ({len(times)})')
        print()

    print(f'**Totals:** {len(rows)} issues · {done} done · {len(rows) - done} in flight'
          + (f' · {empty} with no commits yet' if empty else ''))


def main():
    parser = argparse.ArgumentParser(description="Per-issue commit time ranges for issues you worked on in a window.")
    parser.add_argument('--repo', help="owner/repo (default: current directory's GitHub repo)")
    parser.add_argument('--login', help='GitHub login to report on (default: authenticated `gh` user)')
    parser.add_argument('--since', help='inclusive start date YYYY-MM-DD (default: last week\'s Monday)')
    parser.add_argument('--until', help='inclusive end date YYYY-MM-DD (default: last week\'s Sunday)')
    parser.add_argument('--exclude-label', action='append', default=[], metavar='LABEL',
                        help='extra label to exclude (repeatable)')
    parser.add_argument('--no-default-excludes', action='store_true',
                        help=f'keep {", ".join(DEFAULT_EXCLUDES)} issues instead of excluding them')
    parser.add_argument('--tz', help='IANA timezone for display, e.g. Europe/Prague (default: system / $TZ)')
    parser.add_argument('--format', choices=['md', 'csv', 'raw'], default='md')
    parser.add_argument('--limit', type=int, default=200, help='max issues to fetch (default: 200)')
    parser.add_argument('--workers', type=int, default=8, help='parallel gh calls (default: 8)')
    args = parser.parse_args()

    if args.tz:
        os.environ['TZ'] = args.tz
        if hasattr(time, 'tzset'):
            time.tzset()

    repo = args.repo or (gh(['repo', 'view', '--json', 'nameWithOwner', '-q', '.nameWithOwner'], fatal=False) or '').strip()
    if not repo:
        raise SystemExit('Not inside a GitHub repo — pass --repo owner/repo.')
    login = (args.login or gh(['api', 'user', '--jq', '.login'])).strip()
    since, until = resolve_window(dt.date.today(), args.since, args.until)
    start = dt.datetime.combine(since, dt.time.min).astimezone()
    end = (dt.datetime.combine(until, dt.time.min) + dt.timedelta(days=1)).astimezone()

    excludes = ([] if args.no_default_excludes else list(DEFAULT_EXCLUDES)) + args.exclude_label
    cwd_repo = gh(['repo', 'view', '--json', 'nameWithOwner', '-q', '.nameWithOwner'], fatal=False)
    use_git = bool(cwd_repo) and cwd_repo.strip().lower() == repo.lower()

    issues = fetch_issues(repo, login, since, until, excludes, args.limit, start, end)
    rows = build_rows(repo, issues, use_git, args.workers) if issues else []
    emit(rows, repo, login, since, until, start.tzname(), args.format)


if __name__ == '__main__':
    main()
