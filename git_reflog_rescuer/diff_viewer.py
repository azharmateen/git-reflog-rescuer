"""Show diff between reflog entries: what changed, what was lost."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from git_reflog_rescuer.reflog_parser import ReflogEntry


@dataclass
class DiffInfo:
    """Information about a diff between two commits."""
    hash_from: str
    hash_to: str
    stat: str  # --stat output
    diff: str  # Full diff
    files_changed: int
    insertions: int
    deletions: int
    commit_message: str
    author: str
    error: str | None = None


def get_diff(entry: ReflogEntry, repo_path: str = ".") -> DiffInfo:
    """Get the diff for a single reflog entry (what it introduced)."""
    commit_hash = entry.hash

    # Get commit info
    info = _get_commit_info(commit_hash, repo_path)

    # For commits: diff against parent
    if entry.action.startswith("commit"):
        parent = f"{commit_hash}~1"
        return _compute_diff(parent, commit_hash, repo_path, info)

    # For resets/rebases: show what the commit contains
    return _compute_diff(f"{commit_hash}~1", commit_hash, repo_path, info)


def get_diff_between(entry_a: ReflogEntry, entry_b: ReflogEntry, repo_path: str = ".") -> DiffInfo:
    """Get the diff between two reflog entries."""
    info = _get_commit_info(entry_b.hash, repo_path)
    return _compute_diff(entry_a.hash, entry_b.hash, repo_path, info)


def get_commit_details(commit_hash: str, repo_path: str = ".") -> str:
    """Get detailed commit information."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "show", "--stat", "--format=fuller", commit_hash],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        return result.stdout
    except Exception as e:
        return f"Error: {e}"


def get_file_list(commit_hash: str, repo_path: str = ".") -> list[str]:
    """Get list of files changed in a commit."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return [f for f in result.stdout.strip().splitlines() if f]
    except Exception:
        pass
    return []


def is_commit_reachable(commit_hash: str, repo_path: str = ".") -> bool:
    """Check if a commit is reachable from any branch."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "branch", "--contains", commit_hash],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def _compute_diff(hash_from: str, hash_to: str, repo_path: str, info: dict) -> DiffInfo:
    """Compute diff between two commits."""
    # Get stat
    stat = ""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "diff", "--stat", hash_from, hash_to],
            capture_output=True,
            text=True,
            timeout=10,
        )
        stat = result.stdout if result.returncode == 0 else ""
    except Exception:
        pass

    # Get full diff
    diff = ""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "diff", "--color=never", hash_from, hash_to],
            capture_output=True,
            text=True,
            timeout=10,
        )
        diff = result.stdout if result.returncode == 0 else ""
    except Exception:
        pass

    # Parse stat numbers
    files_changed, insertions, deletions = _parse_stat_summary(stat)

    return DiffInfo(
        hash_from=hash_from,
        hash_to=hash_to,
        stat=stat,
        diff=diff,
        files_changed=files_changed,
        insertions=insertions,
        deletions=deletions,
        commit_message=info.get("message", ""),
        author=info.get("author", ""),
    )


def _get_commit_info(commit_hash: str, repo_path: str) -> dict:
    """Get basic commit info."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "log", "-1", "--format=%an|%s", commit_hash],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split("|", 1)
            return {
                "author": parts[0] if parts else "",
                "message": parts[1] if len(parts) > 1 else "",
            }
    except Exception:
        pass
    return {"author": "", "message": ""}


def _parse_stat_summary(stat: str) -> tuple[int, int, int]:
    """Parse the summary line of git diff --stat."""
    import re
    # "3 files changed, 10 insertions(+), 5 deletions(-)"
    lines = stat.strip().splitlines()
    if not lines:
        return (0, 0, 0)

    last_line = lines[-1]
    files = 0
    ins = 0
    dels = 0

    m = re.search(r'(\d+) files? changed', last_line)
    if m:
        files = int(m.group(1))
    m = re.search(r'(\d+) insertions?', last_line)
    if m:
        ins = int(m.group(1))
    m = re.search(r'(\d+) deletions?', last_line)
    if m:
        dels = int(m.group(1))

    return (files, ins, dels)
