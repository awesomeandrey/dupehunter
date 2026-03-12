# dupehunter

A portable Python CLI that finds and optionally removes or archives duplicate files in a directory tree using SHA-256 hashing.

## Setup

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate

# Install the package and its dependencies
python -m pip install -e .
```

## Usage

```bash
# Scan only (no action taken)
dupehunter -p ./photos -f jpg -f png
dupehunter -p "$(pwd)" -f jpg -f jpeg -f heic -f png -f mp4 -f mov

# Delete duplicates (sent to OS trash)
dupehunter -p ./documents -f pdf --delete

# Archive duplicates to a specific folder
dupehunter -p /media/drive -f jpg -f cr2 --archive /tmp/dupes

# Archive duplicates to an auto-generated folder inside --path
dupehunter -p ~/Photos -f jpg -f heic --archive
```

### Arguments

| Flag | Short | Required | Description |
|---|---|---|---|
| `--path` | `-p` | Yes | Root folder to scan recursively |
| `--file-type` | `-f` | Yes | File extension filter, repeatable |
| `--delete` | — | No | Send duplicates to OS trash |
| `--archive [DEST]` | — | No | Archive duplicates; omit `DEST` to auto-create folder inside `--path` |

`--delete` and `--archive` are mutually exclusive.

### Archive folder structure

When `--archive` is used, each duplicate group gets its own numbered subfolder. The keeper file is copied in with a `keeper_` prefix; all duplicate files are moved in as-is.

```
dupehunter-archive-20260313-143022/
├── 001/
│   ├── keeper_photo.jpg   ← copy of the kept file (original untouched)
│   └── photo_copy.jpg     ← duplicate moved here
├── 002/
│   ├── keeper_video.mp4
│   └── video_backup.mp4
```

Auto-generated archive folder names follow the pattern `dupehunter-archive-YYYYMMDD-HHMMSS` and are created inside the scanned `--path`.

## Running Tests

```bash
pytest test_dupehunter.py -v

# Single test
pytest test_dupehunter.py::test_archive_keeper_copied_with_prefix_and_original_untouched -v
```

## Logs

Each run overwrites `~/.dupehunter.log` with a full execution log.
