# WMS quick project map

This directory is the Exalter Trading & Contracting Django application (WMS).

## Fast orientation

- `WMS/`: Django settings, URL root and WSGI entry point.
- `MyApp/`: domain models, workflow views, mobile API, quotation generation and tests.
- `templates/Workflow/`: current web workflow UI; preserve the existing Bootstrap/NiceAdmin visual language.
- `static/`: shared CSS, JavaScript and images. `media/` contains user/client files and must not be deleted or committed.
- `mobile/`: mobile client source and API integration types.
- `docs/`: operational and product documentation.

## Safe development rules

- Activate `.venv` before Django commands: `.venv\Scripts\python.exe manage.py ...`.
- Run `manage.py check`, targeted tests, then the full suite before handoff.
- Do not create Django/Flyway migration files in this workspace. Report required SQL to the migration team.
- Keep draft quotations private to their estimator; only submitted-for-approval quotations are visible to other roles.
- Preserve quotation history, client response discussion and notification audit trails.
- Keep secrets in environment variables or a secret manager; never commit SMTP credentials.
