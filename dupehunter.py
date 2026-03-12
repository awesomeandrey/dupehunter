import argparse
import hashlib
import logging
import os
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import bext
import send2trash

logging.basicConfig(
    filename=Path.home() / '.dupehunter.log',
    filemode='w',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)


def _fmt_elapsed(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f'{s}s'
    if s < 3600:
        return f'{s // 60}m {s % 60:02d}s'
    return f'{s // 3600}h {(s % 3600) // 60:02d}m'


def hash_file(path: Path) -> str | None:
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            chunk = f.read(65536)
            while chunk:
                h.update(chunk)
                chunk = f.read(65536)
        return h.hexdigest()
    except (OSError, PermissionError) as e:
        logging.warning('Cannot read %s: %s', path, e)
        return None


def collect_files(root: Path, exts: set[str]) -> tuple[list[Path], int]:
    candidates = []
    folders = 0
    for dirpath, _, filenames in os.walk(root):
        folders += 1
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix.lstrip('.').lower() not in exts:
                continue
            try:
                if path.stat().st_size == 0:
                    continue
            except (OSError, PermissionError):
                continue
            candidates.append(path)
    return candidates, folders


def find_duplicates(
    files: list[Path | str],
    stats: dict | None = None,
    draw_fn=None,
) -> dict[str, list[Path]]:
    size_map = defaultdict(list)
    files = [Path(f) for f in files]
    for path in files:
        try:
            size_map[path.stat().st_size].append(path)
        except (OSError, PermissionError):
            continue

    to_hash = [p for paths in size_map.values() if len(paths) > 1 for p in paths]
    skipped = set(files) - set(to_hash)

    hash_map = defaultdict(list)

    for path in to_hash:
        digest = hash_file(path)
        if digest is not None:
            hash_map[digest].append(path)
        if stats is not None:
            stats['scanned'] += 1
            stats['current_file'] = path.name
            live_groups = {d: p for d, p in hash_map.items() if len(p) > 1}
            stats['dupe_groups'] = len(live_groups)
            stats['dupe_files'] = sum(len(p) for p in live_groups.values())
            stats['recoverable_bytes'] = sum(
                p.stat().st_size
                for paths in live_groups.values()
                for p in sorted(paths)[1:]
                if p.exists()
            )
            if draw_fn:
                draw_fn(stats)

    if stats is not None:
        for path in skipped:
            stats['scanned'] += 1
            stats['current_file'] = path.name
            if draw_fn:
                draw_fn(stats)

    return {d: p for d, p in hash_map.items() if len(p) > 1}


def draw_dashboard(stats: dict) -> None:
    WIDTH = 46
    INNER = WIDTH - 2

    bext.goto(0, 0)

    def write(text: str, color: str = 'cyan') -> None:
        bext.fg(color)
        sys.stdout.write(text)

    def row(label: str, value: str, value_color: str = 'green') -> None:
        padding = INNER - 2 - len(label) - len(value)
        write('║ ')
        write(label)
        write(' ' * max(0, padding))
        write(value, value_color)
        write(' ║\n')

    def divider(left: str = '╠', right: str = '╣') -> None:
        write(left + '═' * INNER + right + '\n')

    title = 'DUPEHUNTER v1.0'
    pad_l = (INNER - len(title)) // 2
    pad_r = INNER - len(title) - pad_l

    write('╔' + '═' * INNER + '╗\n')
    write('║' + ' ' * pad_l)
    write(title, 'yellow')
    write(' ' * pad_r + '║\n')
    divider()

    path_val = stats.get('path', '')
    max_path = INNER - 2 - len('Path:    ')
    if len(path_val) > max_path:
        path_val = '...' + path_val[-(max_path - 3):]
    row('Path:    ', path_val, 'white')
    row('Types:   ', '  '.join(stats.get('types', [])), 'white')
    row('Mode:    ', stats.get('mode', 'SCAN ONLY'), 'magenta')
    divider()

    elapsed = _fmt_elapsed(time.monotonic() - stats.get('start_time', time.monotonic()))
    row('Elapsed:', elapsed)
    row('Folders visited:', f"{stats.get('folders', 0):,}")
    row('Files scanned:', f"{stats.get('scanned', 0):,}")

    current = stats.get('current_file', '')
    max_cur = INNER - 2 - len('Currently scanning:  ')
    if len(current) > max_cur:
        current = current[:max_cur - 3] + '...'
    write('║ ')
    write('Currently scanning:  ')
    write(current + ' ' * max(0, max_cur - len(current)), 'yellow')
    write(' ║\n')
    divider()

    row('Duplicate groups:', f"{stats.get('dupe_groups', 0):,}", 'red')
    row('Duplicate files:', f"{stats.get('dupe_files', 0):,}", 'red')

    rb = stats.get('recoverable_bytes', 0)
    if rb >= 1_000_000:
        rb_str = f'{rb / 1_000_000:.1f} MB'
    elif rb >= 1_000:
        rb_str = f'{rb / 1_000:.1f} KB'
    else:
        rb_str = f'{rb} B'
    row('Space recoverable:', rb_str, 'red')
    divider()

    row(stats.get('action_label', 'Scanned (no action):'), f"{stats.get('actioned', 0):,}")
    write('╚' + '═' * INNER + '╝\n')

    bext.fg('reset')
    sys.stdout.flush()


def _delete_duplicates(dupe_groups: dict, stats: dict, draw_fn=None) -> None:
    for digest, paths in dupe_groups.items():
        keeper, *dupes = sorted(paths)
        logging.info('Duplicate group %s: keeper=%s duplicates=%s', digest[:8], keeper, dupes)
        for dupe in dupes:
            try:
                send2trash.send2trash(str(dupe))
                logging.info('Trashed: %s', dupe)
                stats['actioned'] += 1
            except Exception as e:
                logging.error('Failed to trash %s: %s', dupe, e)
            if draw_fn:
                draw_fn(stats)


def _archive_duplicates(dupe_groups: dict, archive_root: Path, stats: dict, draw_fn=None) -> None:
    for group_num, (digest, paths) in enumerate(dupe_groups.items(), start=1):
        keeper, *dupes = sorted(paths)
        logging.info('Duplicate group %s: keeper=%s duplicates=%s', digest[:8], keeper, dupes)

        subfolder = archive_root / f'{group_num:03d}'
        subfolder.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(str(keeper), subfolder / f'keeper_{keeper.name}')
            logging.info('Copied keeper: %s -> %s', keeper, subfolder / f'keeper_{keeper.name}')
        except Exception as e:
            logging.error('Failed to copy keeper %s: %s', keeper, e)

        for dupe in dupes:
            try:
                shutil.move(str(dupe), subfolder / dupe.name)
                logging.info('Archived: %s -> %s', dupe, subfolder / dupe.name)
                stats['actioned'] += 1
            except Exception as e:
                logging.error('Failed to archive %s: %s', dupe, e)
            if draw_fn:
                draw_fn(stats)


def act_on_duplicates(
    dupe_groups: dict,
    args: argparse.Namespace,
    stats: dict,
    draw_fn=None,
    archive_root: Path | None = None,
) -> None:
    if args.delete:
        _delete_duplicates(dupe_groups, stats, draw_fn)
    elif args.archive and archive_root is not None:
        _archive_duplicates(dupe_groups, archive_root, stats, draw_fn)


def main():
    parser = argparse.ArgumentParser(prog='dupehunter')
    parser.add_argument('--path', '-p', required=True, help='Root folder to scan')
    parser.add_argument('--file-type', '-f', action='append', dest='file_types',
                        required=True, metavar='EXT', help='File extension (repeatable)')
    parser.add_argument('--delete', action='store_true', default=False,
                        help='Send duplicates to trash')
    parser.add_argument('--archive', nargs='?', const='AUTO', default=None, metavar='DEST',
                        help='Move duplicates into an archive folder; omit value to auto-create inside --path')
    args = parser.parse_args()

    if args.delete and args.archive:
        parser.error('--delete and --archive are mutually exclusive')

    root = Path(args.path)
    if not root.is_dir():
        print(f"Error: '{args.path}' is not a directory or does not exist.", file=sys.stderr)
        sys.exit(1)

    allowed_exts = {ext.lstrip('.').lower() for ext in args.file_types}

    archive_root: Path | None = None
    if args.archive:
        if args.archive == 'AUTO':
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            archive_root = root / f'dupehunter-archive-{timestamp}'
        else:
            archive_root = Path(args.archive)
        try:
            archive_root.mkdir(parents=True, exist_ok=True)
            probe = archive_root / '.dupehunter_write_test'
            probe.touch()
            probe.unlink()
        except Exception as e:
            print(f"Error: archive destination '{archive_root}' is not writable: {e}", file=sys.stderr)
            sys.exit(1)

    if args.delete:
        mode_str, action_label = 'DELETE → Trash', 'Deleted:'
    elif args.archive:
        mode_str, action_label = f'ARCHIVE → {archive_root}', 'Archived:'
    else:
        mode_str, action_label = 'SCAN ONLY', 'Scanned (no action):'

    logging.info('Starting dupehunter: path=%s exts=%s delete=%s archive=%s',
                 root, sorted(allowed_exts), args.delete, args.archive)

    stats = {
        'path': str(root),
        'types': sorted(allowed_exts),
        'mode': mode_str,
        'action_label': action_label,
        'start_time': time.monotonic(),
        'folders': 0,
        'scanned': 0,
        'current_file': '',
        'dupe_groups': 0,
        'dupe_files': 0,
        'recoverable_bytes': 0,
        'actioned': 0,
    }

    bext.clear()
    bext.hide_cursor()
    try:
        draw_dashboard(stats)

        candidates, folders_visited = collect_files(root, allowed_exts)
        stats['folders'] = folders_visited
        draw_dashboard(stats)

        dupe_groups = find_duplicates(candidates, stats=stats, draw_fn=draw_dashboard)

        stats['dupe_groups'] = len(dupe_groups)
        stats['dupe_files'] = sum(len(p) for p in dupe_groups.values())
        stats['recoverable_bytes'] = sum(
            p.stat().st_size
            for paths in dupe_groups.values()
            for p in sorted(paths)[1:]
            if p.exists()
        )
        stats['current_file'] = 'Done scanning'
        draw_dashboard(stats)

        for digest, paths in dupe_groups.items():
            logging.info('Found duplicate group %s: %s', digest[:8], paths)

        act_on_duplicates(dupe_groups, args, stats, draw_fn=draw_dashboard, archive_root=archive_root)

        stats['current_file'] = ''
        draw_dashboard(stats)

        logging.info('Done. folders=%d scanned=%d dupe_groups=%d dupe_files=%d actioned=%d',
                     stats['folders'], stats['scanned'], stats['dupe_groups'],
                     stats['dupe_files'], stats['actioned'])

        bext.goto(0, 20)
        bext.fg('reset')
    except KeyboardInterrupt:
        stats['current_file'] = 'Interrupted'
        stats['mode'] = stats['mode'] + '  [INTERRUPTED]'
        draw_dashboard(stats)
        logging.warning('Interrupted by user. folders=%d scanned=%d actioned=%d',
                        stats['folders'], stats['scanned'], stats['actioned'])
        bext.goto(0, 20)
        bext.fg('reset')
    finally:
        bext.show_cursor()


if __name__ == '__main__':
    main()
