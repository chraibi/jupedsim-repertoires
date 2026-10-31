# SPDX-License-Identifier: LGPL-3.0-or-later

import subprocess

from jupedsim_repertoires.provenance import code_revision, file_sha256


def _git(directory, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t", "-C", str(directory)]
        + list(args),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_code_revision_outside_repository_is_none(tmp_path):
    assert code_revision.__wrapped__(tmp_path) is None


def test_code_revision_clean_and_dirty(tmp_path):
    _git(tmp_path, "init")
    (tmp_path / "a.txt").write_text("a")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-m", "init")
    head = _git(tmp_path, "rev-parse", "HEAD")
    assert len(head) == 40
    assert code_revision.__wrapped__(tmp_path) == head
    (tmp_path / "b.txt").write_text("b")
    assert code_revision.__wrapped__(tmp_path) == head
    (tmp_path / "a.txt").write_text("changed")
    assert code_revision.__wrapped__(tmp_path) == head + "-dirty"


def test_file_sha256(tmp_path):
    path = tmp_path / "f"
    path.write_bytes(b"abc")
    assert file_sha256(path) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
