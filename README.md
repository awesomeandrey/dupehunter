# dupehunter

A portable Python CLI that finds and optionally removes or archives duplicate files in a directory tree using SHA-256 hashing.

## Setup

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate

# Install the package and its dependencies
pip install -e .
```

## Usage

```bash
# Scan only (no action taken)
dupehunter -p ./photos -f jpg -f png

# Delete duplicates (sent to OS trash)
dupehunter -p ./documents -f pdf --delete

# Archive duplicates to a folder
dupehunter -p /media/drive -f jpg -f cr2 --archive /tmp/dupes

# Multiple extensions
dupehunter --path ~/Downloads --file-type mp4 --file-type mov --archive ~/dupes
```

### Arguments

| Flag | Short | Required | Description |
|---|---|---|---|
| `--path` | `-p` | Yes | Root folder to scan recursively |
| `--file-type` | `-f` | Yes | File extension filter, repeatable |
| `--delete` | — | No | Send duplicates to OS trash |
| `--archive` | — | No | Move duplicates into this destination folder |

`--delete` and `--archive` are mutually exclusive.

## Running Tests

```bash
pytest test_dupehunter.py -v
```

## Logs

Each run overwrites `~/.dupehunter.log` with a full execution log.
