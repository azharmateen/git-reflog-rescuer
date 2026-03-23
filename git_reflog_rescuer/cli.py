"""CLI entry point: TUI launcher and non-TUI list command."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from git_reflog_rescuer import __version__

console = Console()


@click.group(invoke_without_command=True)
@click.version_option(version=__version__)
@click.option("--repo", "-r", default=".", help="Path to git repository")
@click.pass_context
def main(ctx: click.Context, repo: str) -> None:
    """git-reflog-rescuer: Visual TUI for recovering lost git commits."""
    ctx.ensure_object(dict)
    ctx.obj["repo"] = repo

    if ctx.invoked_subcommand is None:
        # Launch TUI
        _launch_tui(repo)


def _launch_tui(repo: str) -> None:
    """Launch the Textual TUI."""
    # Verify we're in a git repo
    import subprocess
    result = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        console.print(f"[red]Error:[/red] '{repo}' is not a git repository.")
        sys.exit(1)

    from git_reflog_rescuer.app import ReflogApp
    app = ReflogApp(repo_path=repo)
    app.run()


@main.command()
@click.option("--max", "max_entries", default=50, help="Maximum entries to show")
@click.option("--orphaned-only", is_flag=True, help="Only show orphaned commits")
@click.pass_context
def list(ctx: click.Context, max_entries: int, orphaned_only: bool) -> None:
    """List reflog entries in the terminal (non-TUI mode)."""
    repo = ctx.obj["repo"]

    try:
        from git_reflog_rescuer.reflog_parser import parse_reflog
        entries = parse_reflog(repo)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if orphaned_only:
        entries = [e for e in entries if e.is_orphaned]

    if not entries:
        if orphaned_only:
            console.print("[green]No orphaned commits found.[/green]")
        else:
            console.print("[yellow]No reflog entries found.[/yellow]")
        return

    from git_reflog_rescuer.timeline import print_summary, print_timeline

    print_summary(entries, console)
    print_timeline(entries, console, max_entries=max_entries)


@main.command()
@click.argument("commit_hash")
@click.option("--name", "-n", help="Branch name (default: rescued/<hash>)")
@click.pass_context
def rescue(ctx: click.Context, commit_hash: str, name: str | None) -> None:
    """Create a branch from a specific commit hash (quick rescue)."""
    repo = ctx.obj["repo"]

    try:
        from git_reflog_rescuer.reflog_parser import parse_reflog
        entries = parse_reflog(repo)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    # Find the entry matching the hash
    target = None
    for entry in entries:
        if entry.hash.startswith(commit_hash) or entry.short_hash == commit_hash:
            target = entry
            break

    if not target:
        console.print(f"[red]Error:[/red] Commit '{commit_hash}' not found in reflog.")
        console.print("Run [cyan]git-reflog-rescuer list[/cyan] to see available entries.")
        sys.exit(1)

    from git_reflog_rescuer.restorer import create_branch_from_commit

    result = create_branch_from_commit(target, branch_name=name, repo_path=repo)
    if result.success:
        console.print(f"[green]{result.message}[/green]")
    else:
        console.print(f"[red]{result.message}[/red]")
        sys.exit(1)


@main.command()
@click.pass_context
def branches(ctx: click.Context) -> None:
    """List all rescue backup branches."""
    repo = ctx.obj["repo"]

    from git_reflog_rescuer.restorer import list_rescue_branches

    rescue_branches = list_rescue_branches(repo)
    if not rescue_branches:
        console.print("[dim]No rescue branches found.[/dim]")
        return

    console.print("[bold]Rescue branches:[/bold]")
    for branch in rescue_branches:
        console.print(f"  {branch}")
    console.print(f"\nTotal: {len(rescue_branches)}")


@main.command()
@click.argument("branch")
@click.pass_context
def cleanup(ctx: click.Context, branch: str) -> None:
    """Delete a rescue backup branch."""
    repo = ctx.obj["repo"]

    from git_reflog_rescuer.restorer import delete_rescue_branch

    result = delete_rescue_branch(branch, repo)
    if result.success:
        console.print(f"[green]{result.message}[/green]")
    else:
        console.print(f"[red]{result.message}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
