import tempfile
from pathlib import Path

from dupehunter import hash_file, find_duplicates


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
