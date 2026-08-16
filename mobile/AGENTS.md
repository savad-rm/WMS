# Mobile client map

- `src/`: mobile screens, role workflows, API client and shared types.
- The mobile app talks to `MyApp/api/`; do not invent a second business workflow.
- Keep quotation status transitions, enquiry access rules, discussion notifications and client response semantics identical to the web application.
- API errors should be rendered as recoverable user messages, not blank screens.
