# Murmur Web customizations

Preserve these user-requested customizations in every update and maintenance session:

- Web only: never add a bundled Hermes service/image or MURMUR_BUILTIN_HERMES_* settings. Keep the separate hermes-agent dependency, editable server selection and sign-in.
- Keep `icon.svg` byte-for-byte as the user-provided `murmur-samsung-dark.svg`, supplied on 2026-10-23. Do not replace it with upstream artwork during version bumps or packaging refreshes unless the user explicitly requests a replacement.
- Icon SHA-256: `ed22ddceeb2135abced16e3f5014a883e1f9c86b023fc9ea88850225f9dd1d6b`.
- Keep the manifest icon URL pointing to this store's `livinduck-murmur-web/icon.svg`. This customization is the Umbrel catalog/launcher icon; the upstream container's browser/PWA assets are separate.
- Preserve the upstream MIT notice in `UPSTREAM-LICENSE` for the underlying artwork.

## Android decoder compatibility patch

- User authorized custom images on 2026-11-02. Read `../sources/murmur/README.md`.
- For every latest stable upstream release, test whether it fixes the noVNC
  H.264-probe hang in both app startup and live-view fallback. If not, update to
  that release and adapt/reapply our patch, publishing a new custom image.
- If upstream passes all decoder regressions, return to its public image and
  remove redundant patches. Retain tests; do not drop the fix just for a version bump.
- Require public AMD64/ARM64 version-and-digest-pinned images, non-H.264 rendering
  after probe timeout, and normal H.264 support when the probe succeeds.
- Routine maintenance publishes the store only; it does not install NAS updates.
