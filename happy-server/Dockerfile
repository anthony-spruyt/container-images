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
FROM node:24.21.0-trixie-slim@sha256:8ec5d7557396cfe32d21c3f9c13072355ceab22b584578ca4bb28af31120cffe

# renovate: datasource=npm depName=happy-server-self-host
ARG HAPPY_SERVER_VERSION=1.1.11

# openssl: Prisma's query engine links libssl and probes for it at generate time.
# Install scripts stay off; the only one needed is `prisma generate` for the runtime client.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl openssl \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g --no-fund --no-audit --ignore-scripts \
      "happy-server-self-host@${HAPPY_SERVER_VERSION}" \
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
