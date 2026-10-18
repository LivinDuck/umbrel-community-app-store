# syntax=docker/dockerfile:1
FROM ghcr.io/pedro-revez-silva/shelfarr:2026.10.05.1@sha256:b4bbdf278cfe6aa4773b102c192ad9c79263c573fc8b51c5861d1a093f9e9092
LABEL org.opencontainers.image.source="https://github.com/LivinDuck/umbrel-community-app-store" \
      org.opencontainers.image.licenses="GPL-3.0-or-later AND AGPL-3.0-or-later" \
      org.opencontainers.image.description="Shelfarr with LivinDuck BookOrbit search, provider resilience and TorBox cache preference"
COPY --chown=rails:rails extensions/ /rails/config/initializers/umbrel_google_books/
COPY --chown=rails:rails migrations/ /rails/db/migrate/
