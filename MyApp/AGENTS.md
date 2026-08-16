# MyApp implementation map

- `models.py`: legacy project/material models plus enquiry, quotation, lines, costing, comments and workflow notifications.
- `workflow_views.py`: web workflow permissions, quotation lifecycle, discussion, notifications and client submission.
- `api/views.py`: mobile REST workflow; keep state transitions aligned with web views.
- `quotation_document.py`: JSON document packing, terms, tracking and presentation rows.
- `quotation_exports.py`: Helvetica quotation PDF/Excel output, page breaks, heading merges and signature/stamp assets.
- `quotation_email.py`: validated client recipient, SMTP delivery and PDF attachment.
- `quotation_activity.py`: discussion events and notification fan-out.
- `tests.py`: regression coverage; extend tests whenever a workflow permission or status changes.

Use existing helpers rather than duplicating status/permission logic. All user input must be validated, and email failures must leave the quotation in its previous state.
