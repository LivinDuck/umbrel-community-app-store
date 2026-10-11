# BookOrbit 3.3.0

Upstream: https://github.com/bookorbit/bookorbit (AGPL-3.0).

The package uses the upstream multi-architecture BookOrbit and pgvector PostgreSQL 18 images, pinned by manifest-list digest. No custom application image is built.

## First login

Open the app through Umbrel. Username: `admin`. Find the unique initial password in Umbrel Files under the app's data folder, `onboarding/admin-password.txt`. Change it in BookOrbit after signing in. An idempotent setup service creates the administrator only when no account exists. It never resets an existing password. The upstream password policy requires mixed case and a digit, so this package uses a purpose-derived secret with a `Bo1-` prefix instead of advertising Umbrel's hex-only APP_PASSWORD as a valid login.

Choose your library folder through Umbrel's app folder settings, create a library at `/books`, and enable folder watching. No download service or metadata-provider account is required. Libraries retain files in their existing folders unless you enable BookOrbit's file-writing or renaming options.

## Reader clients

Enable OPDS in BookOrbit settings and create a dedicated OPDS account. Use `http://<umbrel-host>:39405/api/v1/opds`. OPDS, Kobo device, and KOReader protocol routes bypass Umbrel's browser login and retain BookOrbit's native authentication. Browser setup and administration remain behind Umbrel login. Physical reader pairing must be configured and tested on the device separately.

## Persistence and security

Back up `data/app`, `data/postgres`, and your external ebook folder together. PostgreSQL 18 data is not downgrade-compatible with older major versions. Keep the device seed and generated encryption secrets stable when restoring.

The server follows upstream's read-only root filesystem and minimal capability list: CHOWN, DAC_OVERRIDE, FOWNER, SETGID and SETUID allow its entrypoint to prepare `/data` ownership and drop to PUID/PGID 1000. Both app and setup prevent privilege escalation. PostgreSQL requires a separate per-install password even on Umbrel's shared network. JWT and feature-specific encryption keys are independently derived.

`tests/smoke_bookorbit.py` uses disposable storage to check bootstrap, rejected unauthenticated requests, ebook scanning, and recreation persistence on both AMD64 and ARM64 CI runners.
