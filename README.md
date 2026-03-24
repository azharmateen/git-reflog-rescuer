# git-reflog-rescuer

[![Built with Claude Code](https://img.shields.io/badge/Built%20with-Claude%20Code-blue?logo=anthropic&logoColor=white)](https://claude.ai/code)


Beautiful TUI that turns the scary `git reflog` into a visual timeline for recovering lost commits.

## Features

- **Visual Timeline** -- Reflog entries grouped by day, color-coded by action type (commit, rebase, reset, checkout, merge)
- **Orphan Detection** -- Highlights commits not reachable from any branch (the ones you actually lost)
- **Diff Preview** -- See what each reflog entry changed: files, insertions, deletions
- **Safe Restore Operations** -- Always creates a backup branch before any restore action
  - Create branch at orphaned commit
  - Cherry-pick lost commit onto current branch
  - Soft reset to any reflog point
- **TUI and CLI modes** -- Full Textual TUI with keyboard navigation, or plain terminal list output

## Installation

```bash
pip install git-reflog-rescuer
```

Or from source:

```bash
git clone https://github.com/yourusername/git-reflog-rescuer.git
cd git-reflog-rescuer
pip install -e .
```

## Usage

### TUI Mode (default)

```bash
# Launch the interactive TUI in the current repo
git-reflog-rescuer

# Launch for a specific repo
git-reflog-rescuer --repo /path/to/repo
```

**Keyboard shortcuts:**
| Key | Action |
|-----|--------|
| Up/Down | Navigate timeline |
| Enter | Show diff for selected entry |
| b | Create branch at selected commit |
| c | Cherry-pick selected commit |
| r | Soft reset to selected commit |
| d | Show full commit details |
| ? | Help |
| q | Quit |

### CLI Mode

```bash
# List reflog entries (non-TUI)
git-reflog-rescuer list

# Show only orphaned (lost) commits
git-reflog-rescuer list --orphaned-only

# Quick rescue: create branch from a commit hash
git-reflog-rescuer rescue abc1234

# Rescue with custom branch name
git-reflog-rescuer rescue abc1234 --name my-recovered-work

# List rescue backup branches
git-reflog-rescuer branches

# Clean up a rescue branch
git-reflog-rescuer cleanup rescue-backup/20260324-153000
```

## Timeline Legend

| Symbol | Action | Color |
|--------|--------|-------|
| + | Commit | Green |
| ~ | Amend | Yellow |
| M | Merge | Cyan |
| R | Rebase | Magenta |
| ! | Reset | Red |
| > | Checkout | Blue |
| v | Pull | Blue |
| P | Cherry-pick | Yellow |
| U | Revert | Yellow |

**RED entries** are orphaned commits -- not reachable from any branch. These are the most likely candidates for "lost" work.

## Safety

Every restore operation (cherry-pick, reset) creates a backup branch first at `rescue-backup/YYYYMMDD-HHMMSS`. You can always get back to where you were.

## License

MIT
