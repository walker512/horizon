# Local storage privacy

New workspaces use owner-only POSIX directory permissions (0700) and database
permissions (0600), **before SQLite opens them**. Missing intermediate directories
are also created private. No process-wide umask is changed. SQLite rollback
journals, WAL and shared-memory files inherit the private database's permissions;
real live-journal/WAL tests exercise this with umask 000. Every connection checks
existing database and sidecars before opening. SQLite is opened in `mode=rw`, so a
removed database is not silently recreated during reconnect. Restore also creates
a private data directory. Concurrent threads and separate processes are tested.

Unsafe existing workspaces are **rejected**, not silently chmodded or migrated:
Horizon never changes permissions on an existing directory that might contain
unrelated files. Stop Horizon and all other writers first. On a trusted local
machine, inspect ownership, symlinks/hardlinks and the actual workspace location;
set the dedicated workspace directory to 0700 and its SQLite database and existing
`-journal`, `-wal`, `-shm` files to 0600. Do not delete live WAL/journal files or use
recursive permission changes on unrelated directories. Then restart. Take a trusted
backup first if uncertain. Files must be owned by the current user, regular and
single-link; symlink workspaces and database/sidecar links are rejected. Permissions
are checked on each new connection, not continuously during an open transaction.

This cannot undo previous exposure of old 0755/0644 workspaces. It is not encryption,
secure erasure or a defense against root, the same OS account, compromised ancestors,
ACL overrides, or filesystems that do not enforce POSIX modes. Ancestors and other
processes using this OS account must be trusted; deliberate concurrent path
replacement by that account is outside the threat model. Windows storage currently
fails closed because equivalent ACL verification is not implemented. Database files
and backups still contain sensitive evidence and notes and should not be published.
This patch adds no browser interface. The separate Action desk UI candidate is not included.

Concurrent SQLite sidecar deletion is handled by rechecking the pathname when an
already-open journal/WAL/shared-memory descriptor has become unlinked. Its owner,
file type and permissions must still pass validation. A replacement is checked
independently; linked files with multiple names remain rejected. Validation retries
at most 16 times per sidecar, then fails with a controlled busy/churn error rather
than looping indefinitely. The database itself must always have exactly one link.
