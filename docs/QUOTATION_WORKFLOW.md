# Quotation Workflow Operations

## Quotation references and revisions

- The first quotation for an enquiry receives the next chronological reference in the form `QTN/0001/ETC/MM/YY`.
- A later quotation for the same enquiry is treated as an immutable revision and keeps the base reference with `-R1`, `-R2`, and so on.
- Approved or submitted quotations are never overwritten by an estimator revision. A client revision creates a new database record and repeats the approval workflow; a Marketing Manager/Accountant revision request before final approval returns the current record to `Draft`, clears approvals, and notifies the estimator.
- New quotations and revisions start in `Draft`. The estimator can preview and edit that same record repeatedly without creating a revision.
- Marketing Manager approval begins only after the estimator selects `Submit for Approval`. Once submitted, the draft is locked; later client or approval changes require the normal revision workflow.

## Quotation entry and document layout

- Item units are selected from `M2`, `Nos.`, `ITEM`, `LM`, `RM`, and `Sets`.
- Pressing Enter from a quotation row field inserts the next item immediately below the current row. Completely blank next rows are ignored safely when saving.
- Sections are centred across the structural description area and use Latin section numbering; subheadings are left-aligned and use hierarchical numbering such as `1.1`. Structural rows hide unit/quantity inputs. They may either show a calculated subtotal from item rows or accept a direct editable subtotal. When a structural row has no item rate/amount, the exported layout merges the rate and amount area into one subtotal cell; item rows keep separate rate and amount columns. `M2`, `Nos.`, `ITEM`, `LM`, `RM`, and `Sets` are the supported units, and blank/null rate and amount values are valid.
- Grand totals show a QAR label and the amount in words using the international thousand/million scale; `lakh` is never used and no redundant currency phrase is appended.
- Web preview uses the same generated A4 PDF as the download, including genuine page breaks, repeated table headings, letterhead, footer, and page numbers.
- Preview is intentionally available only after saving a draft. The saved quotation view renders the client-ready PDF and keeps edit and submit-for-approval actions beside it.
- An estimator can import content from a previous approved, submitted, accepted, or rejected quotation into a new quotation, draft edit, or revision editor. Drafts are intentionally excluded because they are private. Line items, editable document text, terms and internal costing are copied into the form; the current enquiry/client, current estimator signatory, new quotation reference and approval state are deliberately retained.
- Importing is an editor convenience only. It never changes the source quotation and never creates a database record until the estimator explicitly saves the current draft.

## Quotation discussions and approvals

- Every quotation has a separate discussion page for Marketing Executives, Marketing Managers, Estimators and Accountants. Messages can receive contextual replies without appearing in the enquiry's general comment history.
- New quotation messages create per-user alerts and numeric unread badges in the enquiry and quotation lists. Opening that quotation's discussion marks only its alerts as read.
- Marketing Manager, Accountant, revision-request, costing-approval, and client-submittal actions are performed from the saved quotation view after reviewing the generated document; they are not exposed on the enquiry view. Client submission opens a mail compose dialog (recipient, optional CC, subject and editable body); the server attaches the generated PDF and reports delivery success/failure. Mobile uses server defaults and does not expose the web compose fields.
- Every client response (`Under Review`, `Approved/Awarded`, or `Rejected`) is written to the quotation discussion and generates notification entries for the authorised workflow participants.
- If Marketing Manager records a client revision request, the quotation enters `Under Revision`. The estimator receives the discussion/notification event and starts **Create Revision** from the quotation view; the enquiry history is not used as the revision entry point.

## Enquiry history and quotation register

- Enquiries remain in the Enquiry History after a quotation is created; creating a quotation does not replace, hide, or convert the enquiry record.
- The enquiry list keeps the original scope/remarks entered when the enquiry was created. Its list status is `Pending` until an estimator submits a quotation for approval and `Quotation Prepared` afterwards; saving a draft alone does not change the enquiry status.
- Quotations and revisions appear independently in the Quotation Register, including internal approval and client-submittal details.
- After submittal, authorised Admin, Marketing Manager, and responsible Marketing Executive users can record the client's status as `Under Review`, `Under Revision`, `Approved`, or `Rejected` and maintain client remarks. These remarks do not overwrite the enquiry scope or the quotation document remarks.
- Client-response tracking is stored inside the quotation's existing structured details payload, so this enhancement requires no database schema migration.

## Visibility and final-state rules

- Only the estimator who owns a draft can edit or view it. Shared quotation registers and enquiry quotation counts exclude drafts.
- Once a quotation is awarded, the revision, client-status, and further approval actions are removed. The quotation and its discussion remain available as immutable history.

## Deadline notifications

Creating an enquiry requires a quotation submission date. The selected date is treated as the end of that local business day, and deduplicated notifications are generated at these stages:

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
