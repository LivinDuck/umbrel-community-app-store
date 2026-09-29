# Umbrel App Store 

This is a personal project with a couple of docker apps not in the umbrelOS store that I needed. THE MAJORITY OF THIS IS AI GENERATED AND UNMAINTAINED!! Don't use unless you know what you are doing.

## Add the store

In Umbrel, open **App Store → menu → Community App Stores**, then add:

```text
https://github.com/LivinDuck/umbrel-community-app-store
```

Find **rmfakecloud** or **Kasm Workspaces** in the LivinDuck store. Adding the store does not install
the app. Install it when you are ready.

| App | Version | Setup |
| --- | --- | --- |
| rmfakecloud | 0.0.31 | [Setup and limitations](livinduck-rmfakecloud/README.md) |
| Kasm Workspaces | 1.19.0-2 | [Setup and limitations](livinduck-kasm/README.md) |

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
and runs disposable rmfakecloud and Kasm container tests on GitHub-hosted runners.
It never connects to the NAS. Actual Umbrel installation and physical tablet
sync remain untested until explicitly performed. Kasm checks exercise installation, login and storage; desktop streaming remains
untested.

Keep personal addresses, passwords, API keys, rendered configuration and runtime
data out of this public repository. Packaging files and the original generic
icon are MIT licensed; upstream rmfakecloud remains AGPL-3.0 licensed.
