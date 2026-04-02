FROM saseq/discord-mcp:1.0.0@sha256:53042c5b48ad270b51f034f124a625c260b0cb935f708a38c54c22e3e31f9375 AS mcp-server

FROM node:22-alpine@sha256:4d64b49e6c891c8fc821007cb1cdc6c0db7773110ac2c34bf2e6960adef62ed3

# Upgrade base packages for security patches and install Java runtime
RUN apk upgrade --no-cache \
    && apk add --no-cache openjdk17-jre-headless

# renovate: depName=supergateway datasource=npm
ARG SUPERGATEWAY_VERSION=3.4.3
RUN npm install -g supergateway@${SUPERGATEWAY_VERSION}

# Copy the MCP server jar from the discord-mcp image (platform-independent Java bytecode)
COPY --from=mcp-server /app/app.jar /app/app.jar

USER 1000

EXPOSE 8080

ENTRYPOINT ["supergateway", \
  "--stdio", "java -jar /app/app.jar", \
  "--outputTransport", "streamableHttp", \
  "--port", "8080", \
  "--healthEndpoint", "/healthz", \
  "--protocolVersion", "2025-03-26", \
  "--stateful"]
