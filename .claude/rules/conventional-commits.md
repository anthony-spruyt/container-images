# Conventional Commits and Naming

This repository follows [Conventional Commits](https://www.conventionalcommits.org/) for all commits, issues, and pull requests.

## Format

```text
<type>(<scope>): <description>
```

- **type**: Category of change (required)
- **scope**: Component affected (optional but recommended)
- **description**: Short summary in imperative mood (required)

## Valid Types

| Type       | Description                                |
| ---------- | ------------------------------------------ |
| `feat`     | New feature or functionality               |
| `fix`      | Bug fix                                    |
| `docs`     | Documentation changes                      |
| `style`    | Code style (formatting, whitespace)        |
| `refactor` | Code restructuring without behavior change |
| `test`     | Adding or updating tests                   |
| `chore`    | Maintenance tasks                          |
| `ci`       | CI/CD pipeline changes                     |
| `build`    | Build system or dependencies               |

## Naming Conventions

### Commits

```text
feat(firemerge): add health check endpoint
fix(chrony): correct NTP pool configuration
ci(workflows): simplify image addition process
docs(readme): update setup instructions
```

### Issues

Use the same format for issue titles:

```text
feat(chrony): add Alpine-based variant
fix(workflow): version validation fails on prereleases
docs(security): add vulnerability disclosure process
```

Add appropriate labels:

- `enhancement` for `feat` types
- `bug` for `fix` types
- `documentation` for `docs` types

### Pull Requests

PR titles must match commit format:

```text
feat(ci): simplify process for adding new container images
docs(readme): align README and CLAUDE.md descriptions
fix(trivy): update scan configuration for new format
```

Link PRs to issues using GitHub keywords in the PR body:

- `Closes #123` or `Fixes #123`
