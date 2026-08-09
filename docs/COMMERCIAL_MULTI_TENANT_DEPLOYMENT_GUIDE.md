# Commercial Multi-Client Deployment and Tenancy Guide

## Executive decision

The current WMS is a single-firm application. Its projects, staff, clients, enquiries, files, counters and notifications have no tenant/company key. Pointing several unrelated firms at one database would create an unacceptable cross-client data-isolation risk.

The recommended commercial starting model is **silo per client from one codebase**:

```text
Shared product engineering, CI/CD and release artifact
                         |
        +----------------+----------------+
        |                |                |
 Client A stack     Client B stack    Client C stack
 app + database     app + database    app + database
 media + secrets    media + secrets   media + secrets
 backup + domain    backup + domain   backup + domain
```

Do not create customer-specific Git branches. Every client runs the same versioned product artifact with environment-based branding, features, plan limits and integration settings.

This is the fastest safe route to market because it works with the present schema and limits a fault, restore or data exposure to one customer. It costs more operationally than a shared database, so automate provisioning from the beginning. AWS describes silo, pool and bridge as distinct SaaS isolation models; the silo model deliberately provides dedicated resources while retaining shared onboarding and operations: [AWS SaaS Lens](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/silo-pool-and-bridge-models.html).

## Recommended commercial topology

For the first 5–20 customers:

- One subdomain per firm, such as `firm-a.product.example`.
- One application service/container per firm.
- One PostgreSQL database and database role per firm. A dedicated managed database instance is optional for premium/compliance customers; database-per-client on a managed cluster is acceptable for standard plans.
- One media bucket or cryptographically isolated bucket prefix per firm, with separate access policy.
- Separate application secret, database credential, backup destination and encryption key per firm.
- Shared container registry, CI/CD pipeline, monitoring platform and tenant provisioning control plane.
- Per-client logs/metrics labels, quotas, release channel, data region and backup policy.

Never rely on hostname alone for isolation. Infrastructure credentials and storage policies must make cross-client access impossible even if application code contains a bug.

## Tenant registry/control plane

Build a small control plane separate from customer business data. It stores only operational metadata:

- tenant ID, legal/display name and status;
- primary domain and allowed domains;
- plan, enabled features and limits;
- deployment/database/media resource identifiers—not raw secrets;
- region/data-residency selection;
- application/schema version and release channel;
- backup status, support tier and billing customer reference;
- provisioning/suspension/deletion audit history.

The control plane triggers infrastructure-as-code to provision a tenant stack, inject secrets, apply Flyway-team schema releases, create the first tenant administrator, run smoke tests and register monitoring. It must not become a shortcut for support staff to read customer project data.

## Customer lifecycle

### Provision

1. Approve contract, data region, retention, SLA, user limits and integrations.
2. Allocate an immutable tenant ID; names/domains may change but this ID does not.
3. Provision database, role, media storage, encryption keys, DNS/TLS, backup policy and application service.
4. Deploy the approved artifact and let the Flyway team apply the recorded schema release.
5. Create the first administrator through a one-time secure invitation; never email a permanent password.
6. Run automated isolation, login, workflow, upload/download, CAD and backup smoke tests.
7. Record customer acceptance and enable production access.

### Operate

- Meter users, storage, projects and expensive processing by tenant.
- Enforce plan limits server-side.
- Deploy in rings: internal, pilot tenants, then general availability.
- Keep the API backward-compatible with supported mobile versions.
- Provide tenant-scoped audit logs, status communication and support access approval.

### Suspend/export/delete

- Suspension blocks login/writes but preserves data under the contract.
- Export produces a documented database/business-data export plus original files and checksums.
- Deletion uses a two-person approval, legal-hold check, delayed/recoverable phase, storage/database deletion and signed evidence. Backups expire according to the contract rather than being silently edited.

## Backup and disaster recovery per client

Run `manage.py backup_wms` inside each client stack with a tenant-specific `WMS_BACKUP_ROOT` or object-store destination. Never place multiple tenants into a shared writable backup prefix using the same credentials.

Every backup manifest, metric and alert must carry the immutable tenant ID. Restore one customer into an isolated recovery stack; do not restore an entire shared database to solve a single-client incident. Premium plans may add a dedicated PostgreSQL instance, shorter RPO, cross-region replica and faster restore SLA.

Recommended tiers:

