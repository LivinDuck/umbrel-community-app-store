# TorBox cache preference

Prefer confirmed cached audiobook torrents after ordinary eligibility checks.
Ebooks and manual choices are unchanged. API failures retain normal ranking.
Read configuration from `/rails/storage/custom/torbox-cache.json` with `api_key`
and `download_client_id`; legacy initializer credentials remain supported.
Never put real credentials in this repository or image.
`test_backend.txt` recreates the schema: run ONLY in disposable, network-isolated containers.
