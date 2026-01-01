# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in this repository, please report it by:

1. **Do not** open a public issue
2. Email the maintainer directly or use GitHub's private vulnerability reporting feature

## Security Measures

This repository implements the following security controls:

### Build Pipeline

- **Vulnerability scanning** - Trivy scans all images before push; blocks CRITICAL and HIGH severity CVEs
- **SBOM generation** - Software Bill of Materials generated for all published images
- **Provenance attestation** - Build provenance attached to all images (SLSA Level 3)
- **SHA-pinned actions** - All GitHub Actions pinned to specific commit hashes

### Code Quality

- **Secrets scanning** - Gitleaks and Secretlint in CI and pre-commit hooks
- **Static analysis** - ShellCheck for bash scripts, actionlint for workflows
- **Dependency updates** - Dependabot configured for all package ecosystems

### Access Control

- **Signed commits** - Required via repository rulesets
- **Pull request reviews** - Required before merging to main
- **Status checks** - MegaLinter must pass before merge
- **No force pushes** - Blocked on main branch

### Development Environment

- **SSH agent forwarding** - Private keys never leave the host
- **Supply chain protection** - safe-chain protects npm/pip from dependency confusion
- **Read-only mounts** - Host configuration mounted read-only where possible
