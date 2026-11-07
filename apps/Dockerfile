# syntax=docker/dockerfile:1.7
# Production image for one Next.js app of the pnpm workspace. Build context: the repo root.
#   docker build -f apps/Dockerfile --build-arg APP=web   --build-arg NEXT_PUBLIC_API_URL=https://api.instantmechanic.online -t autocare-web .
#   (CI builds these per environment with its own domains: .github/workflows/main.yml)
#   docker build -f apps/Dockerfile --build-arg APP=admin --build-arg NEXT_PUBLIC_API_URL=https://api.instantmechanic.online -t autocare-admin .
# NEXT_PUBLIC_* values are inlined into the browser bundle at build time: changing one means rebuilding the image.
# The result is Next's standalone server (output: "standalone", see next.config.ts) running as the non-root `node` user.

ARG NODE_IMAGE=node:24-alpine

# ---------------------------------------------------------------- workspace dependencies of the one app
FROM ${NODE_IMAGE} AS deps
ARG APP
RUN test -n "$APP" || (echo "build with --build-arg APP=web|admin" >&2; exit 1) \
    && npm install -g pnpm@10.33.0 && npm cache clean --force
ENV PNPM_HOME=/pnpm CI=1
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY apps/admin/package.json apps/admin/
COPY packages/ui/package.json packages/ui/
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile --filter "${APP}..." --store-dir /pnpm/store

# ---------------------------------------------------------------- next build (standalone)
FROM deps AS build
ARG APP
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_MAP_TILE_URL=
ARG NEXT_PUBLIC_MAP_ATTRIBUTION=
ARG NEXT_PUBLIC_MAP_PROVIDER=
ARG NEXT_PUBLIC_MAP_KEY=
ARG NEXT_PUBLIC_FILES_URL=
ARG NEXT_PUBLIC_TURNSTILE_SITE_KEY=
ARG NEXT_PUBLIC_SENTRY_DSN=
ARG NEXT_PUBLIC_SENTRY_ENVIRONMENT=production
# The service worker's id (scripts/service-worker.mjs): the commit in CI; time + random when empty.
ARG BUILD_ID=
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_PUBLIC_MAP_TILE_URL=${NEXT_PUBLIC_MAP_TILE_URL} \
    NEXT_PUBLIC_MAP_ATTRIBUTION=${NEXT_PUBLIC_MAP_ATTRIBUTION} \
    NEXT_PUBLIC_MAP_PROVIDER=${NEXT_PUBLIC_MAP_PROVIDER} \
    NEXT_PUBLIC_MAP_KEY=${NEXT_PUBLIC_MAP_KEY} \
    NEXT_PUBLIC_FILES_URL=${NEXT_PUBLIC_FILES_URL} \
    NEXT_PUBLIC_TURNSTILE_SITE_KEY=${NEXT_PUBLIC_TURNSTILE_SITE_KEY} \
    NEXT_PUBLIC_SENTRY_DSN=${NEXT_PUBLIC_SENTRY_DSN} \
    NEXT_PUBLIC_SENTRY_ENVIRONMENT=${NEXT_PUBLIC_SENTRY_ENVIRONMENT} \
    BUILD_ID=${BUILD_ID} \
    NEXT_OUTPUT=standalone \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_OPTIONS=--max-old-space-size=2048
COPY packages/ui packages/ui
COPY apps/${APP} apps/${APP}
RUN pnpm --filter "${APP}" build \
    && mkdir -p apps/${APP}/public \
    && cp -r apps/${APP}/public apps/${APP}/.next/standalone/apps/${APP}/public \
    && cp -r apps/${APP}/.next/static apps/${APP}/.next/standalone/apps/${APP}/.next/static

# ---------------------------------------------------------------- runtime
FROM ${NODE_IMAGE} AS runtime
ARG APP
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
# Only `node` is needed at run time: the npm / npx / corepack CLIs of the base image go (their bundled undici and
# brace-expansion had known vulnerabilities, Trivy, Phase 5.4), and apk security updates are applied.
RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
        /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack /opt/yarn-* /usr/local/bin/yarn /usr/local/bin/yarnpkg
# The traced server, its node_modules and the static files; nothing else from the workspace.
COPY --from=build --chown=node:node /repo/apps/${APP}/.next/standalone /app
WORKDIR /app/apps/${APP}
USER node
EXPOSE 3000
CMD ["node", "server.js"]
