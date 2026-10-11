# Shelfarr

Shelfarr 2026.10.05.1, packaged from the [upstream release](https://github.com/Pedro-Revez-Silva/shelfarr/releases/tag/v2026.10.05.1).
Both upstream images are pinned to public multi-architecture digests for AMD64 and ARM64.
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
