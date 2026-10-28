# Happy relay server (https://github.com/slopus/happy), standalone mode: PGlite and
# local file storage under /data, no Postgres, Redis or S3.
# Designed for PSA restricted: non-root (UID 1000), read-only root filesystem,
# all caps dropped. Mount a volume at /data and an emptyDir at /tmp.
#
# Required env:
#   HANDY_MASTER_SECRET — signs auth tokens; changing it logs every client out
# Optional env:
#   PUBLIC_URL — public base URL for file links sent to clients
#
# Pin to specific digest for supply chain security (renovate updates this)
FROM node:26.12.0-trixie-slim@sha256:e556a144463cc8dc53afe8de6d2fa0db5c132fd39ffa232c17641bd40df2bf11

# renovate: datasource=npm depName=happy-server-self-host
ARG HAPPY_SERVER_VERSION=1.1.11

# Dependency floors. Drop one once happy-server-self-host's own range meets it (#2513);
# dependency-floors.cjs applies only the floors the installed package is below.
# renovate: datasource=npm depName=@fastify/static
ARG FASTIFY_STATIC_FLOOR=10.1.8
# renovate: datasource=npm depName=deepmerge-ts
ARG DEEPMERGE_TS_FLOOR=8.0.2
# renovate: datasource=npm depName=effect
ARG EFFECT_FLOOR=3.22.4
# renovate: datasource=npm depName=sharp
ARG SHARP_FLOOR=0.35.5
# renovate: datasource=npm depName=zod
ARG ZOD_FLOOR=4.6.7

# openssl: Prisma's query engine links libssl and probes for it at generate time.
# Install scripts stay off; the only one needed is `prisma generate` for the runtime client.
RUN --mount=type=bind,source=dependency-floors.cjs,target=/tmp/dependency-floors.cjs \
    apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl openssl \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g --no-fund --no-audit --ignore-scripts \
      "happy-server-self-host@${HAPPY_SERVER_VERSION}" \
    # A global install ignores overrides, so set the floors in the package's own package.json and reinstall in place.
    && node /tmp/dependency-floors.cjs apply /usr/local/lib/node_modules/happy-server-self-host \
      "@fastify/static=${FASTIFY_STATIC_FLOOR}" "deepmerge-ts=${DEEPMERGE_TS_FLOOR}" "effect=${EFFECT_FLOOR}" \
      "sharp=${SHARP_FLOOR}" "zod=${ZOD_FLOOR}" \
    # --legacy-peer-deps: pglite-prisma-adapter's @prisma/client peer range is above the version the package pins.
    && npm install --prefix /usr/local/lib/node_modules/happy-server-self-host \
      --omit=dev --legacy-peer-deps --ignore-scripts --no-package-lock --no-fund --no-audit \
    && /usr/local/lib/node_modules/happy-server-self-host/node_modules/.bin/prisma generate --generator client \
      --schema=/usr/local/lib/node_modules/happy-server-self-host/prisma/schema.prisma \
    && npm cache clean --force \
    # PGlite Bytes columns fail to read (P2023); drop once slopus/happy#686 ships in the npm package.
    && for f in /usr/local/lib/node_modules/happy-server-self-host/node_modules/pglite-prisma-adapter/dist/index.mjs \
      /usr/local/lib/node_modules/happy-server-self-host/node_modules/pglite-prisma-adapter/dist/index.cjs; do \
      sed -i 's/return parsePgBytes(serializedBytes);/return Array.from(parsePgBytes(serializedBytes));/' "$f" \
      && grep -q 'return Array.from(parsePgBytes(serializedBytes));' "$f"; \
    done \
    # Any coding session's socket counts as an active UI client, so every push is suppressed;
    # drop once slopus/happy@1862c2c ships in the npm package.
    && f=/usr/local/lib/node_modules/happy-server-self-host/dist/standalone.mjs \
    && old='return appState !== "background";' \
    && new='return s.data.clientType === "user-scoped" \&\& appState === "active";' \
    && sed -i "s/$old/$new/" "$f" \
    && grep -qF 'return s.data.clientType === "user-scoped" && appState === "active";' "$f" \
    # The runtime runs node directly, so the package managers are not needed after the install.
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
      /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack /root/.npm \
      /opt/yarn-v* /usr/local/bin/yarn /usr/local/bin/yarnpkg \
    && install -d -o 1000 -g 1000 /data

ENV NODE_ENV=production \
    DATA_DIR=/data \
    PGLITE_DIR=/data/pglite \
    PORT=3005

# Migrations and the webapp resolve from the working directory.
WORKDIR /usr/local/lib/node_modules/happy-server-self-host

USER 1000
EXPOSE 3005

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["curl", "-fsS", "http://127.0.0.1:3005/health"]

# Runs node directly: the package's happy-server wrapper does not forward SIGTERM to its child.
CMD ["sh", "-c", "node dist/standalone.mjs migrate && exec node dist/standalone.mjs serve"]
