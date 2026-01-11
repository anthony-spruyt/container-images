# Gastown Dev Container

Pre-built development container image with all CLI tools for the Gastown multi-agent orchestrator.

## Features

- Official devcontainer features pre-installed via [feature-install](https://github.com/MilkClouds/devcontainer-feature-installer)
- Kubernetes toolchain (kubectl, helm, kustomize, flux, cilium)
- Infrastructure tools (terraform, talosctl, velero)
- Development tools (node, python, go, pre-commit)
- Security (safe-chain protecting npm/pip installs)

## Included Tools

### Devcontainer Features

| Tool       | Description                |
| ---------- | -------------------------- |
| Docker     | Docker-in-Docker           |
| Node.js    | JavaScript runtime         |
| Python     | Python runtime             |
| Go         | Go programming language    |
| Terraform  | Infrastructure as Code     |
| kubectl    | Kubernetes CLI             |
| Helm       | Kubernetes package manager |
| GitHub CLI | GitHub command line tool   |

### CLI Tools (via install scripts)

| Tool       | Description                         |
| ---------- | ----------------------------------- |
| flux       | GitOps for Kubernetes               |
| cilium     | CNI and network observability       |
| hubble     | Network observability CLI           |
| kustomize  | Kubernetes configuration management |
| helmfile   | Declarative Helm chart management   |
| talosctl   | Talos Linux management              |
| talhelper  | Talos configuration helper          |
| velero     | Kubernetes backup and restore       |
| age        | File encryption tool                |
| falcoctl   | Falco CLI                           |
| cnpg       | CloudNative-PG kubectl plugin       |
| task       | Task runner (go-task)               |
| yq         | YAML/JSON/XML processor             |
| renovate   | Dependency update tool              |
| sops       | Encrypted secrets editor            |
| pre-commit | Git hooks framework                 |
| safe-chain | Supply chain security for npm/pip   |

## Usage

### Docker

```bash
docker run -it --rm ghcr.io/anthony-spruyt/gastown-dev:latest bash
```

### As devcontainer base image

```json
{
  "image": "ghcr.io/anthony-spruyt/gastown-dev:latest",
  "features": {
    // Add additional features if needed
  }
}
```

## Version Management

- **Devcontainer features**: Versions pinned in `assets/devcontainer.json`, updated by Dependabot
- **Docker base image**: Updated by Dependabot
- **CLI tool scripts**: Versions pinned with renovate annotations

## Related

- [gastown-dev](https://github.com/anthony-spruyt/gastown-dev) - Gastown orchestrator devcontainer configuration
