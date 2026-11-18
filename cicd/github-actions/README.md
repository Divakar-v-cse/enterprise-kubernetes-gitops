# GitHub Actions

The workflows are kept in the location GitHub requires — `.github/workflows/` — rather than duplicated here.

| Workflow | Purpose |
|---|---|
| [`ci.yml`](../../.github/workflows/ci.yml) | Lint, per-service test matrix, frontend typecheck/build, kustomize + kubeconform, Helm lint/template, image builds |
| [`security.yml`](../../.github/workflows/security.yml) | Trivy (filesystem, config, images), Checkov, gitleaks, tracked-secret guard |
| [`deploy.yml`](../../.github/workflows/deploy.yml) | Verifies, then updates image tags in Git; production requires an Environment approval |

Supporting scripts live in [`scripts/ci/`](../../scripts/ci/); Dependabot configuration is in [`.github/dependabot.yml`](../../.github/dependabot.yml).

Required repository settings after the first push:

- Actions → General → allow workflows.
- Environments → `development` (no reviewers) and `production` (required reviewers).
- Optional secret `GITOPS_PAT` if the bot must push to a protected `main`.
- Optional `GITHUB_TOKEN` package write permission for GHCR pushes (declared in `ci.yml`).
