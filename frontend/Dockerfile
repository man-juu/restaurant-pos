# Development image (Vite dev server). The production PWA is built and served by Caddy (slice 0.8).
FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci
COPY . .
CMD ["npm", "run", "dev", "--", "--port", "5173"]
