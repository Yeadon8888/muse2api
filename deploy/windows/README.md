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

## Import an account from the Guanyi fingerprint window

The Guanyi account browser remains the login, proxy, and fingerprint-profile entry
point. `muse2api` owns account routing, task execution, and media delivery. The
import script opens the selected persisted profile, waits for a complete Muse
session, reads HttpOnly cookies through its local CDP endpoint, and uploads them to
the local account pool without printing cookie values or placing the API key on the
process command line.

```powershell
& .\deploy\windows\import-guanyi-account.ps1 `
  -AccountId 0123456789abcdef0123456789abcdef `
  -Label Muse2
```

If the profile is signed out, finish the normal Muse login in the opened window.
Run the same command again after login if the waiting period has already expired.

The public base URL is `https://muse2api-mature-relay.yeadon8888.workers.dev`.

This installation keeps `MUSE2API_ALLOW_UPSTREAM_MUTATION=0`. Update checks remain
available, but the admin page cannot overwrite the maintained branch or push to the
upstream repository. Review and merge upstream changes through Git instead.
