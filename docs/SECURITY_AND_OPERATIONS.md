# Security and Operations

## Implemented controls

- Passwords use Django hashes; legacy values are migrated on deployment.
- Mobile tokens are signed, timestamp-limited, stored in device secure storage, and revocable by token version.
- Login is throttled. Authentication failures do not reveal whether an email exists.
- Project and enquiry authorization is checked server-side for every API request.
- Site writes require both the Supervisor role and project allocation.
- Approval transitions check role and current workflow state inside transactions.
- CAD streaming uses authenticated role checks and private/no-store caching.
- Production settings reject a development secret or missing allowed hosts.

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
