# SPDX-License-Identifier: LGPL-3.0-or-later

import functools
import hashlib
import pathlib
import subprocess

_PACKAGE_DIR = pathlib.Path(__file__).parent
_CHUNK_SIZE = 1024 * 1024


def _git(directory: pathlib.Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), *args],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


@functools.cache
def code_revision(directory: pathlib.Path = _PACKAGE_DIR) -> str | None:
    """Return the git revision of the checkout containing ``directory``.

    Args:
        directory: Any directory inside the checkout.

    Returns:
        The HEAD commit hash, suffixed with ``-dirty`` if tracked files
        have uncommitted changes, or ``None`` outside a git checkout.
    """
    head = _git(directory, "rev-parse", "HEAD")
    if head is None:
        return None
    status = _git(directory, "status", "--porcelain", "--untracked-files=no")
    if status is None:
        return None
    return head + "-dirty" if status else head


def file_sha256(path: pathlib.Path) -> str:
    """Return the hex SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while chunk := file.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()
