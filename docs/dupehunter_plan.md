# dupehunter — Build Plan

## Overview

A portable Python CLI tool that finds and optionally removes or archives duplicate files in a
directory tree by comparing SHA-256 hashes. Targets security-aware users who need predictable,
auditable behavior on large file sets (1k+ files).

---

## Deliverables

- `dupehunter.py` — single-file script, fully self-contained
- `pyproject.toml` — packaging config with entry point for `pip install -e .`

---

## CLI Interface

```
dupehunter --path <dir> --file-type <ext> [-f <ext> ...] [--delete] [--archive <dest>]
```

### Arguments

| Flag | Short | Type | Required | Default | Description |
|---|---|---|---|---|---|
| `--path` | `-p` | str | Yes | — | Root folder to scan recursively |
| `--file-type` | `-f` | str (multi) | Yes | — | File extension filter, repeatable: `-f jpg -f png` |
| `--delete` | — | bool flag | No | False | Send duplicate files to OS trash via send2trash |
| `--archive` | — | str | No | None | Move duplicates into this destination folder |

### argparse Setup

```python
parser = argparse.ArgumentParser(prog='dupehunter')
parser.add_argument('--path', '-p', required=True, help='Root folder to scan')
parser.add_argument('--file-type', '-f', action='append', dest='file_types',
                    required=True, metavar='EXT', help='File extension (repeatable)')
parser.add_argument('--delete', action='store_true', default=False,
                    help='Send duplicates to trash')
parser.add_argument('--archive', default=None, metavar='DEST',
                    help='Move duplicates to this folder')
args = parser.parse_args()
```

### Input Normalization

Normalize extensions on parse — strip leading dots, lowercase — so `.JPG`, `JPG`, and `jpg` all resolve identically:

```python
# Normalize extensions: strip leading dots and lowercase each one.
# This makes -f JPG, -f .jpg, and -f jpg all behave the same way.
allowed_exts = set()
for ext in args.file_types:
    allowed_exts.add(ext.lstrip('.').lower())
```

### Validation Rules (fail fast, before any scanning)

- `--path` must exist and be a directory → `sys.exit(1)` with error message if not
- `--delete` and `--archive` are mutually exclusive → raise `parser.error()`
- If `--archive` is provided, create the destination folder if it does not exist

---

## Core Logic

### Step 1 — File Collection

Use `os.walk()` to traverse the tree. For each file:

1. Check `Path(f).suffix.lstrip('.').lower() in allowed_exts`
2. Skip zero-byte files (they all share the same hash trivially)
3. Append matching paths to a flat list

### Step 2 — Size Pre-filter

Before hashing, group files by `os.path.getsize()`. Any size bucket with only one member is
guaranteed unique — skip those. Only hash files that share a size with at least one other file.
This is the primary performance optimization for 1k+ file sets.

```python
from collections import defaultdict

# Group files by their size in bytes.
# Files with a unique size can't possibly have a duplicate, so we skip them.
size_map = defaultdict(list)
for path in candidates:
    file_size = os.path.getsize(path)
    size_map[file_size].append(path)

# Build the list of files that actually need hashing:
# only those whose size appears more than once.
to_hash = []
for paths in size_map.values():
    if len(paths) > 1:
        for p in paths:
            to_hash.append(p)
```

### Step 3 — SHA-256 Hashing

Read files in 64KB chunks to avoid loading large files entirely into memory.

```python
# hash_file(path)
# Opens a file and computes its SHA-256 hash by reading it in 64KB chunks.
# Reading in chunks avoids loading the whole file into memory (important for large files).
# Returns the hex digest string on success, or None if the file can't be read.
def hash_file(path):
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            # Read 64KB at a time until the file is exhausted
            chunk = f.read(65536)
            while chunk:
                h.update(chunk)
                chunk = f.read(65536)
        return h.hexdigest()
    except (OSError, PermissionError) as e:
        logging.warning("Cannot read %s: %s", path, e)
        return None
```

Return `None` on any read error — skip that file, log the warning, continue.

### Step 4 — Group Duplicates

```python
# Hash every candidate and group paths by their digest.
hash_map = defaultdict(list)
for path in to_hash:
    digest = hash_file(path)
    if digest is not None:
        hash_map[digest].append(path)

# Any hash that maps to more than one file is a duplicate group.
dupe_groups = {}
for digest, paths in hash_map.items():
    if len(paths) > 1:
        dupe_groups[digest] = paths
```

### Step 5 — Act on Duplicates

In each dupe group, keep the **first file** (sorted by path for determinism). Act on the rest.

```python
for digest, paths in dupe_groups.items():
    keeper = sorted(paths)[0]
    for dupe in sorted(paths)[1:]:
        if args.delete:
            send2trash.send2trash(dupe)
        elif args.archive:
            dest = Path(args.archive) / Path(dupe).name
            # Handle name collision in archive folder
            if dest.exists():
                dest = dest.with_stem(dest.stem + '_' + digest[:8])
            shutil.move(dupe, dest)
```

