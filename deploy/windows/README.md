# Windows deployment

This deployment keeps the upstream `muse2api` application local and publishes it through a dedicated Cloudflare Worker.

## Runtime layout

- `start-local.ps1` starts an authenticated SOCKS5-to-HTTP bridge, FastAPI, and Edge CDP on dedicated ports.
- Muse1 proxy credentials are read from the Guanyi desktop account store and decrypted with the current Windows user. They are never written in plaintext.
- `.env` supplies `MUSE2API_KEY` and `MUSE2API_PUBLIC_BASE`; it is ignored by Git.
- `start-cloud.ps1` creates a Cloudflare Tunnel, updates the relay origin, and deploys `muse2api-mature-relay`.
- `stop-local.ps1` stops only the recorded deployment processes and the reserved CDP browser on port 19220.

Run local first, then cloud:

```powershell
& .\deploy\windows\start-local.ps1
& .\deploy\windows\start-cloud.ps1
```

The public base URL is `https://muse2api-mature-relay.yeadon8888.workers.dev`.
