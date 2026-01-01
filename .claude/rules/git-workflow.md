# Git Workflow

This repository has branch protection enabled on `main`. Direct pushes are blocked.

## Making Changes

1. **Create a feature branch** from the current commit:

   ```bash
   git checkout -b <branch-name>
   ```

2. **Push the branch** to origin:

   ```bash
   git push -u origin <branch-name>
   ```

3. **Create a pull request**:

   ```bash
   gh pr create --title "<type>(<scope>): <description>" --body "Description here"
   ```

4. **Wait for status checks** (MegaLinter must pass)

5. **Merge** after approval (or user self-approves if they have permission)

## Branch Naming

Use descriptive branch names:

- `feat/<feature-name>` - New features
- `fix/<issue>` - Bug fixes
- `docs/<topic>` - Documentation changes
- `chore/<task>` - Maintenance tasks

## Important

- Never attempt `git push` directly to `main`
- Always go through the PR workflow
- MegaLinter status check is required before merge
