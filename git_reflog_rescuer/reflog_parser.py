"""Parse git reflog output: extract hash, action, message, timestamp."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ReflogEntry:
    """A single reflog entry."""
    index: int
    hash: str  # Full commit hash
    short_hash: str  # First 7 chars
    action: str  # commit, rebase, reset, checkout, merge, pull, etc.
    message: str  # Human-readable message
    timestamp: datetime
    relative_time: str  # e.g., "2 hours ago"
    selector: str  # e.g., "HEAD@{0}"
    raw_line: str  # Original reflog line
    is_orphaned: bool = False  # True if commit isn't reachable from HEAD
    branch_from: str = ""
    branch_to: str = ""

    @property
    def time_str(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")

    @property
    def day_str(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d")

    @property
    def action_emoji(self) -> str:
        """Return a text symbol for the action type."""
        return ACTION_SYMBOLS.get(self.action, "*")


# Action type symbols for terminal display
ACTION_SYMBOLS: dict[str, str] = {
    "commit": "+",
    "commit (initial)": "+",
    "commit (amend)": "~",
    "commit (merge)": "M",
    "merge": "M",
    "rebase": "R",
    "rebase (start)": "R",
    "rebase (continue)": "R",
    "rebase (finish)": "R",
    "rebase (abort)": "!",
    "rebase (pick)": "R",
    "rebase (reword)": "R",
    "rebase (squash)": "R",
    "reset": "!",
    "checkout": ">",
    "pull": "v",
    "clone": "C",
    "cherry-pick": "P",
    "revert": "U",
}

# Action colors for the TUI
ACTION_COLORS: dict[str, str] = {
    "commit": "green",
    "commit (initial)": "green",
    "commit (amend)": "yellow",
    "commit (merge)": "cyan",
    "merge": "cyan",
    "rebase": "magenta",
    "rebase (start)": "magenta",
    "rebase (continue)": "magenta",
    "rebase (finish)": "magenta",
    "rebase (abort)": "red",
    "reset": "red",
    "checkout": "blue",
    "pull": "blue",
    "clone": "blue",
    "cherry-pick": "yellow",
    "revert": "yellow",
}

# Regex for parsing reflog lines
# Format: hash HEAD@{n}: action: message
REFLOG_LINE_RE = re.compile(
    r'^([0-9a-f]+)\s+'
    r'(HEAD@\{\d+\}):\s+'
    r'(.+)$'
)

# Action extraction from the description
ACTION_RE = re.compile(
    r'^(commit|commit \(initial\)|commit \(amend\)|commit \(merge\)|'
    r'merge|rebase(?:\s*\([^)]*\))?|reset|checkout|pull|clone|cherry-pick|revert)'
    r'(?::\s*(.*))?$',
    re.I,
)

# Checkout message: "checkout: moving from X to Y"
CHECKOUT_RE = re.compile(
    r'checkout: moving from (\S+) to (\S+)',
    re.I,
)


def parse_reflog(repo_path: str = ".") -> list[ReflogEntry]:
    """Parse git reflog and return structured entries."""
    try:
        result = subprocess.run(
            [
                "git", "-C", repo_path, "reflog", "show",
                "--format=%H %gd: %gs",
                "--date=iso",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git reflog failed: {result.stderr.strip()}")
    except FileNotFoundError:
        raise RuntimeError("git is not installed or not in PATH")

    # Also get timestamps
    ts_result = subprocess.run(
        [
            "git", "-C", repo_path, "reflog", "show",
            "--format=%H %gd %gD %ci",
            "--date=iso",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    # Also get relative times
    rel_result = subprocess.run(
        [
            "git", "-C", repo_path, "reflog", "show",
            "--format=%H %gd %cr",
            "--date=relative",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    # Build timestamp lookup
    ts_lookup: dict[str, datetime] = {}
    for line in ts_result.stdout.strip().splitlines():
        parts = line.split(" ", 3)
        if len(parts) >= 4:
            hash_val = parts[0]
            try:
                # Parse ISO date (2024-01-15 10:30:45 +0000)
                date_str = parts[-1].strip() if len(parts) > 3 else ""
                # Handle timezone offset
                date_str = re.sub(r'([+-]\d{2})(\d{2})$', r'\1:\2', date_str)
                ts = datetime.fromisoformat(date_str)
                ts_lookup[f"{hash_val}_{parts[1]}"] = ts
            except (ValueError, IndexError):
                pass

    # Build relative time lookup
    rel_lookup: dict[str, str] = {}
    for line in rel_result.stdout.strip().splitlines():
        parts = line.split(" ", 2)
        if len(parts) >= 3:
            rel_lookup[f"{parts[0]}_{parts[1]}"] = parts[2]

    # Parse main output
    entries: list[ReflogEntry] = []
    for idx, line in enumerate(result.stdout.strip().splitlines()):
        if not line.strip():
            continue

        match = REFLOG_LINE_RE.match(line)
        if not match:
            continue

        hash_val = match.group(1)
        selector = match.group(2)
        description = match.group(3)
        key = f"{hash_val}_{selector}"

        # Parse action and message
        action, message = _parse_action(description)

        # Parse checkout branches
        branch_from = ""
        branch_to = ""
        checkout_m = CHECKOUT_RE.match(description)
        if checkout_m:
            branch_from = checkout_m.group(1)
            branch_to = checkout_m.group(2)

        ts = ts_lookup.get(key, datetime.now())
        rel_time = rel_lookup.get(key, "unknown")

        entry = ReflogEntry(
            index=idx,
            hash=hash_val,
            short_hash=hash_val[:7],
            action=action,
            message=message,
            timestamp=ts,
            relative_time=rel_time,
            selector=selector,
            raw_line=line,
            branch_from=branch_from,
            branch_to=branch_to,
        )
        entries.append(entry)

    # Mark orphaned commits
    _mark_orphaned(entries, repo_path)

    return entries


def _parse_action(description: str) -> tuple[str, str]:
    """Extract action type and message from reflog description."""
    match = ACTION_RE.match(description)
    if match:
        action = match.group(1).lower()
        message = (match.group(2) or "").strip()
        return action, message

    # Fallback
    parts = description.split(":", 1)
    if len(parts) == 2:
        return parts[0].strip().lower(), parts[1].strip()
    return "unknown", description


def _mark_orphaned(entries: list[ReflogEntry], repo_path: str) -> None:
    """Mark entries whose commits are not reachable from any branch."""
    try:
        # Get all reachable commit hashes
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-list", "--all"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        reachable = set(result.stdout.strip().splitlines())

        for entry in entries:
            if entry.hash not in reachable:
                entry.is_orphaned = True
    except (subprocess.TimeoutExpired, RuntimeError):
        pass  # Can't determine orphan status, leave as False
