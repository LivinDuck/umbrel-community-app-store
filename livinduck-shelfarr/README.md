# Shelfarr

Shelfarr 2026.10.05.1, packaged from the [upstream release](https://github.com/Pedro-Revez-Silva/shelfarr/releases/tag/v2026.10.05.1).
The server is a reproducible LivinDuck custom image built on that exact upstream release.
The server and upstream Libation images are pinned to public multi-architecture digests for AMD64 and ARM64.
Shelfarr is GPL-3.0 licensed. The generic bookshelf icon in this package is original, MIT-licensed artwork.

## Setup

1. Install Shelfarr from the LivinDuck community store and open it. Its launch port is 39404.
2. Create your Shelfarr administrator account with a password of at least 12 characters.
3. Configure your sources and optional integrations in Settings. Metadata providers, indexers,
   download clients and Audiobookshelf may require their own accounts or API keys.
4. Keep the default output paths `/audiobooks` and `/ebooks`. Shared Umbrel Downloads
   is mounted at `/downloads`; configure download-client path mapping if the client reports a different path.

On umbrelOS 2.0, use the app's folder settings to select existing audiobook and ebook
libraries, and point Audiobookshelf at those same folders. Merely connecting its API
does not share files. By default, output libraries are private to this app under
`data/audiobooks` and `data/ebooks`. Older Umbrel versions retain these private defaults.
Selected folders must be writable by UID/GID 1000:1000. The default copy import mode
works across separate mounts; hardlinks require a shared filesystem layout.

Audible Backup (Beta) is optional. The included Libation companion stays idle until
enabled and paired through Shelfarr's admin UI. Its private account state is isolated
from Shelfarr, and only completed books and a narrow bridge credential are shared.
It exposes no host port. No external service is installed or configured automatically.

## Authentication and storage

Umbrel login protects all browser routes. Shelfarr additionally requires its own
account; only the initial user can self-register and becomes administrator.
There are no API or webhook exceptions to Umbrel authentication in this package.
External API clients and inbound webhooks that cannot provide Umbrel cookies are therefore
not supported by default. Outbound integrations are configured from the browser.

SQLite databases, generated encryption keys, session secret, settings and uploads
persist in `data/storage`. Companion configuration, tokens and completed backups
persist in `data/libation-config`, `data/libation-control` and `data/libation-books`.
Back up the complete app data, including hidden key files, before upgrades. Shared
Downloads and user-selected external libraries need their own backups. Restoring
databases without their original encryption keys can make saved credentials unreadable.
Do not assume downgrading the image reverses database migrations.

## Validation

`tests/smoke_shelfarr.py` runs the packaged services in disposable Docker Compose
stacks on AMD64 and ARM64 CI runners. It checks HTTP onboarding, account creation,
login rejection, writable output folders, companion token authentication, and account,
session, encrypted-state and file persistence after container recreation.
Package lint verifies public image manifests and Umbrel configuration.

These checks do not install the app on a NAS or test the real Umbrel proxy, paid
accounts, Audible sign-in, downloads from providers, or Audiobookshelf library sync.

## Custom edition and reinstall recovery

Version `2026.10.05.1-patch.1` embeds the BookOrbit search interface, work/edition
and language grouping, chosen-cover/ISBN handoff, transaction-safe request queues,
provider ordering, Google Books resilience and TorBox audiobook cache preference.
Source, licenses, frontend build and backend tests are in `custom/`. GitHub Actions
publishes an immutable multi-architecture image. No host code mount is required.
The BookOrbit identity migration runs on fresh installs and upgrades and preserves
existing columns/indexes. Removing the image does not reverse those additive changes.

BookOrbit must be installed and configured for the custom search interface. Create
`custom/orbit.json` inside Shelfarr's persisted storage directory with `username`
and `password` for your BookOrbit integration account. The account needs access to
BookOrbit metadata search. The default API is
`http://livinduck-bookorbit_server_1:3000/api/v1/`; set `BOOKORBIT_URL` in Umbrel's
custom environment settings to use another server, including the `/api/v1/` suffix.
For cache preference, create `custom/torbox-cache.json` in the same storage with
`api_key` and `download_client_id` (the numeric Shelfarr download client ID).
Keep both files owned by UID 1000, mode 600. Missing TorBox configuration safely
retains normal selection. Missing BookOrbit credentials produce a search error;
they do not prevent startup or administrator setup. Provider keys remain in BookOrbit.

An existing mount at `/rails/config/initializers/umbrel_google_books` takes precedence
over the embedded extensions, and its existing credentials continue working. To use
the packaged code on such an installation, first copy the two credential files into
the persisted storage paths above, then remove only that legacy code mount. Keep
all library and download mounts. This package does not change saved mount settings.

A fresh reinstall restores the **custom software**, not deleted accounts or data.
Before uninstalling, keep a private backup outside the app directory containing all
SQLite databases (using SQLite's backup API or stopping the app first), hidden
`.encryption_keys` and `.secret_key_base`, uploads, custom credentials, Libation
state, and Umbrel folder/settings choices. On umbrelOS 2.0 the active storage mount
may be the app's `home/` directory instead of `data/storage/`; inspect the actual
`/rails/storage` mount. Never publish that backup in this public repository.

To recover: install this package, stop it, restore the saved storage into the actual
`/rails/storage` host directory (including hidden keys), restore Libation state,
and reselect the original library/download folders. Restore extension credentials
into `custom/orbit.json` and `custom/torbox-cache.json` under storage, preserving
UID 1000 access. Restart and confirm login, settings, search and library paths.
Do not restore the old generated Compose files over the new package. User-selected
libraries and BookOrbit itself require their own backups. Existing host services
such as the BookOrbit completion webhook live outside Shelfarr and are not installed
or removed by this package.

Validation covers fresh startup and automatic migration, custom assets and source
availability, onboarding/authentication, encrypted-state and recreation persistence,
search/request authorization and transaction ordering, and TorBox fallback/ranking.
Tests run in disposable containers; they do not uninstall the user's live instance.
