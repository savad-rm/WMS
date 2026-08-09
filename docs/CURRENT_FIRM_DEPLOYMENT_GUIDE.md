# Current Firm Production Deployment Guide

## Purpose and recommended target

This guide deploys the existing single-firm WMS. The recommended first production topology is:

```text
Internet/mobile app
        |
      HTTPS
        |
Nginx reverse proxy
        |
Gunicorn WSGI service (2+ workers)
        |
Managed PostgreSQL ---- persistent private media volume
        |                         |
 database backups          encrypted off-site copies
```

Use an Ubuntu LTS virtual machine or equivalent managed container service in the Qatar/approved data region. Use a managed PostgreSQL service where possible. Do not expose PostgreSQL publicly, do not use SQLite in production, and do not use `manage.py runserver`.

For the first release, keep one application instance and a persistent media volume. Before running multiple application instances, move uploads to compatible object storage or shared protected storage; otherwise a file uploaded through one instance may be absent from another.

Authoritative references: [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/), [Django with Gunicorn](https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/gunicorn/), and [Django security guidance](https://docs.djangoproject.com/en/5.2/topics/security/).

## Production readiness gate

Do not launch until every item has an owner and evidence:

- All automated tests and `manage.py check --deploy` pass using production-like settings.
- UAT covers every role, enquiry/quotation workflow, CAD preview, file permissions, mobile login and notifications.
- PostgreSQL migration rehearsal has been completed with a copy of real data.
- The Flyway team has applied and recorded all approved schema SQL. Application developers do not create Flyway scripts in this repository.
- HTTPS, DNS, email/push notification credentials and the production mobile API URL are ready.
- Backup creation, off-site transfer and a full restore drill have passed.
- Monitoring, incident contacts, rollback owner, maintenance window and go/no-go owner are recorded.
- Client documents and staff data have an approved retention/access policy.

## Environment separation

Maintain three isolated environments:

| Environment | Data | Purpose | Public access |
|---|---|---|---|
| Development | Synthetic | Coding and local tests | No |
| Staging/UAT | Sanitized or synthetic | Release rehearsal and user acceptance | Restricted |
| Production | Real | Live business use | HTTPS only |

Never copy production documents or personal data into developer laptops without explicit approval and sanitization. Each environment must have different database credentials, secret key, media storage and hostname.

## Server preparation

1. Create a non-root `wms` service account and `/srv/wms/{app,venv,media,logs}`.
2. Install a supported Python version, PostgreSQL client tools, Nginx and OS security updates.
3. Deploy a tagged, immutable release to `/srv/wms/app`; never deploy an uncommitted working directory.
4. Create the virtual environment and install:

   ```bash
   /srv/wms/venv/bin/python -m pip install --upgrade pip
   /srv/wms/venv/bin/pip install -r /srv/wms/app/requirements-production.txt
   ```

5. Give the service account read access to code and read/write access only to media/log locations it needs.

## Required production configuration

Store secrets in the hosting secret manager or a root-owned environment file with mode `0600`. Do not commit it.

```dotenv
WMS_DEBUG=false
WMS_SECRET_KEY=<long-random-secret>
WMS_ALLOWED_HOSTS=wms.example.com
WMS_CSRF_TRUSTED_ORIGINS=https://wms.example.com
WMS_SESSION_COOKIE_SECURE=true
WMS_CSRF_COOKIE_SECURE=true
WMS_SECURE_SSL_REDIRECT=true
WMS_BEHIND_HTTPS_PROXY=true
WMS_SECURE_HSTS_SECONDS=3600

WMS_DB_ENGINE=postgresql
WMS_DB_NAME=wms_production
WMS_DB_USER=wms_app
WMS_DB_PASSWORD=<secret>
WMS_DB_HOST=<private-managed-db-host>
WMS_DB_PORT=5432
WMS_DB_SSLMODE=require
WMS_DB_CONN_MAX_AGE=60

WMS_BACKUP_ROOT=/srv/wms/backups
WMS_BACKUP_RETENTION_DAYS=30
WMS_BACKUP_DATABASE_TIMEOUT=3600
```

After HTTPS has been stable, increase HSTS gradually. Do not enable HSTS preload until every required subdomain is permanently HTTPS-ready.

## Database cutover

1. Freeze writes or announce a maintenance window.
2. Create and verify a final source backup.
3. Restore/import into PostgreSQL in staging first and reconcile row counts and critical totals.
4. Give the Flyway team the approved SQL handoff and confirm its schema-history record.
5. Run application checks against the target database. Do not run ad-hoc production DDL from an application shell.
6. Smoke-test authentication, role permissions, projects, enquiries, quotations, comments, notifications and document access.

The username/password staff change requires no new physical column: `MyApp_login.username` and `MyApp_login.password` already exist. Password values remain Django hashes. Do not bulk-convert legacy email usernames; administrators can replace them gradually through Edit Staff.

## Static files, media and CAD assets

Run once per release:

```bash
/srv/wms/venv/bin/python manage.py collectstatic --noinput
```

Nginx may serve `staticfiles/` directly with long cache headers. Media is user-controlled and must never be executed as code. Preserve the application’s authenticated download/view authorization for private quotation, enquiry and CAD files; do not expose the entire media directory as an unrestricted public alias.

The compiled local CAD viewer under `static/cad_viewer/` must be deployed with its workers, fonts and WASM dependencies. Test a real DWG after every static/CDN configuration change.

## Application service and reverse proxy

Run Gunicorn through systemd, not an interactive terminal. Start conservatively, for example two workers and a 120-second timeout, then tune from measured memory and latency:

```bash
/srv/wms/venv/bin/gunicorn WMS.wsgi:application \
  --bind 127.0.0.1:8000 --workers 2 --timeout 120 \
  --access-logfile - --error-logfile -
```

Nginx must terminate TLS, reject unknown hosts, set upload/body limits appropriate for CAD/quotation files, forward `Host` and `X-Forwarded-Proto`, apply request timeouts, and proxy only to `127.0.0.1:8000`. Automate certificate renewal and alert on failure.

## Release procedure

1. Tag the release and record the artifact checksum.
2. Confirm a successful recent backup and tested rollback artifact.
3. Put the application in the approved maintenance/read-only window when schema work requires it.
4. Deploy code and install locked production requirements.
5. Let the Flyway team apply approved schema changes; record their version/result.
6. Run:

   ```bash
   /srv/wms/venv/bin/python manage.py check
   /srv/wms/venv/bin/python manage.py check --deploy
   /srv/wms/venv/bin/python manage.py test
   /srv/wms/venv/bin/python manage.py collectstatic --noinput
   ```

7. Restart Gunicorn, then smoke-test through the public HTTPS hostname.
8. Verify the mobile app is configured with `https://wms.example.com/WMS/api/v1`—never a private IP for production.
9. Monitor errors, latency, authentication failures, database/storage capacity and deadline-notification execution.

## Configurable scheduled backups

The implemented command creates a database backup, `media.tar.gz`, SHA-256 checksums and `manifest.json`; it uses a lock to prevent overlap and removes completed local sets older than the configured retention:

```bash
/srv/wms/venv/bin/python manage.py backup_wms
/srv/wms/venv/bin/python manage.py backup_wms --retention-days 30
/srv/wms/venv/bin/python manage.py backup_wms --skip-media
```

Schedule the supplied `deploy/systemd/wms-backup.service` and `.timer` daily. On Windows Server, use the supplied PowerShell registration script. The scheduler account needs database backup rights and write access to `WMS_BACKUP_ROOT`, but no interactive login.

Recommended policy:

- Daily logical database + media backup; local retention 30 days.
- Copy every successful set to encrypted off-site/object storage with versioning and immutability.
- Weekly checksum verification and monthly alert review.
- Quarterly restore drill into an isolated environment.
- Before every production schema release, create a separately labelled backup.
- Initial targets: RPO 24 hours and RTO 4 hours; improve to managed PostgreSQL point-in-time recovery when business impact requires it.

The local command is a portable safety layer, not a replacement for managed PostgreSQL snapshots/PITR. PostgreSQL WAL archiving can restore to a selected time between base backups; configure it through the managed database provider.

Database and media are separate storage systems, so files uploaded while an online backup is running can fall on either side of the database snapshot. Run the portable backup during the quietest period; use a brief write-maintenance window when a strictly matched legal/archive snapshot is required. Object-storage versioning plus database PITR is the preferred high-availability solution.

## Restore drill

1. Never restore over production as the first test. Provision an isolated database and media directory.
2. Verify every file against `manifest.json` SHA-256 before use.
3. PostgreSQL: restore `database.pgdump` with `pg_restore` into an empty database owned by the restore/test role.
4. SQLite development only: copy `database.sqlite3` while the application is stopped.
5. Extract `media.tar.gz` into the isolated media root and verify permissions.
6. Start the matching application release; run checks and reconcile row/document counts.
7. Test representative downloads, CAD preview, quotation export and role access.
8. Record actual RPO/RTO, failures and corrective actions.

## Monitoring and rollback

Alert on 5xx rate, repeated 401/403/429 changes, response latency, database connection errors, disk/object-store usage, backup failure/missing daily manifest, certificate expiry and notification-job failure. Logs must not contain passwords, tokens or document bodies.

For code rollback, redeploy the prior immutable artifact only when it is compatible with the current schema. Do not blindly reverse data/schema changes. If data was damaged, follow the approved restore plan and preserve the affected database/logs for investigation.
