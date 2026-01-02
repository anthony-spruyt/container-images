# Minimal Chrony NTP Server
# Runs as non-root with zero capabilities required
#
# Environment variables:
#   NTP_SERVERS  - Comma-separated NTP servers (default: time.cloudflare.com)
#   NTP_PORT     - Port to listen on (default: 1123)
#   ENABLE_NTS   - Enable Network Time Security (default: false)
#   LOG_LEVEL    - 0=info, 1=warn, 2=error, 3=fatal (default: 0)
#   NOCLIENTLOG  - Disable client logging (default: false)
#   TZ           - Timezone (default: UTC)

# Pin to specific digest for supply chain security (dependabot will update this)
FROM alpine:3.21@sha256:5405e8f36ce1878720f71217d664aa3dea32e5e5df11acbf07fc78ef5661465b

# Install chrony and timezone data
RUN apk add --no-cache chrony tzdata \
    && rm -rf /var/cache/apk/*

# Create non-root user with fixed UID/GID for Kubernetes compatibility
RUN addgroup -g 1000 chrony \
    && adduser -D -u 1000 -G chrony -h /var/lib/chrony chrony

# Create required directories with correct ownership
RUN mkdir -p /var/lib/chrony /run/chrony \
    && chown -R chrony:chrony /var/lib/chrony /run/chrony \
    && chmod 755 /var/lib/chrony /run/chrony

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

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD chronyc -n tracking || exit 1

# Run as non-root user
USER chrony

ENTRYPOINT ["/usr/local/bin/startup.sh"]
