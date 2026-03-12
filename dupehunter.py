import argparse
import hashlib
import logging
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import bext
import send2trash

logging.basicConfig(
    filename=Path.home() / '.dupehunter.log',
    filemode='w',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)


def hash_file(path):
    # Opens a file and computes its SHA-256 hash by reading it in 64KB chunks.
    # Reading in chunks avoids loading the whole file into memory (important for large files).
    # Returns the hex digest string on success, or None if the file can't be read.
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            chunk = f.read(65536)
            while chunk:
                h.update(chunk)
                chunk = f.read(65536)
        return h.hexdigest()
    except (OSError, PermissionError) as e:
        logging.warning("Cannot read %s: %s", path, e)
        return None


def collect_files(root, exts):
    candidates = []
    folders_visited = 0
    for dirpath, dirnames, filenames in os.walk(root):
        folders_visited += 1
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            suffix = Path(filepath).suffix.lstrip('.').lower()
            if suffix not in exts:
                continue
            try:
                if os.path.getsize(filepath) == 0:
                    continue
            except OSError:
                continue
            candidates.append(filepath)
    return candidates, folders_visited


def find_duplicates(files, stats=None, draw_fn=None):
    # Group files by their size in bytes.
    # Files with a unique size can't possibly have a duplicate, so we skip them.
    size_map = defaultdict(list)
    for path in files:
        try:
            file_size = os.path.getsize(path)
        except OSError:
            continue
        size_map[file_size].append(path)

    # Build the list of files that actually need hashing:
    # only those whose size appears more than once.
    to_hash = []
    for paths in size_map.values():
        if len(paths) > 1:
            to_hash.extend(paths)

    hash_map = defaultdict(list)
    for path in to_hash:
        digest = hash_file(path)
        if digest is not None:
            hash_map[digest].append(path)
        if stats is not None:
            stats['scanned'] += 1
            stats['current_file'] = Path(path).name
            # Update dupe counts so far
            dupe_groups_so_far = {d: p for d, p in hash_map.items() if len(p) > 1}
            stats['dupe_groups'] = len(dupe_groups_so_far)
            stats['dupe_files'] = sum(len(p) for p in dupe_groups_so_far.values())
            stats['recoverable_bytes'] = sum(
                os.path.getsize(p)
                for paths in dupe_groups_so_far.values()
                for p in sorted(paths)[1:]
                if os.path.exists(p)
            )
            if draw_fn:
                draw_fn(stats)

    # Files not needing hashing still count as scanned
    if stats is not None:
        already_counted = set(to_hash)
        for path in files:
            if path not in already_counted:
                stats['scanned'] += 1
                stats['current_file'] = Path(path).name
                if draw_fn:
                    draw_fn(stats)

    dupe_groups = {d: p for d, p in hash_map.items() if len(p) > 1}
    return dupe_groups


def draw_dashboard(stats):
    width = 46
    bext.hide()
    bext.goto(0, 0)

    def border(char='═'):
        return char * (width - 2)

    def row(label, value=None, label_color='cyan', value_color='green', width=width):
        bext.fg('cyan')
        sys.stdout.write('║ ')
        bext.fg(label_color)
        if value is None:
            text = label
            sys.stdout.write(text.ljust(width - 4))
        else:
            sys.stdout.write(label)
            padding = width - 4 - len(label) - len(str(value))
            sys.stdout.write(' ' * max(0, padding))
            bext.fg(value_color)
            sys.stdout.write(str(value))
        bext.fg('cyan')
        sys.stdout.write(' ║\n')

    def divider(left='╠', right='╣', fill='═'):
        bext.fg('cyan')
        sys.stdout.write(left + fill * (width - 2) + right + '\n')

    bext.fg('cyan')
    sys.stdout.write('╔' + border() + '╗\n')

    # Title
    title = 'DUPEHUNTER v1.0'
    pad_left = (width - 2 - len(title)) // 2
    pad_right = width - 2 - len(title) - pad_left
    bext.fg('cyan')
    sys.stdout.write('║' + ' ' * pad_left)
    bext.fg('yellow')
    sys.stdout.write(title)
    bext.fg('cyan')
    sys.stdout.write(' ' * pad_right + '║\n')

    divider()

    # Config section
    path_val = stats.get('path', '')
    if len(path_val) > width - 4 - len('Path:    '):
        path_val = '...' + path_val[-(width - 4 - len('Path:    ') - 3):]
    row('Path:    ', path_val, value_color='white')

    types_val = '  '.join(stats.get('types', []))
    row('Types:   ', types_val, value_color='white')

    mode = stats.get('mode', 'SCAN ONLY')
    row('Mode:    ', mode, value_color='magenta')

    divider()

    # Progress section
    row('Folders visited:', f"{stats.get('folders', 0):,}")
    row('Files scanned:', f"{stats.get('scanned', 0):,}")
    current = stats.get('current_file', '')
    if len(current) > width - 4 - len('Currently scanning:  '):
        current = current[:width - 4 - len('Currently scanning:  ') - 3] + '...'
    bext.fg('cyan')
    sys.stdout.write('║ ')
    bext.fg('cyan')
    sys.stdout.write('Currently scanning:  ')
    bext.fg('yellow')
    padding = width - 4 - len('Currently scanning:  ') - len(current)
    sys.stdout.write(current + ' ' * max(0, padding))
    bext.fg('cyan')
    sys.stdout.write(' ║\n')

    divider()

    # Duplicate stats
    row('Duplicate groups:', f"{stats.get('dupe_groups', 0):,}", value_color='red')
    row('Duplicate files:', f"{stats.get('dupe_files', 0):,}", value_color='red')
    rb = stats.get('recoverable_bytes', 0)
    if rb >= 1_000_000:
        rb_str = f"{rb / 1_000_000:.1f} MB"
    elif rb >= 1_000:
        rb_str = f"{rb / 1_000:.1f} KB"
    else:
        rb_str = f"{rb} B"
    row('Space recoverable:', rb_str, value_color='red')

    divider()

    # Action section
    action_label = stats.get('action_label', 'Scanned (no action):')
    row(action_label, f"{stats.get('actioned', 0):,}")

    bext.fg('cyan')
    sys.stdout.write('╚' + border() + '╝\n')

    bext.fg('reset')
    sys.stdout.flush()


