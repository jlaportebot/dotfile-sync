# dotfile-sync 📁

Keep your dotfiles in sync across machines. A Python CLI for backing up, versioning, and restoring your config files with Git-backed storage.

## Why?

Every developer has been there — you get a new machine and spend hours reconfiguring your shell, editor, git, and tools. `dotfile-sync` makes it trivial to:

- **Track** specific dotfiles by registering them in a manifest
- **Backup** all tracked dotfiles into a Git repository
- **Restore** your dotfiles on any machine with a single command
- **Diff** your current dotfiles against the last backed-up version
- **List** all tracked files and their status

Unlike complex dotfile managers, `dotfile-sync` is simple, transparent, and stores your files as plain files in a Git repo — no symlinks, no magic, just Git.

## Installation

```bash
pip install dotfile-sync
```

Or with [pipx](https://pypa.github.io/pipx/):

```bash
pipx install dotfile-sync
```

## Quick Start

```bash
# Initialize a new dotfile repository
dotfile-sync init

# Track your bash config
dotfile-sync track ~/.bashrc

# Track your git config
dotfile-sync track ~/.gitconfig

# Track a directory of Neovim config
dotfile-sync track ~/.config/nvim/

# Back up all tracked files
dotfile-sync backup -m "Added neovim config"

# Check what's changed since last backup
dotfile-sync diff

# List all tracked files
dotfile-sync list

# Restore everything on a new machine
dotfile-sync restore

# Restore a single file
dotfile-sync restore --only ~/.bashrc
```

## Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize a new dotfile repository in `~/.dotfile-sync` |
| `track <path>` | Add a file or directory to the tracking manifest |
| `untrack <path>` | Remove a file or directory from the manifest |
| `list` | Show all tracked files and their sync status |
| `backup [-m MSG]` | Copy tracked files into the repo and commit |
| `restore [--only PATH]` | Copy files from the repo back to their original locations |
| `diff` | Show differences between live files and the last backup |
| `status` | Show which tracked files have been modified since last backup |
| `push` | Push the backup repo to its remote |
| `pull` | Pull changes from the remote and restore |

## How It Works

1. `dotfile-sync init` creates `~/.dotfile-sync/` with:
   - A bare Git repository for versioned storage
   - A `manifest.json` tracking which files to sync and their original paths
2. `dotfile-sync track <path>` adds the absolute path to the manifest
3. `dotfile-sync backup` copies all tracked files into the repo (preserving directory structure) and commits
4. `dotfile-sync restore` copies files from the repo back to their original locations
5. `dotfile-sync push/pull` syncs with a remote Git repository

The manifest maps original paths to repo paths, so you always know where files came from and where they should go.

## Configuration

The manifest (`~/.dotfile-sync/manifest.json`) stores:

```json
{
  "version": "1.0",
  "files": [
    {
      "original_path": "/home/user/.bashrc",
      "repo_path": "home/user/_bashrc",
      "added_at": "2026-05-17T00:00:00Z"
    }
  ]
}
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License — see [LICENSE](LICENSE) for details.
