# Multi-Stage-Build fuer das React-Frontend.
# Stage 1: Vite-Build via Node 22.
# Stage 2: Nginx serviert die Static-Files plus reverse-proxy zur Backend-API.

# --- Stage 1: Build -----------------------------------------------------------
FROM node:22-alpine AS builder
WORKDIR /build

# pnpm via corepack. Die aktivierte Version MUSS zum "packageManager"-Feld in
# package.json (pnpm@11.9.0) passen — sonst versucht corepack beim ersten
# pnpm-Aufruf, die gepinnte Version nachzuladen, und bricht im nicht-interaktiven
# Build am Download-Prompt ab (exit 1). COREPACK_ENABLE_DOWNLOAD_PROMPT=0 macht
# einen etwaigen Download zusaetzlich non-interactive.
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable && corepack prepare pnpm@11.9.0 --activate

# pnpm-workspace.yaml MUSS mitkopiert werden: dort steht onlyBuiltDependencies
# (esbuild), sonst wird esbuilds Platform-Binary beim Install nicht gebaut und
# der spaetere `pnpm build` (vite) schlaegt fehl.
COPY package.json pnpm-lock.yaml* pnpm-workspace.yaml ./
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

# Healthcheck bewusst auf 127.0.0.1 (nicht localhost): unsere eigene nginx.conf
# bekommt vom Entrypoint-Skript 10-listen-on-ipv6-by-default.sh KEIN
# listen [::]:8080 (es patcht nur die mitgelieferte Default-Config). localhost
# koennte auf ::1 aufloesen, wo nginx nicht lauscht -> Healthcheck haengt auf
# "starting". 127.0.0.1 trifft den IPv4-Listener zuverlaessig.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q --spider http://127.0.0.1:8080/ || exit 1