def act_on_duplicates(dupe_groups, args, stats, draw_fn=None):
    for digest, paths in dupe_groups.items():
        keeper = sorted(paths)[0]
        logging.info("Duplicate group %s: keeper=%s duplicates=%s", digest[:8], keeper, sorted(paths)[1:])
        for dupe in sorted(paths)[1:]:
            if args.delete:
                try:
                    send2trash.send2trash(dupe)
                    logging.info("Trashed: %s", dupe)
                    stats['actioned'] += 1
                except Exception as e:
                    logging.error("Failed to trash %s: %s", dupe, e)
            elif args.archive:
                dest = Path(args.archive) / Path(dupe).name
                if dest.exists():
                    dest = dest.with_stem(dest.stem + '_' + digest[:8])
                try:
                    shutil.move(dupe, dest)
                    logging.info("Archived: %s -> %s", dupe, dest)
                    stats['actioned'] += 1
                except Exception as e:
                    logging.error("Failed to archive %s: %s", dupe, e)
            if draw_fn:
                draw_fn(stats)


def main():
    parser = argparse.ArgumentParser(prog='dupehunter')
    parser.add_argument('--path', '-p', required=True, help='Root folder to scan')
    parser.add_argument('--file-type', '-f', action='append', dest='file_types',
                        required=True, metavar='EXT', help='File extension (repeatable)')
    parser.add_argument('--delete', action='store_true', default=False,
                        help='Send duplicates to trash')
    parser.add_argument('--archive', default=None, metavar='DEST',
                        help='Move duplicates to this folder')
    args = parser.parse_args()

    # Mutual exclusion
    if args.delete and args.archive:
        parser.error("--delete and --archive are mutually exclusive")

    # Validate path
    if not os.path.isdir(args.path):
        print(f"Error: '{args.path}' is not a directory or does not exist.", file=sys.stderr)
        logging.error("Invalid path: %s", args.path)
        sys.exit(1)

    # Normalize extensions
    allowed_exts = set()
    for ext in args.file_types:
        allowed_exts.add(ext.lstrip('.').lower())

    # Validate / create archive destination
    if args.archive:
        archive_path = Path(args.archive)
        try:
            archive_path.mkdir(parents=True, exist_ok=True)
            # Verify it's writable
            test_file = archive_path / '.dupehunter_write_test'
            test_file.touch()
            test_file.unlink()
        except Exception as e:
            print(f"Error: archive destination '{args.archive}' is not writable: {e}", file=sys.stderr)
            logging.error("Archive destination not writable: %s: %s", args.archive, e)
            sys.exit(1)

    # Determine mode label
    if args.delete:
        mode_str = 'DELETE → Trash'
        action_label = 'Deleted:'
    elif args.archive:
        mode_str = f'ARCHIVE → {args.archive}'
        action_label = 'Archived:'
    else:
        mode_str = 'SCAN ONLY'
        action_label = 'Scanned (no action):'

    logging.info("Starting dupehunter: path=%s exts=%s delete=%s archive=%s",
                 args.path, sorted(allowed_exts), args.delete, args.archive)

    stats = {
        'path': args.path,
        'types': sorted(allowed_exts),
        'mode': mode_str,
        'folders': 0,
        'scanned': 0,
        'current_file': '',
        'dupe_groups': 0,
        'dupe_files': 0,
        'recoverable_bytes': 0,
        'actioned': 0,
        'action_label': action_label,
    }

    # Clear screen once before we start
    bext.clear()
    draw_dashboard(stats)

    logging.info("Scanning: path=%s exts=%s", args.path, sorted(allowed_exts))
    candidates, folders_visited = collect_files(args.path, allowed_exts)
    stats['folders'] = folders_visited
    draw_dashboard(stats)

    dupe_groups = find_duplicates(candidates, stats=stats, draw_fn=draw_dashboard)

    # Final dupe stats
    stats['dupe_groups'] = len(dupe_groups)
    stats['dupe_files'] = sum(len(p) for p in dupe_groups.values())
    stats['recoverable_bytes'] = sum(
        os.path.getsize(p)
        for paths in dupe_groups.values()
        for p in sorted(paths)[1:]
        if os.path.exists(p)
    )
    stats['current_file'] = 'Done scanning'
    draw_dashboard(stats)

    for digest, paths in dupe_groups.items():
        logging.info("Found duplicate group %s: %s", digest[:8], paths)

    act_on_duplicates(dupe_groups, args, stats, draw_fn=draw_dashboard)

    stats['current_file'] = ''
    draw_dashboard(stats)

    logging.info("Done. folders=%d scanned=%d dupe_groups=%d dupe_files=%d actioned=%d",
                 stats['folders'], stats['scanned'], stats['dupe_groups'],
                 stats['dupe_files'], stats['actioned'])

    # Move cursor below dashboard
    bext.goto(0, 20)
    bext.fg('reset')


if __name__ == '__main__':
    main()
