# Product and Workflow Guide

## What WMS is

WMS is a construction and fit-out work management system. It joins pre-sales enquiries, quotation and costing approval, project setup, planning, site execution, material control, accounting, documents, and project communication in one role-controlled application.

The web application is the complete administrative interface. WMS Mobile is the focused operational client for employees who need project information, approvals, communication, and site reporting away from a desk.

## Roles

| Role | Primary responsibilities |
|---|---|
| Admin | Staff/project administration, allocations, reporting, project creation, document transfer |
| Marketing Executive | Create enquiries, attach files, comment, collect documents, record client acceptance |
| Marketing Manager | Review enquiries, assign estimators, first quotation approval |
| Estimator | Assigned enquiries, quotation versions, costing |
| Project Manager | Allocated projects, scope/materials/schedules, costing and material-request approval |
| Accountant | Final quotation approval, project payments, accounting |
| Document Controller | Verify project documents and release approved quotations |
| Supervisor | Site progress, workers, usage, requests, photos |
| Purchaser | Allocated projects, demand, deliveries, material issue status |

Project Managers, Supervisors, and Purchasers only see projects assigned through their allocation records. Authorization is enforced by the server.

## Enquiry-to-project workflow

```mermaid
flowchart LR
  E["Marketing creates enquiry"] --> A["Manager assigns estimator"]
  A --> Q["Estimator creates quotation and costing"]
  Q --> M["Marketing Manager approval"]
  M --> C["Accountant approval"]
  Q --> P["Project Manager costing approval"]
  C --> D{"Quotation and costing approved?"}
  P --> D
  D -->|Yes| S["Document Controller submits quotation"]
  S --> W["Marketing records acceptance"]
  W --> R["Admin creates project and transfers documents"]
```

Enquiry states are `open → assigned → quoted → approved → submitted → awarded`. `closed` is terminal for an enquiry that does not proceed. Quotations are versioned. Submission requires both quotation approvals and Project Manager costing approval.

## Project execution

1. Admin creates the project and allocates operational staff.
2. Project Manager defines scope, required materials, and schedules. Lists support bulk entry and copying from another project.
3. Supervisor reports workers, usage, progress, site photos, and requests.
4. Project Manager approves or rejects pending material requests.
5. Purchaser records deliveries and material issue progress.
6. The project team communicates through project chat.
7. Accounting records payments and transactions.
8. Operational and commercial closeout precedes completed status.

## Mobile navigation

- **Home:** role metrics and recent projects.
- **Projects:** allocated/searchable portfolio, planning and operational details.
- **Workflow:** enquiry, quotation, costing, and approvals for eligible roles.
- **Alerts:** employee notifications and read state.
- **Profile:** account, server connection, password, and sign-out.

## CAD

DWG and DXF attachments are rendered locally in the web CAD viewer after authorization. Mobile identifies CAD attachments and directs detailed drawing inspection to that full viewer.
