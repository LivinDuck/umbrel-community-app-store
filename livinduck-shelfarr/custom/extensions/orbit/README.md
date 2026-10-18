# BookOrbit search integration

BookOrbit search and edition grouping for Shelfarr 2026.10.05.1.
See the parent Shelfarr package README for setup and recovery.
Credentials are read from `/rails/storage/custom/orbit.json`; the legacy initializer credentials file remains supported.
`BOOKORBIT_URL` can override the default internal BookOrbit API URL (include `/api/v1/`).

Build: `npm ci && npm test && npm run build && python3 package-source.py`.
The search footer offers the corresponding integration source, including licenses.
Backend tests in `test_backend.txt` recreate the schema: run ONLY in disposable, network-isolated containers.
The packaged Rails migration adds identity columns and a unique index idempotently.
