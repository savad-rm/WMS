"""Create an auditable WMS database and media backup set."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, connections


SUPPORTED_ENGINES = {
    'django.db.backends.sqlite3': 'sqlite',
    'django.db.backends.postgresql': 'postgresql',
    'django.db.backends.mysql': 'mysql',
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_backup_root(value: str | os.PathLike[str]) -> Path:
    root = Path(value).expanduser().resolve()
    base_dir = Path(settings.BASE_DIR).resolve()
    media_root = Path(settings.MEDIA_ROOT).resolve()
    if root in (base_dir, media_root) or root.is_relative_to(media_root):
        raise CommandError('Backup directory must be outside the application and media directories.')
    return root


class Command(BaseCommand):
    help = 'Back up the configured database and media files with checksums and retention.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--destination',
            default=getattr(settings, 'WMS_BACKUP_ROOT', ''),
            help='Backup root; defaults to WMS_BACKUP_ROOT.',
        )
        parser.add_argument(
            '--retention-days',
            type=int,
            default=getattr(settings, 'WMS_BACKUP_RETENTION_DAYS', 30),
            help='Delete completed local backup sets older than this many days; 0 disables pruning.',
        )
        parser.add_argument('--skip-media', action='store_true', help='Back up only the database.')

    def handle(self, *args, **options):
        destination = options['destination']
        if not destination:
            raise CommandError('Set WMS_BACKUP_ROOT or pass --destination.')
        if options['retention_days'] < 0:
            raise CommandError('--retention-days cannot be negative.')

        backup_root = _safe_backup_root(destination)
        backup_root.mkdir(parents=True, exist_ok=True)
        lock_path = backup_root / '.backup.lock'
        try:
            lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise CommandError(
                f'Another backup appears to be running ({lock_path}). Remove a stale lock only after verification.'
            ) from exc

        run_started = datetime.now(timezone.utc)
        run_name = run_started.strftime('%Y%m%dT%H%M%SZ')
        partial_dir = backup_root / f'.partial-{run_name}-{uuid.uuid4().hex[:8]}'
        final_dir = backup_root / run_name
        os.write(lock_descriptor, f'{os.getpid()} {run_name}\n'.encode('ascii'))
        os.close(lock_descriptor)

        try:
            if final_dir.exists():
                raise CommandError(f'Backup set already exists: {final_dir}')
            partial_dir.mkdir()
            database_file, engine_name = self._backup_database(partial_dir)
            files = [database_file]
            if not options['skip_media']:
                media_file = self._backup_media(partial_dir)
                if media_file:
                    files.append(media_file)

            manifest = {
                'schema_version': 1,
                'application': 'WMS',
                'created_at_utc': run_started.isoformat(),
                'database_engine': engine_name,
                'media_included': not options['skip_media'],
                'files': {
                    item.name: {'bytes': item.stat().st_size, 'sha256': _sha256(item)}
                    for item in files
                },
            }
            manifest_path = partial_dir / 'manifest.json'
            manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
            partial_dir.replace(final_dir)
            self._prune(backup_root, options['retention_days'], run_started)
            self.stdout.write(self.style.SUCCESS(f'Backup completed: {final_dir}'))
        except Exception:
            shutil.rmtree(partial_dir, ignore_errors=True)
            raise
        finally:
            lock_path.unlink(missing_ok=True)

    def _backup_database(self, target_dir: Path) -> tuple[Path, str]:
        configuration = connections['default'].settings_dict
        engine = configuration['ENGINE']
        engine_name = SUPPORTED_ENGINES.get(engine)
        if not engine_name:
            raise CommandError(f'Unsupported database engine for backup: {engine}')
        if engine_name == 'sqlite':
            output = target_dir / 'database.sqlite3'
            connection = connections['default']
            connection.ensure_connection()
            with closing(sqlite3.connect(output)) as target_db:
                connection.connection.backup(target_db)
                integrity = target_db.execute('PRAGMA integrity_check').fetchone()
                if not integrity or integrity[0] != 'ok':
                    raise CommandError('The SQLite backup failed its integrity check.')
            return output, engine_name

        close_old_connections()

        if engine_name == 'postgresql':
            output = target_dir / 'database.pgdump'
            command = ['pg_dump', '--format=custom', f'--file={output}']
            self._add_connection_options(command, configuration, engine_name)
            command.append(str(configuration['NAME']))
            environment = os.environ.copy()
            if configuration.get('PASSWORD'):
                environment['PGPASSWORD'] = str(configuration['PASSWORD'])
            self._run_dump(command, environment)
            return output, engine_name

        output = target_dir / 'database.sql'
        command = ['mysqldump', '--single-transaction', '--routines', '--events']
        defaults_file = os.environ.get('WMS_MYSQL_DEFAULTS_FILE')
        if defaults_file:
            command.insert(1, f'--defaults-extra-file={Path(defaults_file).resolve()}')
        self._add_connection_options(command, configuration, engine_name)
        command.extend([f'--result-file={output}', str(configuration['NAME'])])
        environment = os.environ.copy()
        if configuration.get('PASSWORD') and not defaults_file:
            environment['MYSQL_PWD'] = str(configuration['PASSWORD'])
        self._run_dump(command, environment)
        return output, engine_name

    @staticmethod
    def _add_connection_options(command, configuration, engine_name):
        option_names = {'HOST': 'host', 'PORT': 'port', 'USER': 'username' if engine_name == 'postgresql' else 'user'}
        for setting_name, option_name in option_names.items():
            value = configuration.get(setting_name)
            if value:
                command.append(f'--{option_name}={value}')

    @staticmethod
    def _run_dump(command, environment):
        try:
            subprocess.run(
                command, env=environment, check=True, capture_output=True, text=True,
                timeout=int(os.environ.get('WMS_BACKUP_DATABASE_TIMEOUT', '3600')),
            )
        except FileNotFoundError as exc:
            raise CommandError(f'Required database backup executable was not found: {command[0]}') from exc
        except subprocess.TimeoutExpired as exc:
            raise CommandError('Database backup timed out.') from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or '').strip()[-1000:]
            raise CommandError(f'Database backup failed: {detail or "unknown database-tool error"}') from exc

    @staticmethod
    def _backup_media(target_dir: Path) -> Path | None:
        media_root = Path(settings.MEDIA_ROOT).resolve()
        if not media_root.exists():
            return None
        output = target_dir / 'media.tar.gz'
        with tarfile.open(output, 'w:gz') as archive:
            for path in sorted(media_root.rglob('*')):
                if path.is_file() and not path.is_symlink():
                    archive.add(path, arcname=Path('media') / path.relative_to(media_root), recursive=False)
        return output

    @staticmethod
    def _prune(backup_root: Path, retention_days: int, now: datetime):
        if not retention_days:
            return
        cutoff = now - timedelta(days=retention_days)
        for path in backup_root.iterdir():
            if not path.is_dir() or not path.name.endswith('Z'):
                continue
            try:
                created = datetime.strptime(path.name, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if created < cutoff:
                shutil.rmtree(path)
