# Murmur Web customizations

Preserve these user-requested customizations in every update and maintenance session:

- Web only: never add a bundled Hermes service/image or MURMUR_BUILTIN_HERMES_* settings. Keep the separate hermes-agent dependency, editable server selection and sign-in.
- Keep `icon.svg` byte-for-byte as the user-provided `murmur-samsung-dark.svg`, supplied on 2026-10-23. Do not replace it with upstream artwork during version bumps or packaging refreshes unless the user explicitly requests a replacement.
- Icon SHA-256: `ed22ddceeb2135abced16e3f5014a883e1f9c86b023fc9ea88850225f9dd1d6b`.
- Keep the manifest icon URL pointing to this store's `livinduck-murmur-web/icon.svg`. This customization is the Umbrel catalog/launcher icon; the upstream container's browser/PWA assets are separate.
- Preserve the upstream MIT notice in `UPSTREAM-LICENSE` for the underlying artwork.
