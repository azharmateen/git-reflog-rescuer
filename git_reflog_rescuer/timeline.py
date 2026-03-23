"""Build visual timeline: group by day, color by action type, highlight orphaned commits."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from git_reflog_rescuer.reflog_parser import ACTION_COLORS, ReflogEntry


def group_by_day(entries: list[ReflogEntry]) -> dict[str, list[ReflogEntry]]:
    """Group reflog entries by day."""
    groups: dict[str, list[ReflogEntry]] = defaultdict(list)
    for entry in entries:
        day = entry.day_str
        groups[day].append(entry)
    return dict(groups)


def print_timeline(
    entries: list[ReflogEntry],
    console: Console | None = None,
    max_entries: int = 50,
    highlight_orphaned: bool = True,
) -> None:
    """Print a beautiful timeline to the terminal."""
    console = console or Console()

    if not entries:
        console.print("[yellow]No reflog entries found.[/yellow]")
        return

    grouped = group_by_day(entries)

    shown = 0
    for day, day_entries in sorted(grouped.items(), reverse=True):
        console.print(f"\n[bold blue]{day}[/bold blue]")
        console.print("[dim]" + "-" * 60 + "[/dim]")

        for entry in day_entries:
            if shown >= max_entries:
                remaining = len(entries) - shown
                console.print(f"\n[dim]... and {remaining} more entries[/dim]")
                return

            _print_entry(console, entry, highlight_orphaned)
            shown += 1


def _print_entry(console: Console, entry: ReflogEntry, highlight_orphaned: bool) -> None:
    """Print a single timeline entry."""
    color = ACTION_COLORS.get(entry.action, "white")
    symbol = entry.action_emoji

    # Build the line
    line = Text()

    # Time
    time_str = entry.timestamp.strftime("%H:%M:%S")
    line.append(f"  {time_str} ", style="dim")

    # Symbol
    line.append(f"[{symbol}]", style=f"bold {color}")

    # Hash
    if entry.is_orphaned and highlight_orphaned:
        line.append(f" {entry.short_hash}", style="bold red on dark_red")
        line.append(" ORPHANED", style="bold red")
    else:
        line.append(f" {entry.short_hash}", style=f"bold {color}")

    # Action
    line.append(f" {entry.action}", style=color)

    # Message
    if entry.message:
        msg = entry.message[:60]
        line.append(f": {msg}", style="white")

    # Branch info for checkouts
    if entry.branch_from and entry.branch_to:
        line.append(f" ({entry.branch_from} -> {entry.branch_to})", style="dim")

    console.print(line)


def build_timeline_data(entries: list[ReflogEntry]) -> list[dict[str, Any]]:
    """Build structured timeline data for the TUI."""
    timeline: list[dict[str, Any]] = []

    for entry in entries:
        color = ACTION_COLORS.get(entry.action, "white")
        timeline.append({
            "index": entry.index,
            "hash": entry.short_hash,
            "full_hash": entry.hash,
            "action": entry.action,
            "symbol": entry.action_emoji,
            "message": entry.message,
            "time": entry.timestamp.strftime("%H:%M:%S"),
            "date": entry.day_str,
            "relative": entry.relative_time,
            "color": color,
            "is_orphaned": entry.is_orphaned,
            "selector": entry.selector,
            "branch_from": entry.branch_from,
            "branch_to": entry.branch_to,
        })

    return timeline


def print_summary(entries: list[ReflogEntry], console: Console | None = None) -> None:
    """Print a summary of the reflog."""
    console = console or Console()

    if not entries:
        console.print("[yellow]Empty reflog.[/yellow]")
        return

    # Count by action
    action_counts: dict[str, int] = defaultdict(int)
    orphaned_count = 0
    for e in entries:
        action_counts[e.action] += 1
        if e.is_orphaned:
            orphaned_count += 1

    table = Table(title="Reflog Summary")
    table.add_column("Action", style="bold")
    table.add_column("Count", justify="right")

    for action, count in sorted(action_counts.items(), key=lambda x: -x[1]):
        color = ACTION_COLORS.get(action, "white")
        table.add_row(f"[{color}]{action}[/{color}]", str(count))

    console.print(table)
    console.print(f"\nTotal entries: {len(entries)}")
    if orphaned_count:
        console.print(f"[red bold]Orphaned commits: {orphaned_count}[/red bold] (recoverable!)")

    # Time range
    if len(entries) >= 2:
        newest = entries[0].timestamp.strftime("%Y-%m-%d %H:%M")
        oldest = entries[-1].timestamp.strftime("%Y-%m-%d %H:%M")
        console.print(f"Time range: {oldest} -> {newest}")
