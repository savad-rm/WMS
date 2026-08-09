# WMS Documentation Centre

This documentation set is the operational source of truth for the WMS web, API, CAD-viewer, and mobile applications.

| Document | Audience | Purpose |
|---|---|---|
| [Product and workflow](PRODUCT_AND_WORKFLOW.md) | Operations, product owners, QA | Product scope, roles, states, and business flows |
| [Architecture](ARCHITECTURE.md) | Developers, architects | Components, boundaries, data flow, and design decisions |
| [API reference](API_REFERENCE.md) | Mobile/backend developers, QA | Authentication, endpoints, payloads, permissions, and errors |
| [Mobile guide](MOBILE_GUIDE.md) | Mobile developers, testers, users | Setup, configuration, navigation, and releases |
| [Deployment runbook](DEPLOYMENT_RUNBOOK.md) | DevOps, maintainers | Configuration, migration, rollout, verification, and rollback |
| [Current firm deployment](CURRENT_FIRM_DEPLOYMENT_GUIDE.md) | Owners, DevOps, release team | Production topology, configuration, release, backup and recovery |
| [Commercial multi-client deployment](COMMERCIAL_MULTI_TENANT_DEPLOYMENT_GUIDE.md) | Product, architecture, commercial and security teams | Safe client isolation, SaaS operations and tenancy roadmap |
| [Security and operations](SECURITY_AND_OPERATIONS.md) | Security, DevOps, support | Controls, secrets, monitoring, backup, and incident response |

## Repository layout

```text
WMS/
├── MyApp/                 Django models, web views, and API
│   └── api/               Versioned mobile REST API
├── WMS/                   Django configuration
├── templates/             Role-based web interface
├── cad_frontend/          Source for local 2D CAD viewing
├── static/cad_viewer/     Deployable CAD JavaScript/WebAssembly
├── mobile/                Expo React Native TypeScript client
└── docs/                  Product and engineering documentation
```

Product owners approve role/workflow changes. Backend owners update the API reference with contract changes. Mobile owners verify supported SDK versions. Release owners maintain the runbook. Security-sensitive changes require both permitted-access and denied-access tests.
