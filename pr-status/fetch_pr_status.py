#!/usr/bin/env python3
"""Fetch a GitHub user's authored PRs with their review status.

Read-only: shells out to `gh` (which must be authenticated) and never writes.
Prints a Markdown table (default) or JSON to stdout.

Examples:
    python3 fetch_pr_status.py                         # your open PRs in the current repo
    python3 fetch_pr_status.py --repo owner/repo
    python3 fetch_pr_status.py --author someone --state all
    python3 fetch_pr_status.py --format json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone

# Reviewers that are bots, not humans — surfaced separately so they don't look
# like a real human sign-off.
BOT_REVIEWERS = {"copilot-pull-request-reviewer"}

PR_FIELDS = (
    "number,title,reviewDecision,headRefName,isDraft,"
    "reviewRequests,reviews,updatedAt,url"
)


def run_gh(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["gh", *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        sys.exit("error: `gh` CLI not found on PATH.")
    except subprocess.CalledProcessError as exc:
        sys.exit(f"error: `gh {' '.join(args)}` failed:\n{exc.stderr.strip()}")

    return result.stdout


def resolve_repo(explicit: str | None) -> str:
    if explicit:
        return explicit

    out = run_gh(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]).strip()
    if not out:
        sys.exit(
            "error: could not detect a repo from the current directory.\n"
            "       pass --repo owner/repo."
        )

    return out


def resolve_author(explicit: str | None) -> str:
    if explicit:
        return explicit

    return run_gh(["api", "user", "--jq", ".login"]).strip()


def reviewer_handle(entry: dict) -> str | None:
    """A reviewRequests entry is either a user (login) or a team (name/slug)."""
    return entry.get("login") or entry.get("slug") or entry.get("name")


def latest_human_verdicts(reviews: list[dict], author: str) -> dict[str, dict]:
    """Map each non-author, non-bot reviewer to their most recent review event."""
    latest: dict[str, dict] = {}
    for review in reviews:
        who = (review.get("author") or {}).get("login")
        if not who or who == author or who in BOT_REVIEWERS:
            continue

        prev = latest.get(who)
        if prev is None or review.get("submittedAt", "") >= prev.get("submittedAt", ""):
            latest[who] = review

    return latest


def bot_commented(reviews: list[dict]) -> bool:
    return any((r.get("author") or {}).get("login") in BOT_REVIEWERS for r in reviews)


def classify(pr: dict, author: str) -> dict:
    decision = pr.get("reviewDecision") or ""
    requested = [h for h in (reviewer_handle(e) for e in pr.get("reviewRequests", [])) if h]
    verdicts = latest_human_verdicts(pr.get("reviews", []), author)

    approvals = sorted(w for w, r in verdicts.items() if r.get("state") == "APPROVED")
    changes = sorted(w for w, r in verdicts.items() if r.get("state") == "CHANGES_REQUESTED")
    commented = sorted(w for w, r in verdicts.items() if r.get("state") == "COMMENTED")

    # "changes requested, but the blocking reviewer was NOT re-requested" — i.e. a
    # human asked for changes and isn't currently in the pending review-request set.
    awaiting_rereview = sorted(w for w in changes if w not in requested)

    if decision == "APPROVED":
        flag = "✅ approved"
    elif decision == "CHANGES_REQUESTED" or changes:
        flag = "🔴 changes requested"
    elif requested:
        flag = "⏳ awaiting review"
    elif decision == "REVIEW_REQUIRED" and not approvals:
        flag = "⚠️ no reviewer set"
    else:
        flag = "•"

    return {
        "number": pr["number"],
        "title": pr["title"],
        "url": pr.get("url", ""),
        "isDraft": pr.get("isDraft", False),
        "decision": decision or "(none)",
        "requested": requested,
        "approvals": approvals,
        "changesRequested": changes,
        "commented": commented,
        "awaitingRereview": awaiting_rereview,
        "botReviewed": bot_commented(pr.get("reviews", [])),
        "updatedAt": pr.get("updatedAt"),
        "flag": flag,
    }


def fmt_date(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()

        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso


def reviewers_cell(row: dict) -> str:
    parts: list[str] = []
    for who in row["approvals"]:
        parts.append(f"✅ {who}")
    for who in row["changesRequested"]:
        suffix = " (no re-review)" if who in row["awaitingRereview"] else " (re-review pending)"
        parts.append(f"🔴 {who}{suffix}")
    for who in row["requested"]:
        if who not in row["approvals"] and who not in row["changesRequested"]:
            parts.append(f"⏳ {who}")
    for who in row["commented"]:
        if who not in row["approvals"] and who not in row["changesRequested"] and who not in row["requested"]:
            parts.append(f"💬 {who}")
    if not parts:
        parts.append("🤖 Copilot only" if row["botReviewed"] else "— none")

    return "<br>".join(parts)


def render_md(rows: list[dict], repo: str, author: str, state: str) -> str:
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    lines = [
        f"**Open PRs by `{author}` in `{repo}`** (state: {state}) — as of {now}",
        "",
        "| PR | Title | Status | Reviewers | Updated |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        draft = " _(draft)_" if row["isDraft"] else ""
        title = row["title"].replace("|", "\\|")
        link = f"[#{row['number']}]({row['url']})" if row["url"] else f"#{row['number']}"
        lines.append(
            f"| {link} | {title}{draft} | {row['flag']} | "
            f"{reviewers_cell(row)} | {fmt_date(row['updatedAt'])} |"
        )

    approved = [r for r in rows if r["decision"] == "APPROVED"]
    needs_rereview = [r for r in rows if r["awaitingRereview"]]
    no_reviewer = [r for r in rows if r["flag"] == "⚠️ no reviewer set"]
    awaiting = [r for r in rows if r["requested"] and r["decision"] != "APPROVED"]

    nums = lambda group: ", ".join(f"#{r['number']}" for r in group)

    lines += ["", "**Summary**"]
    lines.append(f"- {len(rows)} open PR(s).")
    if approved:
        lines.append(f"- ✅ Mergeable (approved): {nums(approved)}")
    if needs_rereview:
        lines.append(
            "- 🔴 Changes requested, **no re-review requested**: "
            + ", ".join(f"#{r['number']} ({', '.join(r['awaitingRereview'])})" for r in needs_rereview)
        )
    if awaiting:
        lines.append(f"- ⏳ Awaiting a named reviewer: {nums(awaiting)}")
    if no_reviewer:
        lines.append(f"- ⚠️ No reviewer requested yet: {nums(no_reviewer)}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="owner/repo (default: current dir's GitHub repo)")
    parser.add_argument("--author", help="PR author login (default: authenticated gh user)")
    parser.add_argument("--state", default="open", choices=["open", "closed", "merged", "all"])
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--format", default="md", choices=["md", "json"])
    args = parser.parse_args()

    repo = resolve_repo(args.repo)
    author = resolve_author(args.author)

    raw = run_gh(
        [
            "pr", "list",
            "-R", repo,
            "--state", args.state,
            "--author", author,
            "--limit", str(args.limit),
            "--json", PR_FIELDS,
        ]
    )
    prs = json.loads(raw)
    rows = sorted((classify(pr, author) for pr in prs), key=lambda r: r["number"], reverse=True)

    if args.format == "json":
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        if not rows:
            print(f"No {args.state} PRs authored by `{author}` in `{repo}`.")
        else:
            print(render_md(rows, repo, author, args.state))


if __name__ == "__main__":
    main()
