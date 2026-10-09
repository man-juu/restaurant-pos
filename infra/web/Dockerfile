# Production web image: builds the PWA, then serves it with Caddy (no Node at runtime,
# docs/04 section 8). Caddy also terminates TLS and proxies /api and the admin API.
# Build context: repository root.

FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM caddy:2-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f
COPY --from=build /src/dist /srv
COPY infra/web/Caddyfile /etc/caddy/Caddyfile
