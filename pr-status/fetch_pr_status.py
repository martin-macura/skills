#!/usr/bin/env python3
"""Fetch a GitHub user's authored PRs with their review status.

Read-only for the PR/issue data: shells out to `gh` (which must be
authenticated) and never writes. When a project board is configured it also
reads the board to show each linked issue's column, and *drafts* (never runs)
`gh project item-edit` commands to move In-Progress issues to "In Review" —
only once **every** open PR closing the issue has a human reviewer, so a stack
with one reviewed layer and four unreviewed ones stays In Progress.

Prints a Markdown table (default) or JSON to stdout.

Examples:
    python3 fetch_pr_status.py                         # your open PRs in the current repo
    python3 fetch_pr_status.py --repo owner/repo
    python3 fetch_pr_status.py --author someone --state all
    python3 fetch_pr_status.py --format json
    python3 fetch_pr_status.py --board 3 --board-owner softero-cz
    python3 fetch_pr_status.py --no-board
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone

# Reviewers that are bots, not humans — surfaced separately so they don't look
# like a real human sign-off.
BOT_REVIEWERS = {"copilot-pull-request-reviewer"}

# Repos with a known default project board: repo -> (project number, owner).
# Keeps the board column on for the user's usual repo without a flag; other
# repos get no board column unless --board is passed.
DEFAULT_BOARDS = {
    "softero-cz/siegl-app": ("3", "softero-cz"),
}

# Board column emoji per (lower-cased) status option name. Unknown options just
# render without an emoji, so a renamed/extra column still shows its text.
BOARD_EMOJI = {
    "to estimate": "📐",
    "todo": "📋",
    "in progress": "🔧",
    "in review": "👀",
    "merged": "🔀",
    "completed": "✅",
    "done": "✅",
}

PR_FIELDS = (
    "number,title,state,reviewDecision,headRefName,isDraft,"
    "reviewRequests,reviews,updatedAt,url,closingIssuesReferences"
)

# Fallbacks only — see issues_for_pr. The title/branch carry at most ONE issue
# number, so they can't describe a PR that closes several.
ISSUE_IN_TITLE = re.compile(r"#(\d+)")
ISSUE_IN_BRANCH = re.compile(r"^[a-z]+/(\d+)-")


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


def run_gh_optional(args: list[str]) -> tuple[str | None, str | None]:
    """Like run_gh but returns (stdout, None) or (None, error) instead of exiting.

    Used for the project-board reads, which need the `read:project` scope and
    should degrade to "board unavailable" rather than kill the whole report.
    """
    try:
        result = subprocess.run(
            ["gh", *args],
            check=True,
            capture_output=True,
            text=True,
        )

        return result.stdout, None
    except FileNotFoundError:
        return None, "`gh` CLI not found on PATH"
    except subprocess.CalledProcessError as exc:
        return None, (exc.stderr.strip() or "gh command failed")


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


def resolve_board(args: argparse.Namespace, repo: str) -> tuple[str | None, str | None]:
    if args.no_board:
        return None, None
    if args.board:
        return args.board, (args.board_owner or repo.split("/")[0])
    if repo in DEFAULT_BOARDS:
        return DEFAULT_BOARDS[repo]

    return None, None


def issues_for_pr(pr: dict) -> list[int]:
    """Every issue the PR closes, ascending.

    `closingIssuesReferences` is GitHub's own linkage, parsed from the
    `Fixes #N` / `Closes #N` lines in the PR body — so it catches a batch PR
    that closes several issues, which the title and branch name cannot. Only
    when GitHub reports no link at all do we fall back to the `#NNN` in the
    title, then the `<feat|fix|chore|...>/NNN-...` branch prefix (a PR whose
    body forgot the trailer still shows its board column that way).
    """
    linked = sorted(
        {ref["number"] for ref in (pr.get("closingIssuesReferences") or []) if ref.get("number")}
    )
    if linked:
        return linked

    m = ISSUE_IN_TITLE.search(pr.get("title", ""))
    if m:
        return [int(m.group(1))]
    m = ISSUE_IN_BRANCH.search(pr.get("headRefName", ""))
    if m:
        return [int(m.group(1))]

    return []


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

    # A real human is on the hook: requested (minus bots) or has already reviewed.
    human_requested = [w for w in requested if w not in BOT_REVIEWERS]
    has_human_reviewer = bool(human_requested or approvals or changes or commented)

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
        "state": pr.get("state"),
        "isDraft": pr.get("isDraft", False),
        "decision": decision or "(none)",
        "issues": issues_for_pr(pr),
        "requested": requested,
        "approvals": approvals,
        "changesRequested": changes,
        "commented": commented,
        "awaitingRereview": awaiting_rereview,
        "hasHumanReviewer": has_human_reviewer,
        "botReviewed": bot_commented(pr.get("reviews", [])),
        "updatedAt": pr.get("updatedAt"),
        "flag": flag,
    }


def fetch_board(board_number: str, owner: str, want: set[int]) -> tuple[dict | None, str | None]:
    """Read the project board: project id, Status field + options, and the
    status/item-id of each wanted issue. Returns (board, None) or (None, error).

    The item list is fetched with a limit past the board's total item count —
    a short limit silently drops issues and makes them look "not on board".
    """
    out, err = run_gh_optional(
        ["project", "list", "--owner", owner, "--format", "json", "--limit", "200"]
    )
    if out is None:
        return None, f"couldn't list projects for {owner} ({err})"

    projects = json.loads(out).get("projects", [])
    proj = next((p for p in projects if str(p.get("number")) == str(board_number)), None)
    if not proj:
        return None, f"project #{board_number} not found for owner {owner}"

    project_id = proj.get("id")
    total = (proj.get("items") or {}).get("totalCount") or 0

    out, err = run_gh_optional(
        ["project", "field-list", str(board_number), "--owner", owner, "--format", "json", "--limit", "100"]
    )
    if out is None:
        return None, f"couldn't read board fields ({err})"

    status_field = next(
        (f for f in json.loads(out).get("fields", []) if (f.get("name") or "").strip().lower() == "status"),
        None,
    )
    if not status_field:
        return None, "board has no 'Status' field"

    options = {(o.get("name") or "").strip().lower(): o.get("id") for o in status_field.get("options", [])}

    out, err = run_gh_optional(
        ["project", "item-list", str(board_number), "--owner", owner, "--format", "json",
         "--limit", str(max(total + 25, 100))]
    )
    if out is None:
        return None, f"couldn't list board items ({err})"

    items: dict[int, dict] = {}
    for it in json.loads(out).get("items", []):
        c = it.get("content") or {}
        if c.get("type") == "Issue" and c.get("number") in want:
            items[c.get("number")] = {"status": it.get("status") or "", "itemId": it.get("id")}

    return {
        "number": str(board_number),
        "owner": owner,
        "projectId": project_id,
        "statusFieldId": status_field.get("id"),
        "options": options,
        "inReviewOptionId": options.get("in review"),
        "items": items,
    }, None


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


def board_cell(row: dict, board: dict) -> str:
    """One line per linked issue; issues sharing a column collapse onto one line,
    so a five-issue batch PR reads as '🔧 In Progress (#1089, #1093, …)'."""
    issues = row.get("issues") or []
    if not issues:
        return "—"

    by_status: dict[str, list[int]] = {}
    for issue in issues:
        info = board["items"].get(issue)
        status = info["status"] or "(no status)" if info else "_(not on board)_"
        by_status.setdefault(status, []).append(issue)

    parts = []
    for status, nums in by_status.items():
        listed = ", ".join(f"#{n}" for n in nums)
        if status == "_(not on board)_":
            parts.append(f"{listed} _(not on board)_")
            continue
        emoji = BOARD_EMOJI.get(status.strip().lower(), "")
        parts.append(f"{f'{emoji} {status}'.strip()} ({listed})")

    return "<br>".join(parts)


def move_candidates(
    rows: list[dict], board: dict | None
) -> tuple[list[tuple[int, list[dict], dict]], list[tuple[int, list[dict], list[dict]]]]:
    """Split 'In Progress' issues into (ready to move, still blocked).

    The unit is the **issue**, not the PR: work is often split into a stack of
    PRs that all close the same issue (`Fixes #N` in each), and an issue is only
    genuinely in review once *every* PR in that stack has a human reviewer. Going
    per-PR let one reviewed layer drag the whole issue to "In Review" while the
    rest of the stack still sat unreviewed — and emitted the same item-edit
    command once per PR, since they share one board item.

    Only **open** PRs count toward the stack; a merged/closed layer is done and
    isn't waiting on anyone. A draft with no reviewer does block, which is the
    point — the issue isn't fully up for review yet.
    """
    if not board or not board.get("inReviewOptionId"):
        return [], []

    by_issue: dict[int, list[dict]] = {}
    for row in rows:
        if row.get("state") not in (None, "OPEN"):
            continue
        for issue in row.get("issues") or []:
            by_issue.setdefault(issue, []).append(row)

    ready: list[tuple[int, list[dict], dict]] = []
    blocked: list[tuple[int, list[dict], list[dict]]] = []
    for issue in sorted(by_issue):
        info = board["items"].get(issue)
        if not info or (info["status"] or "").strip().lower() != "in progress":
            continue

        stack = sorted(by_issue[issue], key=lambda r: r["number"])
        missing = [r for r in stack if not r.get("hasHumanReviewer")]
        if missing:
            blocked.append((issue, stack, missing))
        else:
            ready.append((issue, stack, info))

    return ready, blocked


def render_md(
    rows: list[dict],
    repo: str,
    author: str,
    state: str,
    board: dict | None,
    board_error: str | None,
) -> str:
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    has_board = board is not None

    lines = [f"**Open PRs by `{author}` in `{repo}`** (state: {state}) — as of {now}", ""]
    if has_board:
        lines += [
            "| PR | Title | Status | Reviewers | Board | Updated |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    else:
        lines += [
            "| PR | Title | Status | Reviewers | Updated |",
            "| --- | --- | --- | --- | --- |",
        ]

    for row in rows:
        draft = " _(draft)_" if row["isDraft"] else ""
        title = row["title"].replace("|", "\\|")
        link = f"[#{row['number']}]({row['url']})" if row["url"] else f"#{row['number']}"
        if has_board:
            lines.append(
                f"| {link} | {title}{draft} | {row['flag']} | {reviewers_cell(row)} | "
                f"{board_cell(row, board)} | {fmt_date(row['updatedAt'])} |"
            )
        else:
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

    if board_error:
        lines += ["", f"> ⚠️ Board status unavailable: {board_error}"]

    ready, blocked = move_candidates(rows, board)
    if ready:
        lines += [
            "",
            "**Move to In Review** — In Progress on the board **and every open PR** closing "
            "the issue has a human reviewer. These are GitHub writes; run them yourself:",
        ]
        # One command per fenced block, and NO trailing `# comment` — the chat UI's
        # Run button feeds the block to a runner that doesn't strip shell comments,
        # so an inline comment ends up as a bogus argument. The issue/PR label goes
        # on a prose line above the fence instead.
        for issue, stack, info in ready:
            label = "PRs" if len(stack) > 1 else "PR"
            lines += [
                "",
                f"Issue #{issue} ({label} {nums(stack)}):",
                "",
                "```bash",
                f"gh project item-edit --project-id {board['projectId']} "
                f"--id {info['itemId']} --field-id {board['statusFieldId']} "
                f"--single-select-option-id {board['inReviewOptionId']}",
                "```",
            ]

    if blocked:
        lines += [
            "",
            "**Staying In Progress** — part of the stack has no reviewer yet, so the issue "
            "isn't fully in review:",
        ]
        for issue, stack, missing in blocked:
            lines.append(
                f"- **#{issue}** — {len(missing)}/{len(stack)} open PR(s) without a reviewer: "
                f"{nums(missing)}"
            )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="owner/repo (default: current dir's GitHub repo)")
    parser.add_argument("--author", help="PR author login (default: authenticated gh user)")
    parser.add_argument("--state", default="open", choices=["open", "closed", "merged", "all"])
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--format", default="md", choices=["md", "json"])
    parser.add_argument("--board", help="project board number for issue status (default: known per-repo board)")
    parser.add_argument("--board-owner", help="owner of the project board (default: repo owner)")
    parser.add_argument("--no-board", action="store_true", help="skip the board status column entirely")
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

    board = None
    board_error = None
    board_number, board_owner = resolve_board(args, repo)
    if board_number and rows:
        want = {issue for r in rows for issue in (r.get("issues") or [])}
        if want:
            board, board_error = fetch_board(board_number, board_owner, want)

    if args.format == "json":
        if board:
            for row in rows:
                row["board"] = [
                    {
                        "issue": issue,
                        "status": (board["items"].get(issue) or {}).get("status"),
                        "itemId": (board["items"].get(issue) or {}).get("itemId"),
                    }
                    for issue in (row.get("issues") or [])
                ]
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        if not rows:
            print(f"No {args.state} PRs authored by `{author}` in `{repo}`.")
        else:
            print(render_md(rows, repo, author, args.state, board, board_error))


if __name__ == "__main__":
    main()
