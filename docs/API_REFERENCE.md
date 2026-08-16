# Mobile API Reference

## Conventions

- Base path: `/WMS/api/v1/`
- JSON except multipart uploads.
- Header: `Authorization: Bearer <token>`.
- Collections: `{ "results": [...] }`.
- Dates use ISO format where supported. Legacy money/quantity values remain strings.

Error envelope:

```json
{"error":{"code":"validation_error","message":"Request failed.","fields":{"field":["Explanation"]}}}
```

## Authentication and account

| Method | Path | Purpose | Access |
|---|---|---|---|
| POST | `auth/login/` | Email/password exchange for token/profile | Public, 10/minute throttle |
| POST | `auth/logout/` | Revoke issued account tokens | Authenticated |
| GET | `me/` | Current account/staff profile | Authenticated |
| PATCH | `me/` | Change password using `current_password`, `new_password` | Authenticated |

Login payload: `{"username":"firstname.lastname","password":"secret"}`. The legacy `email` request key remains accepted for already-released mobile clients, but it contains the account login identifier rather than necessarily being an email address.

## Dashboard and projects

| Method | Path | Purpose |
|---|---|---|
| GET | `dashboard/` | Role metrics and recent projects |
| GET | `projects/?q=&status=` | Search accessible projects |
| GET | `projects/{id}/` | Overview, scope, schedules, progress, materials, team, capabilities |
| GET/POST | `projects/{id}/chat/` | Read/send project messages |
| POST | `projects/{id}/site-updates/` | Supervisor operational record |
| GET | `materials/` | Material catalogue |
| POST | `material-requests/{id}/approve/` | Approve request |
| POST | `material-requests/{id}/reject/` | Reject request |

Site-update payloads:

| `type` | Required fields |
|---|---|
| `progress` | `work_id`, `status`, `progress`, optional `date` |
| `material_request` | `material_id`, `quantity`, optional `date` |
| `material_usage` | `material_id`, `quantity`, optional `date` |
| `workers` | `work_type`, `worker_count`, optional `date` |
| `photo` | multipart image `photo`, optional `date` |

## Notifications

| Method | Path | Purpose |
|---|---|---|
| GET | `notifications/` | Current employee notifications |
| POST | `notifications/{id}/read/` | Mark an owned notification read |

## Enquiry workflow

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `enquiries/` | Role list / Marketing enquiry creation |
| GET | `enquiries/{id}/` | Detail, files, comments, quotation versions, permitted actions |
| POST | `enquiries/{id}/comments/` | Add comment or remark |
| POST | `enquiries/{id}/actions/{action}/` | Execute workflow transition |

| Action | Role | Payload/precondition |
|---|---|---|
| `assign` | Marketing Manager, Project Manager | `estimator_id` |
| `quote` | Assigned Estimator | Save a private draft using `amount`, `details`, three costing amounts, optional notes |
| `submit_for_approval` | Draft owner Estimator | Lock the draft, make it visible to other workflow roles, and start Marketing Manager review |
| `manager_approve` | Marketing Manager | Manager-review quotation |
| `accountant_approve` | Accountant | Accountant-review quotation |
| `costing_approve` | Project Manager | Quotation has costing |
| `request_revision` | Marketing Manager at `manager_review`; Accountant at `accountant_review` | `{"remarks":"..."}` (required, max 2,000 chars); returns the quotation to draft and notifies the estimator |
| `submit` | Document Controller, Marketing Executive, Marketing Manager | Quotation status `approved`; server emails the generated PDF to the client and sets client status to `under_review` |
| `client_response` | Admin, Marketing Executive, Marketing Manager | `{"client_status":"under_review\|under_revision\|approved\|rejected", "client_remarks":"..."}`; Manager/Admin may set `under_revision`, which notifies the estimator |
| `award` | Marketing Executive, Marketing Manager | Submitted quotation; sets client status to `approved` and finalises the enquiry |

Detailed enquiry responses keep every quotation revision in `quotations`. Each quotation includes the existing identity, amount, status, details, and creation fields plus:

| Field | Type | Meaning |
|---|---|---|
| `submitted_at` | ISO datetime or `null` | First recorded client-submittal time |
| `client_status` | string | `under_review`, `approved`, or `rejected` |
| `client_remarks` | string | Client feedback maintained by authorised web users |

### Client-submittal lifecycle

`Draft` quotations are private to their estimator and are not returned to other roles. After `submit_for_approval`, the quotation proceeds through `manager_review` and `accountant_review` to `approved`. The `submit` action sends the PDF using configured SMTP; if the recipient or mail server is invalid, the API returns a validation error and leaves the quotation approved/not submitted. A successful send records `submitted_at` and `under_review`. Marketing Executive or Marketing Manager can then use `award`; this records `approved`, publishes a discussion message/notifications, and removes revision/status actions. The web client provides CC, subject, and body fields; the mobile action uses server-configured defaults.

## Responses

- `200` successful read/update
- `201` created
- `204` logout
- `400` invalid data or state
- `401` missing/invalid/expired/revoked token
- `403` role or allocation denied
- `404` missing or inaccessible record
- `429` login throttled
