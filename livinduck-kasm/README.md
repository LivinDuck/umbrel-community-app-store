# Kasm Workspaces 1.19.0 (package 1.19.0-1)

This package uses LinuxServer.io's `1.19.0-ls150` image, pinned by its public
AMD64/ARM64 index digest. It runs a nested Docker engine in privileged mode.
Privileged mode grants broad host capabilities; install only if you trust Kasm
and its container image. It does not mount Umbrel's Docker socket. The nginx
sidecar bridges the HTTPS setup wizard to Umbrel's authenticated app proxy.

## First run

1. Open **Kasm Workspaces** from Umbrel. The launch page is on port **39401**.
2. Select **Setup & updates**, review the upstream EULA, and choose strong
   passwords for `admin@kasm.local` and `user@kasm.local`.
3. Select only the workspace images you need. Downloads need internet access
   and may consume many gigabytes. Wait for the wizard to finish.
4. When setup completes, it returns to the launch page. Wait for **Kasm is ready**,
   then select **Open Kasm**. It uses your browser's
   current hostname with **HTTPS port 39402**. Expect a self-signed certificate
   warning on first access; proceed only for your own trusted server.
5. Sign in using the administrator password you chose. Use `user@kasm.local`
   for ordinary workspace sessions.

The minimum upstream baseline is 2 CPU cores, 4 GB RAM and 50 GB free disk;
allow more for active sessions and images. ARM64 has a different workspace
selection from AMD64. Host support for privileged nested Docker and its storage
driver is required. Actual Umbrel hardware compatibility is not yet verified.
GPU/gamepad passthrough is not configured.

The wizard and launch page require Umbrel login, with no authentication
whitelist. Port 3000 is not published to the host. Kasm's HTTPS port 39402 uses
Kasm's own authentication and bypasses Umbrel login by design: the native HTTPS
endpoint preserves secure cookies and the matching session port required by
upstream. Use a trusted LAN. Tor or other Umbrel remote access does not
implicitly expose port 39402; public reverse-proxy deployment needs separate
TLS, routing and Kasm zone configuration. Other containers on Umbrel's shared
Docker network can reach the wizard directly; this is not an isolation boundary
against a compromised neighboring app.

## Startup status

The launch page polls Kasm's actual HTTPS API health endpoint every five seconds
until it is ready. A running setup wizard does not mean Kasm itself is ready.
Initial startup can continue for several minutes after installation work.
Keep an active installer open; do not start concurrent installation attempts.
If the installer reports an error, retain its terminal output for diagnosis.

This package revision changes the completion redirect and readiness display;
it does not change the upstream image or automatically repair failed network
plugins. An observed initial network-plugin error on the user's ARM64 host was
followed by a healthy installation without any intervention from this package.

## Data and recovery

- `data/opt` holds the nested Docker images/volumes, Kasm database, installation,
  certificates and configuration.
- `data/profiles` is available inside Kasm as `/profiles`. Sessions are disposable
  by default. To preserve user files, configure each workspace's persistent
  profile path, for example `/profiles/ubuntu/{username}`, following the
  [upstream profile instructions](https://docs.kasm.com/docs/latest/guide/persistent_data/persistent_profiles).
- Stop the entire Umbrel app before taking a consistent backup of **both**
  directories. Preserve numeric ownership and permissions. Backups can be large
  because the nested Docker state is included. Restore with the app stopped.
- Avoid changing the backing filesystem or moving the nested Docker store
  between incompatible architectures/storage drivers.

## Updates

Updating the outer image does **not** upgrade an already installed Kasm system.
Back up first, update the Umbrel package, then open **Setup & updates** and run
the upstream upgrade. Update workspace image tags as directed by upstream.
The inner installer downloads additional service/workspace images at setup;
those upstream-managed images are not frozen by the outer image digest.
An outer-image downgrade is not a database rollback; recover the matching
backup if an upgrade must be undone.

Keep the wizard enabled for browser-managed upgrades. If you choose its disable
option, **Open Kasm** still works. To re-enable the wizard, an administrator must
stop the app, remove only `data/opt/NO_WIZARD` from this app's installed data,
then start it again. Do not delete the rest of `data/opt`.

## Licensing and sources

Kasm Workspaces is subject to its own EULA, presented during setup. Its Community
edition has usage/session restrictions; review the current
[Kasm licensing terms](https://kasm.com/docs/latest/license.html).
LinuxServer's container packaging is GPL-3.0; this store's original icon and
integration files are MIT licensed. This is an independent community package.

- [Container documentation](https://docs.linuxserver.io/images/docker-kasm/)
- [Container source and releases](https://github.com/linuxserver/docker-kasm)
- [Kasm system requirements](https://docs.kasm.com/docs/develop/explanations/system-requirements)

## Verification scope

The store's pinned Umbrel linter checks both public multi-architecture image
pins, manifest, ports and Compose wiring. CI runs disposable AMD64 and ARM64
containers to verify the launch page, HTTPS wizard bridge, Socket.IO onboarding
metadata, nested Docker startup, writable state, certificate and Docker-volume
persistence after recreation, and launch-page access when the wizard is disabled.

These checks do not accept the EULA, create Kasm accounts, download desktop
workspaces or prove a full Kasm installation. Umbrel app-proxy authentication,
full installation/update automation and browser desktop streaming remain untested.
Read-only inspection of the user's ARM64 Umbrel confirmed that the existing
installation eventually served its login page and returned a healthy API response;
no repair or restart was performed on that host. See the workflow for actual CI results.
