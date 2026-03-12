# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

**dupehunter** is a portable Python CLI that finds and optionally removes or archives duplicate files in a directory tree using SHA-256 hashing. It targets security-aware users who need predictable, auditable behavior on large file sets (1,000+ files).

This is a **self-education project**. All Python code must be written as if by a strong mid-level Python developer: use idiomatic constructs (list/dict comprehensions, `pathlib`, type hints, context managers, stdlib modules) but avoid advanced patterns like metaclasses, descriptors, decorators beyond `@property`, or abstract base classes. Code should be clear and readable first — cleverness for its own sake is discouraged.

## Commands

```bash
# Install dependencies (run once, or after pyproject.toml changes)
python -m pip install -e .

# Run all tests
python -m pytest test_dupehunter.py -v

# Run a single test
python -m pytest test_dupehunter.py::test_detects_duplicate_group -v

# Run the tool
python dupehunter.py --path /some/folder -f jpg -f png          # scan only
python dupehunter.py --path /some/folder -f pdf --delete        # send dupes to OS trash
python dupehunter.py --path /some/folder -f mp4 --archive /tmp/dupes  # move dupes to folder
```

## Architecture

Everything lives in a single file: `dupehunter.py`. No helper modules.

### Data flow

```
main()
 ├─ collect_files(root, exts)        → flat list of matching, non-empty file paths
 ├─ find_duplicates(files, ...)      → {sha256_digest: [path, path, ...]}
 │    ├─ size pre-filter             (skip files with a unique size — no hashing needed)
 │    └─ hash_file(path)             → hex digest or None on read error
 └─ act_on_duplicates(groups, args)  → trash or move all but sorted(paths)[0]
```

### Key design decisions

- **Size pre-filter before hashing** — the primary perf optimization; files with a unique size are guaranteed unique and never hashed.
- **Keeper selection** — within each duplicate group, `sorted(paths)[0]` (lexicographic) is always kept; the rest are acted on. This is deterministic and auditable.
- **Archive name collision** — if a destination filename already exists, the hash prefix (`digest[:8]`) is appended to the stem before moving.
- **`draw_dashboard(stats)`** redraws the full `bext` terminal UI in-place via `bext.goto(0,0)` after every file processed. `stats` is a plain dict passed by reference throughout.
- **Logging** overwrites `~/.dupehunter.log` on every run (`filemode='w'`). Logs at group/action granularity — not per-file during scan.

### Dependencies

| Package | Role |
|---|---|
| `bext` | Terminal cursor positioning and color (use `bext.hide_cursor()`, not `bext.hide()`) |
| `send2trash` | OS-native trash (cross-platform) |

Both must be installed in whichever Python interpreter is active. With pyenv, multiple interpreters may exist — install into the one that will run the tool/tests.

### Error handling contract

- Unreadable file during hash → log WARNING, `hash_file` returns `None`, file skipped
- `send2trash` or `shutil.move` failure → log ERROR, skip file, continue
- Bad `--path` → `sys.exit(1)` before any scanning
- `--delete` + `--archive` together → `parser.error()` (argparse exits cleanly)
- Archive destination unwritable → `sys.exit(1)` before any scanning

### Tests

`test_dupehunter.py` covers `hash_file` and `find_duplicates` only — no CLI, no dashboard, no deletion. Uses only `pytest` and stdlib `tempfile`.