---

## Dashboard (bext)

Render a live, in-place dashboard using `bext` cursor positioning. Redraw on every file
processed — do not use `print()` for any dashboard output.

### Layout

```
╔══════════════════════════════════════════╗
║           DUPEHUNTER v1.0                ║
╠══════════════════════════════════════════╣
║  Path:    /home/user/photos              ║
║  Types:   jpg  png  pdf                  ║
║  Mode:    ARCHIVE → /home/user/dupes/    ║
╠══════════════════════════════════════════╣
║  Folders visited:              87        ║
║  Files scanned:             1,042        ║
║  Currently scanning:  DSC_0042.jpg       ║
╠══════════════════════════════════════════╣
║  Duplicate groups:             12        ║
║  Duplicate files:              29        ║
║  Space recoverable:        48.3 MB       ║
╠══════════════════════════════════════════╣
║  Archived:                     17        ║
╚══════════════════════════════════════════╝
```

### Color Scheme

| Element | bext color |
|---|---|
| Box borders + labels | Cyan |
| Numeric counts | Green |
| Current file (scanning) | Yellow |
| Dupe hits | Red |
| Mode line | Magenta |

### Implementation Pattern

```python
import bext

# draw_dashboard(stats)
# stats is a plain dict with keys: scanned, folders, current_file,
# dupe_groups, dupe_files, recoverable_bytes, archived.
# Redraws the entire dashboard in place — call this after each file processed.
def draw_dashboard(stats):
    bext.goto(0, 0)
    bext.clear()
    bext.fg('cyan')
    print('╔' + '═' * 44 + '╗')
    # ... render rows
    bext.fg('green')
    print("  Files scanned: " + str(stats['scanned']))
    bext.reset()
```

Call `draw_dashboard(stats)` after processing each file during the scan phase, and once more
after the action phase completes.

Use `bext.hide()` to hide the cursor during rendering to prevent flicker.

---

## Logging

Log file location: `~/.dupehunter.log`  
Overwritten on every run via `filemode='w'`.

```python
logging.basicConfig(
    filename=Path.home() / '.dupehunter.log',
    filemode='w',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
```

### What to Log

| Event | Level |
|---|---|
| Program start with resolved args | INFO |
| Scan start — path + extension list | INFO |
| Each dupe group found — hash prefix + all paths | INFO |
| File deleted (send2trash) | INFO |
| File archived (src → dest) | INFO |
| Unreadable file (permission/OS error) | WARNING |
| Bad path, missing dependency, mutual exclusion | ERROR |
| Program end — summary counts | INFO |

Do not log the currently-scanned filename on every file — that would produce 1k+ log lines
per run. Log at group/action granularity only.

---

## Performance Requirements

- Must handle 1,000+ files without perceptible slowdown
- Size pre-filter must be applied before any hashing
- Chunk-read all files (64KB blocks) — never load entire file into memory
- No threading required — I/O is sequential, GIL is not a bottleneck here

---

## Error Handling

| Scenario | Behavior |
|---|---|
| `--path` does not exist | Print error, `sys.exit(1)` before scan |
| `--delete` + `--archive` both set | `parser.error()` — argparse exits cleanly |
| File unreadable during hash | Log WARNING, skip file, continue |
| `send2trash` fails | Log ERROR, skip file, continue |
| `shutil.move` fails (archive) | Log ERROR, skip file, continue |
| Archive destination unwritable | Log ERROR, `sys.exit(1)` before scan |

Never crash silently. Every caught exception must be logged.

---

## Packaging (`pyproject.toml`)

```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "dupehunter"
version = "1.0.0"
requires-python = ">=3.10"
dependencies = [
    "send2trash",
    "bext",
]

[project.scripts]
dupehunter = "dupehunter:main"
```

Install and run as a real CLI command:

```bash
pip install -e .
dupehunter --path ./photos -f jpg -f png --archive ./dupes
```

---

## Module Inventory

| Module | Source | Role |
|---|---|---|
| `argparse` | stdlib | CLI interface |
| `os` | stdlib | Directory walking |
| `hashlib` | stdlib | SHA-256 hashing |
| `shutil` | stdlib | File move (archive) |
| `logging` | stdlib | Execution log |
| `pathlib.Path` | stdlib | Path manipulation |
| `collections.defaultdict` | stdlib | Hash/size grouping |
| `send2trash` | PyPI | Safe OS-trash deletion |
| `bext` | PyPI | Terminal color + cursor |

---

## Code Structure

```
dupehunter.py
├── imports
├── logging setup
├── def hash_file(path)            # returns digest string or None
├── def collect_files(root, exts)  # returns list of matching file paths
├── def find_duplicates(files)     # returns dict of {hash: [paths]}
├── def draw_dashboard(stats)      # redraws terminal dashboard in place
├── def act_on_duplicates(dupe_groups, args, stats)
└── def main()
    ├── parse args
    ├── validate args
    ├── setup logging
    ├── collect_files
    ├── find_duplicates  (with dashboard updates per file)
    ├── act_on_duplicates (with dashboard updates per action)
    └── final dashboard draw + log summary
```

