# Security and Operations

## Implemented controls

- Passwords use Django hashes; legacy values are migrated on deployment.
- Mobile tokens are signed, timestamp-limited, stored in device secure storage, and revocable by token version.
- Login is throttled. Authentication failures do not reveal whether an email exists.
- Project and enquiry authorization is checked server-side for every API request.
- Site writes require both the Supervisor role and project allocation.
- Approval transitions check role and current workflow state inside transactions.
- Draft quotations are private to their estimator; server-side visibility checks protect quotation HTML, PDF, discussion, and API responses.
- SMTP credentials and sender configuration are environment secrets. Mail errors are logged without passwords, tokens, document contents, or full message bodies.
- Client responses and quotation discussions are permission-checked and generate auditable notification records.
- CAD streaming uses authenticated role checks and private/no-store caching.
- Production settings reject a development secret or missing allowed hosts.

## Web session lifecycle

- Web sessions expire after 30 minutes of inactivity by default (`WMS_SESSION_IDLE_TIMEOUT`). The absolute cookie lifetime is 8 hours by default (`WMS_SESSION_COOKIE_AGE`). Both values are configurable per deployment.
- `SESSION_EXPIRE_AT_BROWSER_CLOSE` is enabled by default so closing the browser removes the session cookie. A deployment may explicitly disable it only when its device/session policy requires persistent browser sessions.
- Each web session stores the account's `api_token_version`. Password changes, administrator credential/role changes, mobile logout and other credential revocations increment that version. A session with an older version is rejected on its next request and redirected to login.
- Login rotates the session identifier and clears any previous role/session data, preventing session fixation and cross-role session reuse.
- The middleware checks the account, token version and idle timestamp before protected WMS views execute. Deleted accounts and malformed/stale session values are rejected without exposing a traceback.

Recommended production values should be set through environment configuration, for example:

```text
WMS_SESSION_IDLE_TIMEOUT=1800
WMS_SESSION_COOKIE_AGE=28800
WMS_SESSION_EXPIRE_AT_BROWSER_CLOSE=true
```

## Production requirements

- HTTPS only; terminate TLS at a maintained reverse proxy and forward scheme safely.
- Store application/database/signing secrets outside Git.
- Restrict database and media backups using encryption and least privilege.
- Set upload limits at proxy and Django layers; scan client documents according to company policy.
- Do not expose Django's development server or SQLite database on a public network.
- Use a supported production database before multi-instance/high-concurrency deployment.
- Apply OS, Python, Django, npm, and mobile SDK security updates through tested releases.

## Logging and monitoring

Capture request ID, timestamp, route, method, status, latency, authenticated account ID, and deployment version. Never log passwords, bearer tokens, full client documents, or sensitive request bodies. Alert on elevated 5xx, repeated login failure/429 responses, unexpected 403 changes, storage exhaustion, backup failure, and database errors.

## Backup and recovery

- Back up database and media together so references remain consistent.
- Schedule `manage.py backup_wms`; each completed set includes checksums and a manifest and must be copied to encrypted off-site storage.
- Define recovery-point and recovery-time objectives with the business owner.
- Keep off-site encrypted copies and test restoration on a schedule.
- Before migrations, create a labeled backup and record its checksum/location.

## Incident response

1. Triage severity and preserve logs/evidence.
2. Contain: revoke tokens by incrementing account token versions, rotate secrets when necessary, and disable affected ingress.
3. Determine affected users, projects, files, and time window.
4. Recover from a known-good artifact/backup and verify authorization paths.
5. Notify required stakeholders under organizational and legal policy.
6. Document root cause and tracked corrective actions.

Rotating `WMS_SECRET_KEY` invalidates all signed mobile tokens and Django sessions. Treat it as a coordinated security operation.
