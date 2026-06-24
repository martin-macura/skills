#!/usr/bin/env python3
"""Gather reviewer findings from recent PRs so they can be distilled into AI-docs rules.

Reads GitHub only (``gh`` read-only) — never writes. Groups every inline review
comment and review summary left by someone *other than the PR author* on the PRs
in a date window, so the calling skill can spot recurring issues and fold them
into AGENTS.md / CLAUDE.md.

Examples:
    python3 fetch_review_findings.py                       # your PRs, last 30 days, current repo
    python3 fetch_review_findings.py --all-authors         # everyone's PRs
    python3 fetch_review_findings.py --since 2026-05-24 --humans-only
    python3 fetch_review_findings.py --repo owner/repo --format json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone


def run(args: list[str]) -> str:
    res = subprocess.run(args, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        raise SystemExit(f"command failed: {' '.join(args)}")
    return res.stdout


def gh_paginated_objects(path: str) -> list[dict]:
    """`gh api --paginate -q '.[]'` streams one JSON object per line across pages."""
    out = run(["gh", "api", f"{path}?per_page=100", "--paginate", "-q", ".[]"])

    return [json.loads(line) for line in out.splitlines() if line.strip()]


def resolve_repo(explicit: str | None) -> str:
    if explicit:
        return explicit

    return run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"]).strip()


def resolve_login(explicit: str | None) -> str:
    if explicit and explicit != "@me":
        return explicit

    return run(["gh", "api", "user", "-q", ".login"]).strip()


def is_bot(login: str) -> bool:
    lo = login.lower()

    return lo.endswith("[bot]") or "copilot" in lo or lo.endswith("-bot")


def parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None

    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="owner/repo (default: current dir's GitHub repo)")
    ap.add_argument("--author", default="@me",
                    help="whose PRs to scan (default: @me, the authenticated user)")
    ap.add_argument("--all-authors", action="store_true", help="scan PRs by anyone, not just --author")
    ap.add_argument("--since", help="inclusive start date YYYY-MM-DD (default: 30 days ago)")
    ap.add_argument("--until", help="inclusive end date YYYY-MM-DD (default: today)")
    ap.add_argument("--limit", type=int, default=80, help="max PRs to consider (default: 80)")
    ap.add_argument("--humans-only", action="store_true", help="exclude bot/Copilot reviewers")
    ap.add_argument("--format", choices=["md", "json"], default="md", help="output shape (default: md)")
    args = ap.parse_args()

    repo = resolve_repo(args.repo)
    me = resolve_login(args.author)

    until = parse_iso((args.until or datetime.now(timezone.utc).strftime("%Y-%m-%d")) + "T23:59:59+00:00")
    since = parse_iso((args.since + "T00:00:00+00:00")) if args.since \
        else (until - timedelta(days=30)).replace(hour=0, minute=0, second=0)

    list_args = ["pr", "list", "--repo", repo, "--state", "all", "--limit", str(args.limit),
                 "--json", "number,title,author,createdAt,mergedAt,updatedAt,state"]
    if not args.all_authors:
        list_args += ["--author", args.author]
    prs = json.loads(run(["gh", *list_args]))

    def in_window(pr) -> bool:
        stamp = parse_iso(pr.get("mergedAt")) or parse_iso(pr.get("updatedAt")) or parse_iso(pr.get("createdAt"))

        return stamp is not None and since <= stamp <= until

    prs = sorted((p for p in prs if in_window(p)), key=lambda p: p["number"], reverse=True)

    results = []
    reviewers_seen: set[str] = set()
    for pr in prs:
        n = pr["number"]
        author = (pr.get("author") or {}).get("login", "")
        findings = []

        for c in gh_paginated_objects(f"repos/{repo}/pulls/{n}/comments"):
            login = (c.get("user") or {}).get("login", "")
            if not login or login == author:
                continue
            if args.humans_only and is_bot(login):
                continue
            findings.append({
                "reviewer": login, "isBot": is_bot(login), "kind": "inline",
                "state": None, "path": c.get("path"),
                "line": c.get("line") or c.get("original_line"),
                "body": (c.get("body") or "").strip(),
                "diffHunk": c.get("diff_hunk") or "",
            })

        for r in gh_paginated_objects(f"repos/{repo}/pulls/{n}/reviews"):
            login = (r.get("user") or {}).get("login", "")
            body = (r.get("body") or "").strip()
            if not login or login == author or not body:
                continue
            if args.humans_only and is_bot(login):
                continue
            findings.append({
                "reviewer": login, "isBot": is_bot(login), "kind": "review",
                "state": r.get("state"), "path": None, "line": None,
                "body": body, "diffHunk": "",
            })

        if not findings:
            continue
        for f in findings:
            reviewers_seen.add(f["reviewer"])
        results.append({
            "pr": n, "title": pr["title"], "url": f"https://github.com/{repo}/pull/{n}",
            "state": pr["state"], "mergedAt": pr.get("mergedAt"),
            "author": author, "isYou": author == me, "findings": findings,
        })

    win = f"{since.date()} .. {until.date()}"
    if args.format == "json":
        print(json.dumps({
            "repo": repo, "window": win, "prsWithFindings": len(results),
            "reviewers": sorted(reviewers_seen), "results": results,
        }, indent=2, ensure_ascii=False))

        return

    scope = "everyone" if args.all_authors else f"@{me}"
    print(f"# Reviewer findings — {repo}")
    print(f"Window: {win} · PRs by {scope} with reviewer comments: {len(results)}")
    print(f"Reviewers seen: {', '.join(sorted(reviewers_seen)) or '—'}\n")
    if not results:
        print("_No reviewer comments in this window._")

        return

    for r in results:
        merged = f"merged {r['mergedAt'][:10]}" if r["mergedAt"] else r["state"].lower()
        who = "you" if r["isYou"] else r["author"]
        print(f"## PR #{r['pr']} — {r['title']}  ({merged}, author {who})")
        print(r["url"])
        by_reviewer: dict[str, list[dict]] = {}
        for f in r["findings"]:
            by_reviewer.setdefault(f["reviewer"], []).append(f)
        for reviewer, items in by_reviewer.items():
            tag = " [bot]" if items[0]["isBot"] else ""
            print(f"\n### @{reviewer}{tag}")
            for f in items:
                if f["kind"] == "review":
                    state = f" ({f['state'].lower()})" if f["state"] else ""
                    print(f"- _review summary{state}:_ {f['body']}")

                    continue
                loc = f"`{f['path']}:{f['line']}`" if f["path"] else "`(general)`"
                print(f"- {loc} — {f['body']}")
                hunk = [ln for ln in f["diffHunk"].splitlines() if not ln.startswith("@@")]
                if hunk:
                    tail = "\n".join(hunk[-4:])
                    print(f"  ```\n{tail}\n  ```")
        print()


if __name__ == "__main__":
    main()
