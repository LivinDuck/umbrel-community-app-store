# Store maintenance

- This repository is public. Never commit credentials, runtime data, local NAS addresses or rendered secrets.
- Store ID is `livinduck`; app directory names and manifest IDs must start with `livinduck-`.
- Use current upstream releases and publicly pullable, digest-pinned multi-architecture images.
- Follow Umbrel's packaging guidance, linked from https://github.com/getumbrel/umbrel-apps/blob/master/AGENTS.md.
- Preserve stable IDs, data mounts and authentication secrets across updates.
- Keep browser onboarding protected by Umbrel auth; exempt only necessary client protocol paths.
- Publishing a package does not authorize installation on the NAS or changes to client devices.
- Run package lint and applicable CI checks. State clearly whether Umbrel and real-device tests were performed.
