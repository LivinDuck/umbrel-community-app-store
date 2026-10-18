# Murmur Web

Murmur **0.5.1**, using the official upstream multi-architecture image, with only
the web service and Umbrel login proxy. No bundled Hermes container is installed.

## Fresh installation

1. Install and configure **Hermes Agent** from Umbrel's official store.
2. Install **Murmur Web** from the LivinDuck community store.
3. Open Murmur Web from Umbrel. It connects automatically to Hermes Agent.

The launch port is **39406**. Umbrel supplies the shared Docker network and login
proxy. The internal connection is `http://hermes-agent_web_1:18789`, using the
official Hermes app's existing Umbrel proxy authentication mode. No extra
password is configured by this package. The package assumes that standard Hermes
configuration; custom Hermes authentication is not configured here.

The default Hermes connection is fixed. Additional servers can be added through
**Settings → Server**, with their credentials when required. Voice input needs
HTTPS; ordinary chat can use Umbrel's local HTTP address.

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
absence of built-in Hermes, external connectivity, server-side authentication,
cross-origin rejection, writable settings and persistence across restart and
container recreation. The fixture is not a full Hermes Agent installation.

Real Umbrel installation, its login proxy, live agent chat and browser interaction
are not covered by that disposable test. No NAS installation is performed when
publishing this package.

Upstream documentation: https://github.com/getumbrel/murmur/blob/v0.5.1/docs/STANDALONE.md

The upstream icon is distributed under the accompanying `UPSTREAM-LICENSE` (MIT).
