# Patched Murmur image maintenance

The user authorized a custom image on 2026-11-02 to fix Android Chrome HTTPS
startup hanging inside noVNC's H.264 probe. Store publication is authorized;
NAS installation is **not** part of routine maintenance.

`upstream.json` pins the stable source commit, matching public upstream image,
and custom package version. `prepare.py <new-directory>` fetches that commit and
applies `android-decoder.patch`. The image workflow tests it before building
AMD64/ARM64 `ghcr.io/livinduck/murmur-web:<packageVersion>-<store commit>` images.
`Dockerfile` layers the patched frontend over the exact upstream runtime image;
it does not add Hermes. Verify anonymous pullability and pin the resulting
multiarch index digest before changing the package. Tags are immutable by commit.

## Required behavior

- noVNC is imported only when the live viewer is needed, never before sign-in.
- Its H.264 capability query and test-frame flush have a combined two-second
  deadline. Timeout/rejection returns unsupported, releasing the test decoder.
- Other RFB encodings continue working; a successful probe still enables H.264.
- A five-second viewer loader deadline also bounds unrelated loading failures.

## Every upstream update

1. Check the latest stable release and official Umbrel package, including source,
   migration and image changes. Test whether upstream now fixes BOTH startup and
   the viewer fallback. An upstream change or release-note claim alone is not proof.
2. If upstream passes the regression cases, use its public digest-pinned image
   and remove only redundant patches. Retain regression coverage for future runs.
3. Otherwise advance to the latest stable source/image, adapt the patch, update
   `upstream.json`, and publish a fresh custom multiarch image. Do not hold back
   upstream updates simply to retain the existing patched version.
4. The patch includes `test/decoder-browser.mjs`: production-page sign-in must
   render with a hung VideoDecoder probe; noVNC must connect to a disposable VNC
   server, omit H.264 when unsupported, and render raw pixels. Cover stalled
   isConfigSupported, stalled flush, rejected probe and successful H.264 support.
   The test's loopback network permission applies only to its disposable browser.
5. Run frontend build/typecheck and unit/browser tests, then the store image lint
   and fresh/upgrade smoke tests on both architectures for the actual image.
   Preserve port, data, authentication choices, external Hermes and exact icon.

A desktop Chromium mobile profile and a fixture are not an actual Android phone
or live Hermes viewer test. State that limitation. Never reset data, weaken auth,
modify the user's browser or change Hermes Agent as part of package maintenance.
