# Work Management System (WMS)

Django application for project planning, site execution, purchasing, accounting, marketing enquiries, estimation, quotation approval, and document control.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

## Configuration

The application supports these environment variables:

- `WMS_SECRET_KEY`: required for production.
- `WMS_DEBUG`: `true` for local development; set to `false` in production.
- `WMS_ALLOWED_HOSTS`: comma-separated host names.

Uploaded files are stored below `media/`. Enquiry files are restricted to Excel, image, PDF, CAD, and Word formats with a 20 MB per-file limit.

## Local CAD viewer

Enquiry attachments and collected project documents in `.dwg` or `.dxf` format
have a secured **View CAD** action. The read-only viewer provides pan, zoom,
fit-to-screen, layer visibility, background control, measurements, and original
file download. Parsing and rendering happen locally in the browser; drawings are
not sent to Autodesk or another external service.

The production viewer assets are committed below `static/cad_viewer/`. Rebuild
them after changing `cad_frontend/`:

```powershell
cd cad_frontend
npm.cmd install
npm.cmd run build
```

Node.js 24 or newer is required only to rebuild these assets, not to run Django.
See `cad_frontend/THIRD_PARTY_NOTICES.md` for open-source licenses and source links.

## Enquiry workflow

1. Marketing Executive creates an enquiry and collects client documents.
2. Marketing Manager or Project Manager assigns an Estimator.
3. Estimator adds quotation and costing.
4. Marketing Manager gives the first quotation approval.
5. Accountant gives the second quotation approval.
6. Project Manager approves costing.
7. Document Controller verifies documents and submits the quotation.
8. Marketing Executive records client acceptance.
9. Admin creates the project and transfers the awarded enquiry and documents.

## Project planning lists

Project Managers can add multiple scope-of-work, schedule, catalog-material, and project-material rows in one submission. The scope and project-material forms can fetch all existing rows from another project, place them into the editable list, and save them to the target project after review.

## Verification

```powershell
python manage.py makemigrations --check --dry-run
python manage.py check
python manage.py test MyApp
```

For production, set the environment variables above and run `python manage.py check --deploy` as part of deployment validation.

## Mobile application and system documentation

The cross-platform client is in [`mobile/`](mobile/README.md). It uses Expo React Native and TypeScript, connects to the versioned `/WMS/api/v1/` API, stores its bearer token in the device secure store, and changes navigation and actions according to the signed-in user's WMS role.

Product, architecture, API, deployment, mobile, and security documentation starts at [`docs/README.md`](docs/README.md).
