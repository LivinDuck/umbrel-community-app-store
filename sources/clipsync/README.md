# ClipSync Server

A single-household clipboard relay for ClipSync on Android and macOS. Devices pair once with expiring, single-use codes. HTTPS writes are persisted to SQLite and immediately delivered over authenticated WebSockets. Every reconnect receives the latest clipboard; no periodic clipboard polling, Google login, or Firebase is required for this backend.

## Umbrel setup

Install **ClipSync** from [LivinDuck’s community app store](https://github.com/LivinDuck/umbrel-community-app-store). Open its dashboard while signed in to Umbrel. Umbrel protects the dashboard; ClipSync does not ask for a second password. Existing settings, certificates, and paired devices are preserved when updating. There are no device accounts.

1. Point a DNS-only hostname at your public IP using your existing DDNS. Enter `https://home.example.com:39443` in **Public server address**. No changes to existing A/AAAA/CNAME records are made by ClipSync.
2. For automatic certificates, create a Cloudflare **API token** with **Zone → DNS → Edit** and **Zone → Zone → Read**, restricted to that DNS zone. Paste it into the dashboard and save. Use an API token, not a global API key or an Origin CA certificate.
3. Forward TCP **39443** on your router to TCP **39443** on the Umbrel machine. Do not forward the dashboard port (39440). Existing HTTP/HTTPS services on ports 80, 443, or other ports are unaffected. Caddy uses only DNS-01 validation and binds internal port 8443; it creates temporary `_acme-challenge` TXT records and does not redirect HTTP.
4. Allow certificate issuance to finish. Open `https://home.example.com:39443/health`; a trusted HTTPS connection and a small ClipSync JSON response confirm the endpoint is reachable. Check both your home connection and mobile data. If your router lacks NAT loopback, configure split DNS locally for the same hostname.
5. Create one pairing code per device. Choose **Your server** in each app, enter the full HTTPS address including its port, then the code. Codes expire after five minutes and can only be used once.

Cloudflare’s ordinary proxy does not support arbitrary ports such as 39443: keep this hostname DNS-only. A Cloudflare Origin CA certificate is not normally trusted by direct native clients; the bundled helper obtains a publicly trusted certificate instead. ClipSync never takes over your domain or existing router forwards. The token remains on your server and is used for certificate renewals.

Devices keep their own credentials (Keychain on Mac, Android Keystore encryption on Android). You can remove any device in the dashboard, immediately closing its live connections. Pair it again to restore access. Switching app backends preserves the saved server pairing and local history; **Disconnect** removes that device’s local credential. To revoke a lost device, remove it in the dashboard as well.

## Existing reverse proxy

If you already terminate trusted HTTPS, you can omit the Cloudflare token and proxy the private **3001** sync port, including WebSocket upgrades at `/v1/events`. Do not proxy port 3000 publicly. The Umbrel package intentionally exposes only its dedicated TLS port, so an external proxy needs explicitly configured access to the private API network; it does not silently open another unencrypted WAN port. Save the full public HTTPS origin in the dashboard. Removing the Cloudflare token disables the built-in TLS listener.

## Standalone Docker

Run `docker compose -f compose.yml up --build -d` from this directory. Open `http://localhost:39440` and choose the settings password on first run. The dashboard binds loopback only; access a remote Docker host through an SSH port forward or another authenticated management route. Server state and certificates use named volumes. The app is not dependent on Umbrel internals.

Runtime settings: `HOST` (default `0.0.0.0`), `PORT` (dashboard, default 3000), `API_PORT` (default 3001), `DATA_DIR` (default `./data`), `ADMIN_PASSWORD` (optional standalone settings password, at least 12 characters), `ADMIN_AUTH` (`password` by default; the Umbrel package sets `umbrel` because its private dashboard is protected by app_proxy—never enable this mode for an exposed dashboard), `CADDY_ADMIN_URL` (private helper endpoint), `SYNC_UPSTREAM` (internal API hostname:port). User-facing connection settings are edited in the dashboard without restarts.

## Behavior and limitations

- One shared clipboard per server, with up to 100 paired devices. This is a personal relay, not a multi-tenant account service.
- Text up to 32,768 characters and images up to 30,000,000 bytes. Use the updated native clients for 30 MB images. Firebase retains its separate 1.5 MB image limit.
- Only the latest clipboard is retained remotely. History stays in the apps. ClipSync uses TLS in transit; server storage is not end-to-end encrypted. Back up the app data directory and protect those backups, including DNS credentials and the latest clipboard.
- The Mac keeps its existing automatic-copy monitor; Android keeps its foreground receiving service and its app/Quick Settings sending actions. This does not bypass Android’s background clipboard restrictions or operating-system suspension.
- WebSockets use heartbeat frames, automatic reconnection, and a fresh current-item snapshot on connection. Heartbeats check connection liveness; they do not poll the clipboard. Delivery requires an active Internet connection. This release does not add an offline upload queue.
- Pairing codes and dashboard sessions are ephemeral; generate a new code or unlock again after a server restart. Device credentials, connection settings, clipboard state, and certificates persist.
- Mainland China reachability depends on the route to your home connection; the self-hosted sync path has no Google dependency, but connectivity still needs to be tested from the actual networks you use.

## Development and publication

Use Node.js 24+: `npm ci && npm test && npm start`. Tests exercise actual HTTP/WebSocket pairing, push, image limits, persistence, revocation, and endpoint isolation. Runtime image builds target `linux/amd64` and `linux/arm64`.

The local `server/` directory is mirrored into `sources/clipsync/` in the community app-store repository. Its **Build ClipSync images** workflow runs tests and publishes version/commit-tagged `ghcr.io/livinduck/clipsync-server` and `ghcr.io/livinduck/clipsync-tls`. The Umbrel package pins their immutable multi-architecture digests. No credentials or personal hostnames belong in either repository.
