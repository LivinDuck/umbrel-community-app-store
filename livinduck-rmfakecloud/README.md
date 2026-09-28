# rmfakecloud on Umbrel

Upstream: https://github.com/ddvk/rmfakecloud (AGPL-3.0).
Uses the unmodified public `ddvk/rmfakecloud:0.0.31` image, pinned to the
multi-architecture digest in `docker-compose.yml`. Supports ARM64 and AMD64.

## After you choose to install

1. Open the app from Umbrel. Its browser address uses port **39400**.
2. Enter your chosen email and a strong password. With an empty data directory,
   the first login creates the administrator. There are no default credentials.
3. Back up the reMarkable before changing its cloud connection.
4. Follow [upstream device setup](https://ddvk.github.io/rmfakecloud/remarkable/setup/)
   to install/configure **rmfakecloud-proxy on the tablet**. Set its upstream
   server to `http://<your-Umbrel-LAN-IP>:39400` for a trusted LAN.
   This is the proxy's upstream address, not the server's `STORAGE_URL` setting.
5. Keep server `STORAGE_URL` unset. Its default `https://local.appspot.com` is
   intercepted by the tablet proxy; firmware 3.15+ rejects storage addresses
   with an explicit port. Prefer this package-specific instruction where older
   upstream setup examples suggest setting STORAGE_URL to the LAN address.
6. In the web interface select **Code → Generate Code**, then pair the tablet
   with that code. Verify synchronization with a disposable document first.

The NAS package cannot configure the tablet for you. Tablet updates can require
re-enabling its proxy. Desktop/mobile clients also require upstream-specific
configuration. This package does not configure external access or HTTPS;
HTTP to the server is intended only for a trusted LAN. For remote access, use
an appropriately configured VPN or HTTPS setup following upstream guidance.

## Authentication and persistence

- Umbrel login protects the browser interface, including initial account creation.
- Only the listed tablet protocol paths bypass Umbrel cookies. Pairing codes,
  bearer tokens and signed file URLs are checked by rmfakecloud; discovery,
  health and telemetry paths are public protocol endpoints.
- `/ui/api/*` is **not** exempted from Umbrel login.
- `${APP_SEED}` supplies a stable per-install JWT secret so restarts do not
  invalidate device tokens. Never publish its actual value.
- Account and document data live at `${APP_DATA_DIR}/data/cloud`, mounted at `/data`.
- The service runs as UID/GID 1000 and requests no host devices, Docker socket,
  privileged mode, or shared NAS folders.
- Back up app data before updates. A rollback after a data-format migration
  may require restoring the matching backup. Do not edit/delete cloud files
  behind the app: upstream warns that deletions can propagate to the tablet.

## Scope and verification

CI checks the manifest and images, then tests browser HTML, first account
creation, login, a persistent folder, pairing/token exchange, unauthorized sync
rejection, and data/token survival after container recreation. It runs the
upstream image with the package's user, environment and storage settings.

These tests do not install Umbrel or exercise its real app proxy. Actual Umbrel
installation, browser interaction through Umbrel, and physical tablet sync are
not yet verified. Port 39400 must remain free when you install.

SMTP and handwriting recognition need optional external credentials and are
not configured. Legacy MQTT screen sharing needs certificates and extra
networking and is not exposed by this package. REST screen sharing from newer
firmware is routed, but has not been tested. Upstream reports sync support
through tablet software 3.27.1; later firmware may need a newer release.

## Updating

Review upstream release notes; update the version and multi-architecture digest,
run CI, and record relevant migration notes in `releaseNotes`. Preserve the app
ID, JWT seed wiring and data mount. Never replace the digest just because a tag
was rebuilt without reviewing the change.
