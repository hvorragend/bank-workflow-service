# Multi-Stage-Build fuer das React-Frontend.
# Stage 1: Vite-Build via Node 22.
# Stage 2: Nginx serviert die Static-Files plus reverse-proxy zur Backend-API.

# --- Stage 1: Build -----------------------------------------------------------
FROM node:22-alpine AS builder
WORKDIR /build

# pnpm via corepack (kommt mit Node 22 mit).
RUN corepack enable && corepack prepare pnpm@latest-10 --activate

COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile=false --prefer-offline

COPY tsconfig.json tsconfig.node.json vite.config.ts tailwind.config.ts postcss.config.js index.html ./
COPY src ./src

RUN pnpm build

# --- Stage 2: Nginx ----------------------------------------------------------
FROM nginx:1.27-alpine AS runtime
RUN rm -rf /usr/share/nginx/html/*
COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q --spider http://localhost:8080/ || exit 1
