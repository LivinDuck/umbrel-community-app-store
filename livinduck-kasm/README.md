# Kasm Workspaces 1.19.0 (package 1.19.0-2)

Requires **umbrelOS 2.0 or later**. Open Kasm from the Umbrel dashboard: it uses
**HTTPS port 39401** for both initial setup and everyday use. There is no launcher
page and no separate host-published Kasm port. Umbrel terminates HTTPS and
protects all routes with Umbrel login; the internal gateway connects to Kasm
over HTTPS. Follow Umbrel's HTTPS certificate setup instructions if your browser
does not yet trust the device's certificate.

## First run

1. Open **Kasm Workspaces** from Umbrel. Before installation, it opens `/setup/`.
2. Review the Kasm EULA and choose strong passwords for `admin@kasm.local` and
   `user@kasm.local`. Select the workspace images you need.
3. Wait for installation to finish. Downloads and startup can take several
   minutes and many gigabytes. Keep the installer open; avoid concurrent installs.
4. On completion, the wizard opens Kasm directly on the same address. If its
   services are still starting, a temporary page retries automatically.
5. Sign in as `admin@kasm.local` with your chosen password. Use `user@kasm.local`
   for ordinary workspace sessions.

For subsequent visits the Umbrel icon opens Kasm directly. Keep the wizard
enabled if you want browser-managed updates at `/setup/` on the same address.

The upstream baseline is 2 CPU cores, 4 GB RAM and 50 GB free disk; allow more for
active sessions and workspace images. AMD64 and ARM64 have different available
workspaces. GPU and gamepad passthrough are not configured.

## Permissions and networking

LinuxServer.io's `1.19.0-ls150` image runs its own Docker engine and requires
privileged mode. This grants broad host capabilities: install only if you trust
Kasm and its container image. Umbrel's Docker socket is not mounted.

Internal Kasm HTTPS remains on port 39402, with the wizard on port 3000. Neither
is published to the host. The default Kasm zone's **Proxy Port** is set to **0**,
which tells Kasm to use the browser's port for workspace connections, as required
by its reverse-proxy documentation. The gateway supports WebSockets and streams
uploads. It reads the installation directory read-only to distinguish a fresh
install from a temporarily unavailable installation; those files are never
served as web content.

Umbrel login protects both Kasm and setup, without route exemptions. Other
containers on Umbrel's shared Docker network may still reach internal services;
this is not isolation against a compromised neighboring app. This package targets
Umbrel's local HTTPS access. External reverse proxies and companion API clients
have not been validated.

## Data, updates and recovery

- `data/opt` holds the nested Docker images/volumes, database, installation,
  certificates and configuration.
- `data/profiles` is available to workspaces as `/profiles`. Sessions are
  disposable by default. Configure persistent profiles such as
  `/profiles/ubuntu/{username}` following the
  [upstream instructions](https://docs.kasm.com/docs/latest/guide/persistent_data/persistent_profiles).
- Stop the app before backing up both directories. Preserve numeric ownership
  and permissions. Backups include nested Docker state and can be large.
- Restore with the app stopped, on a compatible architecture and storage driver.

Updating the package preserves existing Kasm accounts and data. An existing
default zone using the old package's port 39402 is migrated once to Proxy Port 0.
Other custom port values are preserved and may need adjustment by their owner.
Old port-39402 bookmarks must be replaced with the URL opened by Umbrel.

Updating the outer image alone does **not** upgrade an existing Kasm installation.
Back up first, update the package, then open `/setup/` and perform the upstream
upgrade. Update workspace image tags as directed by upstream. Inner service and
workspace images are managed by the installer, not frozen by the outer digest.
An image downgrade does not roll back the database; restore a matching backup.

If you disable the wizard, Kasm still opens normally. To re-enable it, stop the
app, remove only `data/opt/NO_WIZARD` from this app's installed data, and start it
again. Keep installer error output if setup fails; an error can be different
from slow startup.

## Licensing and sources

Kasm is subject to its own EULA and Community edition restrictions, presented
during setup. Review [Kasm licensing](https://kasm.com/docs/latest/license.html).
LinuxServer's container packaging is GPL-3.0. This store's original integration
files and icon are MIT licensed; this is an independent community package.

- [Container documentation](https://docs.linuxserver.io/images/docker-kasm/)
- [Container source](https://github.com/linuxserver/docker-kasm)
- [Reverse-proxy configuration](https://www.kasmweb.com/docs/latest/how_to/reverse_proxy.html)

## Verification

The pinned Umbrel linter checks metadata, wiring and public AMD64/ARM64 image
pins. Disposable CI tests exercise installation through the real wizard,
WebSocket transport, the direct app route, API health, accepted/rejected account
logins, default-zone migration and persistence after container recreation.
See the workflow for actual results for the published commit.

Umbrel's HTTPS listener was confirmed by read-only inspection on an ARM64
umbrelOS 2.0 host. End-to-end Umbrel authentication, browser desktop streaming,
external reverse proxies and a full historical-version upgrade remain untested.
No test installs or modifies an app on the user's NAS.
