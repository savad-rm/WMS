# WMS Mobile Guide

## Supported client

WMS Mobile is a single Expo React Native/TypeScript codebase for Android and iOS. Android development and JavaScript bundling can run on Windows. A macOS or managed EAS build is required for final iOS App Store signing.

## Developer setup

Prerequisites: Node.js 24+, npm 11+, WMS backend, Android emulator or physical device.

```powershell
cd mobile
Copy-Item .env.example .env
npm.cmd install
npm.cmd run typecheck
npm.cmd start
```

Set `EXPO_PUBLIC_API_URL` according to the device:

- Android emulator: `http://10.0.2.2:8000/WMS/api/v1`
- iOS simulator: `http://127.0.0.1:8000/WMS/api/v1`
- Physical device: `http://<development-computer-LAN-IP>:8000/WMS/api/v1`
- Production: `https://wms.example.com/WMS/api/v1`

Run Django on the LAN only for controlled development: `python manage.py runserver 0.0.0.0:8000`. Production must use HTTPS and a production WSGI/ASGI server.

## Source layout

```text
mobile/
├── App.tsx                 Navigation root
├── src/api/client.ts       HTTP/error/token boundary
├── src/auth/               Session lifecycle
├── src/components/         Shared WMS UI primitives
├── src/hooks/              Data-loading behavior
├── src/screens/            Role-aware feature screens
├── src/theme.ts            Web-aligned design tokens
└── src/types.ts            API/navigation types
```

## User operation

1. Sign in with the same WMS username/password used on the web application.
2. Home reflects the signed-in role and accessible records.
3. Projects are filtered by allocation for site roles.
4. Supervisor uses **Add site update** for progress, material, and worker entries.
5. Project Manager reviews pending material requests in Project Detail.
6. Workflow roles use **Available actions**; the server returns only valid next actions, including revision requests during manager/accountant review.
7. Estimator quotation drafts are private. Other roles see the quotation only after **Submit for approval**. Client submission sends the server-generated PDF by email; a failed recipient/SMTP configuration is returned as an error without changing workflow state. Marketing Executive/Manager can award a submitted quotation, which creates discussion and notification activity.
8. Password change revokes the session and requires sign-in again.

## Quality gates

```powershell
npm.cmd run typecheck
npx.cmd expo config --type public
npx.cmd expo export --platform android
```

Test at minimum: invalid login, token expiry, offline retry, every role's tabs, denied unallocated project, site update, material approval, full enquiry approval, logout, password rotation, small phone, tablet, and dark system appearance.

## Releases

Use separate application identifiers and API URLs for development/staging/production. Increment `version`, Android `versionCode`, and iOS `buildNumber`. Commit `package-lock.json`. Create signed artifacts only from a tagged, tested commit. Record API version and backend migration in release notes.
