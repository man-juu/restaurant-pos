# Development image (Vite dev server). The production PWA is built and served by Caddy (slice 0.8).
FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci
COPY . .
CMD ["npm", "run", "dev", "--", "--port", "5173"]
