# Template map

- `Workflow/base.html`: shared EXALTER shell, navigation, alerts and notification dropdown.
- `Workflow/dashboard.html`: enquiry history and quotation register; drafts are intentionally excluded from shared-role views.
- `Workflow/enquiry_detail.html`: estimator quotation editor, autosave and enquiry documents/discussion.
- `Workflow/quotation_view.html`: saved PDF preview, approvals, compose-and-send client email and client response actions.
- `Workflow/quotation_discussion.html`: threaded quotation messages and client-response badges.

Keep inline UI changes consistent with the existing Bootstrap/NiceAdmin colors and responsive table patterns. Use CSRF-protected POST forms for state changes and avoid browser alerts for recoverable validation errors.

## List and dashboard conventions

- Every list must expose one primary search/filter surface. Use server-side filter forms for workflow registers; do not also initialise a client-side table search there.
- Client-side table enhancement is opt-in only: add `data-wms-table="client"` only when the page has no server-side search/filter form.
- Dashboard metric cards must be keyboard-accessible links to a filtered register view. Keep their filter key in the view, test it, and preserve the existing EXALTER card styling.
