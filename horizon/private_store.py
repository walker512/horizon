"""POSIX local-store permissions; not encryption or same-account isolation."""
import os
from pathlib import Path
import stat


def _check(info, directory=False):
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (not kind(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077 or (not directory and info.st_nlink != 1)):
        raise ValueError('Unsafe workspace permissions or file type. Use an owned private directory (0700) and regular single-link files (0600); stop other writers before repairing an existing workspace.')


def prepare(path, create=True):
    """Create private missing directories and database, reject unsafe existing state.

    No process-wide umask changes, no chmod of existing user-owned directories.
    Ancestors and other processes using this OS account must be trusted.
    """
    if os.name != 'posix':
        raise ValueError('Private workspace storage currently requires POSIX permissions; Windows ACL support is not implemented.')
    path = Path(path).absolute()
    missing = []
    parent = path.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for folder in reversed(missing):
        try:
            folder.mkdir(mode=0o700)
        except FileExistsError:
            pass
        _check(folder.lstat(), directory=True)
    _check(path.parent.lstat(), directory=True)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    if create:
        try:
            fd = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            fd = os.open(path, flags)
    else:
        fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        _check(info)
        if (info.st_dev, info.st_ino) != (path.lstat().st_dev, path.lstat().st_ino):
            raise ValueError('Workspace database changed during validation.')
    finally:
        os.close(fd)
    for suffix in ('-journal', '-wal', '-shm'):
        sidecar = Path(str(path) + suffix)
        try:
            fd = os.open(sidecar, flags)
        except FileNotFoundError:
            continue
        try:
            _check(os.fstat(fd))
        finally:
            os.close(fd)
    return path