| Tier | Isolation | Backup target | Example service objective |
|---|---|---|---|
| Standard | Dedicated database/media; shared managed cluster/runtime | Daily + provider PITR | RPO up to 24h, RTO 4–8h |
| Business | Dedicated database, stronger compute limits | PITR + daily immutable copy | RPO 1h, RTO 2–4h |
| Regulated/Enterprise | Dedicated full stack/account/region where required | Customer-specific PITR/replication | Contract-specific |

Objectives must be measured through restore drills, not promised from backup-job success alone. PostgreSQL documents WAL-based continuous archiving and point-in-time recovery here: [PostgreSQL PITR](https://www.postgresql.org/docs/17/continuous-archiving.html).

## Product changes required before pooled multi-tenancy

Do not switch to a shared database merely to reduce hosting cost. A pooled version requires a deliberate product program:

1. Add a `Tenant`/`Organization` aggregate with immutable ID, status, locale, timezone, currency and plan.
2. Add a non-null tenant foreign key to every tenant-owned record, including staff/login relationships, projects, materials, enquiries, quotations, comments, notifications, counters and documents.
3. Change every uniqueness rule to include tenant where appropriate—for example `(tenant, username)`, `(tenant, project_no)` and tenant-scoped quotation counters.
4. Resolve tenant from authenticated identity, not an editable request parameter or untrusted hostname.
5. Enforce tenant filtering in a single repository/manager/service layer and background jobs; prevent unrestricted model access in business code.
6. Put tenant identity in signed mobile tokens, storage paths, cache keys, task payloads, audit events and metrics.
7. Add PostgreSQL row-level security as defense in depth where feasible; application checks remain mandatory.
8. Test negative cross-tenant access for every endpoint, file route, export, search, notification and asynchronous job.
9. Build tenant-aware data export/deletion, support impersonation approval and audit logging.
10. Rehearse conversion from silo databases and define a reversible cutover.

AWS notes that pooled storage co-mingles tenant data and requires explicit isolation controls; pooled failures also increase blast radius: [pooled isolation considerations](https://docs.aws.amazon.com/whitepapers/latest/saas-tenant-isolation-strategies/pool-isolation.html).

## Recommended long-term bridge model

When automation and customer count justify it, evolve to a bridge model:

- shared edge, identity/onboarding, billing, release and observability services;
- pooled application compute for standard tenants only after tenant-aware code is proven;
- database-per-tenant or schema-per-tenant for business data;
- dedicated full-stack option for regulated/premium customers;
- common API/product behavior across every tier.

This retains strong data isolation while improving operational efficiency. A fully pooled database should be the last optimization, not the first commercial architecture.

## Configuration and customization policy

Replace hard-coded firm identity with configuration/data, not customer forks:

- company name, logo, colours within an approved theme system;
- address, currency, timezone, tax/quotation numbering and default terms;
- enabled modules/roles/workflows;
- email/SMS/push sender and templates;
- storage/retention limits and integrations.

Configuration changes require validation, audit history and safe defaults. Core permission rules cannot be weakened by branding or feature flags.

## Commercial readiness beyond deployment

Before marketing broadly, complete:

- legal terms, privacy notice, data-processing agreement and subprocessor list;
- security vulnerability process, dependency/patch policy and incident notification procedure;
- customer onboarding, administrator guide, support runbooks and status page;
- audit events for authentication, permissions, approvals, exports and destructive actions;
- configurable email/push delivery and verified sender domains;
- accessibility, localization, currency/tax and timezone review for target markets;
- usage metering, plan enforcement, billing reconciliation and grace-period behavior;
- public API/version policy and supported mobile release matrix;
- penetration test and tenant-isolation test before any pooled architecture;
- SLA wording grounded in measured availability and restore results.

## Phased roadmap

| Phase | Goal | Exit criterion |
|---|---|---|
| 0 | Stabilize current firm | UAT, security review and restore drill pass |
| 1 | Productize configuration | No firm-specific code branches; branding/terms configurable |
| 2 | Silo pilot customers | Automated isolated provisioning and per-tenant monitoring/backups |
| 3 | Commercial operations | Billing, support, audit, onboarding/offboarding and release rings work |
| 4 | Bridge architecture | Shared control plane with proven database/media isolation |
| 5 | Optional pooling | Tenant-aware schema, enforcement and cross-tenant security testing pass |

The immediate recommendation is to complete Phase 0, then sell controlled pilots using Phase 2 isolation. Do not promise a shared SaaS platform until the tenant-aware work and operational controls have been verified.

