# Murmur Web

Murmur **0.9.0** (package **0.9.0**), using the official upstream multi-architecture image, with only
the web service and Umbrel login proxy. No bundled Hermes container is installed.

## Fresh installation

1. Install and configure **Hermes Agent** (0.21.4 or newer) from Umbrel's official store.
2. Install **Murmur Web** from the LivinDuck community store.
3. Open Murmur Web, choose your Hermes server, and enter its credentials if requested.

The launch port is **39406**. Umbrel supplies the shared Docker network and login
proxy. The local Hermes Agent is suggested at `http://hermes-agent_web_1:18789`.
The package does not fix `HERMES_URL` or supply Hermes credentials. Murmur's
onboarding lets you select the server and use its supported password sign-in.
This does not imply support for arbitrary reverse-proxy or SSO authentication.

Manage server addresses and credentials in **Settings → Server**. Voice input
needs HTTPS; ordinary chat can use Umbrel's local HTTP address.

Background notifications also require HTTPS and must be enabled in Settings.
On iPhone and iPad, open Murmur from the Home Screen to enable them. Notification
subscriptions and keys persist in `data/murmur/notifications.json` alongside
connection settings. No additional volume or bundled Hermes service is needed.

### Updating from 0.5.1 or 0.5.1-patch.1

Update Murmur Web in Umbrel; no uninstall or data reset is needed. The fixed
connection disappears and server selection returns if no saved connections exist.
Previously saved connections remain available in Settings → Server. Newer features
may require a newer Hermes Agent version; update that separate app as needed.

## Features that depend on Hermes

Email in Murmur 0.9.0 requires the `murmur-mail` plugin, bundled in Umbrel's
Hermes image `v0.22.5-1`. If your separate Hermes Agent lacks it, Murmur does
not offer email. Update Hermes Agent separately when needed; this package
never supplies or updates it. Apps connected through Nous Research require
consent in Murmur before connecting.

## Data and updates

- Murmur settings persist in `data/murmur`, mounted at `/data`.
- Agents, conversations, model configuration and API keys stay in **Hermes Agent**.
- Removing Murmur Web does not remove the separate Hermes Agent app's data.
- Removing the official Murmur app deletes its own bundled Hermes data; it does
  not transfer that data into Hermes Agent or this package.
- This package has its own ID, so official Murmur updates cannot add a bundled
  Hermes service to it. Image updates must be published to this community package.
- Back up settings before updates; image downgrades do not guarantee data rollback.

## Validation

The package linter checks Compose wiring, public image availability, and AMD64 /
ARM64 support. The Murmur-specific CI test runs the pinned image on both
architectures with a disposable Hermes API fixture. It checks the web UI,
absence of built-in Hermes, server selection, token and password authentication,
removal of the old fixed connection on update, saved-connection upgrades from 0.5.1, 0.7.0, 0.7.1 and 0.8.0,
cross-origin rejection, writable settings and persistence across restart and
container recreation. The fixture is not a full Hermes Agent installation.

Real Umbrel installation, its login proxy, live agent chat and browser interaction
are not covered by that disposable test. No NAS installation is performed when
publishing this package.

Upstream documentation: https://github.com/getumbrel/murmur/blob/v0.9.0/docs/STANDALONE.md

## Custom icon

The Umbrel catalog/launcher uses the user-provided `murmur-samsung-dark.svg`,
committed as `icon.svg`. Keep this artwork across upstream updates; see
[maintenance instructions](AGENTS.md). The upstream container's browser/PWA
icons are separate. The upstream MIT notice is retained in `UPSTREAM-LICENSE`
for the underlying artwork.
