# dotfile-sync 📁

Keep your dotfiles in sync across machines. A Python CLI for backing up, versioning, and restoring your config files with Git-backed storage.

## Why?

Every developer has been there — you get a new machine and spend hours reconfiguring your shell, editor, git, and tools. `dotfile-sync` makes it trivial to:

- **Track** specific dotfiles by registering them in a manifest
- **Backup** all tracked dotfiles into a Git repository
- **Restore** your dotfiles on any machine with a single command
- **Diff** your current dotfiles against the last backed-up version
- **List** all tracked files and their status
- **Handle conflicts** — detect when both local and repo versions changed
- **Dry-run preview** — see what would happen before making changes
- **Lifecycle hooks** — run custom commands before/after backup/restore
- **Ignore patterns** — exclude files using `.gitignore`-style patterns
- **Template engine** — use Jinja2 templates for machine-specific configs

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

### Conflict Resolution

```bash
# Detect conflicts (both local and repo versions changed)
dotfile-sync diff --conflicts

# Resolve conflicts with strategy
dotfile-sync backup --conflict-strategy keep_local
dotfile-sync backup --conflict-strategy keep_repo
dotfile-sync backup --conflict-strategy keep_newer
dotfile-sync backup --conflict-strategy make_backup
dotfile-sync backup --conflict-strategy skip
dotfile-sync backup --conflict-strategy abort
```

### Dry-run Preview

```bash
# Preview what backup would do
dotfile-sync backup --dry-run

# Preview what restore would do
dotfile-sync restore --dry-run

# Preview with specific file
dotfile-sync restore --dry-run --only ~/.bashrc
```

### Lifecycle Hooks

```bash
# Add a pre-backup hook
dotfile-sync hook add pre_backup "echo 'Backing up...'"

# Add a post-restore hook
dotfile-sync hook add post_restore "source ~/.bashrc"

# List all hooks
dotfile-sync hook list

# Remove a hook
dotfile-sync hook remove pre_backup 0
```

### Ignore Patterns

```bash
# Add an ignore pattern (fnmatch-style)
dotfile-sync ignore "*.local"
dotfile-sync ignore "secrets/"

# List all ignore patterns
dotfile-sync ignore --list

# Remove an ignore pattern
dotfile-sync ignore "*.local" --remove
```

### Templates (Jinja2)

```bash
# Track a file as a template
dotfile-sync track ~/.bashrc --template

# Create machine-specific context
dotfile-sync context set machine-work '{"editor": "vim", "theme": "dark"}'

# Render template on restore
dotfile-sync restore --render
```

## How It Works

1. `dotfile-sync init` creates `~/.dotfile-sync/` with:
   - A bare Git repository for versioned storage
   - A `manifest.json` tracking which files to sync and their original paths
   - Optional `hooks.json` for lifecycle hooks
   - Optional `templates/` directory for template files
   - Optional `contexts/` directory for machine-specific variables
   - Optional `.dotfileignore` for ignore patterns

2. `dotfile-sync track <path>` adds the absolute path to the manifest

3. `dotfile-sync backup` copies all tracked files into the repo (preserving directory structure) and commits

4. `dotfile-sync restore` copies files from the repo back to their original locations

5. `dotfile-sync push/pull` syncs with a remote Git repository

The manifest maps original paths to repo paths, so you always know where files came from and where they should go.

## Manifest

The manifest (`~/.dotfile-sync/manifest.json`) stores:

```json
{
  "version": "1.0",
  "files": [
    {
      "original_path": "/home/user/.bashrc",
      "repo_path": "home/user/_bashrc",
      "added_at": "2026-05-17T00:00:00Z",
      "is_template": false
    }
  ]
}
```

## Templates & Contexts

For machine-specific configurations, use Jinja2 templates:

1. Track a file as a template:
   ```bash
   dotfile-sync track ~/.bashrc --template
   ```

2. This moves `~/.bashrc` to `~/.dotfile-sync/templates/home/user/_bashrc.tmpl` and stores a rendered copy in the repo

3. Create machine-specific contexts:
   ```bash
   dotfile-sync context set machine-work '{"editor": "vim", "theme": "dark", "host": "work-laptop"}'
   dotfile-sync context set profile-dev '{"python_venv": "~/.venv"}'
   ```

4. On restore, templates are rendered with merged context:
   ```bash
   dotfile-sync restore --render --machine work --profile dev
   ```

Context merge order: default → machine → profile → environment (DOTFILE_SYNC_*) → CLI extra

Available template variables:
- `machine` — current machine name
- `profile` — current profile
- `home` — home directory
- `user` — username
- `hostname` — hostname
- Any variables from context files or environment

## Hook Events

| Event | When it runs |
|-------|--------------|
| `pre_backup` | Before copying files to repo |
| `post_backup` | After commit |
| `pre_restore` | Before copying files from repo |
| `post_restore` | After files restored |
| `pre_track` | Before adding to manifest |
| `post_track` | After adding to manifest |
| `pre_push` | Before git push |
| `post_push` | After git push |

Hooks receive environment variables:
- `DOTFILE_SYNC_HOOK_EVENT` — the event name
- `DOTFILE_SYNC_FILE_PATH` — file being processed (for track/restore)
- `DOTFILE_SYNC_OPERATION` — operation name
- `DOTFILE_SYNC_REPO_DIR` — repo directory

## Ignore Patterns

Create `.dotfileignore` in `~/.dotfile-sync/` with patterns:

```
# Comments start with #
*.local
secrets/
!secrets/important.txt  # negation
/tmp/  # only at root
build/  # directories
```

Built-in patterns: `.git/`, `__pycache__/`, `*.pyc`, `.DS_Store`, `*.swp`, `*.swo`, `*~`, `.dotfile-sync/`

## Configuration

The repo is at `~/.dotfile-sync/`. Key files:

- `manifest.json` — tracked files
- `hooks.json` — lifecycle hooks
- `.dotfileignore` — ignore patterns
- `templates/` — Jinja2 template files (`.tmpl` extension)
- `contexts/*.yaml` — machine/profile contexts
- `files/` — backed-up file copies

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License — see [LICENSE](LICENSE) for details.