import argparse
import tempfile
from pathlib import Path

from dupehunter import act_on_duplicates, find_duplicates, hash_file


def test_identical_content_produces_same_hash():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        file_a = root / 'a.jpg'
        file_b = root / 'b.jpg'

        file_a.write_bytes(b'hello duplicate world')
        file_b.write_bytes(b'hello duplicate world')

        assert hash_file(file_a) == hash_file(file_b)


def test_different_content_produces_different_hash():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        file_a = root / 'a.jpg'
        file_b = root / 'b.jpg'

        file_a.write_bytes(b'content alpha')
        file_b.write_bytes(b'content beta')

        assert hash_file(file_a) != hash_file(file_b)


def test_missing_file_returns_none():
    assert hash_file(Path('/tmp/this_file_does_not_exist_xyz.jpg')) is None


def test_detects_duplicate_group():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dupe_a = root / 'dupe_a.jpg'
        dupe_b = root / 'dupe_b.jpg'
        unique = root / 'unique.jpg'

        dupe_a.write_bytes(b'same content')
        dupe_b.write_bytes(b'same content')
        unique.write_bytes(b'different content')

        groups = find_duplicates([dupe_a, dupe_b, unique])

        assert len(groups) == 1
        found_paths = list(groups.values())[0]
        assert dupe_a in found_paths
        assert dupe_b in found_paths


def test_no_duplicates_returns_empty():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        files = []
        for i in range(4):
            path = root / f'file_{i}.jpg'
            path.write_bytes(f'unique content number {i}'.encode())
            files.append(path)

        assert find_duplicates(files) == {}


def test_multiple_duplicate_groups():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        group1_a = root / 'g1a.jpg'
        group1_b = root / 'g1b.jpg'
        group2_a = root / 'g2a.jpg'
        group2_b = root / 'g2b.jpg'

        group1_a.write_bytes(b'group one content')
        group1_b.write_bytes(b'group one content')
        group2_a.write_bytes(b'group two content')
        group2_b.write_bytes(b'group two content')

        groups = find_duplicates([group1_a, group1_b, group2_a, group2_b])

        assert len(groups) == 2


# --- archive behaviour ---

def _make_args(archive: str | None = None, delete: bool = False) -> argparse.Namespace:
    return argparse.Namespace(delete=delete, archive=archive)


def test_archive_creates_numbered_subfolder():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dupe_a = root / 'dupe_a.jpg'
        dupe_b = root / 'dupe_b.jpg'
        dupe_a.write_bytes(b'same bytes')
        dupe_b.write_bytes(b'same bytes')

        archive_root = root / 'archive'
        groups = find_duplicates([dupe_a, dupe_b])
        act_on_duplicates(groups, _make_args(archive='archive'), stats={'actioned': 0},
                          archive_root=archive_root)

        assert (archive_root / '001').is_dir()


def test_archive_keeper_copied_with_prefix_and_original_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # keeper is the lexicographically first path: aaa.jpg
        keeper = root / 'aaa.jpg'
        dupe = root / 'zzz.jpg'
        keeper.write_bytes(b'identical')
        dupe.write_bytes(b'identical')

        archive_root = root / 'archive'
        groups = find_duplicates([keeper, dupe])
        act_on_duplicates(groups, _make_args(archive='archive'), stats={'actioned': 0},
                          archive_root=archive_root)

        assert (archive_root / '001' / 'keeper_aaa.jpg').exists()
        assert keeper.exists()  # original keeper untouched


def test_archive_dupes_moved_into_subfolder():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        keeper = root / 'aaa.jpg'
        dupe = root / 'zzz.jpg'
        keeper.write_bytes(b'identical')
        dupe.write_bytes(b'identical')

        archive_root = root / 'archive'
        groups = find_duplicates([keeper, dupe])
        act_on_duplicates(groups, _make_args(archive='archive'), stats={'actioned': 0},
                          archive_root=archive_root)

        assert (archive_root / '001' / 'zzz.jpg').exists()
        assert not dupe.exists()  # dupe removed from source


def test_archive_multiple_groups_get_separate_subfolders():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        g1a = root / 'g1a.jpg'
        g1b = root / 'g1b.jpg'
        g2a = root / 'g2a.png'
        g2b = root / 'g2b.png'
        g1a.write_bytes(b'group one')
        g1b.write_bytes(b'group one')
        g2a.write_bytes(b'group two')
        g2b.write_bytes(b'group two')

        archive_root = root / 'archive'
        groups = find_duplicates([g1a, g1b, g2a, g2b])
        act_on_duplicates(groups, _make_args(archive='archive'), stats={'actioned': 0},
                          archive_root=archive_root)

        subfolders = sorted(p.name for p in archive_root.iterdir() if p.is_dir())
        assert subfolders == ['001', '002']


def test_archive_auto_path_created_inside_scan_root():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dupe_a = root / 'a.jpg'
        dupe_b = root / 'b.jpg'
        dupe_a.write_bytes(b'same')
        dupe_b.write_bytes(b'same')

        # Simulate what main() does for AUTO: generate archive_root inside root
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        archive_root = root / f'dupehunter-archive-{timestamp}'
        archive_root.mkdir()

        groups = find_duplicates([dupe_a, dupe_b])
        act_on_duplicates(groups, _make_args(archive='AUTO'), stats={'actioned': 0},
                          archive_root=archive_root)

        assert archive_root.parent == root
        assert archive_root.name.startswith('dupehunter-archive-')
        assert (archive_root / '001').is_dir()
