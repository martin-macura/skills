#!/usr/bin/env python3
"""Summarize the GitHub PR reviews a user submitted on a repo within a date window.

Defaults to "last week" (the previous Mon-Sun) in local time. Bursts of
inline-comment reviews (GitHub records one review object per inline comment
submitted on its own) are grouped into sessions so the output stays readable.

Examples:
    # Last week, current repo, authenticated user:
    python3 fetch_reviews.py
    # Explicit repo + window:
    python3 fetch_reviews.py --repo owner/repo --since 2026-06-01 --until 2026-06-07
    # Only reviews on other people's PRs (drop your own):
    python3 fetch_reviews.py --exclude-own
    # Raw per-event timestamps / CSV:
    python3 fetch_reviews.py --format raw
"""
import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time


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


ISSUE_TITLE = re.compile(r'#(\d+)')
ISSUE_BRANCH = re.compile(r'(?:^|/)(\d+)[-_/]')
ISSUE_BODY = re.compile(
    r'(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?|relate[sd]?|ref)\b[^#\n]*#(\d+)',
    re.IGNORECASE,
)


def derive_issue(title, branch, body):
    for pattern, text in ((ISSUE_TITLE, title), (ISSUE_BRANCH, branch)):
        match = pattern.search(text or '')
        if match:
            return match.group(1)

    match = ISSUE_BODY.search('\n'.join((body or '').splitlines()[:6]))

    return match.group(1) if match else '?'


def resolve_window(today, since_arg, until_arg):
    if not since_arg and not until_arg:
        monday = today - dt.timedelta(days=today.weekday())

        return monday - dt.timedelta(days=7), monday - dt.timedelta(days=1)

    until = dt.date.fromisoformat(until_arg) if until_arg else today
    since = dt.date.fromisoformat(since_arg) if since_arg else until - dt.timedelta(days=6)

    return since, until


def parse_local(iso):
    utc = dt.datetime.strptime(iso, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)

    return utc.astimezone()


def cluster(events, gap):
    sessions, current = [], [events[0]]
    for event in events[1:]:
        if event[0] - current[-1][0] > gap:
            sessions.append(current)
            current = [event]
        else:
            current.append(event)

    sessions.append(current)

    return sessions


def session_label(session):
    start, end = session[0][0], session[-1][0]
    date = f'{start.day}.{start.month}.'
    fmt = lambda t: f'{t.hour}:{t.minute:02d}'

    return f'{date} {fmt(start)}' if fmt(start) == fmt(end) else f'{date} {fmt(start)}–{fmt(end)}'


def verdict(events):
    decisions = [state for _, state in events if state != 'COMMENTED']
    mapping = {'APPROVED': 'approved', 'CHANGES_REQUESTED': 'changes requested', 'DISMISSED': 'dismissed'}

    return mapping.get(decisions[-1], '') if decisions else ''


def main():
    parser = argparse.ArgumentParser(description='Summarize a user\'s PR reviews on a repo over a time window.')
    parser.add_argument('--repo', help='owner/repo (default: current directory\'s GitHub repo)')
    parser.add_argument('--login', help='GitHub login to report on (default: authenticated `gh` user)')
    parser.add_argument('--since', help='inclusive start date YYYY-MM-DD (default: last week\'s Monday)')
    parser.add_argument('--until', help='inclusive end date YYYY-MM-DD (default: last week\'s Sunday)')
    parser.add_argument('--gap-minutes', type=int, default=45, help='gap that splits review sessions (default: 45)')
    parser.add_argument('--format', choices=['md', 'csv', 'raw'], default='md')
    parser.add_argument('--exclude-own', action='store_true', help='drop PRs you authored')
    parser.add_argument('--only-own', action='store_true', help='keep only PRs you authored')
    args = parser.parse_args()

    repo = args.repo
    if not repo:
        repo = gh(['repo', 'view', '--json', 'nameWithOwner', '-q', '.nameWithOwner'], fatal=False)
        if not repo:
            raise SystemExit('Not inside a GitHub repo — pass --repo owner/repo.')

        repo = repo.strip()

    login = (args.login or gh(['api', 'user', '--jq', '.login'])).strip()
    since, until = resolve_window(dt.date.today(), args.since, args.until)
    start = dt.datetime.combine(since, dt.time.min).astimezone()
    end = (dt.datetime.combine(until, dt.time.min) + dt.timedelta(days=1)).astimezone()

    search_from = (since - dt.timedelta(days=1)).isoformat()
    found = gh(['search', 'prs', '--repo', repo, '--reviewed-by', login,
                '--updated', f'>={search_from}', '--limit', '300', '--json', 'number'])
    numbers = [pr['number'] for pr in json.loads(found)]

    rows = []
    for number in numbers:
        jq = f'.[] | select(.user.login=="{login}") | "\\(.submitted_at)|\\(.state)"'
        lines = gh(['api', f'repos/{repo}/pulls/{number}/reviews', '--paginate', '--jq', jq], fatal=False) or ''
        events = []
        for line in lines.splitlines():
            if not line.strip():
                continue

            iso, state = line.split('|')
            local = parse_local(iso)
            if start <= local < end:
                events.append((local, state))

        if not events:
            continue

        events.sort()
        meta_raw = gh(['api', f'repos/{repo}/pulls/{number}',
                       '--jq', '{title:.title, branch:.head.ref, body:.body, author:.user.login}'], fatal=False)
        meta = json.loads(meta_raw) if meta_raw else {'title': '', 'branch': '', 'body': '', 'author': '?'}
        rows.append({
            'pr': number,
            'issue': derive_issue(meta['title'], meta['branch'], meta['body']),
            'author': meta['author'],
            'own': meta['author'] == login,
            'events': events,
        })

    if args.exclude_own:
        rows = [row for row in rows if not row['own']]
    if args.only_own:
        rows = [row for row in rows if row['own']]

    rows.sort(key=lambda row: row['events'][0][0])

    emit(rows, repo, login, since, until, start.tzname(), args.format, dt.timedelta(minutes=args.gap_minutes))


def emit(rows, repo, login, since, until, tzname, fmt, gap):
    if not rows:
        print(f'No reviews by {login} on {repo} between {since} and {until}.')

        return

    if fmt == 'raw':
        for row in rows:
            for when, state in row['events']:
                print(f"#{row['issue']}\tPR{row['pr']}\t{when.strftime('%Y-%m-%d %H:%M')}\t{state}\t{row['author']}")

        return

    if fmt == 'csv':
        print('issue,pr,author,own,sessions,events,verdict')
        for row in rows:
            sessions = ' | '.join(session_label(s) for s in cluster(row['events'], gap))
            print(f"{row['issue']},{row['pr']},{row['author']},{int(row['own'])},"
                  f"\"{sessions}\",{len(row['events'])},{verdict(row['events'])}")

        return

    print(f'**GitHub PR reviews by `{login}` on `{repo}`**')
    print(f'Window: {since} – {until}  ·  times in local {tzname}\n')
    print('| Issue | PR | Author | Review sessions | Events | Verdict |')
    print('|---|---|---|---|---|---|')
    for row in rows:
        sessions = ' · '.join(session_label(s) for s in cluster(row['events'], gap))
        author = '★ you' if row['own'] else row['author']
        print(f"| #{row['issue']} | {row['pr']} | {author} | {sessions} | {len(row['events'])} | {verdict(row['events'])} |")

    own = sum(1 for row in rows if row['own'])
    events = sum(len(row['events']) for row in rows)
    print(f'\n**Totals:** {len(rows)} PRs ({own} yours ★, {len(rows) - own} peer) · {events} review events')


if __name__ == '__main__':
    main()
