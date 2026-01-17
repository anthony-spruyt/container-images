# Custom MegaLinter flavor for container/infrastructure projects
# Based on ci_light, adds actionlint, markdownlint, lychee
#
# Included linters (11):
# - DOCKERFILE_HADOLINT, BASH_SHELLCHECK, BASH_SHFMT, YAML_YAMLLINT
# - ACTION_ACTIONLINT, MARKDOWN_MARKDOWNLINT, JSON_JSONLINT
# - REPOSITORY_GITLEAKS, REPOSITORY_SECRETLINT, REPOSITORY_TRIVY
# - SPELL_LYCHEE

# Source images for linters not in ci_light
# renovate: datasource=docker depName=rhysd/actionlint
FROM rhysd/actionlint:1.7.10@sha256:ef8299f97635c4c30e2298f48f30763ab782a4ad2c95b744649439a039421e36 AS actionlint

# renovate: datasource=docker depName=lycheeverse/lychee
FROM lycheeverse/lychee:sha-db63437-alpine@sha256:50726dbf2af609acc8adc8ce09ee1248af7753108ae29c09849c8cc86a957a34 AS lychee

# Base: ci_light has shellcheck, shfmt, hadolint, yamllint, gitleaks, secretlint, trivy, jsonlint
# renovate: datasource=docker depName=oxsecurity/megalinter-ci_light
FROM oxsecurity/megalinter-ci_light:v9.2.0@sha256:13345038effc56d6eadf2168373b52ae3ac90279881894a6e0760a6ff27fa591

# Add actionlint (GitHub Actions linter)
COPY --link --from=actionlint /usr/local/bin/actionlint /usr/bin/actionlint

# Add lychee (link checker)
COPY --link --from=lychee /usr/local/bin/lychee /usr/bin/lychee

# Add markdownlint-cli via npm (node already available in ci_light)
# renovate: datasource=npm depName=markdownlint-cli
ARG MARKDOWNLINT_VERSION=0.44.0
RUN npm install -g markdownlint-cli@${MARKDOWNLINT_VERSION} \
    && npm cache clean --force \
    && rm -rf /root/.npm/_cacache

# Set custom flavor name
ENV MEGALINTER_FLAVOR=container-images
