FROM saseq/discord-mcp:1.0.0 AS mcp-server

FROM node:22-alpine

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
  "--healthEndpoint", "/healthz"]
