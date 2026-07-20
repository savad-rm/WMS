# WMS Mobile

Cross-platform Android/iOS operational client for the WMS Django application.

## Stack

- Expo SDK 57 / React Native / strict TypeScript
- React Navigation native stack and bottom tabs
- Expo SecureStore for bearer-token storage
- Versioned Django REST API at `/WMS/api/v1/`

## Start

```powershell
Copy-Item .env.example .env
# Edit EXPO_PUBLIC_API_URL for the emulator/device.
npm.cmd install
npm.cmd run typecheck
npm.cmd start
```

The default Android-emulator URL is `http://10.0.2.2:8000/WMS/api/v1`. A physical device must use the development computer's LAN address. Production must use HTTPS.

See [the complete mobile guide](../docs/MOBILE_GUIDE.md), [API reference](../docs/API_REFERENCE.md), and [deployment runbook](../docs/DEPLOYMENT_RUNBOOK.md).
