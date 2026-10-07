# Production web image: builds the PWA, then serves it with Caddy (no Node at runtime,
# docs/04 section 8). Caddy also terminates TLS and proxies /api and the admin API.
# Build context: repository root.

FROM node:22-alpine AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /src/dist /srv
COPY infra/web/Caddyfile /etc/caddy/Caddyfile
