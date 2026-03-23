"""Restore operations: create branch, cherry-pick, reset. Always creates backup first."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone

from git_reflog_rescuer.reflog_parser import ReflogEntry


@dataclass
class RestoreResult:
    success: bool
    operation: str
    message: str
    backup_branch: str = ""
    target_branch: str = ""
    commit_hash: str = ""


def _run_git(args: list[str], repo_path: str = ".") -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path] + args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", "Command timed out"
    except FileNotFoundError:
        return 1, "", "git not found"


def _get_current_branch(repo_path: str = ".") -> str:
    """Get the current branch name."""
    rc, out, _ = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_path)
    return out if rc == 0 else "HEAD"


def _create_backup(repo_path: str = ".") -> str:
    """Create a backup branch at current HEAD."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    branch_name = f"rescue-backup/{timestamp}"
    rc, _, err = _run_git(["branch", branch_name], repo_path)
    if rc != 0:
        raise RuntimeError(f"Failed to create backup branch: {err}")
    return branch_name


def create_branch_from_commit(
    entry: ReflogEntry,
    branch_name: str | None = None,
    repo_path: str = ".",
) -> RestoreResult:
    """Create a new branch pointing at the reflog entry's commit.

    This is the safest restore method -- it doesn't modify your current branch.
    """
    if not branch_name:
        short = entry.short_hash
        branch_name = f"rescued/{short}"

    # Check if branch already exists
    rc, _, _ = _run_git(["rev-parse", "--verify", branch_name], repo_path)
    if rc == 0:
        return RestoreResult(
            success=False,
            operation="create-branch",
            message=f"Branch '{branch_name}' already exists. Choose a different name.",
        )

    # Create the branch
    rc, out, err = _run_git(["branch", branch_name, entry.hash], repo_path)
    if rc != 0:
        return RestoreResult(
            success=False,
            operation="create-branch",
            message=f"Failed to create branch: {err}",
            commit_hash=entry.hash,
        )

    return RestoreResult(
        success=True,
        operation="create-branch",
        message=f"Created branch '{branch_name}' at {entry.short_hash}",
        target_branch=branch_name,
        commit_hash=entry.hash,
    )


def cherry_pick_commit(
    entry: ReflogEntry,
    repo_path: str = ".",
) -> RestoreResult:
    """Cherry-pick a commit onto the current branch.

    Creates a backup branch first.
    """
    # Create backup
    try:
        backup = _create_backup(repo_path)
    except RuntimeError as e:
        return RestoreResult(
            success=False,
            operation="cherry-pick",
            message=str(e),
        )

    current = _get_current_branch(repo_path)

    # Perform cherry-pick
    rc, out, err = _run_git(["cherry-pick", "--no-commit", entry.hash], repo_path)
    if rc != 0:
        # Abort the cherry-pick
        _run_git(["cherry-pick", "--abort"], repo_path)
        return RestoreResult(
            success=False,
            operation="cherry-pick",
            message=f"Cherry-pick failed (conflicts). Aborted. Backup at '{backup}'. Error: {err}",
            backup_branch=backup,
            commit_hash=entry.hash,
        )

    # Commit the cherry-pick
    rc, _, err = _run_git(
        ["commit", "-m", f"Cherry-pick {entry.short_hash}: {entry.message}"],
        repo_path,
    )
    if rc != 0:
        return RestoreResult(
            success=False,
            operation="cherry-pick",
            message=f"Commit failed after cherry-pick: {err}",
            backup_branch=backup,
            commit_hash=entry.hash,
        )

    return RestoreResult(
        success=True,
        operation="cherry-pick",
        message=f"Cherry-picked {entry.short_hash} onto '{current}'. Backup at '{backup}'.",
        backup_branch=backup,
        target_branch=current,
        commit_hash=entry.hash,
    )


def reset_to_entry(
    entry: ReflogEntry,
    mode: str = "soft",
    repo_path: str = ".",
) -> RestoreResult:
    """Reset current branch to a reflog entry.

    Creates a backup branch first.

    Args:
        mode: "soft" (keep changes staged), "mixed" (unstage), or "hard" (discard).
    """
    if mode not in ("soft", "mixed", "hard"):
        return RestoreResult(
            success=False,
            operation="reset",
            message=f"Invalid reset mode: {mode}. Use soft, mixed, or hard.",
        )

    # Create backup
    try:
        backup = _create_backup(repo_path)
    except RuntimeError as e:
        return RestoreResult(
            success=False,
            operation="reset",
            message=str(e),
        )

    current = _get_current_branch(repo_path)

    # Perform reset
    rc, out, err = _run_git(["reset", f"--{mode}", entry.hash], repo_path)
    if rc != 0:
        return RestoreResult(
            success=False,
            operation="reset",
            message=f"Reset failed: {err}. Backup at '{backup}'.",
            backup_branch=backup,
            commit_hash=entry.hash,
        )

    return RestoreResult(
        success=True,
        operation="reset",
        message=(
            f"Reset '{current}' to {entry.short_hash} (--{mode}). "
            f"Backup at '{backup}'."
        ),
        backup_branch=backup,
        target_branch=current,
        commit_hash=entry.hash,
    )


def list_rescue_branches(repo_path: str = ".") -> list[str]:
    """List all rescue backup branches."""
    rc, out, _ = _run_git(["branch", "--list", "rescue-backup/*", "rescued/*"], repo_path)
    if rc != 0:
        return []
    return [b.strip().lstrip("* ") for b in out.splitlines() if b.strip()]


def delete_rescue_branch(branch: str, repo_path: str = ".") -> RestoreResult:
    """Delete a rescue branch (cleanup)."""
    if not branch.startswith(("rescue-backup/", "rescued/")):
        return RestoreResult(
            success=False,
            operation="delete-branch",
            message="Can only delete rescue-backup/* or rescued/* branches.",
        )

    rc, _, err = _run_git(["branch", "-D", branch], repo_path)
    if rc != 0:
        return RestoreResult(
            success=False,
            operation="delete-branch",
            message=f"Failed to delete: {err}",
        )

    return RestoreResult(
        success=True,
        operation="delete-branch",
        message=f"Deleted branch '{branch}'.",
    )
