# Jenkins

The pipeline definition lives at [`jenkins/Jenkinsfile`](../../jenkins/Jenkinsfile) (Jenkins requires the file in the repository root or a configured path; the root-level copy is not duplicated because the job can point at `jenkins/Jenkinsfile`).

## Job setup

1. New Item → Pipeline → Pipeline script from SCM.
2. SCM: Git, repository URL, branch `*/main`, script path `jenkins/Jenkinsfile`.
3. Credentials: `ghcr-token` (username/password for GHCR), optional `gitops-github-token`.
4. Agents must have Docker (Docker Pipeline plugin) and, for the verification stage, the `argocd` CLI.

## Stages

Checkout → Lint → parallel unit/API tests (6 suites) → Build images → Security scans (Trivy image + config) → Validate Kubernetes and Helm → Publish (main only) → Update GitOps config (dev) → Production approval (`input` gate) → Verify rollout.

## Parameters

| Parameter | Meaning |
|---|---|
| `TARGET_ENV` | `development` or `production` |
| `RUN_SECURITY_SCAN` | Skip scans for fast iterations |
| `IMAGE_TAG` | Override the commit SHA tag |

The production path pauses on an `input` step restricted to `platform-leads`; the GitOps promotion still requires an Argo CD sync, so two independent approvals stand between code and production.

## Note

Jenkins is optional. GitHub Actions is the primary pipeline; the Jenkinsfile exists to show the same stages in a Jenkins-native form and was not executed here (no Jenkins controller in this environment).
