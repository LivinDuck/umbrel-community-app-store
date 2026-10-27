# Umbrel App Store 

This is a personal project with a couple of docker apps not in the umbrelOS store that I needed. THE MAJORITY OF THIS IS AI GENERATED AND UNMAINTAINED!! Don't use unless you know what you are doing.

## Add the store

In Umbrel, open **App Store → menu → Community App Stores**, then add:

```text
https://github.com/LivinDuck/umbrel-community-app-store
```

Find **rmfakecloud**, **Kasm Workspaces**, **DiscoPanel**, **ClipSync**, **Shelfarr**, or **Murmur Web** in the LivinDuck store. Adding the store does not install
the app. Install it when you are ready.

| App | Version | Setup |
| --- | --- | --- |
| rmfakecloud | 0.0.31 | [Setup and limitations](livinduck-rmfakecloud/README.md) |
| Kasm Workspaces | 1.19.0-2 | [Setup and limitations](livinduck-kasm/README.md) |
| DiscoPanel | 2.0.15 | [Setup and limitations](livinduck-discopanel/README.md) |
| ClipSync | 1.0.2 | [Pairing and dedicated-port HTTPS setup](livinduck-clipsync/README.md) |
| Shelfarr | 2026.10.05.1 | [Setup and library folders](livinduck-shelfarr/README.md) |
| Murmur Web | 0.8.0 | [Connect to the existing Hermes Agent app](livinduck-murmur-web/README.md) |

## Packaging workflow

Send the upstream GitHub URL and any required integrations. For each app:

1. Review its license, current release, images, architecture and setup requirements.
2. Add a `livinduck-<name>` directory with its manifest, Compose services and persistent data scaffolding.
3. Pin public upstream images by version and multi-architecture digest.
4. Check package wiring, authentication and storage; run applicable CI smoke tests.
5. Document validation limits and publish. NAS installation is a separate action.

Updates repeat the same review, including data migrations and backup/recovery.
No automatic installation or upstream version bumping is configured.

The `Validate apps` workflow uses a pinned revision of Umbrel's package linter
with the official catalog available for dependency and port-conflict checks,
and runs disposable rmfakecloud, Kasm and DiscoPanel container tests on GitHub-hosted runners.
It never connects to the NAS. Actual Umbrel installation and physical tablet
sync remain untested until explicitly performed. Kasm checks exercise installation, login and storage; desktop streaming remains
untested.

Keep personal addresses, passwords, API keys, rendered configuration and runtime
data out of this public repository. Packaging files and the original generic
icon are MIT licensed; upstream rmfakecloud remains AGPL-3.0 licensed.

ClipSync server sources live in `sources/clipsync/`. Its separate image workflow publishes multi-architecture server/HTTPS images, and **Validate ClipSync** exercises disposable amd64 and arm64 containers. ClipSync uses its own TLS port and never claims ports 80 or 443.

**Validate Shelfarr** tests setup, account authentication, the optional Libation companion,
and storage persistence in disposable AMD64 and ARM64 containers.

**Validate Murmur Web** tests web-only operation, external Hermes API connectivity
using a disposable fixture, origin checks and settings persistence on AMD64 and ARM64.
