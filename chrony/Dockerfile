# Minimal Chrony NTP Server
# Starts as root, drops to chrony user (UID 1000) after initialization
# No capabilities required when using high port (1123) and -x flag
#
# Environment variables:
#   NTP_SERVERS  - Comma-separated NTP servers (default: time.cloudflare.com)
#   NTP_PORT     - Port to listen on (default: 1123)
#   ENABLE_NTS   - Enable Network Time Security (default: false)
#   LOG_LEVEL    - 0=info, 1=warn, 2=error, 3=fatal (default: 0)
#   NOCLIENTLOG  - Disable client logging (default: false)
#   TZ           - Timezone (default: UTC)

# Pin to specific digest for supply chain security (dependabot will update this)
FROM alpine:3.23@sha256:865b95f46d98cf867a156fe4a135ad3fe50d2056aa3f25ed31662dff6da4eb62

# Install chrony and timezone data
# Note: chrony package creates its own user/group, we'll replace them with UID/GID 1000
RUN apk add --no-cache chrony tzdata \
    && rm -rf /var/cache/apk/* \
    && deluser chrony 2>/dev/null || true \
    && delgroup chrony 2>/dev/null || true \
    && addgroup -g 1000 chrony \
    && adduser -D -u 1000 -G chrony -h /var/lib/chrony chrony

# Create required directories with correct ownership
# Mode 750 required by chronyd for command socket security
RUN mkdir -p /var/lib/chrony \
    && chown -R chrony:chrony /var/lib/chrony \
    && chmod 750 /var/lib/chrony

# Copy startup script
COPY assets/startup.sh /usr/local/bin/startup.sh
RUN chmod +x /usr/local/bin/startup.sh

# Environment defaults
ENV NTP_SERVERS="time.cloudflare.com" \
    NTP_PORT="1123" \
    ENABLE_NTS="false" \
    LOG_LEVEL="0" \
    NOCLIENTLOG="false" \
    TZ="UTC"

# Expose NTP port (high port - no NET_BIND_SERVICE needed)
EXPOSE 1123/udp

# Health check (uses socket in /var/lib/chrony to avoid /run permissions)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD chronyc -h /var/lib/chrony/chrony.sock -n tracking || exit 1

# Run as chrony user - use -U flag to bypass superuser check
USER chrony

ENTRYPOINT ["/usr/local/bin/startup.sh"]
