# WMS code-quality and logic audit

Audit date: 2026-07-18

## Scope and verification

The Django project, models, URL configuration, legacy role dashboards, workflow module,
templates, migrations, settings, and tests were reviewed. Verification completed with:

- `manage.py check`
- `manage.py makemigrations --check --dry-run`
- `manage.py test` (12 passing tests)
- `manage.py check --deploy` with production-like environment settings
- Python compilation/AST checks for syntax, duplicate functions, duplicate URL names/routes,
  and invalid `.get().update()` calls
- Ruff correctness checks (`E9`, `F63`, `F7`, `F82`, and `F841`)

All of the checks above pass. No unapplied model changes were detected.

## Corrected in this audit

- Added session authentication enforcement for every non-public `/WMS/` route.
- Added role enforcement to the new Project Manager bulk planning endpoints.
- Removed the hard-coded administrator chat login, which could violate the chat foreign key.
- Restricted non-admin chat deletion to messages owned by the current user.
- Replaced chat N+1 staff lookups with a fixed two-query response.
- Fixed material-request editing, which attempted to update a nonexistent `unit` field and
  fetched materials using the request ID instead of the project ID.
- Scoped reused estimate numbers to their project to prevent cross-project data selection.
- Fixed project completion (`Model.get().update()` was invalid ORM usage).
- Made missing work-progress records initialize safely and scoped them to the project.
- Fixed notification totals that could reset to zero when a later project had no notices.
- Fixed uploaded-file URLs to use the actual name returned by storage after collision handling.
- Made quotation approvals/submission/award concurrency-safe and required costing approval
  before client submission.
- Rejected `NaN` and infinite quotation/costing amounts.
- Scoped workflow dashboard totals to the enquiries visible to the signed-in user.
- Removed debug `print()` calls, wildcard model imports, unused imports, and unused local
  assignments detected by Ruff.
- Added production-safe secret/host validation and secure cookie/HSTS/HTTPS environment options.
- Added regression coverage for the corrected workflows and defects.

## Remaining modernization work

These are structural legacy risks rather than safe one-line corrections. They should be handled
as focused follow-up changes with UI regression testing:

1. **Mutation through GET requests (high priority).** Forty legacy delete/approve/reject/status
   routes still change data through links. They should become CSRF-protected POST forms. Changing
   the views alone would break the current templates, so routes and all calling templates must be
   migrated together.
2. **Complete role authorization (high priority).** Authentication is now global, but much of the
   legacy URL set still relies on navigation visibility rather than a server-side role decorator.
   Split URLs by role namespace and apply role checks at the namespace/view layer.
3. **Monolithic legacy view module.** `MyApp/views.py` contains hundreds of functions. Split it into
   Admin, Project Manager, Supervisor, Accountant, Purchaser, and shared service modules before
   broad refactoring.
4. **Legacy schema types.** Dates, money, quantities, and phone values are often stored as strings
   or integers. Move them gradually to `DateField`, `DecimalField`, and string phone fields with
   data migrations and production-data validation.
5. **Naming consistency.** Model classes and many functions are lowercase or contain spelling
   mistakes. Renaming them requires compatibility migrations/import aliases and should not be
   combined with feature work.
6. **Test depth.** The 12 tests cover the new workflow and planning paths. Add permission and CRUD
   tests for every legacy role before decomposing the monolithic module.

The current changes deliberately avoid schema renames and sweeping template rewrites because those
would create disproportionate regression risk without complete legacy workflow coverage.
