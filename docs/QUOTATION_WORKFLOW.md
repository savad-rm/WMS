# Quotation Workflow Operations

## Quotation references and revisions

- The first quotation for an enquiry receives the next chronological reference in the form `QTN/0001/ETC/MM/YY`.
- A later quotation for the same enquiry is treated as an immutable revision and keeps the base reference with `-R1`, `-R2`, and so on.
- Approved or submitted quotations are never overwritten. A revision creates a new database record and repeats the approval workflow.

## Enquiry history and quotation register

- Enquiries remain in the Enquiry History after a quotation is created; creating a quotation does not replace, hide, or convert the enquiry record.
- The enquiry list keeps the original scope/remarks entered when the enquiry was created. Its list status is `Pending` until a quotation exists and `Quotation Prepared` afterwards.
- Quotations and revisions appear independently in the Quotation Register, including internal approval and client-submittal details.
- After submittal, authorised Admin, Marketing Manager, and responsible Marketing Executive users can record the client's status as `Under Review`, `Approved`, or `Rejected` and maintain client remarks. These remarks do not overwrite the enquiry scope or the quotation document remarks.
- Client-response tracking is stored inside the quotation's existing structured details payload, so this enhancement requires no database schema migration.

## Deadline notifications

Creating an enquiry requires a quotation submission deadline. Deduplicated notifications are generated at these stages:

- Within seven days.
- Within three days.
- Within 24 hours.
- Overdue.

Recipients include the enquiry creator, assigned estimator, Marketing Managers, Document Controllers, Admins, and Operation Managers. Alerts are available in the workflow header, notification page, dashboard unread count, and mobile API.

The web and mobile endpoints generate any currently due alerts when users access the application. Production should additionally run the management command every 15 minutes so alerts are generated even during quiet periods:

```powershell
C:\path\to\WMS\.venv\Scripts\python.exe C:\path\to\WMS\manage.py send_deadline_notifications
```

Configure that command in Windows Task Scheduler under the same service account that runs WMS. On Linux, use the equivalent cron or systemd timer. The command is safe to repeat because every recipient/stage/deadline combination has a unique deduplication key.

## Template assets and downloads

The deployable Exalter assets are stored in `MyApp/quotation_templates/`, not `media/`. Runtime uploads under `media/` are ignored by Git and must be backed up separately or stored in production object storage.

Each saved quotation can be downloaded as:

- An editable Excel workbook based on the supplied Exalter workbook.
- A client-ready PDF using the supplied Exalter letterhead on every page.

The exported client document excludes the internal material, labour, and other costing fields.
