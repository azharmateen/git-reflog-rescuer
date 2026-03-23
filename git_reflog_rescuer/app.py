"""Textual TUI: timeline view, diff preview, action bar."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static

from git_reflog_rescuer.diff_viewer import get_commit_details, get_diff
from git_reflog_rescuer.reflog_parser import (
    ACTION_COLORS,
    ReflogEntry,
    parse_reflog,
)
from git_reflog_rescuer.restorer import (
    cherry_pick_commit,
    create_branch_from_commit,
    reset_to_entry,
)


class TimelineItem(ListItem):
    """A single item in the timeline list."""

    def __init__(self, entry: ReflogEntry) -> None:
        super().__init__()
        self.entry = entry

    def compose(self) -> ComposeResult:
        e = self.entry
        color = ACTION_COLORS.get(e.action, "white")
        orphan = " [ORPHANED]" if e.is_orphaned else ""
        time_str = e.timestamp.strftime("%H:%M")
        msg = e.message[:50] if e.message else ""

        label_text = f"{time_str} [{e.action_emoji}] {e.short_hash} {e.action}: {msg}{orphan}"

        label = Label(label_text)
        if e.is_orphaned:
            label.styles.color = "red"
            label.styles.text_style = "bold"
        else:
            label.styles.color = color
        yield label


class DiffPanel(Static):
    """Panel showing diff/details for the selected entry."""

    content: reactive[str] = reactive("")

    def watch_content(self, value: str) -> None:
        self.update(value)


class StatusBar(Static):
    """Bottom status bar showing available actions."""

    message: reactive[str] = reactive("Select an entry to view details")

    def watch_message(self, value: str) -> None:
        self.update(value)


class ReflogApp(App):
    """Main TUI application for git reflog rescue."""

    CSS = """
    Screen {
        layout: horizontal;
    }

    #timeline-panel {
        width: 45%;
        border: round $accent;
        height: 100%;
    }

    #detail-panel {
        width: 55%;
        border: round $primary;
        height: 100%;
        overflow-y: scroll;
    }

    #timeline-title {
        dock: top;
        text-align: center;
        text-style: bold;
        color: $accent;
        padding: 0 1;
    }

    #detail-title {
        dock: top;
        text-align: center;
        text-style: bold;
        color: $primary;
        padding: 0 1;
    }

    #timeline-list {
        height: 1fr;
    }

    #diff-content {
        height: 1fr;
        padding: 0 1;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }

    .day-header {
        text-style: bold;
        color: $accent;
        padding: 0 1;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("b", "create_branch", "Create Branch", show=True),
        Binding("c", "cherry_pick", "Cherry-Pick", show=True),
        Binding("r", "reset_soft", "Reset (soft)", show=True),
        Binding("d", "show_details", "Full Details", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("?", "help", "Help", show=True),
    ]

    def __init__(self, repo_path: str = ".", **kwargs) -> None:
        super().__init__(**kwargs)
        self.repo_path = repo_path
        self.entries: list[ReflogEntry] = []
        self.selected_entry: ReflogEntry | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="timeline-panel"):
                yield Label("Timeline", id="timeline-title")
                yield ListView(id="timeline-list")
            with Vertical(id="detail-panel"):
                yield Label("Details", id="detail-title")
                yield DiffPanel(id="diff-content")
        yield StatusBar(id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Load reflog data on mount."""
        self.title = "git-reflog-rescuer"
        self.sub_title = self.repo_path

        try:
            self.entries = parse_reflog(self.repo_path)
        except RuntimeError as e:
            self.query_one("#diff-content", DiffPanel).content = f"Error: {e}"
            return

        if not self.entries:
            self.query_one("#diff-content", DiffPanel).content = "No reflog entries found."
            return

        # Populate timeline
        timeline = self.query_one("#timeline-list", ListView)
        current_day = ""
        for entry in self.entries:
            day = entry.day_str
            if day != current_day:
                current_day = day
                # Add day separator as a ListItem with special styling
                item = ListItem(Label(f"--- {day} ---"))
                item.disabled = True
                timeline.append(item)
            timeline.append(TimelineItem(entry))

        orphaned = sum(1 for e in self.entries if e.is_orphaned)
        status = self.query_one("#status-bar", StatusBar)
        status.message = (
            f"{len(self.entries)} entries | "
            f"{orphaned} orphaned | "
            "b=branch  c=cherry-pick  r=reset  d=details  q=quit"
        )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle timeline item selection."""
        item = event.item
        if isinstance(item, TimelineItem):
            self.selected_entry = item.entry
            self._show_entry_diff(item.entry)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Show preview on highlight."""
        item = event.item
        if isinstance(item, TimelineItem):
            self.selected_entry = item.entry
            self._show_entry_preview(item.entry)

    def _show_entry_preview(self, entry: ReflogEntry) -> None:
        """Show a quick preview of the entry."""
        panel = self.query_one("#diff-content", DiffPanel)
        lines = [
            f"Commit:     {entry.hash}",
            f"Action:     {entry.action}",
            f"Message:    {entry.message}",
            f"Time:       {entry.time_str} ({entry.relative_time})",
            f"Selector:   {entry.selector}",
            f"Orphaned:   {'YES - recoverable!' if entry.is_orphaned else 'No'}",
        ]
        if entry.branch_from:
            lines.append(f"Checkout:   {entry.branch_from} -> {entry.branch_to}")
        lines.append("")
        lines.append("Press Enter for diff, 'b' to create branch, 'c' to cherry-pick")
        panel.content = "\n".join(lines)

    def _show_entry_diff(self, entry: ReflogEntry) -> None:
        """Show the diff for a reflog entry."""
        panel = self.query_one("#diff-content", DiffPanel)
        try:
            diff_info = get_diff(entry, self.repo_path)
            lines = [
                f"Commit:  {entry.hash}",
                f"Author:  {diff_info.author}",
                f"Message: {diff_info.commit_message}",
                f"Stats:   {diff_info.files_changed} files, "
                f"+{diff_info.insertions} -{diff_info.deletions}",
                "",
                "--- Stat ---",
                diff_info.stat or "(no changes)",
                "",
                "--- Diff ---",
                diff_info.diff[:5000] or "(no diff available)",
            ]
            if len(diff_info.diff) > 5000:
                lines.append(f"\n... truncated ({len(diff_info.diff)} chars total)")
            panel.content = "\n".join(lines)
        except Exception as e:
            panel.content = f"Error loading diff: {e}"

    def action_create_branch(self) -> None:
        """Create a branch from the selected entry."""
        if not self.selected_entry:
            return
        result = create_branch_from_commit(self.selected_entry, repo_path=self.repo_path)
        self._show_result(result.message)

    def action_cherry_pick(self) -> None:
        """Cherry-pick the selected entry."""
        if not self.selected_entry:
            return
        result = cherry_pick_commit(self.selected_entry, repo_path=self.repo_path)
        self._show_result(result.message)

    def action_reset_soft(self) -> None:
        """Soft reset to the selected entry."""
        if not self.selected_entry:
            return
        result = reset_to_entry(self.selected_entry, mode="soft", repo_path=self.repo_path)
        self._show_result(result.message)

    def action_show_details(self) -> None:
        """Show full commit details."""
        if not self.selected_entry:
            return
        panel = self.query_one("#diff-content", DiffPanel)
        details = get_commit_details(self.selected_entry.hash, self.repo_path)
        panel.content = details

    def action_help(self) -> None:
        """Show help."""
        panel = self.query_one("#diff-content", DiffPanel)
        panel.content = """
git-reflog-rescuer - Keyboard Shortcuts

Navigation:
  Up/Down     Navigate timeline
  Enter       Show diff for selected entry
  d           Show full commit details

Actions:
  b           Create branch at selected commit
  c           Cherry-pick selected commit onto current branch
  r           Soft reset current branch to selected commit

Note: All restore actions create a backup branch first
      (rescue-backup/YYYYMMDD-HHMMSS).

Legend:
  [+] commit      [~] amend      [M] merge
  [R] rebase      [!] reset      [>] checkout
  [v] pull        [P] cherry-pick [U] revert

  RED entries are orphaned (not reachable from any branch)
  These are the ones most likely to be "lost" work!

Press q to quit.
"""

    def _show_result(self, message: str) -> None:
        """Show operation result."""
        status = self.query_one("#status-bar", StatusBar)
        status.message = message
        panel = self.query_one("#diff-content", DiffPanel)
        panel.content = f"Operation result:\n\n{message}"
