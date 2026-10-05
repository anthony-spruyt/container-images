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

# openssl: Prisma's query engine links libssl and probes for it at generate time
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl openssl \
    && rm -rf /var/lib/apt/lists/*

# npm 11 skips install scripts unless allowed; these fetch Prisma's engines and run `prisma generate`.
RUN npm install -g --no-fund --no-audit \
      --allow-scripts=happy-server-self-host,@prisma/client,prisma,@prisma/engines,sharp \
      "happy-server-self-host@${HAPPY_SERVER_VERSION}" \
    && npm cache clean --force \
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
