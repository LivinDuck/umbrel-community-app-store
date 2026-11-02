# syntax=docker/dockerfile:1
ARG UPSTREAM_IMAGE
FROM --platform=$BUILDPLATFORM node:22-alpine3.24@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS build
WORKDIR /src
COPY . .
RUN npm ci --ignore-scripts --no-audit --no-fund && npm run postinstall && npm run build
# Keep upstream's server, runtime, UID, volumes, entrypoint and healthcheck.
FROM ${UPSTREAM_IMAGE}
COPY --from=build /src/dist /app/dist
COPY --from=build /src/node_modules/@novnc/novnc/docs/LICENSE.MPL-2.0 /app/licenses/novnc.MPL-2.0
LABEL org.opencontainers.image.source="https://github.com/LivinDuck/umbrel-community-app-store"
