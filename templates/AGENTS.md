# Template map

- `Workflow/base.html`: shared EXALTER shell, navigation, alerts and notification dropdown.
- `Workflow/dashboard.html`: enquiry history and quotation register; drafts are intentionally excluded from shared-role views.
- `Workflow/enquiry_detail.html`: estimator quotation editor, autosave and enquiry documents/discussion.
- `Workflow/quotation_view.html`: saved PDF preview, approvals, compose-and-send client email and client response actions.
- `Workflow/quotation_discussion.html`: threaded quotation messages and client-response badges.

Keep inline UI changes consistent with the existing Bootstrap/NiceAdmin colors and responsive table patterns. Use CSRF-protected POST forms for state changes and avoid browser alerts for recoverable validation errors.
