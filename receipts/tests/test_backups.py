import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from receipts.backups import create_database_backup, prune_database_backups


class DatabaseBackupTests(SimpleTestCase):
    def test_backup_is_a_consistent_readable_sqlite_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            database_path = directory_path / "source.sqlite3"
            backup_dir = directory_path / "backups"
            with closing(sqlite3.connect(database_path)) as database:
                database.execute("CREATE TABLE receipt (id INTEGER PRIMARY KEY, market TEXT)")
                database.execute("INSERT INTO receipt (market) VALUES ('REWE')")
                database.commit()

            backup_path = create_database_backup(
                database_path,
                backup_dir,
                now=datetime(2026, 7, 25, 12, 30, tzinfo=timezone.utc),
            )

            self.assertEqual(
                backup_path.name,
                "receipt-backup-2026-07-25_12-30-00_UTC.sqlite3",
            )
            with closing(sqlite3.connect(backup_path)) as backup:
                self.assertEqual(
                    backup.execute("SELECT market FROM receipt").fetchall(),
                    [("REWE",)],
                )
                self.assertEqual(backup.execute("PRAGMA quick_check").fetchone(), ("ok",))

    def test_backup_names_do_not_overwrite_an_existing_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            database_path = directory_path / "source.sqlite3"
            backup_dir = directory_path / "backups"
            with closing(sqlite3.connect(database_path)) as database:
                database.execute("CREATE TABLE receipt (id INTEGER PRIMARY KEY)")
                database.commit()
            now = datetime(2026, 7, 25, 12, 30, tzinfo=timezone.utc)

            first = create_database_backup(database_path, backup_dir, now=now)
            second = create_database_backup(database_path, backup_dir, now=now)

            self.assertNotEqual(first, second)
            self.assertEqual(
                second.name,
                "receipt-backup-2026-07-25_12-30-00_UTC-2.sqlite3",
            )
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())

    def test_retention_only_removes_managed_backups_older_than_thirty_days(self):
        with tempfile.TemporaryDirectory() as directory:
            backup_dir = Path(directory)
            old_backup = backup_dir / "receipt-backup-old.sqlite3"
            recent_backup = backup_dir / "receipt-backup-recent.sqlite3"
            unrelated_file = backup_dir / "notes.txt"
            for path in (old_backup, recent_backup, unrelated_file):
                path.touch()
            now = datetime(2026, 7, 25, 12, 30, tzinfo=timezone.utc)
            os.utime(old_backup, (now.timestamp(), (now - timedelta(days=31)).timestamp()))
            os.utime(recent_backup, (now.timestamp(), (now - timedelta(days=29)).timestamp()))
            os.utime(unrelated_file, (now.timestamp(), (now - timedelta(days=60)).timestamp()))

            removed = prune_database_backups(backup_dir, retention_days=30, now=now)

            self.assertEqual(removed, [old_backup])
            self.assertFalse(old_backup.exists())
            self.assertTrue(recent_backup.exists())
            self.assertTrue(unrelated_file.exists())

    def test_worker_once_runs_without_waiting(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            database_path = directory_path / "source.sqlite3"
            backup_dir = directory_path / "backups"
            with closing(sqlite3.connect(database_path)) as database:
                database.execute("CREATE TABLE receipt (id INTEGER PRIMARY KEY)")
                database.commit()
            output = StringIO()

            call_command(
                "backup_worker",
                once=True,
                database_path=str(database_path),
                backup_dir=str(backup_dir),
                retention_days=30,
                interval_seconds=86400,
                stdout=output,
            )

            self.assertEqual(len(list(backup_dir.glob("receipt-backup-*.sqlite3"))), 1)
            self.assertIn("Database backup created:", output.getvalue())

    def test_worker_rejects_a_non_positive_interval(self):
        with self.assertRaisesMessage(CommandError, "interval-seconds must be at least 1"):
            call_command("backup_worker", once=True, interval_seconds=0)
