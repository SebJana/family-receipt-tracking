import sqlite3

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from receipts.backups import create_database_backup, prune_database_backups


class Command(BaseCommand):
    help = "Create a consistent SQLite database backup and prune expired backups."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database-path",
            default=str(settings.DATABASE_PATH),
            help="SQLite database to back up.",
        )
        parser.add_argument(
            "--backup-dir",
            default=str(settings.DATABASE_BACKUP_DIR),
            help="Directory where backup files are stored.",
        )
        parser.add_argument(
            "--retention-days",
            type=int,
            default=settings.DATABASE_BACKUP_RETENTION_DAYS,
            help="Delete managed backups older than this many days.",
        )

    def handle(self, *args, **options):
        if options["retention_days"] < 1:
            raise CommandError("retention-days must be at least 1")

        try:
            backup_path = create_database_backup(
                options["database_path"],
                options["backup_dir"],
            )
            removed = prune_database_backups(
                options["backup_dir"],
                options["retention_days"],
            )
        except (FileNotFoundError, OSError, sqlite3.DatabaseError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Database backup created: {backup_path} "
                f"({len(removed)} expired backup(s) removed)"
            )
        )