Keep all logic in `dupehunter.py`. No helper modules. `main()` is the entry point registered
in `pyproject.toml`.

---

## Example Usage

```bash
# Dry run — scan only, no action
dupehunter -p ./photos -f jpg -f png

# Delete duplicates
dupehunter -p ./documents -f pdf --delete

# Archive duplicates to a folder
dupehunter -p /media/drive -f jpg -f cr2 -f raw --archive /tmp/dupes

# Multiple extensions, verbose
dupehunter --path ~/Downloads --file-type mp4 --file-type mov --file-type avi --archive ~/dupes
```

---

## Tests (`test_dupehunter.py`)

Tests cover core duplicate-detection logic only. No CLI, no dashboard, no file deletion.
Uses `pytest` and `tempfile` from stdlib — no other dependencies needed.

```python
import os
import tempfile

# Import the two functions under test directly from the script.
# These must be importable without side effects (no code running at module level
# outside of main() and the logging setup).
from dupehunter import hash_file, find_duplicates


def test_identical_content_produces_same_hash():
    # Two files with the same bytes must return the same digest.
    with tempfile.TemporaryDirectory() as tmp:
        file_a = os.path.join(tmp, 'a.jpg')
        file_b = os.path.join(tmp, 'b.jpg')

        with open(file_a, 'wb') as f:
            f.write(b'hello duplicate world')
        with open(file_b, 'wb') as f:
            f.write(b'hello duplicate world')

        assert hash_file(file_a) == hash_file(file_b)


def test_different_content_produces_different_hash():
    # Two files with different bytes must return different digests.
    with tempfile.TemporaryDirectory() as tmp:
        file_a = os.path.join(tmp, 'a.jpg')
        file_b = os.path.join(tmp, 'b.jpg')

        with open(file_a, 'wb') as f:
            f.write(b'content alpha')
        with open(file_b, 'wb') as f:
            f.write(b'content beta')

        assert hash_file(file_a) != hash_file(file_b)


def test_missing_file_returns_none():
    # A path that does not exist must return None, not raise an exception.
    result = hash_file('/tmp/this_file_does_not_exist_xyz.jpg')
    assert result is None


def test_detects_duplicate_group():
    # Three files: two identical, one unique.
    # find_duplicates must return exactly one group containing the two identical paths.
    with tempfile.TemporaryDirectory() as tmp:
        dupe_a = os.path.join(tmp, 'dupe_a.jpg')
        dupe_b = os.path.join(tmp, 'dupe_b.jpg')
        unique = os.path.join(tmp, 'unique.jpg')

        with open(dupe_a, 'wb') as f:
            f.write(b'same content')
        with open(dupe_b, 'wb') as f:
            f.write(b'same content')
        with open(unique, 'wb') as f:
            f.write(b'different content')

        groups = find_duplicates([dupe_a, dupe_b, unique])

        # Exactly one duplicate group should be found
        assert len(groups) == 1

        # That group must contain both duplicate paths
        found_paths = list(groups.values())[0]
        assert dupe_a in found_paths
        assert dupe_b in found_paths


def test_no_duplicates_returns_empty():
    # All unique files must produce an empty result — no groups.
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for i in range(4):
            path = os.path.join(tmp, 'file_%d.jpg' % i)
            with open(path, 'wb') as f:
                f.write(('unique content number %d' % i).encode())
            files.append(path)

        groups = find_duplicates(files)

        assert len(groups) == 0


def test_multiple_duplicate_groups():
    # Two separate pairs of duplicates must produce two separate groups.
    with tempfile.TemporaryDirectory() as tmp:
        group1_a = os.path.join(tmp, 'g1a.jpg')
        group1_b = os.path.join(tmp, 'g1b.jpg')
        group2_a = os.path.join(tmp, 'g2a.jpg')
        group2_b = os.path.join(tmp, 'g2b.jpg')

        with open(group1_a, 'wb') as f:
            f.write(b'group one content')
        with open(group1_b, 'wb') as f:
            f.write(b'group one content')
        with open(group2_a, 'wb') as f:
            f.write(b'group two content')
        with open(group2_b, 'wb') as f:
            f.write(b'group two content')

        groups = find_duplicates([group1_a, group1_b, group2_a, group2_b])

        assert len(groups) == 2
```

### Running the Tests

```bash
pytest test_dupehunter.py -v
```

### What These Tests Cover

| Test | What it verifies |
|---|---|
| `test_identical_content_produces_same_hash` | Core hashing correctness |
| `test_different_content_produces_different_hash` | No false positives from hash_file |
| `test_missing_file_returns_none` | Error handling in hash_file |
| `test_detects_duplicate_group` | Core dupe detection works end-to-end |
| `test_no_duplicates_returns_empty` | No false positives from find_duplicates |
| `test_multiple_duplicate_groups` | Grouping works across multiple independent groups |
