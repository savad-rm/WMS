# Deployment Runbook

## Required configuration

| Variable | Production requirement |
|---|---|
| `WMS_SECRET_KEY` | Long random secret from secret manager; never rotate without a session/token plan |
| `WMS_DEBUG` | `false` |
| `WMS_ALLOWED_HOSTS` | Explicit comma-separated host names |
| `WMS_SESSION_COOKIE_SECURE` | `true` |
| `WMS_CSRF_COOKIE_SECURE` | `true` |
| `WMS_SECURE_SSL_REDIRECT` | `true` behind correctly configured proxy |
| `WMS_SECURE_HSTS_SECONDS` | Increase after HTTPS validation |
| `WMS_MOBILE_TOKEN_MAX_AGE` | Organizational token lifetime in seconds |
| `WMS_EMAIL_BACKEND` | Production SMTP backend; do not leave the local development backend enabled |
| `WMS_EMAIL_HOST`, `WMS_EMAIL_PORT` | Reachable approved SMTP service |
| `WMS_EMAIL_HOST_USER`, `WMS_EMAIL_HOST_PASSWORD` | Secret-managed verified sender credentials |
| `WMS_EMAIL_USE_TLS`, `WMS_EMAIL_USE_SSL` | Exactly one transport security mode enabled |
| `WMS_DEFAULT_FROM_EMAIL` | Verified sender address used for quotation delivery |

## Backend release

1. Announce maintenance/risk window and identify rollback owner.
2. Back up the database and `media/`; verify backup readability.
3. Deploy application code and install `requirements.txt` into the WMS virtual environment.
4. Have the Flyway team apply the approved schema SQL and record its version, then run:

```powershell
..venv\Scripts\python.exe manage.py check
..venv\Scripts\python.exe manage.py makemigrations --check --dry-run
..venv\Scripts\python.exe manage.py test
..venv\Scripts\python.exe manage.py collectstatic --noinput
..venv\Scripts\python.exe manage.py check --deploy
```

5. Restart application workers using the service manager.
6. Smoke test web login, `/WMS/api/v1/auth/login/`, role project filtering, media access, CAD viewing, and quotation delivery. For delivery, submit an approved quotation to a controlled mailbox and verify the PDF attachment, `Under Review` state, and discussion/notification entry. Also verify an intentionally failed SMTP/recipient attempt leaves the quotation approved and not submitted.
7. Monitor 4xx/5xx rates, latency, database locks, storage, and authentication failures.

## Mobile release

1. Point the release profile at the production HTTPS API.
2. Run TypeScript, Expo-config, Android export, and manual role regression tests.
3. Increment platform build numbers.
4. Generate signed Android/iOS artifacts using protected signing credentials.
5. Roll out to internal testers, then a staged production percentage.
6. Watch crash-free sessions, authentication errors, and API compatibility before full rollout.

## Rollback

- Mobile: halt rollout and restore the previous store build/channel. API v1 remains backward compatible within the release line.
- Backend code: redeploy the prior artifact only if its migrations are forward-compatible.
- Database: never reverse a data migration blindly. Restore the verified backup when a destructive migration cannot safely reverse.
- Record incident timeline, affected versions, decision owner, and follow-up actions.

Use [Current firm deployment](CURRENT_FIRM_DEPLOYMENT_GUIDE.md) for the complete production procedure and [Commercial multi-client deployment](COMMERCIAL_MULTI_TENANT_DEPLOYMENT_GUIDE.md) for customer isolation and productization.

## Post-release evidence

Archive commit/tag, dependency lock files, migration plan, test results, deployment timestamps, artifact checksums, approvers, monitoring snapshot, and rollback decision.
