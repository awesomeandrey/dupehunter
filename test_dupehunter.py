import os
import tempfile

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

        assert len(groups) == 1

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
