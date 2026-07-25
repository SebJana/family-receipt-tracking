import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path


BACKUP_PREFIX = "receipt-backup-"
BACKUP_PATTERN = f"{BACKUP_PREFIX}*.sqlite3"


def create_database_backup(database_path, backup_dir, now=None):
    """Create and verify an atomic SQLite backup, returning its final path."""
    source_path = Path(database_path).resolve()
    destination_dir = Path(backup_dir).resolve()
    if str(database_path) == ":memory:" or not source_path.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {database_path}")

    destination_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    destination_path = _available_backup_path(destination_dir, timestamp)

    temporary_file = tempfile.NamedTemporaryFile(
        dir=destination_dir,
        prefix=f".{BACKUP_PREFIX}",
        suffix=".tmp",
        delete=False,
    )
    temporary_path = Path(temporary_file.name)
    temporary_file.close()

    try:
        source_uri = f"{source_path.as_uri()}?mode=ro"
        with (
            closing(sqlite3.connect(source_uri, uri=True)) as source,
            closing(sqlite3.connect(temporary_path)) as destination,
        ):
            source.backup(destination)
            check_result = destination.execute("PRAGMA quick_check").fetchone()
            if not check_result or check_result[0] != "ok":
                result = check_result[0] if check_result else "no result"
                raise sqlite3.DatabaseError(f"Backup integrity check failed: {result}")
        os.replace(temporary_path, destination_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    return destination_path


def prune_database_backups(backup_dir, retention_days, now=None):
    """Delete managed backup files older than the configured retention window."""
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")

    destination_dir = Path(backup_dir)
    if not destination_dir.exists():
        return []

    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = current_time - timedelta(days=retention_days)
    removed = []
    for backup_path in destination_dir.glob(BACKUP_PATTERN):
        modified = datetime.fromtimestamp(backup_path.stat().st_mtime, timezone.utc)
        if modified < cutoff:
            backup_path.unlink()
            removed.append(backup_path)
    return removed


def _available_backup_path(backup_dir, timestamp):
    timestamp_label = timestamp.strftime("%Y-%m-%d_%H-%M-%S_UTC")
    candidate = backup_dir / f"{BACKUP_PREFIX}{timestamp_label}.sqlite3"
    sequence = 2
    while candidate.exists():
        candidate = backup_dir / f"{BACKUP_PREFIX}{timestamp_label}-{sequence}.sqlite3"
        sequence += 1
    return candidate
